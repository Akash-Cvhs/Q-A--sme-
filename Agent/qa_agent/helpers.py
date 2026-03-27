#============================================================
# HELPER FUNCTIONS
# ============================================================
import requests
import os
from thefuzz import fuzz
import time
from dotenv import load_dotenv
import re

load_dotenv()

# Quiet mode helper
def qprint(*args, **kwargs):
    """Print only if not in quiet mode"""
    if not os.environ.get('QA_QUIET_MODE'):
        print(*args, **kwargs)

GCP_URL = "https://addressvalidation.googleapis.com/v1:validateAddress"
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY","AIzaSyCJd1lEIhrDT90ZzS7MqNL-SCEbjjS1CKQ")

# DB config (duplicate or centralize)
from .db import get_db_connection, schema_name
from .cache import get_npi_cache





STATE_MAP = {
    "california": "CA",
    "new york": "NY",
    "texas": "TX",
    "florida": "FL"
}

def normalize_state(state: str) -> str:
    if not state:
        return ""
    s = state.strip().lower()
    return STATE_MAP.get(s, state.upper())


def extract_house_number(street: str) -> str:
    if not street:
        return ""
    parts = street.strip().split()
    return parts[0] if parts[0].isdigit() else ""


def call_google_api(payload: dict, retries=2):
    url = f"{GCP_URL}?key={GOOGLE_MAPS_API_KEY}"
    
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=5)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == retries:
                qprint(f"❌ Google API failed after retries: {e}")
                return None
            time.sleep(0.5)


def norm_text(text):
    """Normalize text for comparison"""
    if not text:
        return ""
    return str(text).lower().replace("dr.", "").replace(".", "").strip()

def norm_phone(phone):
    """Extract digits only from phone number"""
    if not phone:
        return ""
    return "".join(filter(str.isdigit, str(phone)))


def normalize_zip(z):
    return z.split("-")[0] if z else ""




def cross_validate_address_fields(address: dict) -> dict:
    street = (address.get("street") or "").strip()
    city = (address.get("city") or "").strip()
    state = normalize_state(address.get("state") or "")
    raw_zip = (address.get("zip_code") or address.get("postalcode") or "").strip()

    incorrect = {}
    confidence = 100

    # ------------------------
    # BUILD PAYLOAD (SMART ZIP)
    # ------------------------
    payload = {
        "address": {
            "addressLines": [street],
            "locality": city,
            "administrativeArea": state,
            "regionCode": "US"
        }
    }

    if raw_zip.isdigit() and len(raw_zip) == 5:
        payload["address"]["postalCode"] = raw_zip

    data = call_google_api(payload)

    if not data:
        return {
            "address_valid": False,
            "incorrect_fields": {"address": {"reason": "google_api_failed"}},
        }

    result = data.get("result", {})
    verdict = result.get("verdict", {})
    postal = result.get("address", {}).get("postalAddress", {})

    google_street = (postal.get("addressLines") or [None])[0]
    google_city = postal.get("locality")
    google_state = postal.get("administrativeArea")
    google_zip = normalize_zip(postal.get("postalCode"))

    input_zip = normalize_zip(raw_zip)

    # ------------------------
    # STREET (SMART FUZZY)
    # ------------------------
    if google_street and street:
        score = fuzz.token_sort_ratio(street.lower(), google_street.lower())
        if score < 80:
            incorrect["street"] = {
                "submitted": street,
                "expected": google_street,
                "reason": f"street_mismatch ({score})"
            }
            confidence -= 15

    # ------------------------
    # CITY (STRICT)
    # ------------------------
    if google_city:
        if not city:
            incorrect["city"] = {
                "submitted": "",
                "expected": google_city,
                "reason": "missing_city"
            }
            confidence -= 20
        else:
            score = fuzz.ratio(city.lower(), google_city.lower())
            if score < 85:
                incorrect["city"] = {
                    "submitted": city,
                    "expected": google_city,
                    "reason": f"city_mismatch ({score})"
                }
                confidence -= 20

    # ------------------------
    # STATE (NORMALIZED)
    # ------------------------
    if google_state:
        norm_input = normalize_state(state)
        norm_google = normalize_state(google_state)

        if not norm_input:
            incorrect["state"] = {
                "submitted": "",
                "expected": norm_google,
                "reason": "missing_state"
            }
            confidence -= 15

        elif norm_input != norm_google:
            incorrect["state"] = {
                "submitted": state,
                "expected": norm_google,
                "reason": "state_mismatch"
            }
            confidence -= 20

    # ------------------------
    # ZIP (FULL LOGIC)
    # ------------------------
    if not raw_zip:
        incorrect["postalcode"] = {
            "submitted": "",
            "expected": google_zip,
            "reason": "missing_zip"
        }
        confidence -= 25

    elif not raw_zip.isdigit():
        incorrect["postalcode"] = {
            "submitted": raw_zip,
            "expected": google_zip,
            "reason": "invalid_zip_format"
        }
        confidence -= 25

    elif len(raw_zip) != 5:
        if google_zip and google_zip.startswith(raw_zip):
            incorrect["postalcode"] = {
                "submitted": raw_zip,
                "expected": google_zip,
                "reason": "partial_zip_recovered"
            }
            confidence -= 10
        else:
            incorrect["postalcode"] = {
                "submitted": raw_zip,
                "expected": google_zip,
                "reason": "zip_not_inferred"
            }
            confidence -= 20

    elif google_zip and input_zip != google_zip:
        incorrect["postalcode"] = {
            "submitted": raw_zip,
            "expected": google_zip,
            "reason": "zip_mismatch"
        }
        confidence -= 20

    # ------------------------
    # 🔥 CROSS-FIELD VALIDATION (CRITICAL FIX)
    # ------------------------
    if google_zip and google_city:
        if city and city.lower() != google_city.lower():
            incorrect["city"] = {
                "submitted": city,
                "expected": google_city,
                "reason": "city_zip_conflict"
            }
            confidence -= 15

    if google_zip and google_state:
        if normalize_state(state) != normalize_state(google_state):
            incorrect["state"] = {
                "submitted": state,
                "expected": google_state,
                "reason": "state_zip_conflict"
            }
            confidence -= 15

    # ------------------------
    # 🔥 GARBAGE DETECTION
    # ------------------------
    if not google_street and not google_city:
        incorrect["address"] = {
            "submitted": address,
            "reason": "invalid_address_no_match"
        }
        confidence -= 40

    # ------------------------
    # FINAL DECISION
    # ------------------------
    confidence = max(0, min(confidence, 100))

    address_valid = confidence >= 75 and "address" not in incorrect

    return {
        "address_valid": address_valid,
        "incorrect_fields": incorrect
    }

def normalize_name(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', name.lower())


def match_insurance_in_db(submitted_name: str) -> dict:
    """
    Intelligent insurance matcher (QA + SME combined)

    Returns:
    {
        success: bool,
        match_type: "exact" | "fuzzy" | "none",
        official_name: str,
        confidence: float,
        suggestions: list
    }
    """

    conn = get_db_connection()
    if not conn:
        qprint("⚠️ DB unavailable — skipping insurance validation")
        return {"success": True, "match_type": "skipped"}

    try:
        cursor = conn.cursor()

        # ------------------------
        # STEP 1: EXACT MATCH
        # ------------------------
        cursor.execute(f"""
            SELECT payer_name
            FROM {schema_name}.insurance_companies
            WHERE LOWER(payer_name) = LOWER(%s)
            LIMIT 1
        """, (submitted_name,))

        row = cursor.fetchone()

        if row:
            cursor.close()
            conn.close()
            return {
                "success": True,
                "match_type": "exact",
                "official_name": row[0],
                "confidence": 100
            }

        # ------------------------
        # STEP 2: FETCH CANDIDATES
        # ------------------------
        cursor.execute(f"""
            SELECT payer_name
            FROM {schema_name}.insurance_companies
            WHERE status = 'ACTIVE'
        """)

        companies = cursor.fetchall()

        cursor.close()
        conn.close()

        if not companies:
            return {"success": False, "match_type": "none"}

        # ------------------------
        # STEP 3: FUZZY MATCH
        # ------------------------
        candidates = []

        norm_input = normalize_name(submitted_name)

        for (payer_name,) in companies:
            norm_db = normalize_name(payer_name)

            token_score = fuzz.token_sort_ratio(norm_input, norm_db)
            partial_score = fuzz.partial_ratio(norm_input, norm_db)

            confidence = (token_score * 0.7) + (partial_score * 0.3)

            candidates.append({
                "official_name": payer_name,
                "confidence": round(confidence, 2)
            })

        candidates.sort(key=lambda x: x["confidence"], reverse=True)

        best = candidates[0]

        qprint(f"    🏢 Best match: {best['official_name']} ({best['confidence']}%)")

        # ------------------------
        # STEP 4: DECISION
        # ------------------------
        if best["confidence"]  > 65:
            return {
                "success": True,
                "match_type": "fuzzy_strong",
                "official_name": best["official_name"],
                "confidence": best["confidence"]
            }

        elif best["confidence"] >= 60:
            return {
                "success": True,
                "match_type": "fuzzy_medium",
                "official_name": best["official_name"],
                "confidence": best["confidence"],
               
            }

        else:
            return {
                "success": False,
                "match_type": "low_confidence",
                "confidence": best["confidence"],
                "suggestions": candidates[:3]
            }

    except Exception as e:
        qprint(f"⚠️ Insurance matching error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": True, "match_type": "error"}   

def nppes_lookup_tool(npi_number: str):
    """Fetch provider details from NPPES Registry by NPI with caching."""
    npi_number = str(npi_number).strip()
    
    if not npi_number or len(npi_number) != 10:
        return {"error": "Invalid NPI format (must be 10 digits)", "searched_npi": npi_number}
    
    # Check cache first
    cache = get_npi_cache()
    cached_result = cache.get_npi_lookup(npi_number)
    
    if cached_result is not None:
        qprint(f"  → NPI {npi_number} found in cache")
        return cached_result
    
    # Cache miss - query NPPES API
    url = f"https://npiregistry.cms.hhs.gov/api/?number={npi_number}&version=2.1"
    
    qprint(f"  → Querying NPPES for NPI: {npi_number}")
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("result_count", 0) == 0:
            qprint(f"  ✗ NPI {npi_number} not found in registry")
            result = {"error": "NPI not found in registry", "searched_npi": npi_number}
            # Cache negative results too (with error key)
            cache.set_npi_lookup(npi_number, result)
            return result
        
        provider = data["results"][0]
        basic = provider.get("basic", {})
        addresses = provider.get("addresses", [])
        
        practice_address = None
        for addr in addresses:
            if addr.get("address_purpose") == "LOCATION":
                practice_address = addr
                break
        
        if not practice_address and addresses:
            practice_address = addresses[0]
        
        if not practice_address:
            practice_address = {}
        
        if basic.get("organization_name"):
            provider_name = basic.get("organization_name")
        else:
            first_name = basic.get("first_name", "")
            last_name = basic.get("last_name", "")
            provider_name = f"{first_name} {last_name}".strip()
        
        result = {
            "npi": npi_number,
            "provider_name": provider_name,
            "address": practice_address.get("address_1", ""),
            "city": practice_address.get("city", ""),
            "state": practice_address.get("state", ""),
            "postal_code": practice_address.get("postal_code", ""),
            "phone": practice_address.get("telephone_number", "")
        }
        
        qprint(f"  ✓ Found: {provider_name} at {result['city']}, {result['state']}")
        
        # Cache the successful result
        cache.set_npi_lookup(npi_number, result)
        
        return result
        
    except Exception as e:
        qprint(f"  ✗ NPPES API error: {e}")
        result = {"error": f"NPPES lookup error: {str(e)}", "searched_npi": npi_number}
        # Don't cache API errors (transient failures)
        return result


def nppes_fuzzy_search(physician_name: str, address: str, city: str, state: str, limit: int = 10):
    """
    Multi-stage fuzzy search with fallback strategies and caching:
    1. Search by last name + state
    2. If fails, search by city + state
    3. Calculate name-priority match scores
    """
    # Clean inputs
    physician_name = physician_name.strip().replace("Dr.", "").replace("Dr", "").strip()
    address = address.strip()
    city = city.strip()
    state = state.strip().upper()
    
    # Check cache first
    cache = get_npi_cache()
    cached_result = cache.get_fuzzy_search(physician_name, address, city, state)
    
    if cached_result is not None:
        qprint(f"  → Fuzzy search result found in cache")
        return cached_result
    
    # Cache miss - perform fuzzy search
    qprint(f"  → Fuzzy searching NPPES: {physician_name}")
    qprint(f"     Location: {address}, {city}, {state}")
    city = city.strip()
    state = state.strip().upper()
    
    if not physician_name or not state:
        return {"error": "Physician name and state are required for fuzzy search"}
    
    # Extract last name for better searching
    name_parts = physician_name.split()
    last_name = name_parts[-1] if name_parts else physician_name
    
    providers = []
    
    # STRATEGY 1: Search by last name + state
    qprint(f"  → Strategy 1: Searching by last name '{last_name}' in {state}")
    url1 = f"https://npiregistry.cms.hhs.gov/api/?version=2.1&last_name={last_name}&state={state}&limit=200"
    
    try:
        response = requests.get(url1, timeout=20)
        data = response.json()
        
        if data.get("result_count", 0) > 0:
            qprint(f"  ✓ Found {data.get('result_count')} providers with last name '{last_name}' in {state}")
            providers.extend(data.get("results", []))
        else:
            qprint(f"  ℹ️  No providers found with last name '{last_name}' in {state}")
    except Exception as e:
        qprint(f"  ⚠️  Strategy 1 failed: {e}")
    
    # STRATEGY 2: Search by city + state (fallback)
    if len(providers) < 10:
        qprint(f"  → Strategy 2: Searching by city '{city}' in {state}")
        url2 = f"https://npiregistry.cms.hhs.gov/api/?version=2.1&city={city}&state={state}&limit=200"
        
        try:
            response = requests.get(url2, timeout=20)
            data = response.json()
            
            if data.get("result_count", 0) > 0:
                qprint(f"  ✓ Found {data.get('result_count')} providers in {city}, {state}")
                providers.extend(data.get("results", []))
            else:
                qprint(f"  ℹ️  No providers found in {city}, {state}")
        except Exception as e:
            qprint(f"  ⚠️  Strategy 2 failed: {e}")
    
    # STRATEGY 3: Search by state only (last resort)
    if len(providers) < 10:
        qprint(f"  → Strategy 3: Searching entire state {state}")
        url3 = f"https://npiregistry.cms.hhs.gov/api/?version=2.1&state={state}&enumeration_type=NPI-1&limit=200"
        
        try:
            response = requests.get(url3, timeout=20)
            data = response.json()
            
            if data.get("result_count", 0) > 0:
                qprint(f"  ✓ Found {data.get('result_count')} providers in {state}")
                providers.extend(data.get("results", []))
            else:
                qprint(f"  ✗ No providers found in {state}")
        except Exception as e:
            qprint(f"  ⚠️  Strategy 3 failed: {e}")
    
    if not providers:
        qprint(f"  ✗ All search strategies failed - no providers found")
        return {"error": "No providers found after exhaustive search", "candidates": []}
    
    qprint(f"  ℹ️  Total candidates collected: {len(providers)}")
    
    # Remove duplicates
    unique_providers = {p.get("number"): p for p in providers}.values()
    
    # Calculate match scores with NAME as primary
    candidates = []
    for provider in unique_providers:
        basic = provider.get("basic", {})
        addresses = provider.get("addresses", [])
        
        # Get provider name
        if basic.get("organization_name"):
            provider_name = basic.get("organization_name")
        else:
            first_name = basic.get("first_name", "")
            last_name_p = basic.get("last_name", "")
            provider_name = f"{first_name} {last_name_p}".strip()
        
        # Calculate name similarity (PRIMARY - most important)
        name_score = fuzz.token_sort_ratio(physician_name.lower(), provider_name.lower())
        
        # Skip if name match is too low (< 50%)
        if name_score < 50:
            continue
        
        # Get practice address
        practice_address = None
        for addr in addresses:
            if addr.get("address_purpose") == "LOCATION":
                practice_address = addr
                break
        
        if not practice_address and addresses:
            practice_address = addresses[0]
        
        if not practice_address:
            continue
        
        # Calculate address similarity (SECONDARY)
        provider_address = practice_address.get("address_1", "").lower()
        address_score = fuzz.token_set_ratio(address.lower(), provider_address)
        
        # Calculate location similarity
        provider_city = practice_address.get("city", "").lower()
        provider_state = practice_address.get("state", "").upper()
        
        city_score = fuzz.ratio(city.lower(), provider_city)
        state_match = 100 if state == provider_state else 0
        
        # WEIGHTED FORMULA: Name is PRIMARY (70%), Location is SECONDARY (30%)
        confidence_score = (
            (name_score * 0.70) +      # 70% weight on NAME (PRIMARY)
            (address_score * 0.15) +   # 15% weight on address
            (city_score * 0.10) +      # 10% weight on city
            (state_match * 0.05)       # 5% weight on state
        )
        
        candidates.append({
            "npi": provider.get("number"),
            "provider_name": provider_name,
            "address": practice_address.get("address_1", ""),
            "city": practice_address.get("city", ""),
            "state": practice_address.get("state", ""),
            "postal_code": practice_address.get("postal_code", ""),
            "phone": practice_address.get("telephone_number", ""),
            "confidence_score": round(confidence_score, 2),
            "name_match": name_score,
            "address_match": address_score,
            "city_match": city_score,
            "state_match": state_match
        })
    
    # Sort by confidence score (name-heavy)
    candidates.sort(key=lambda x: (x["confidence_score"], x["name_match"]), reverse=True)
    
    # Return top matches
    top_candidates = candidates[:limit]
    
    if top_candidates:
        best = top_candidates[0]
        qprint(f"  ✓ Best match: {best['provider_name']} (confidence: {best['confidence_score']}%)")
        qprint(f"     Name: {best['name_match']}% (PRIMARY) | Address: {best['address_match']}% | City: {best['city_match']}%")
    else:
        qprint(f"  ✗ No providers with name match ≥50% found")
    
    result = {
        "candidates": top_candidates,
        "search_params": {
            "physician_name": physician_name,
            "address": address,
            "city": city,
            "state": state
        },
        "total_scanned": len(unique_providers)
    }
    
    # Cache the result
    cache.set_fuzzy_search(physician_name, address, city, state, result)
    
    return result

#  fuzzy address correction
def fuzzy_address_correction(address: dict) -> dict:
    street = address.get("street", "")
    city = address.get("city", "")
    state = address.get("state", "")
    postal_code = address.get("postal_code", "")

    query = f"{street}, {city}, {state} {postal_code}"

    try:
        # Step 1: Autocomplete
        auto_url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
        auto_params = {
            "input": query,
            "types": "address",
            "components": "country:us",
            "key": GOOGLE_MAPS_API_KEY
        }

        auto_resp = requests.get(auto_url, params=auto_params, timeout=10).json()

        if not auto_resp.get("predictions"):
            return {"error": "no_predictions"}

        place_id = auto_resp["predictions"][0]["place_id"]

        # Step 2: Place Details (STRUCTURED)
        details_url = "https://maps.googleapis.com/maps/api/place/details/json"
        details_params = {
            "place_id": place_id,
            "fields": "address_components",
            "key": GOOGLE_MAPS_API_KEY
        }

        details = requests.get(details_url, params=details_params, timeout=10).json()

        comps = details.get("result", {}).get("address_components", [])

        corrected = {
            "street": "",
            "city": "",
            "state": "",
            "postalcode": ""
        }

        street_number = ""
        route = ""

        for c in comps:
            types = c["types"]

            if "street_number" in types:
                street_number = c["long_name"]

            elif "route" in types:
                route = c["long_name"]

            elif "locality" in types:
                corrected["city"] = c["long_name"]

            elif "administrative_area_level_1" in types:
                corrected["state"] = c["short_name"]

            elif "postal_code" in types:
                corrected["postalcode"] = c["long_name"]

        corrected["street"] = f"{street_number} {route}".strip()

        return corrected

    except Exception as e:
        return {"error": str(e)}
    


def validate_npi_with_fuzzy(presc: dict) -> dict:
    npi = (presc.get("npi_number") or "").strip()

    if not npi:
        return {}

    # Step 1: direct lookup
    nppes_data = nppes_lookup_tool(npi)

    if "error" not in nppes_data:
        return {}  # valid, no correction needed

    # Step 2: fuzzy fallback
    fuzzy_result = nppes_fuzzy_search(
        presc.get("physician_name", ""),
        presc.get("address", ""),
        presc.get("city", ""),
        presc.get("state", "")
    )

    if isinstance(fuzzy_result, dict):
        candidates = fuzzy_result.get("candidates", [])

        if candidates:
            best = candidates[0]
            confidence = best.get("confidence_score", 0)

            if confidence >= 65:
                return {
                    "npi_number": {
                        "submitted": npi,
                        "expected": best.get("npi"),
                        "confidence": confidence,
                        "reason": "nppes_fuzzy_match"
                    },
                    "physician_name": {
                        "submitted": presc.get("physician_name"),
                        "expected": best.get("provider_name"),
                        "confidence": confidence,
                        "reason": "nppes_fuzzy_match"
                    },
                    "physician_address": {
                        "submitted": presc.get("address"),
                        "expected": best.get("address"),
                        "confidence": confidence,
                        "reason": "nppes_fuzzy_match"
                    }
                }

    return {}

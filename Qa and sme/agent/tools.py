import json
import os
import requests
from typing import Dict, Any, List
from dotenv import load_dotenv
from thefuzz import fuzz

load_dotenv()
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")


def extract_incorrect_fields(full_json):
    """Extract incorrect fields from input JSON."""
    if isinstance(full_json, str):
        try:
            full_json = json.loads(full_json)
        except Exception as e:
            print(f"Error parsing JSON in extract_incorrect_fields: {e}")
            return {"error": "Invalid JSON string"}
    
    if "incorrect_fields" in full_json:
        incorrect = full_json["incorrect_fields"]
        if incorrect:
            print(f"✓ Found {len(incorrect)} incorrect fields from Q/A agent")
            return incorrect
    
    return {"message": "No incorrect_fields found in input"}


def address_validation_tool(address: Dict[str, str]):
    """Validate and correct address using Google Address Validation API."""
    if not GOOGLE_MAPS_API_KEY:
        return {"error": "Google Maps API key not configured"}
    
    street = address.get("street", "")
    city = address.get("city", "")
    state = address.get("state", "")
    postal_code = address.get("postal_code", "")
    
    print(f"  → Validating address: {street}, {city}, {state} {postal_code}")
    
    url = f"https://addressvalidation.googleapis.com/v1:validateAddress?key={GOOGLE_MAPS_API_KEY}"
    
    payload = {
        "address": {
            "regionCode": "US",
            "postalCode": postal_code,
            "administrativeArea": state,
            "locality": city,
            "addressLines": [street]
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()
        
        if "result" not in data:
            return {"error": "Unable to validate address", "submitted": address}
        
        result = data["result"]
        verdict = result.get("verdict", {})
        corrected_address = result.get("address", {})
        postal_address = corrected_address.get("postalAddress", {})
        
        address_lines = postal_address.get("addressLines", [])
        corrected_street = address_lines[0] if address_lines else street
        corrected_city = postal_address.get("locality", city)
        corrected_state = postal_address.get("administrativeArea", state)
        corrected_postal = postal_address.get("postalCode", postal_code)
        
        is_valid = verdict.get("addressComplete", False)
        
        print(f"  ✓ Address validation: {'Valid' if is_valid else 'Invalid'}")
        
        return {
            "valid": is_valid,
            "corrected_address": {
                "street": corrected_street,
                "city": corrected_city,
                "state": corrected_state,
                "postal_code": corrected_postal
            },
            "original_address": address
        }
    except Exception as e:
        print(f"  ✗ Address validation error: {e}")
        return {"error": f"Address validation error: {str(e)}", "submitted": address}


def nppes_lookup_tool(npi_number: str):
    """Fetch provider details from NPPES Registry by NPI."""
    npi_number = str(npi_number).strip()
    
    if not npi_number or len(npi_number) != 10:
        return {"error": "Invalid NPI format (must be 10 digits)", "searched_npi": npi_number}
    
    url = f"https://npiregistry.cms.hhs.gov/api/?number={npi_number}&version=2.1"
    
    print(f"  → Querying NPPES for NPI: {npi_number}")
    
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("result_count", 0) == 0:
            print(f"  ✗ NPI {npi_number} not found in registry")
            return {"error": "NPI not found in registry", "searched_npi": npi_number}
        
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
        
        print(f"  ✓ Found: {provider_name} at {result['city']}, {result['state']}")
        
        return result
        
    except Exception as e:
        print(f"  ✗ NPPES API error: {e}")
        return {"error": f"NPPES lookup error: {str(e)}", "searched_npi": npi_number}


def nppes_fuzzy_search(physician_name: str, address: str, city: str, state: str, limit: int = 10):
    """
    Multi-stage fuzzy search with fallback strategies:
    1. Search by last name + state
    2. If fails, search by city + state
    3. Calculate name-priority match scores
    """
    print(f"  → Fuzzy searching NPPES: {physician_name}")
    print(f"     Location: {address}, {city}, {state}")
    
    # Clean inputs
    physician_name = physician_name.strip().replace("Dr.", "").replace("Dr", "").strip()
    address = address.strip()
    city = city.strip()
    state = state.strip().upper()
    
    if not physician_name or not state:
        return {"error": "Physician name and state are required for fuzzy search"}
    
    # Extract last name for better searching
    name_parts = physician_name.split()
    last_name = name_parts[-1] if name_parts else physician_name
    
    providers = []
    
    # STRATEGY 1: Search by last name + state
    print(f"  → Strategy 1: Searching by last name '{last_name}' in {state}")
    url1 = f"https://npiregistry.cms.hhs.gov/api/?version=2.1&last_name={last_name}&state={state}&limit=200"
    
    try:
        response = requests.get(url1, timeout=20)
        data = response.json()
        
        if data.get("result_count", 0) > 0:
            print(f"  ✓ Found {data.get('result_count')} providers with last name '{last_name}' in {state}")
            providers.extend(data.get("results", []))
        else:
            print(f"  ℹ️  No providers found with last name '{last_name}' in {state}")
    except Exception as e:
        print(f"  ⚠️  Strategy 1 failed: {e}")
    
    # STRATEGY 2: Search by city + state (fallback)
    if len(providers) < 10:
        print(f"  → Strategy 2: Searching by city '{city}' in {state}")
        url2 = f"https://npiregistry.cms.hhs.gov/api/?version=2.1&city={city}&state={state}&limit=200"
        
        try:
            response = requests.get(url2, timeout=20)
            data = response.json()
            
            if data.get("result_count", 0) > 0:
                print(f"  ✓ Found {data.get('result_count')} providers in {city}, {state}")
                providers.extend(data.get("results", []))
            else:
                print(f"  ℹ️  No providers found in {city}, {state}")
        except Exception as e:
            print(f"  ⚠️  Strategy 2 failed: {e}")
    
    # STRATEGY 3: Search by state only (last resort)
    if len(providers) < 10:
        print(f"  → Strategy 3: Searching entire state {state}")
        url3 = f"https://npiregistry.cms.hhs.gov/api/?version=2.1&state={state}&enumeration_type=NPI-1&limit=200"
        
        try:
            response = requests.get(url3, timeout=20)
            data = response.json()
            
            if data.get("result_count", 0) > 0:
                print(f"  ✓ Found {data.get('result_count')} providers in {state}")
                providers.extend(data.get("results", []))
            else:
                print(f"  ✗ No providers found in {state}")
        except Exception as e:
            print(f"  ⚠️  Strategy 3 failed: {e}")
    
    if not providers:
        print(f"  ✗ All search strategies failed - no providers found")
        return {"error": "No providers found after exhaustive search", "candidates": []}
    
    print(f"  ℹ️  Total candidates collected: {len(providers)}")
    
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
        print(f"  ✓ Best match: {best['provider_name']} (confidence: {best['confidence_score']}%)")
        print(f"     Name: {best['name_match']}% (PRIMARY) | Address: {best['address_match']}% | City: {best['city_match']}%")
    else:
        print(f"  ✗ No providers with name match ≥50% found")
    
    return {
        "candidates": top_candidates,
        "search_params": {
            "physician_name": physician_name,
            "address": address,
            "city": city,
            "state": state
        },
        "total_scanned": len(unique_providers)
    }

#  fuzzy address correction

def fuzzy_address_correction(submitted_address: dict) -> dict:
    """
    Fuzzy address correction using Google Places Autocomplete API
    """
    street = submitted_address.get("street", "")
    city = submitted_address.get("city", "")
    state = submitted_address.get("state", "")
    postal_code = submitted_address.get("postal_code", "")
    
    # Construct search query
    query = f"{street}, {city}, {state} {postal_code}"
    
    url = f"https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {
        "input": query,
        "types": "address",
        "components": f"country:us",
        "key": GOOGLE_MAPS_API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data.get("status") == "OK" and data.get("predictions"):
            # Get top prediction
            top_match = data["predictions"][0]
            place_id = top_match["place_id"]
            
            # Get detailed address from Place Details API
            details_url = f"https://maps.googleapis.com/maps/api/place/details/json"
            details_params = {
                "place_id": place_id,
                "fields": "address_components,formatted_address",
                "key": GOOGLE_MAPS_API_KEY
            }
            
            details_response = requests.get(details_url, params=details_params, timeout=10)
            details_data = details_response.json()
            
            if details_data.get("status") == "OK":
                result = details_data["result"]
                address_components = result["address_components"]
                
                # Parse components
                corrected = {
                    "street": "",
                    "city": "",
                    "state": "",
                    "postal_code": ""
                }
                
                for component in address_components:
                    types = component["types"]
                    if "street_number" in types:
                        corrected["street"] = component["long_name"] + " "
                    elif "route" in types:
                        corrected["street"] += component["long_name"]
                    elif "locality" in types:
                        corrected["city"] = component["long_name"]
                    elif "administrative_area_level_1" in types:
                        corrected["state"] = component["short_name"]
                    elif "postal_code" in types:
                        corrected["postal_code"] = component["long_name"]
                
                # Calculate confidence based on similarity
                street_score = fuzz.ratio(street.lower(), corrected["street"].lower())
                city_score = fuzz.ratio(city.lower(), corrected["city"].lower())
                state_score = 100 if state.upper() == corrected["state"].upper() else 0
                zip_score = 100 if postal_code[:5] == corrected["postal_code"][:5] else 0
                
                confidence = (
                    street_score * 0.4 +
                    city_score * 0.25 +
                    state_score * 0.20 +
                    zip_score * 0.15
                )
                
                return {
                    "success": True,
                    "corrected_address": corrected,
                    "confidence_score": round(confidence, 2),
                    "formatted_address": result["formatted_address"]
                }
        
        return {"error": "NO_SUGGESTIONS_FOUND"}
        
    except Exception as e:
        print(f"Fuzzy address correction error: {e}")
        return {"error": str(e)}

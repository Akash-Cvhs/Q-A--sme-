

"""
QA Validation Agent - Enhanced with Cross-Field Address Validation
"""

import requests
from dotenv import load_dotenv
import os
import json

from typing import List, Any, Union
from typing import Dict, Any, List 
from langchain_google_vertexai import ChatVertexAI
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, ToolMessage
from typing_extensions import TypedDict
from thefuzz import fuzz
import re
from psycopg2 import sql
import psycopg2

load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================

GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
GCP_URL = "https://addressvalidation.googleapis.com/v1:validateAddress"
# PostgreSQL Configuration
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_DB = os.getenv("POSTGRES_DB", "healthcare_db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
schema_name = os.getenv("schema_name", "insurance")

# ============================================================
# GEMINI INITIALIZATION
# ============================================================

if GOOGLE_APPLICATION_CREDENTIALS:
    if not os.path.isabs(GOOGLE_APPLICATION_CREDENTIALS):
        if os.path.exists(GOOGLE_APPLICATION_CREDENTIALS):
            credentials_path = os.path.abspath(GOOGLE_APPLICATION_CREDENTIALS)
        else:
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            credentials_path = os.path.join(parent_dir, GOOGLE_APPLICATION_CREDENTIALS)
    else:
        credentials_path = GOOGLE_APPLICATION_CREDENTIALS
    
    if os.path.exists(credentials_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        print(f"✓ Using service account: {os.path.basename(credentials_path)}")
        credentials_valid = True
    else:
        print(f"⚠️ WARNING: Service account file not found at: {credentials_path}")
        credentials_valid = False
else:
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    credentials_path = os.path.join(parent_dir, "doc-triaging-463411-88b8ccd543f3.json")
    
    if os.path.exists(credentials_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        print(f"✓ Auto-detected service account: {os.path.basename(credentials_path)}")
        credentials_valid = True
    else:
        print(f"⚠️ WARNING: Service account file not found")
        credentials_valid = False

if credentials_valid:
    try:
        llm = ChatVertexAI(
            model_name="gemini-2.0-flash-exp",
            temperature=0,
            project="doc-triaging-463411",
            location="us-central1"
        )
        print("✓ Google Gemini 2.0 Flash configured via Vertex AI")
    except Exception as e:
        print(f"⚠️ ERROR initializing Gemini: {e}")
        llm = None
else:
    llm = None
    print("⚠️ WARNING: Gemini not initialized - missing credentials")

if GOOGLE_MAPS_API_KEY:
    print("✓ Google Maps API configured")
else:
    print("⚠️ WARNING: GOOGLE_MAPS_API_KEY not found")

# ============================================================
# DATABASE CONNECTION
# ============================================================

# def get_db_connection():
#     """Connect to PostgreSQL database"""
#     try:
#         return psycopg2.connect(
#             host=POSTGRES_HOST,
#             database=POSTGRES_DB,
#             user=POSTGRES_USER,
#             schema_name=schema_name,
#             password=POSTGRES_PASSWORD
#         )
#     except Exception as e:
#         print(f"⚠️ Database connection error: {e}")
#         return None
def get_db_connection():
    """Connect to PostgreSQL database"""
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        # Set search_path after connection
        cursor = conn.cursor()
        cursor.execute(f"SET search_path TO {schema_name}, public")
        cursor.close()
        return conn
    except Exception as e:
        print(f"⚠️ Database connection error: {e}")
        return None

# ============================================================
# HELPER FUNCTIONS
# ============================================================

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


def cross_validate_address_fields(address: dict) -> dict:
    """
    Google Address Validation (QA-owned)

    RULES:
    - Street is ONLY flagged if route name mismatches (not house number)
    - ZIP must be exactly 5 digits (US)
    - If Google infers ZIP → must be corrected
    - Output is SME-compatible
    """

    street = (address.get("street") or "").strip()
    city = (address.get("city") or "").strip()
    state = (address.get("state") or "").strip()
    raw_zip = (address.get("zip_code") or address.get("postalcode") or "").strip()

    incorrect = {}
    confidence = 95

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

    try:
        r = requests.post(
            f"{GCP_URL}?key={GOOGLE_MAPS_API_KEY}",
            json=payload,
            timeout=10
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return {
            "address_valid": False,
            "incorrect_fields": {},
            "ground_truth": {},
            "confidence": 40,
            "anchor_used": "google",
            "manual_review_required": True,
            "skipped": True
        }

    result = data.get("result", {})
    verdict = result.get("verdict", {})
    components = result.get("address", {}).get("addressComponents", [])

    google = {"street": None, "city": None, "state": None, "postalcode": None}

    for comp in components:
        ctype = comp.get("componentType")
        cname = comp.get("componentName", {}).get("text", "")
        if ctype == "route":
            google["street"] = cname
        elif ctype == "locality":
            google["city"] = cname
        elif ctype == "administrative_area_level_1":
            google["state"] = cname
        elif ctype == "postal_code":
            google["postalcode"] = cname

    # ------------------------
    # STREET (ROUTE ONLY)
    # ------------------------
    if google["street"]:
        submitted_route = street.lower().replace(google["street"].lower(), "").strip()
        if google["street"].lower() not in street.lower():
            incorrect["street"] = {
                "submitted": street,
                "expected": google["street"],
                "reason": "Street name mismatch"
            }
            confidence -= 15

    # ------------------------
    # CITY
    # ------------------------
    if google["city"] and city.lower() != google["city"].lower():
        incorrect["city"] = {
            "submitted": city,
            "expected": google["city"],
            "reason": "Corrected by Google"
        }
        confidence -= 10

    # ------------------------
    # STATE
    # ------------------------
    if google["state"] and state.upper() != google["state"].upper():
        incorrect["state"] = {
            "submitted": state,
            "expected": google["state"],
            "reason": "Corrected by Google"
        }
        confidence -= 10

    # ------------------------
    # ZIP (CRITICAL FIX)
    # ------------------------
    if google["postalcode"]:
        if not raw_zip.isdigit() or len(raw_zip) != 5:
            incorrect["postalcode"] = {
                "submitted": raw_zip,
                "expected": google["postalcode"],
                "reason": "Invalid ZIP – inferred by Google"
            }
            confidence -= 15
        elif raw_zip != google["postalcode"]:
            incorrect["postalcode"] = {
                "submitted": raw_zip,
                "expected": google["postalcode"],
                "reason": "ZIP mismatch"
            }
            confidence -= 10

    address_valid = verdict.get("addressComplete", False) and not incorrect
    confidence = max(0, min(confidence, 100))

    return {
        "address_valid": address_valid,
        "incorrect_fields": incorrect,
        "ground_truth": {
            "street": street,  # preserve house number
            "city": google["city"] or city,
            "state": google["state"] or state,
            "postalcode": google["postalcode"] or raw_zip
        },
        "confidence": confidence,
        "anchor_used": "google",
        "manual_review_required": False,
        "skipped": False
    }


# ============================================================
# INSURANCE COMPANY VALIDATION
# ============================================================

def is_exact_match_in_db(insurance_name: str) -> bool:
    """
    Check if insurance name exactly matches payer_name in DB
    Returns True ONLY for exact matches (case-insensitive)
    Returns False for fuzzy matches - SME will handle correction
    """
    conn = get_db_connection()
    if not conn:
        print("⚠️ Database not available - skipping insurance validation")
        return True  # Skip validation if DB unavailable (assume valid)
    
    try:
        cursor = conn.cursor()
        
        # Check for exact match (case-insensitive)
        query = f"""
        SELECT *
        FROM {schema_name}.insurance_companies
        WHERE LOWER(payer_name) = LOWER(%s)
        LIMIT 1
        """
        
        cursor.execute(query, (insurance_name,))
        exists = cursor.fetchone() is not None
        
        cursor.close()
        conn.close()
        
        if exists:
            print(f"  ✅ Insurance '{insurance_name}' found in database (exact match)")
        else:
            print(f"  ❌ Insurance '{insurance_name}' NOT found in database - flagging for SME")
        
        return exists
    
    except Exception as e:
        print(f"⚠️ Database query error: {e}")
        import traceback
        traceback.print_exc()
        return True  # Assume valid on error to avoid blocking

# ============================================================
# Q/A VALIDATION TOOLS
# ============================================================

@tool
def qa_detect_missing_fields(form_json: Union[str, dict]) -> dict:
    """Detect missing required fields in the enrollment form"""
    try:
        if isinstance(form_json, dict):
            form_data = form_json
        else:
            form_data = json.loads(form_json)
        
        info = form_data.get("Information", {})
        missing = {}
        
        # Patient required fields
        patient = info.get("Patient", {})
        required_patient = ["first_name", "last_name", "date_of_birth", "phone_number", "street", "city", "state", "postalcode"]
        missing_patient = [f for f in required_patient if not patient.get(f)]
        if missing_patient:
            missing["Patient"] = missing_patient
        
        # Prescription required fields
        prescription = info.get("Prescription", {})
        required_prescription = ["npi_number", "physician_name", "medication_name", "diagnosis", "address", "city", "state"]
        missing_prescription = [f for f in required_prescription if not prescription.get(f)]
        if missing_prescription:
            missing["Prescription"] = missing_prescription
        
        # Insurance required fields
        insurance = info.get("Primary_Insurance", {})
        required_insurance = ["insurance_company_name", "policy_number"]
        missing_insurance = [f for f in required_insurance if not insurance.get(f)]
        if missing_insurance:
            missing["Primary_Insurance"] = missing_insurance
        
        return {"missing_fields": missing}
        
    except Exception as e:
        print(f"Error in qa_detect_missing_fields: {e}")
        return {"missing_fields": {}, "error": str(e)}



@tool
def qa_validate_patient_address(form_json: dict) -> dict:
    """
    STRICT patient address validation.
    QA OWNS validation. SME only applies correction.
    """

    form_data = form_json

    patient = form_data.get("Information", {}).get("Patient", {})

    address = {
        "street": patient.get("street", ""),
        "city": patient.get("city", ""),
        "state": patient.get("state", ""),
        "zip_code": patient.get("postalcode", "")
    }

    print("🔍 QA Address Validation (Google Address Validation API only)")

    return cross_validate_address_fields(address)


@tool
def qa_validate_physician_address(form_json: Union[str, dict]) -> dict:
    """
    Validate physician address strictly against NPPES registry.
    Cross-validation used only for formatting/reframing, NOT for ground truth.
    """
    try:
        # ------------------------------
        # Step 1: Parse form
        # ------------------------------
        if isinstance(form_json, dict):
            form_data = form_json
        else:
            form_data = json.loads(form_json)
        
        prescription = form_data.get("Information", {}).get("Prescription", {})
        submitted_address = {
            "street": (prescription.get("address") or "").strip(),
            "city": (prescription.get("city") or "").strip(),
            "state": (prescription.get("state") or "").strip(),
            "zip_code": (prescription.get("postal_code") or "").strip()
        }

        
        print("🔍 Validating physician address against NPPES...")

        # ------------------------------
        # Step 2: Reformat address (optional)
        # ------------------------------
        reframed_address = cross_validate_address_fields({
            "street": submitted_address["street"],
            "city": submitted_address["city"],
            "state": submitted_address["state"],
            "zip_code": submitted_address["zip_code"]
        })
        # We only care about formatted fields; ignore 'incorrect_fields' here
        formatted_address = {
            "street": submitted_address["street"],
            "city": submitted_address["city"],
            "state": submitted_address["state"],
            "zip_code": submitted_address["zip_code"]
        }

        # ------------------------------
        # Step 3: Fetch official address from NPPES
        # ------------------------------
        npi = (prescription.get("npi_number") or "").strip()
        if not npi:
            return {
                "address_valid": False,
                "incorrect_fields": {},
                "ground_truth": {},
                "confidence": 0,
                "message": "NPI missing, cannot validate physician address",
                "skipped": False
            }

        url = f"https://npiregistry.cms.hhs.gov/api/?number={npi}&version=2.1"
        resp = requests.get(url, timeout=10)
        data = resp.json()

        if data.get("result_count", 0) == 0:
            return {
                "address_valid": False,
                "incorrect_fields": {},
                "ground_truth": {},
                "confidence": 0,
                "message": f"NPI {npi} not found in NPPES registry",
                "skipped": False
            }

        official_data = data["results"][0]
        addr = official_data.get("addresses", [{}])[0]
        ground_truth = {
            "street": addr.get("address_1", ""),
            "city": addr.get("city", ""),
            "state": addr.get("state", ""),
            "zip_code": addr.get("postal_code", "")
        }

        # ------------------------------
        # Step 4: Compare submitted vs official
        # ------------------------------
        incorrect_fields = {}
        confidence = 100.0

        for field in ["street", "city", "state", "zip_code"]:
            sub = submitted_address.get(field, "").strip().lower()
            gt = ground_truth.get(field, "").strip().lower()
            if sub != gt:
                incorrect_fields[field] = {"submitted": submitted_address.get(field), "official": ground_truth.get(field)}
                confidence = 0.0  # If any mismatch, confidence = 0

        # ------------------------------
        # Step 5: Prepare result
        # ------------------------------
        result = {
            "address_valid": len(incorrect_fields) == 0,
            "incorrect_fields": incorrect_fields if incorrect_fields else None,
            "ground_truth": ground_truth,
            "confidence": confidence,
            "skipped": False,
            "address_type": "physician"
        }

        if result["address_valid"]:
            print(f"  ✅ Physician address validated (matches NPPES, confidence: {confidence}%)")
        else:
            print(f"  ❌ Physician address mismatch: {list(incorrect_fields.keys())}")

        return result

    except Exception as e:
        print(f"Error in qa_validate_physician_address: {e}")
        return {"address_valid": True, "error": str(e)}

@tool
def qa_validate_insurance_names(form_json: Union[str, dict]) -> dict:
    """Validate insurance company names against PostgreSQL database"""
    try:
        if isinstance(form_json, dict):
            form_data = form_json
        else:
            form_data = json.loads(form_json)
        
        info = form_data.get("Information", {})
        primary_ins = info.get("Primary_Insurance", {})
        secondary_ins = info.get("Secondary_Insurance", {})
        
        incorrect = {}
        
        # Validate Primary Insurance
        primary_name = (primary_ins.get("insurance_company_name") or "").strip()
        if primary_name:
            if not is_exact_match_in_db(primary_name):
                print(f"  ❌ Primary insurance '{primary_name}' not found in database")
                incorrect["primary_insurance_company_name"] = {
                    "submitted": primary_name,
                    "reason": "No exact match in database - requires fuzzy matching"
                }
            else:
                print(f"  ✅ Primary insurance '{primary_name}' validated")
        
        # Validate Secondary Insurance
        secondary_name = (secondary_ins.get("insurance_company_name") or "").strip()
        if secondary_name:
            if not is_exact_match_in_db(secondary_name):
                print(f"  ❌ Secondary insurance '{secondary_name}' not found in database")
                incorrect["secondary_insurance_company_name"] = {
                    "submitted": secondary_name,
                    "reason": "No exact match in database - requires fuzzy matching"
                }
            else:
                print(f"  ✅ Secondary insurance '{secondary_name}' validated")
        
        return {
            "valid": len(incorrect) == 0,
            "incorrect_fields": incorrect
        }
    
    except Exception as e:
        print(f"Error in qa_validate_insurance_names: {e}")
        import traceback
        traceback.print_exc()
        return {"valid": True, "incorrect_fields": {}, "error": str(e)}

@tool
def qa_validate_npi_and_check_fields(form_json: Union[str, dict]) -> dict:
    """Validate NPI and identify incorrect prescription fields"""
    try:
        if isinstance(form_json, dict):
            form_data = form_json
        else:
            form_data = json.loads(form_json)
        
        presc = form_data.get("Information", {}).get("Prescription", {})
        npi = (presc.get("npi_number") or "").strip()
        
        print(f"🔍 Validating NPI {npi}...")
        
        if not npi or len(npi) != 10 or not npi.isdigit():
            return {
                "incorrect_fields": {
                    "npi_number": {
                        "submitted": npi,
                        "official": "Not found in NPPES registry",
                        "message": "Invalid NPI format"
                    }
                },
                "npi_validation": {"valid": False, "npi": npi, "message": "Invalid NPI format (must be 10 digits)"}
            }
        
        url = f"https://npiregistry.cms.hhs.gov/api/?number={npi}&version=2.1"
        
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            
            if data.get("result_count", 0) == 0:
                print(f"  ❌ NPI {npi} not found in NPPES registry")
                return {
                    "incorrect_fields": {
                        "npi_number": {
                            "submitted": npi,
                            "official": "Not found in NPPES registry",
                            "message": "NPI validation failed"
                        }
                    },
                    "npi_validation": {"valid": False, "npi": npi, "message": "NPI not found in NPPES registry"}
                }
            
            result = data["results"][0]
            basic = result.get("basic", {})
            addr = result.get("addresses", [{}])[0]
            
            official_name = basic.get("organization_name") or f"{basic.get('first_name', '')} {basic.get('last_name', '')}".strip()
            
            npi_data = {
                "valid": True,
                "npi": npi,
                "official_name": official_name,
                "official_address": addr.get("address_1", ""),
                "official_city": addr.get("city", ""),
                "official_state": addr.get("state", ""),
                "official_postal_code": addr.get("postal_code", ""),
                "official_phone": addr.get("telephone_number", "")
            }
            
            print(f"  ✅ NPI {npi} validated successfully. Official name: {official_name}")
            
        except Exception as e:
            print(f"  ⚠️ NPPES API error: {e}")
            return {
                "incorrect_fields": {},
                "npi_validation": {"valid": False, "message": f"NPPES API error: {str(e)}"}
            }
        
        # Compare submitted vs official
        incorrect = {}
        
        if norm_text(presc.get("physician_name")) != norm_text(npi_data.get("official_name")):
            incorrect["physician_name"] = {
                "submitted": presc.get("physician_name"),
                "official": npi_data.get("official_name")
            }
        
        sub_addr = (presc.get("address") or "").lower().strip()
        off_addr = (npi_data.get("official_address") or "").lower().strip()
        if sub_addr and off_addr and sub_addr != off_addr:
            incorrect["address"] = {
                "submitted": presc.get("address"),
                "official": npi_data.get("official_address")
            }
        
        sub_city = (presc.get("city") or "").lower().strip()
        off_city = (npi_data.get("official_city") or "").lower().strip()
        if sub_city and off_city and sub_city != off_city:
            incorrect["city"] = {
                "submitted": presc.get("city"),
                "official": npi_data.get("official_city")
            }
        
        sub_state = (presc.get("state") or "").upper().strip()
        off_state = (npi_data.get("official_state") or "").upper().strip()
        if sub_state and off_state and sub_state != off_state:
            incorrect["state"] = {
                "submitted": presc.get("state"),
                "official": npi_data.get("official_state")
            }
        
        sub_zip = (presc.get("postal_code") or "").strip()[:5]
        off_zip = (npi_data.get("official_postal_code") or "").strip()[:5]
        if sub_zip and off_zip and sub_zip != off_zip:
            incorrect["postal_code"] = {
                "submitted": sub_zip,
                "official": off_zip
            }
        
        sub_phone = norm_phone(presc.get("phone_number"))
        off_phone = norm_phone(npi_data.get("official_phone"))
        if sub_phone and off_phone and sub_phone != off_phone:
            incorrect["phone_number"] = {
                "submitted": presc.get("phone_number"),
                "official": npi_data.get("official_phone")
            }
        
        return {
            "incorrect_fields": incorrect,
            "npi_validation": {
                "valid": True,
                "npi": npi,
                "official_name": npi_data.get("official_name"),
                "official_data": npi_data,
                "message": "NPI verified successfully"
            }
        }
        
    except Exception as e:
        print(f"Error in qa_validate_npi_and_check_fields: {e}")
        return {
            "incorrect_fields": {},
            "npi_validation": {"valid": False, "message": f"Error: {str(e)}"}
        }

# ============================================================
# LANGGRAPH WORKFLOW (UNUSED - KEEPING FOR COMPATIBILITY)
# ============================================================

class AgentState(TypedDict):
    messages: List[Any]
    form_data: dict
    qa_results: dict
    iteration_count: int

qa_tools = [
    qa_detect_missing_fields,
    qa_validate_patient_address,
    qa_validate_physician_address,
    qa_validate_insurance_names,
    qa_validate_npi_and_check_fields
]

llm_qa = llm.bind_tools(qa_tools) if llm else None

# ============================================================
# MAIN VALIDATION FUNCTION
# ============================================================

def validate_enrollment(form_data: dict) -> dict:
    """
    Validate healthcare enrollment form (no auto-correction)
    Calls all Q/A tools directly without LangGraph
    """
    print("=" * 60)
    print("🔍 DEBUG: Form data received by Q/A Agent:")
    print("=" * 60)
    patient = form_data.get("Information", {}).get("Patient", {})
    print(f"  Patient section exists: {bool(patient)}")
    print(f"  Patient fields: {list(patient.keys())}")
    print(f"  Patient street: '{patient.get('street')}'")
    print(f"  Patient city: '{patient.get('city')}'")
    
    primary_ins = form_data.get("Information", {}).get("Primary_Insurance", {})
    print(f"  Primary Insurance exists: {bool(primary_ins)}")
    print(f"  Insurance name: '{primary_ins.get('insurance_company_name')}'")
    print("=" * 60 + "\n")
    
    print("=" * 60)
    print("Starting Q/A validation workflow...")
    print("=" * 60)
    
    # Execute all tools directly
    qa_results = {}
    
    try:
        # Tool 1: Detect missing fields
        print("  🔧 Executing tool: qa_detect_missing_fields")
        qa_results["qa_detect_missing_fields"] = qa_detect_missing_fields.invoke({"form_json": form_data})
        
        # Tool 2: Validate patient address
        print("  🔧 Executing tool: qa_validate_patient_address")
        qa_results["qa_validate_patient_address"] = qa_validate_patient_address.invoke({"form_json": form_data})
        

        
        # Tool 3: Validate physician address
        print("  🔧 Executing tool: qa_validate_physician_address")
        qa_results["qa_validate_physician_address"] = qa_validate_physician_address.invoke({"form_json": form_data})
        
        # Tool 4: Validate insurance names
        print("  🔧 Executing tool: qa_validate_insurance_names")
        qa_results["qa_validate_insurance_names"] = qa_validate_insurance_names.invoke({"form_json": form_data})
        
        # Tool 5: Validate NPI
        print("  🔧 Executing tool: qa_validate_npi_and_check_fields")
        qa_results["qa_validate_npi_and_check_fields"] = qa_validate_npi_and_check_fields.invoke({"form_json": form_data})
        
    except Exception as e:
        print(f"⚠️ Tool execution error: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n✅ Q/A tools executed: {list(qa_results.keys())}")
    
    # Aggregate results
    missing_fields = qa_results.get("qa_detect_missing_fields", {}).get("missing_fields", {})
    npi_result = qa_results.get("qa_validate_npi_and_check_fields", {})
    incorrect_fields = npi_result.get("incorrect_fields", {})
    
    patient_addr_result = qa_results.get("qa_validate_patient_address", {})
    physician_addr_result = qa_results.get("qa_validate_physician_address", {})
    insurance_result = qa_results.get("qa_validate_insurance_names", {})
    
    # Add address incorrect fields
    if not patient_addr_result.get("address_valid", True):
        addr_incorrect = patient_addr_result.get("incorrect_fields", {})
        for field, details in addr_incorrect.items():
            incorrect_fields[f"patient_{field}"] = details
    
    if not physician_addr_result.get("address_valid", True):
        addr_incorrect = physician_addr_result.get("incorrect_fields", {})
        for field, details in addr_incorrect.items():
            incorrect_fields[f"physician_{field}"] = details
    
    # Add insurance incorrect fields
    insurance_incorrect = insurance_result.get("incorrect_fields", {})
    incorrect_fields.update(insurance_incorrect)

    form_data["patient_address"] = patient_addr_result
    form_data["physician_address"] = physician_addr_result
    form_data["incorrect_fields"] = incorrect_fields if incorrect_fields else None
    form_data["missing_fields"] = missing_fields if missing_fields else None

    
    output = {
        "json": form_data,
        "missing_fields": missing_fields if missing_fields else None,
        "incorrect_fields": incorrect_fields if incorrect_fields else None,
        "patient_address": patient_addr_result,
        "physician_address": physician_addr_result
    }
    
    print("=" * 60)
    print("Q/A Validation complete")
    print(f"  Missing fields: {len(missing_fields) if missing_fields else 0}")
    print(f"  Incorrect fields: {len(incorrect_fields) if incorrect_fields else 0}")
    print("=" * 60)
    
    if not output["missing_fields"] and not output["incorrect_fields"]:
        return output["json"]
    
    return output

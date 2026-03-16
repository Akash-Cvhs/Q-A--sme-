
"""
SME Agent - Subject Matter Expert Correction Agent
Performs intelligent correction with:
- Fuzzy NPI matching
- Insurance company name matching (70% threshold) - PRIORITY
- Cross-field address validation (65% threshold) - NON-BLOCKING
- Proper JSON reordering even on errors
"""

import json
import os
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv
from pydantic import BaseModel
import psycopg2

# Gemini Integration
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import Tool

# Fuzzy matching
from thefuzz import fuzz

# Tools
from tools import (
    extract_incorrect_fields,
    address_validation_tool,
    nppes_lookup_tool,
    nppes_fuzzy_search
)

load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================

GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")

# PostgreSQL Configuration
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_DB = os.getenv("POSTGRES_DB", "healthcare_db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
schema_name = os.getenv("schema_name", "insurance")
# ============================================================
# DATABASE CONNECTION
# ============================================================

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
# GEMINI CONFIGURATION
# ============================================================

# Better credential path resolution
credentials_valid = False
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

# ============================================================
# STRICT SCHEMAS FOR TOOL CALLING
# ============================================================

class AddressInput(BaseModel):
    street: str
    city: str
    state: str
    postal_code: str

class AddressToolArgs(BaseModel):
    address: AddressInput

class ExtractArgs(BaseModel):
    full_json: Dict[str, Any]

class NPPESArgs(BaseModel):
    npi_number: str

class NPPESFuzzyArgs(BaseModel):
    physician_name: str
    address: str
    city: str
    state: str

# ============================================================
# ROBUST JSON EXTRACTOR FOR LLM OUTPUT
# ============================================================

def safe_extract_json(content):
    """Safely extract JSON from LLM output."""
    if isinstance(content, dict):
        return content
    
    if isinstance(content, list):
        combined = ""
        for block in content:
            if isinstance(block, str):
                combined += block
            elif isinstance(block, dict) and "text" in block:
                combined += block["text"]
        content = combined
    
    if not isinstance(content, str):
        return None
    
    txt = content.strip()
    
    # Remove markdown code blocks using character codes to avoid syntax errors
    code_fence = chr(96) + chr(96) + chr(96)
    if txt.startswith(code_fence):
        txt = txt.replace(code_fence + 'json', '').replace(code_fence, '').strip()
    
    # Try parse entire text
    try:
        return json.loads(txt)
    except:
        pass
    
    # Try extract {...}
    try:
        s = txt.index("{")
        e = txt.rindex("}")
        return json.loads(txt[s:e + 1])
    except:
        pass
    
    return None

# ============================================================
# TOOL WRAPPERS
# ============================================================

def tool_extract_wrapper(args: Dict[str, Any]):
    """Extract incorrect fields"""
    full_json = args["full_json"]
    if isinstance(full_json, str):
        try:
            full_json = json.loads(full_json)
        except Exception as e:
            print(f"Error parsing full_json: {e}")
            return {"error": "Invalid JSON string"}
    return extract_incorrect_fields(full_json)

def tool_address_wrapper(args: Dict[str, Any]):
    """Address validation"""
    a = args["address"]
    if isinstance(a, str):
        try:
            a = json.loads(a)
        except Exception as e:
            print(f"Error parsing address: {e}")
            return {"error": "Invalid address format"}
    
    return address_validation_tool({
        "street": a.get("street", ""),
        "city": a.get("city", ""),
        "state": a.get("state", ""),
        "postal_code": a.get("postal_code", "")
    })

def tool_nppes_wrapper(args: Dict[str, Any]):
    """NPPES lookup by NPI"""
    npi = args["npi_number"]
    if isinstance(npi, dict):
        npi = npi.get("npi_number", "")
    if isinstance(npi, str) and npi.startswith("{"):
        try:
            npi_dict = json.loads(npi)
            npi = npi_dict.get("npi_number", npi)
        except:
            pass
    
    result = nppes_lookup_tool(npi)
    if isinstance(result, dict) and result.get("npi"):
        return result
    
    return {"error": "No provider found", "searched_npi": npi}

def tool_nppes_fuzzy_wrapper(args: Dict[str, Any]):
    """Fuzzy NPPES search by name, address, and location"""
    physician_name = args.get("physician_name", "")
    address = args.get("address", "")
    city = args.get("city", "")
    state = args.get("state", "")
    
    return nppes_fuzzy_search(physician_name, address, city, state)

# ============================================================
# TOOL BINDING
# ============================================================

extract_tool_lc = Tool(
    name="extract_incorrect_fields",
    description="Extract incorrect fields from the input JSON.",
    func=tool_extract_wrapper,
    args_schema=ExtractArgs
)

address_tool_lc = Tool(
    name="address_validation_tool",
    description="Validate and correct address using Google Address Validation.",
    func=tool_address_wrapper,
    args_schema=AddressToolArgs
)

nppes_tool_lc = Tool(
    name="nppes_lookup_tool",
    description="Fetch doctor details using NPI Registry API by NPI number.",
    func=tool_nppes_wrapper,
    args_schema=NPPESArgs
)

nppes_fuzzy_tool_lc = Tool(
    name="nppes_fuzzy_search",
    description="Search for providers in NPPES by name, address, city, and state when NPI is invalid.",
    func=tool_nppes_fuzzy_wrapper,
    args_schema=NPPESFuzzyArgs
)

TOOLS = [extract_tool_lc, address_tool_lc, nppes_tool_lc, nppes_fuzzy_tool_lc]

# ============================================================
# INITIALIZE GEMINI
# ============================================================

llm = None
if not credentials_valid:
    print("⚠️ WARNING: GOOGLE_APPLICATION_CREDENTIALS not found")
else:
    try:
        llm = ChatVertexAI(
            model_name="gemini-2.0-flash-exp",
            temperature=0,
            project="doc-triaging-463411",
            location="us-central1"
        ).bind_tools(TOOLS)
        print("✓ Google Gemini 2.0 Flash configured for SME Agent")
    except Exception as e:
        print(f"⚠️ ERROR initializing Gemini: {e}")
        llm = None

# ============================================================
# INSURANCE FUZZY MATCHING (70% THRESHOLD)
# ============================================================

def fuzzy_match_insurance_company(submitted_name: str) -> dict:
    """
    Fuzzy match insurance company name against PostgreSQL database.
    Threshold: 70% confidence for auto-correction.
    """
    conn = get_db_connection()
    if not conn:
        print("⚠️ Database not available - skipping insurance correction")
        return {"error": "DATABASE_UNAVAILABLE"}
    
    try:
        cursor = conn.cursor()
        
        cursor.execute(f"""
            SELECT payer_id, payer_name
            FROM {schema_name}.insurance_companies
            WHERE status = 'ACTIVE'
        """)
        
        companies = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not companies:
            return {"error": "NO_INSURANCE_DATA_IN_DB"}
        
        candidates = []
        
        for payer_id, payer_name in companies:
            # Token sort ratio (main scoring method)
            token_score = fuzz.token_sort_ratio(
                submitted_name.lower(), 
                payer_name.lower()
            )
            
            # Partial ratio for substring matching
            partial_score = fuzz.partial_ratio(
                submitted_name.lower(),
                payer_name.lower()
            )
            
            # Weighted confidence: 70% token_sort, 30% partial
            confidence = (token_score * 0.7) + (partial_score * 0.3)
            
            candidates.append({
                "id": payer_id,
                "official_name": payer_name,
                "confidence_score": round(confidence, 2)
            })
        
        # Sort by confidence
        candidates.sort(key=lambda x: x["confidence_score"], reverse=True)
        
        best_match = candidates[0]
        
        print(f"    🏢 Best insurance match: {best_match['official_name']} (confidence: {best_match['confidence_score']}%)")
        
        if best_match["confidence_score"] >= 60:
            return {
                "success": True,
                "official_name": best_match["official_name"],
                "confidence": best_match["confidence_score"],
                "submitted_name": submitted_name
            }
        else:
            return {
                "error": "LOW_CONFIDENCE",
                "message": f"Best match confidence {best_match['confidence_score']}% is below threshold (70%)",
                "submitted_name": submitted_name,
                "best_match": best_match,
                "top_suggestions": candidates[:3]
            }
        
    except Exception as e:
        print(f"⚠️ Insurance fuzzy matching error: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

# ============================================================
# SME AGENT
# ============================================================

class SMEAgent:
    """
    The SME Agent performs intelligent correction with:
    
    1. Extract incorrect fields
    2. Validate NPI and perform fuzzy matching if needed
    3. Correct insurance names (70% threshold) - PRIORITY, NON-BLOCKING
    4. Correct addresses (65% threshold) - NON-BLOCKING
    5. Apply corrections to BOTH Prescription AND HCP_Consent
    6. Reorder JSON structure (even on errors)
    """
    
    def __init__(self):
        if not llm:
            raise Exception("Google Gemini not configured. Please set GOOGLE_APPLICATION_CREDENTIALS.")
        self.llm = llm
        self.tool_map = {
            "extract_incorrect_fields": tool_extract_wrapper,
            "address_validation_tool": tool_address_wrapper,
            "nppes_lookup_tool": tool_nppes_wrapper,
            "nppes_fuzzy_search": tool_nppes_fuzzy_wrapper
        }
    
    def run(self, full_json: Dict[str, Any]):
        """
        Run the SME validation workflow with intelligent corrections.
        Returns clean JSON without incorrect_fields/missing_fields.
        Always reorders JSON structure, even on validation errors.
        """
        try:  # ✅ FIX 1: Wrap everything in try/except
            print("=" * 60)
            print("🚀 SME AGENT: Starting intelligent corrections...")
            print("=" * 60)
            
            # Step 1: Extract incorrect fields
            print("→ Step 1: Extracting incorrect fields...")
            incorrect_fields = extract_incorrect_fields(full_json)
            
            if "message" in incorrect_fields or "error" in incorrect_fields:
                print(f"  ℹ️ {incorrect_fields}")
                clean_json = self._clean_output(full_json)
                return clean_json
            
            print(f"  ✓ Found {len(incorrect_fields)} incorrect fields")
            
            # Get prescription data
            prescription = full_json.get("Information", {}).get("Prescription", {})
            npi = (prescription.get("npi_number") or "").strip()
            
            # Initialize final_json early so we can always return a clean structure
            final_json = full_json.copy()
            
            # Collect warnings (non-blocking issues)
            warnings = []
            
            # ============================================================
            # Step 2: NPI Validation and Correction
            # ============================================================
            corrected_prescription = prescription.copy()
            corrected_npi = None
            corrected_physician_name = None
            
            if npi:
                print(f"\n→ Step 2: Validating NPI {npi}...")
                nppes_data = nppes_lookup_tool(npi)
                
                if "error" not in nppes_data:
                    # Valid NPI
                    print(f"  ✓ NPI valid: {nppes_data.get('provider_name')}")
                    corrected_npi = npi
                    corrected_physician_name = nppes_data.get("provider_name")
                    corrected_prescription.update({
                        "physician_name": corrected_physician_name,
                        "address": nppes_data.get("address"),
                        "city": nppes_data.get("city"),
                        "state": nppes_data.get("state"),
                        "postal_code": nppes_data.get("postal_code"),
                        "phone_number": nppes_data.get("phone", corrected_prescription.get("phone_number", ""))
                    })
                else:
                    # Invalid NPI - try fuzzy search
                    print(f"  ✗ NPI invalid or not found")
                    print(f"  ℹ️ Attempting fuzzy search with name + address...")
                    
                    fuzzy_result = nppes_fuzzy_search(
                        corrected_prescription.get("physician_name", ""),
                        corrected_prescription.get("address", ""),
                        corrected_prescription.get("city", ""),
                        corrected_prescription.get("state", "")
                    )
                    
                    if isinstance(fuzzy_result, dict) and "error" not in fuzzy_result:
                        candidates = fuzzy_result.get("candidates", [])
                        
                        if candidates and len(candidates) > 0:
                            best_match = candidates[0]
                            confidence = best_match.get("confidence_score", 0)
                            
                            if confidence >= 65:
                                print(f"  ✓ High-confidence fuzzy match found ({confidence}%)")
                                print(f"    {best_match.get('provider_name')} - NPI: {best_match.get('npi')}")
                                corrected_npi = best_match.get("npi")
                                corrected_physician_name = best_match.get("provider_name")
                                corrected_prescription.update({
                                    "npi_number": corrected_npi,
                                    "physician_name": corrected_physician_name,
                                    "address": best_match.get("address"),
                                    "city": best_match.get("city"),
                                    "state": best_match.get("state"),
                                    "postal_code": best_match.get("postal_code"),
                                    "phone_number": best_match.get("phone", corrected_prescription.get("phone_number", ""))
                                })
                            else:
                                print(f"  ⚠️ Low confidence match ({confidence}%)")
                                final_json["validation_error"] = f"NPI {npi} is invalid. Best match confidence: {confidence}% (threshold: 65%)"
                                final_json["validation_status"] = "FAILED"
                                final_json["Information"]["Prescription"] = corrected_prescription
                                return self._clean_output(final_json)
                        else:
                            print(f"  ✗ No fuzzy matches found")
                            final_json["validation_error"] = f"NPI {npi} is invalid and no providers match the given information"
                            final_json["validation_status"] = "FAILED"
                            final_json["Information"]["Prescription"] = corrected_prescription
                            return self._clean_output(final_json)
                    else:
                        print(f"  ✗ Fuzzy search failed")
                        final_json["validation_error"] = f"NPI {npi} is invalid and fuzzy search failed"
                        final_json["validation_status"] = "FAILED"
                        final_json["Information"]["Prescription"] = corrected_prescription
                        return self._clean_output(final_json)
            
            # Step 3: Apply NPI corrections to final_json
            final_json["Information"]["Prescription"] = corrected_prescription
            
            # Update HCP_Consent
            if "HCP_Consent" in final_json.get("Information", {}):
                hcp_consent = final_json["Information"]["HCP_Consent"].copy()
                
                if corrected_npi:
                    hcp_consent["npi_number"] = corrected_npi
                    print(f"  ✓ Also updated HCP_Consent NPI: {corrected_npi}")
                
                if corrected_physician_name:
                    hcp_consent["physician_name"] = corrected_physician_name
                
                if corrected_prescription.get("address"):
                    hcp_consent["address"] = corrected_prescription.get("address")
                    hcp_consent["city"] = corrected_prescription.get("city")
                    hcp_consent["state"] = corrected_prescription.get("state")
                
                final_json["Information"]["HCP_Consent"] = hcp_consent

            # ============================================================
            # Step 4: Insurance Company Name Correction (70% Threshold) - PRIORITY
            # ============================================================
            print("\n→ Step 4: Correcting Insurance Company Names (70% threshold)...")

            qa_incorrect_fields = full_json.get("incorrect_fields", {})  # ✅ FIX: snake_case

            # Get insurance from ORIGINAL location (before reordering)
            primary_insurance = final_json["Information"].get("Primary_Insurance", {})
            secondary_insurance = final_json["Information"].get("Secondary_Insurance", {})

            # Correct Primary Insurance
            primary_name = (primary_insurance.get("insurance_company_name") or "").strip()

            if primary_name and "primary_insurance_company_name" in qa_incorrect_fields:  # ✅ FIX: snake_case
                print(f"    🔍 Checking primary insurance: '{primary_name}'")
                result = fuzzy_match_insurance_company(primary_name)
                
                if result.get("success"):
                    # Update the ORIGINAL location
                    primary_insurance["insurance_company_name"] = result["official_name"]
                    print(f"    ✅ Primary insurance corrected: '{primary_name}' → '{result['official_name']}'")
                    
                    # Also update in final_json to ensure it persists
                    final_json["Information"]["Primary_Insurance"]["insurance_company_name"] = result["official_name"]
                    
                elif result.get("error") == "LOW_CONFIDENCE":
                    print(f"    ⚠️  {result['message']}")
                    warnings.append(f"Primary insurance: {result['message']}")
                elif result.get("error") in ["DATABASE_UNAVAILABLE", "NO_INSURANCE_DATA_IN_DB"]:
                    print(f"    ℹ️  Skipping insurance correction: {result['error']}")
            else:
                if primary_name:
                    print(f"    ℹ️  Primary insurance '{primary_name}' not flagged by QA - skipping")

            # Correct Secondary Insurance
            secondary_name = (secondary_insurance.get("insurance_company_name") or "").strip()

            if secondary_name and "secondary_insurance_company_name" in qa_incorrect_fields:  # ✅ FIX: snake_case
                print(f"    🔍 Checking secondary insurance: '{secondary_name}'")
                result = fuzzy_match_insurance_company(secondary_name)
                
                if result.get("success"):
                    # Update the ORIGINAL location
                    secondary_insurance["insurance_company_name"] = result["official_name"]
                    print(f"    ✅ Secondary insurance corrected: '{secondary_name}' → '{result['official_name']}'")
                    
                    # Also update in final_json to ensure it persists
                    final_json["Information"]["Secondary_Insurance"]["insurance_company_name"] = result["official_name"]
                    
                elif result.get("error") == "LOW_CONFIDENCE":
                    print(f"    ⚠️  {result['message']}")
                    warnings.append(f"Secondary insurance: {result['message']}")
                elif result.get("error") in ["DATABASE_UNAVAILABLE", "NO_INSURANCE_DATA_IN_DB"]:
                    print(f"    ℹ️  Skipping insurance correction: {result['error']}")
            else:
                if secondary_name:
                    print(f"    ℹ️  Secondary insurance '{secondary_name}' not flagged by QA - skipping")


            # ============================================================
            # Step 5: Patient Address Correction (QA-Driven, NON-BLOCKING)
            # ============================================================

            print("\n→ Step 5: Applying Patient Address Corrections (QA-Driven)")

            qapatientaddress = full_json.get("patient_address", {})

            if not qapatientaddress or qapatientaddress.get("address_valid", True):
                print("  ℹ️  Address valid or no QA output, skipping correction")
            else:
                incorrect = qapatientaddress.get("incorrect_fields", {})
                groundtruth = qapatientaddress.get("ground_truth", {})
                confidence = qapatientaddress.get("confidence", 100)

                if confidence < 65:
                    print(f"  ⚠️  Address confidence too low ({confidence}%), skipping correction")
                    warnings.append(f"Patient address confidence {confidence} below threshold")
                elif not incorrect:
                    print("  ✓ No address corrections needed")
                else:
                    patient_info = final_json["Information"].get("Patient")
                    patient_consent = final_json["Information"].get("Patient_Consent")  # ✅ FIX: Get consent too

                    if not patient_info:
                        print("  ⚠️  Patient section missing, skipping address correction")
                    else:
                        fieldmap = {
                            "street": "street",
                            "city": "city",
                            "state": "state",
                            "postalcode": "postalcode",
                        }

                        applied = []

                        for qa_field, patient_field in fieldmap.items():
                            if qa_field in incorrect:
                                value = incorrect[qa_field].get("expected")
                                reason = incorrect[qa_field].get("reason", "QA correction")
                                
                                if value:
                                    # ✅ Update Patient
                                    patient_info[patient_field] = value
                                    print(f"    ✅ Patient.{patient_field}: '{value}' ← {reason}")
                                    
                                    # ✅ FIX: Also update Patient_Consent
                                    if patient_consent and isinstance(patient_consent, dict):
                                        patient_consent[patient_field] = value
                                        print(f"       (Also updated Patient_Consent.{patient_field})")
                                    
                                    applied.append(patient_field)

                        if applied:
                            print(f"  ✓ Patient address corrected (confidence: {confidence}%)")
                            print(f"    Updated sections: Patient, Patient_Consent")
                        else:
                            print("  ℹ️  QA flagged address but no applicable corrections")

            # ============================================================
            # Final: Clean and Return
            # ============================================================
            clean_json = self._clean_output(final_json)
            
            # Add warnings if any
            if warnings:
                clean_json["validation_warnings"] = warnings
            
            print("\n→ ✅ All Corrections Applied:")
            print(f"  - NPI: {corrected_prescription.get('npi_number', 'N/A')}")
            print(f"  - Physician: {corrected_prescription.get('physician_name', 'N/A')}")
            print(f"  - Address: {corrected_prescription.get('address', 'N/A')}, {corrected_prescription.get('city', 'N/A')}, {corrected_prescription.get('state', 'N/A')} {corrected_prescription.get('postal_code', 'N/A')}")
            if corrected_npi:
                print(f"  - HCP_Consent NPI also updated to: {corrected_npi}")
            if warnings:
                print(f"  ⚠️  Warnings: {len(warnings)}")
                for w in warnings:
                    print(f"      - {w}")
            
            print("=" * 60)
            return clean_json
        
       
        except Exception as e:
            print(f"\n❌ SME AGENT ERROR: {e}")
            import traceback
            traceback.print_exc()
            
            # ✅ FIX: Ensure final_json exists
            if 'final_json' not in locals():
                final_json = full_json.copy()
            
            # Mark as error
            final_json["validation_status"] = "ERROR"
            final_json["validation_error"] = str(e)
            
            # ✅ FIX: Force cleanup even on error
            try:
                cleaned = self._clean_output(final_json)
                print("  ✓ Output cleaned despite error")
                return cleaned
            except Exception as cleanup_error:
                print(f"  ⚠️ Cleanup also failed: {cleanup_error}")
                # Last resort: return raw with error markers
                final_json.pop("patient_address", None)
                final_json.pop("physician_address", None)
                final_json.pop("incorrect_fields", None)
                final_json.pop("missing_fields", None)
                return final_json

    
    
    #     return clean
    def _clean_output(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove validation metadata and reorder Information sections"""
        if not isinstance(json_data, dict):
            print(f"  ⚠️ Invalid input to _clean_output: {type(json_data)}")
            return {}
        
        clean = json_data.copy()
        
        # ✅ Remove QA output keys (snake_case) - ALWAYS runs
        print("  → Removing QA metadata keys...")
        clean.pop("patient_address", None)
        clean.pop("physician_address", None)
        clean.pop("incorrect_fields", None)
        clean.pop("missing_fields", None)
        
        # Fallback camelCase keys
        clean.pop("patientaddress", None)
        clean.pop("physicianaddress", None)
        clean.pop("incorrectfields", None)
        clean.pop("missingfields", None)
        print("  ✓ QA metadata removed")
        
        # ✅ Reorder Information sections
        if "Information" in clean and isinstance(clean["Information"], dict):
            try:
                print("  → Reordering Information sections...")
                clean["Information"] = self._reorder_information(clean["Information"])
                print("  ✓ Information sections reordered successfully")
            except Exception as e:
                print(f"  ⚠️ Reordering failed: {e}")
                import traceback
                traceback.print_exc()
                # Keep original structure if reordering fails
        else:
            print("  ⚠️ No Information section to reorder")
        
        return clean

        
    def _reorder_information(self, information: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reorder Information sections to match required structure:
        1. Prescriber_Information (from Prescription)
        2. Patient_Information (from Patient)
        3. Patient_Consent
        4. HCP_Consent
        5. Diagnosis (from Prescription)
        6. Prescription
        7. Insurance (Primary + Secondary)
        8. Caregiver_Information
        """
        ordered = {}

        presc = information.get("Prescription", {})

        patient_info = (
            information.get("Patient_Information")
            or information.get("Patient")
            or {}
        )

        
        # 1. Prescriber Information (extract from Prescription)
        if "Prescription" in information:
            presc = information["Prescription"]
            ordered["Prescriber_Information"] = {
                "physician_name": presc.get("physician_name", ""),
                "npi_number": presc.get("npi_number", ""),
                "physician_specialty": presc.get("physician_specialty", ""),
                "address": presc.get("address", ""),
                "city": presc.get("city", ""),
                "state": presc.get("state", ""),
                "postal_code": presc.get("postal_code", ""),
                "phone_number": presc.get("phone_number", ""),
                "physician_email": presc.get("physician_email", ""),  
                "practice_facility_name": presc.get("practice_facility_name", ""),
                "hco_name": presc.get("hco_name", ""),
                "pin": presc.get("pin", "")
                
                
            }
        
        # 2. Patient Information - ✅ PASS-THROUGH (preserves Step 5 updates)
        if "Patient_Information" in information:
            ordered["Patient_Information"] = information["Patient_Information"]
            print("  DEBUG: Reordering 'Patient_Information' (found in original)")
        elif "Patient" in information:
            # ✅ FIX 7: Rename "Patient" → "Patient_Information" while preserving updates
            ordered["Patient_Information"] = information["Patient"]
            print("  DEBUG: Reordering 'Patient' → 'Patient_Information' (renamed)")
        else:
            print("  ⚠️ No patient section found during reordering")
        
        # # 3. Patient Consent - controlled pass-through + schema guarantee
        # if "Patient_Consent" in information:
        #     patient_consent = information["Patient_Consent"]

        #     ordered["Patient_Consent"] = {
        #         **patient_consent,  # preserve all existing fields
        #         "patient_auth_text": patient_consent.get("patient_auth_text", "")
        #     }
        # 3. Patient Consent – derive from Prescription + preserve text
        patient_consent = information.get("Patient_Consent", {})

        ordered["Patient_Consent"] = {
            **patient_consent,  # preserve any existing fields
            # "patient_consent_name": (
            #     patient_consent.get("patient_consent_name")
            #     or presc.get("patient_consent_name", "")
            # ),
            "patient_consent_name": (
                patient_consent.get("patient_consent_name") or 
                (f"{patient_info.get('first_name')} {patient_info.get('last_name')}" 
                if presc.get("patient_sign_present") else "")
            ),
            "patient_consent_date": (
                patient_consent.get("patient_consent_date")
                or presc.get("patient_consent_date", "")
            ),
            "patient_auth_text": patient_consent.get("patient_auth_text", ""),
            "care_program": presc.get("care_program", ""),

            # --- Add these lines to preserve the booleans ---
            "patient_sign_present": (
                patient_consent.get("patient_sign_present") 
                or presc.get("patient_sign_present", False)
            )
            
            
        }



        # # 4. HCP Consent - controlled pass-through + schema guarantee
        # if "HCP_Consent" in information:
        #     hcp_consent = information["HCP_Consent"]

        #     ordered["HCP_Consent"] = {
        #         **hcp_consent,  # preserve all existing fields
        #         "hcp_auth_text": hcp_consent.get("hcp_auth_text", "")
        #     }

        # 4. HCP Consent – derive from Prescription + preserve text
        hcp_consent = information.get("HCP_Consent", {})

        ordered["HCP_Consent"] = {
            **hcp_consent,  # preserve existing fields
            "hcp_consent_name": (
                hcp_consent.get("hcp_consent_name")
                or presc.get("hcp_consent_name", "")
            ),

            "hcp_consent_date": (
                hcp_consent.get("hcp_consent_date")
                or presc.get("hcp_consent_date", "")
            ),
            "hcp_auth_text": hcp_consent.get("hcp_auth_text", ""),

            "hcp_sign_present": (
                hcp_consent.get("hcp_sign_present") 
                or presc.get("hcp_sign_present", False)
            )
            
            
        }


        
        # 5. Diagnosis (extract from Prescription)
        if "Prescription" in information:
            presc = information["Prescription"]
            ordered["Diagnosis"] = {
                "diagnosis": presc.get("diagnosis", ""),
                "icd_10_code": presc.get("icd_10_code", "")
            }
        
        # 6. Prescription (medication details only)
        if "Prescription" in information:
            presc = information["Prescription"]
            ordered["Prescription"] = {
                "medication_name": presc.get("medication_name", ""),
                "strength": presc.get("strength", ""),
                "frequency": presc.get("frequency", ""),
                "refills": presc.get("refills", ""),  
                "special_instructions": presc.get("special_instructions", ""),
                "prescribed_date": presc.get("prescribed_date", ""),
                "number_of_people_in_household": presc.get("number_of_people_in_household", ""),
                "annual_household_income": presc.get("annual_household_income", ""),
            }
        
        # 7. Insurance (combine Primary and Secondary)
        insurance = {}
        if "Primary_Insurance" in information:
            insurance["Primary_Insurance"] = information["Primary_Insurance"]
        if "Secondary_Insurance" in information:
            insurance["Secondary_Insurance"] = information["Secondary_Insurance"]
        if insurance:
            ordered["Insurance"] = insurance
        
        # 8. Caregiver Information (if exists)
        if "Caregiver_Information" in information:
            ordered["Caregiver_Information"] = information["Caregiver_Information"]

        # 9. Financial Information (derived from Prescription – ALWAYS present)
        # ordered["financial_information"] = {
        #     "house_member_count": presc.get("number_of_people_in_household", ""),
        #     "annual_income": presc.get("annual_household_income", "")
        # }


        # 10. Form Information (ALWAYS present)
        ordered["form_information"] = {
            "form_name": information.get("form_information", {}).get("form_name", "")
        }


        return ordered

# ============================================================
# CONVERT TO FINAL CORRECTED OUTPUT STRUCTURE
# ============================================================

def build_final_output(raw):
    """Normalize SME output."""
    if isinstance(raw, dict) and "json" in raw:
        root = raw["json"]
    elif isinstance(raw, dict):
        root = raw
    else:
        return {"error": "Invalid SME output format", "raw": raw}
    
    # Remove QA output keys
    root.pop("patient_address", None)
    root.pop("physician_address", None)
    root.pop("incorrect_fields", None)
    root.pop("missing_fields", None)
    
    # Fallbacks
    root.pop("patientaddress", None)
    root.pop("physicianaddress", None)
    root.pop("incorrectfields", None)
    root.pop("missingfields", None)
    
    return {
        "File_name": root.get("File_name", []),
        "Intent": root.get("Intent", []),
        "Information": root.get("Information", {}),
        "splited_file_id": root.get("splited_file_id", []),
        "rotated_file_id": root.get("rotated_file_id", []),
        "validation_warnings": root.get("validation_warnings", [])
    }


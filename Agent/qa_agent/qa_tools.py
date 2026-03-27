from langchain_core.tools import tool
from .helpers import nppes_lookup_tool, nppes_fuzzy_search
from .schemas import FieldCorrection

import json
import requests
from typing import Union

from .helpers import (
    cross_validate_address_fields,
    match_insurance_in_db,
    norm_text,
    norm_phone
)
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
    try:
    
        form_data = form_json
        

        patient = form_data.get("Information", {}).get("Patient", {})

        address = {
            "street": patient.get("street", ""),
            "city": patient.get("city", ""),
            "state": patient.get("state", ""),
            "zip_code": patient.get("postalcode", "")
        }

        print("🔍 QA Address Validation (Google Address Validation API only)")
        print(address)

        # return cross_validate_address_fields(address)
        # 1. Capture the result in a variable
        validated_address = cross_validate_address_fields(address)

        # 2. Print the result (the "after" version)
        print("✅ Address after cross-validation:")
        print(validated_address)

        # 3. Finally, return the result to the caller
        return validated_address
    
    except Exception as e:
        print(f"Error in qa_validate_physician_address: {e}")
        return {"address_valid": True, "error": str(e)}
    



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
     
        form_data = form_json
        
        
        prescription = form_data.get("Information", {}).get("Prescription", {})
        submitted_address = {
            "street": (prescription.get("address") or "").strip(),
            "city": (prescription.get("city") or "").strip(),
            "state": (prescription.get("state") or "").strip(),
            "zip_code": (prescription.get("postal_code") or "").strip()
        }

        
        print("🔍 Validating physician address against NPPES...")
        print(submitted_address)

        # return cross_validate_address_fields(submitted_address)
        # 1. Capture the result in a variable
        validated_address = cross_validate_address_fields(submitted_address)

        # 2. Print the result (the "after" version)
        print("✅ Address after cross-validation:")
        print(validated_address)

        # 3. Finally, return the result to the caller
        return validated_address
        

    except Exception as e:
        print(f"Error in qa_validate_physician_address: {e}")
        return {"address_valid": True, "error": str(e)}


@tool
def qa_validate_insurance_names(form_json: Union[str, dict]) -> dict:
    """Validate insurance company names against PostgreSQL database"""
    try:
        form_data = form_json if isinstance(form_json, dict) else json.loads(form_json)

        info = form_data.get("Information", {})
        primary_ins = info.get("Primary_Insurance", {})
        secondary_ins = info.get("Secondary_Insurance", {})

        incorrect = {}

        # ------------------------
        # PRIMARY INSURANCE
        # ------------------------
        primary_name = (primary_ins.get("insurance_company_name") or "").strip()

        if primary_name:
            print(f"  🔍 Checking primary insurance: '{primary_name}'")
            result = match_insurance_in_db(primary_name)

            if result.get("success"):

                if result["match_type"] == "exact":
                    print(f"  ✅ Exact match: {primary_name}")
                    # No correction needed - exact match

                elif result["match_type"] == "fuzzy_strong":
                    # High confidence fuzzy match - add to incorrect_fields (no auto-correction)
                    print(f"  🔍 Fuzzy match found: {primary_name} → {result['official_name']} ({result['confidence']}%)")
                    incorrect["primary_insurance_company_name"] = {
                        "submitted": primary_name,
                        "expected": result["official_name"],
                        "confidence": result["confidence"],
                        "reason": "fuzzy_match_high_confidence"
                    }

                elif result["match_type"] == "fuzzy_medium":
                    # Medium confidence fuzzy match - add to incorrect_fields
                    print(f"  🔍 Fuzzy match found: {primary_name} → {result['official_name']} ({result['confidence']}%)")
                    incorrect["primary_insurance_company_name"] = {
                        "submitted": primary_name,
                        "expected": result["official_name"],
                        "confidence": result["confidence"],
                        "reason": "fuzzy_match_medium_confidence"
                    }

            else:
                # No match found or low confidence
                best_suggestion = None
                suggestions_list = result.get("suggestions", [])
                
                if suggestions_list and len(suggestions_list) > 0:
                    best_suggestion = suggestions_list[0].get("official_name")
                
                incorrect["primary_insurance_company_name"] = {
                    "submitted": primary_name,
                    "expected": best_suggestion,
                    "confidence": result.get("confidence", 0),
                    "reason": "no_match_found",
                    "suggestions": suggestions_list
                }

        # ------------------------
        # SECONDARY INSURANCE
        # ------------------------
        secondary_name = (secondary_ins.get("insurance_company_name") or "").strip()

        if secondary_name:
            print(f"  🔍 Checking secondary insurance: '{secondary_name}'")
            result = match_insurance_in_db(secondary_name)

            if result.get("success"):

                if result["match_type"] == "exact":
                    print(f"  ✅ Exact match: {secondary_name}")
                    # No correction needed - exact match

                elif result["match_type"] == "fuzzy_strong":
                    # High confidence fuzzy match - add to incorrect_fields (no auto-correction)
                    print(f"  🔍 Fuzzy match found: {secondary_name} → {result['official_name']} ({result['confidence']}%)")
                    incorrect["secondary_insurance_company_name"] = {
                        "submitted": secondary_name,
                        "expected": result["official_name"],
                        "confidence": result["confidence"],
                        "reason": "fuzzy_match_high_confidence"
                    }

                elif result["match_type"] == "fuzzy_medium":
                    # Medium confidence fuzzy match - add to incorrect_fields
                    print(f"  🔍 Fuzzy match found: {secondary_name} → {result['official_name']} ({result['confidence']}%)")
                    incorrect["secondary_insurance_company_name"] = {
                        "submitted": secondary_name,
                        "expected": result["official_name"],
                        "confidence": result["confidence"],
                        "reason": "fuzzy_match_medium_confidence"
                    }

            else:
                # No match found or low confidence
                best_suggestion = None
                suggestions_list = result.get("suggestions", [])
                
                if suggestions_list and len(suggestions_list) > 0:
                    best_suggestion = suggestions_list[0].get("official_name")
                
                incorrect["secondary_insurance_company_name"] = {
                    "submitted": secondary_name,
                    "expected": best_suggestion,
                    "confidence": result.get("confidence", 0),
                    "reason": "no_match_found",
                    "suggestions": suggestions_list
                }

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

    """
    Validate NPI number and associated physician details using NPPES registry
    with fuzzy fallback support.

    This tool performs:
    1. NPI format validation (must be 10-digit numeric)
    2. Direct lookup using NPPES API
    3. Fuzzy matching fallback using physician name + address if NPI is invalid

    Input:
        form_json (dict or str):
            Healthcare enrollment form containing:
            {
                "Information": {
                    "Prescription": {
                        "npi_number": str,
                        "physician_name": str,
                        "address": str,
                        "city": str,
                        "state": str
                    }
                }
            }

    Output:
        dict:
            {
                "incorrect_fields": {
                    "<field_name>": {
                        "submitted": str,
                        "expected": str | None,
                        "confidence": float,
                        "reason": str
                    }
                }
            }

    Notes:
        - Returns empty incorrect_fields if NPI and associated data are valid
        - Uses confidence threshold (>=65) for fuzzy match acceptance
        - Does NOT apply corrections, only suggests them (QA responsibility)
    """
    try:
        if isinstance(form_json, dict):
            form_data = form_json
        else:
            form_data = json.loads(form_json)

        presc = form_data.get("Information", {}).get("Prescription", {})
        npi = (presc.get("npi_number") or "").strip()

        incorrect = {}

        # ------------------------
        # STEP 1: FORMAT CHECK
        # ------------------------
        if not npi or len(npi) != 10 or not npi.isdigit():
            incorrect["npi_number"] = {
                "submitted": npi,
                "expected": "10 digit numeric NPI",
                "confidence": 100,
                "reason": "invalid_format"
            }
            return {"incorrect_fields": incorrect}

        # ------------------------
        # STEP 2: DIRECT LOOKUP
        # ------------------------
        nppes_data = nppes_lookup_tool(npi)

        if "error" not in nppes_data:
            # VALID → compare fields
            official_name = nppes_data.get("provider_name")

            if norm_text(presc.get("physician_name")) != norm_text(official_name):
                incorrect["physician_name"] = {
                    "submitted": presc.get("physician_name"),
                    "expected": official_name,
                    "confidence": 95,
                    "reason": "nppes_exact_mismatch"
                }

            return {"incorrect_fields": incorrect}

        # ------------------------
        # STEP 3: FUZZY FALLBACK
        # ------------------------
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
                    # incorrect["npi_number"] = {
                    #     "submitted": npi,
                    #     "expected": best.get("npi"),
                    #     "confidence": confidence,
                    #     "reason": "nppes_fuzzy_match"
                    # }
                    incorrect["npi_number"] = FieldCorrection(
                        submitted=npi,
                        expected=best.get("npi"),
                        confidence=max(0, min(confidence, 100)),
                        reason="nppes_fuzzy_match"
                    ).dict()

                    incorrect["physician_name"] = FieldCorrection(
                        submitted=presc.get("physician_name"),
                        expected=best.get("provider_name"),
                        confidence=confidence,
                        reason="nppes_fuzzy_match"
                    ).dict()

                    incorrect["physician_address"] = FieldCorrection(
                        submitted=presc.get("address"),
                        expected=best.get("address"),
                        confidence=confidence,
                        reason="nppes_fuzzy_match"
                    ).dict()

                else:
                    incorrect["npi_number"] = FieldCorrection(
                        submitted=npi,
                        expected=None,
                        confidence=confidence,
                        reason="low_confidence_fuzzy"
                    ).dict()

        return {"incorrect_fields": incorrect}

    except Exception as e:
        return {"incorrect_fields": {}, "error": str(e)}
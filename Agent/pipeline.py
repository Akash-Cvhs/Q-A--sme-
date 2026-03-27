"""
Healthcare Enrollment Form Processing Pipeline
Orchestrates Q/A validation and SME correction agents
"""

import json
import sys
import os
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import from agent modules
from qa_agent.qa_agent import validate_enrollment
from sme_agent.sme_agent import SMEAgent


def process_enrollment(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Complete enrollment form processing pipeline.
    
    Flow:
    1. QA Agent validates the form and identifies issues
    2. SME Agent applies corrections from QA output
    
    Args:
        form_data: Input enrollment form dictionary
    
    Returns:
        dict: Corrected enrollment form or error dict
    """
    print("=" * 60)
    print("ENROLLMENT FORM PROCESSING PIPELINE")
    print("=" * 60)
    
    # ============================================================
    # STEP 1: Q/A VALIDATION
    # ============================================================
    print("\nStep 1: Q/A Validation")
    print("-" * 60)
    
    try:
        qa_result = validate_enrollment(form_data)
    except Exception as e:
        print(f"\nQ/A Validation Failed: {str(e)}")
        return {
            "error": "QA_VALIDATION_FAILED",
            "message": f"Q/A validation error: {str(e)}",
            "original_form": form_data
        }
    
    # Check if QA found any issues
    has_issues = False
    if isinstance(qa_result, dict):
        missing_fields = qa_result.get("missing_fields")
        incorrect_fields = qa_result.get("incorrect_fields")
        
        if missing_fields or incorrect_fields:
            has_issues = True
            print(f"\nValidation Issues Found:")
            if missing_fields:
                total_missing = sum(len(fields) for fields in missing_fields.values())
                print(f"   - Missing fields: {total_missing}")
            if incorrect_fields:
                print(f"   - Incorrect fields: {len(incorrect_fields)}")
    
    # If no issues, return the original form
    if not has_issues:
        print("\nForm is valid - no corrections needed")
        return qa_result
    
    # ============================================================
    # STEP 2: SME CORRECTION
    # ============================================================
    print("\nStep 2: SME Correction")
    print("-" * 60)
    
    try:
        sme_agent = SMEAgent()
        corrected_form = sme_agent.run(qa_result)
    except Exception as e:
        print(f"\nSME Correction Failed: {str(e)}")
        return {
            "error": "SME_CORRECTION_FAILED",
            "message": f"SME correction error: {str(e)}",
            "qa_result": qa_result
        }
    
    # Check if SME returned an error
    if isinstance(corrected_form, dict) and "error" in corrected_form:
        print(f"\nSME Error: {corrected_form.get('message', 'Unknown error')}")
        return {
            **corrected_form,
            "qa_result": qa_result
        }
    
    # ============================================================
    # FINAL RESULT
    # ============================================================
    print("\n" + "=" * 60)
    print("PROCESSING COMPLETE")
    print("=" * 60)
    
    return corrected_form


# ============================================================
# TEST RUNNER - Only runs when called directly
# ============================================================

if __name__ == "__main__":
    # Test case with realistic data
    test_form = {
        "File_name": ["enrollment_test_001.pdf"],
        "Intent": ["Enrollment Form"],
        "Information": {
            "Patient": {
                "care_program": "LIBTAYO SURROUND",
                "first_name": "John",
                "last_name": "Smith",
                "date_of_birth": "04-12-1968",
                "phone_number": "9145551213",
                "patient_email": "john.smith@email.com",
                "street": "3745 Berry Street",
                "city": "Woodland Park",
                "state": "CO",
                "postalcode": "8063"
            },
            "Primary_Insurance": {
                "insurance_company_name": "unitdhealth",
                "group_number": "GRP100A",
                "insurance_phone": "1-800-555-2583",
                "policy_number": "BC123456789",
                "policy_holder_first_name": "John",
                "policy_holder_last_name": "Smith"
            },
            "Prescription": {
                "physician_name": "ARDALAN ENKESHAFI",
                "physician_specialty": "Medical Oncology",
                "phone_number": "443-602-6207",
                "npi_number": "1030001269",
                "hco_name": "Wrong Hospital Name",
                "address": "6410 ROCKLEDGE DR STE 304",
                "city": "Bethesda",
                "state": "CO",
                "postal_code": "20817",
                "medication_name": "LIBTAYO",
                "strength": "350-mg vial",
                "frequency": "Every 2 weeks",
                "diagnosis": "C34.01",
                "icd_10_code": "C44.01",
                "prescribed_date": "10/02/2020"
            },
            "Caregiver_Information": {
                "first_name": "Mary",
                "last_name": "Smith"
            }
        },
        "splited_file_id": [],
        "rotated_file_id": []
    }
    
    print("\nInput Form:")
    print(f"   File: {test_form['File_name'][0]}")
    print(f"   Patient: {test_form['Information']['Patient']['first_name']} {test_form['Information']['Patient']['last_name']}")
    print(f"   Physician: {test_form['Information']['Prescription']['physician_name']}")
    print(f"   NPI: {test_form['Information']['Prescription']['npi_number']}")
    print(f"   Insurance: {test_form['Information']['Primary_Insurance']['insurance_company_name']}\n")
    
    # Run the pipeline
    result = process_enrollment(test_form)
    
    # Display results
    print("\n" + "=" * 60)
    print("FINAL RESULT")
    print("=" * 60)
    
    if isinstance(result, dict) and "error" in result:
        print("\nProcessing Failed")
        print(f"   Error: {result.get('error')}")
        print(f"   Message: {result.get('message')}")
    else:
        print("\nProcessing Successful\n")
        print("Corrected Form:")
        print(json.dumps(result, indent=2))
        
        # Highlight key corrections
        if "Information" in result:
            info = result["Information"]
            
            print("\n" + "=" * 60)
            print("KEY CORRECTIONS APPLIED:")
            print("=" * 60)
            
            # Patient corrections
            patient = info.get("Patient", {})
            print(f"\nPatient:")
            print(f"   Postal Code: {patient.get('postalcode')}")
            
            # Prescription corrections
            presc = info.get("Prescription", {})
            print(f"\nPrescription:")
            print(f"   NPI: {presc.get('npi_number')}")
            print(f"   Physician: {presc.get('physician_name')}")
            print(f"   State: {presc.get('state')}")
            
            # Insurance corrections
            insurance = info.get("Primary_Insurance", {})
            print(f"\nInsurance:")
            print(f"   Company: {insurance.get('insurance_company_name')}")
            print("=" * 60)

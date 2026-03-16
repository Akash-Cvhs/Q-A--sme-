"""
Healthcare Enrollment Form Processing Pipeline
Orchestrates Q/A validation and SME correction agents
"""

import json
from typing import Dict, Any

# FIXED: Use absolute imports from agent package
from qa_gent import validate_enrollment
from sme_agent import SMEAgent

def process_enrollment(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Single function that runs Q/A validation then SME correction.
    
    Args:
        form_data: Input enrollment form dictionary
    
    Returns:
        Final corrected form from SME agent or error dict
    """
    # Step 1: Run Q/A validation
    print("=" * 60)
    print("Step 1: Q/A Validation")
    print("=" * 60)
    
    try:
        qa_result = validate_enrollment(form_data)
    except Exception as e:
        return {
            "error": "QA_VALIDATION_FAILED",
            "message": f"Q/A validation error: {str(e)}"
        }
    
    # Step 2: Pass Q/A result to SME agent
    print("\n" + "=" * 60)
    print("Step 2: SME Correction")
    print("=" * 60)
    
    # Extract the form JSON and validation results from Q/A
    if isinstance(qa_result, dict):
        if "json" in qa_result:
            # Q/A found issues - format for SME with ALL validation data
            form_json = qa_result["json"]
            incorrect_fields = qa_result.get("incorrect_fields", {})
            missing_fields = qa_result.get("missing_fields", {})
            patient_address = qa_result.get("patient_address", {})  # ← ADD THIS
            physician_address = qa_result.get("physician_address", {})  # ← ADD THIS
            
            # Create the format SME expects (MUST include address validation results)
            sme_input = {
                **form_json,  # Include all form data
                "incorrect_fields": incorrect_fields,  # Add incorrect fields from Q/A
                "missing_fields": missing_fields,  # Add missing fields from Q/A
                "patient_address": patient_address,  # ← ADD THIS - Contains ground_truth!
                "physician_address": physician_address  # ← ADD THIS
            }
            
            print(f"\n📋 Passing to SME:")
            print(f"   - Incorrect fields: {len(incorrect_fields)}")
            print(f"   - Missing fields: {len(missing_fields) if missing_fields else 0}")
            
            # DEBUG: Show address validation data being passed
            if patient_address:
                print(f"   - Patient address validation: {patient_address.get('address_valid', 'N/A')}")
                if not patient_address.get("address_valid") and not patient_address.get("skipped"):
                    incorrect_addr = patient_address.get("incorrect_fields", {})
                    ground_truth = patient_address.get("ground_truth", {})
                    print(f"     • Incorrect fields: {list(incorrect_addr.keys())}")
                    print(f"     • Ground truth available: {bool(ground_truth)}")
        else:
            # Q/A returned clean form (no issues found)
            sme_input = qa_result
    else:
        sme_input = qa_result
    
    # Run SME agent
    try:
        sme_agent = SMEAgent()
        sme_result = sme_agent.run(sme_input)
    except Exception as e:
        return {
            "error": "SME_CORRECTION_FAILED",
            "message": f"SME correction error: {str(e)}",
            "qa_result": qa_result
        }
    
    # Check if SME returned an error
    if isinstance(sme_result, dict) and "error" in sme_result:
        print("\n⚠️ SME Agent returned error:")
        print(f"   {sme_result.get('message', 'Unknown error')}")
        # Return error with Q/A result as fallback
        return {
            **sme_result,
            "qa_result": qa_result,
            "status": "VALIDATION_FAILED"
        }
    
    print("\n" + "=" * 60)
    print("Processing Complete")
    print("=" * 60)
    
    return sme_result

# ============================================================
# HARDCODED TEST DATA - Only runs when called directly
# ============================================================

if __name__ == "__main__":
    # Import with relative paths when running directly from agent folder
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    from qa_gent import validate_enrollment
    from sme_agent import SMEAgent
    
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
                "state": "MD",  # ← WRONG - should be CO
                "postalcode": "80863"
            },
            "Primary_Insurance": {
                "insurance_company_name": "BlueCross BlueShield",
                "group_number": "GRP100A",
                "insurance_phone": "1-800-555-2583",
                "policy_number": "BC123456789",
                "policy_holder_first_name": "John",
                "policy_holder_last_name": "Smith"
            },
            "Prescription": {
                "physician_name": "ARDALAN ENKESHAFI",
                "physician_specialty": "Medical Oncologist",
                "phone_number": "443-602-6207",
                "npi_number": "1773004526",
                "hco_name": "Wrong Hospital Name",
                "address": "6410 ROCKLEDGE DR STE 304",
                "city": "BETHESDA",
                "state": "MD",
                "postal_code": "208171841",
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
    
    print("=" * 60)
    print("Healthcare Enrollment Form Processing")
    print("=" * 60)
    print(f"\nProcessing: {test_form['File_name'][0]}")
    print(f"Patient: {test_form['Information']['Patient']['first_name']} {test_form['Information']['Patient']['last_name']}")
    print(f"Physician: {test_form['Information']['Prescription']['physician_name']}")
    print(f"NPI: {test_form['Information']['Prescription']['npi_number']}\n")
    
    result = process_enrollment(test_form)
    
    print("\n" + "=" * 60)
    print("FINAL RESULT")
    print("=" * 60)
    
    # Check if result is an error
    if isinstance(result, dict) and "error" in result:
        print("\n❌ Processing Failed")
        print(f"Error Type: {result.get('error')}")
        print(f"Message: {result.get('message')}")
        if "details" in result:
            print(f"\nDetails:")
            print(json.dumps(result.get('details'), indent=2))
    else:
        print("\n✅ Processing Successful")
        print("\nCorrected Form:")
        print(json.dumps(result, indent=2))
        
        # Highlight corrections
        if "Information" in result:
            info = result["Information"]
            
            print("\n" + "=" * 60)
            print("Corrections Applied:")
            print("=" * 60)
            
            # Show prescriber corrections
            if "Prescriber_Information" in info:
                presc = info["Prescriber_Information"]
                print("\n📋 Prescriber Information:")
                print(f"   NPI: {presc.get('npi_number')}")
                print(f"   Physician: {presc.get('physician_name')}")
                print(f"   Address: {presc.get('address')}")
                print(f"   City: {presc.get('city')}, {presc.get('state')} {presc.get('postal_code')}")
                if presc.get('phone_number'):
                    print(f"   Phone: {presc.get('phone_number')}")
            
            # Show patient address corrections
            if "Patient_Information" in info:
                patient = info["Patient_Information"]
                print("\n🏠 Patient Address:")
                print(f"   {patient.get('street')}")
                print(f"   {patient.get('city')}, {patient.get('state')} {patient.get('postalcode')}")
            
            # Show warnings if any
            if "validation_warnings" in result:
                print("\n⚠️  Validation Warnings:")
                for warning in result["validation_warnings"]:
                    print(f"   - {warning}")

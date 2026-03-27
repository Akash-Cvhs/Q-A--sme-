"""
Test with nested {value, confidence} format
Using John Smith data with incorrect fields (same as previous tests)
"""

import sys
import os
import json
import time

# Set quiet mode for clean output (comment out to see full logs)
# os.environ['QA_QUIET_MODE'] = '1'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline_async import process_enrollment

# John Smith form in nested {value, confidence} format
# Contains same incorrect data as previous tests:
# - Wrong postal code: 8063 (should be 80863)
# - Wrong physician state: CO (should be MD)
# - Wrong NPI: 1030001269 (should be 1003000126)
# - Wrong insurance: unitdhealth (should be UnitedHealth Group Incorporated)

test_form = {
    "File_name": ["enrollment_001.pdf"],
    "Intent": ["Enrollment Form"],
    "Information": {
        "Patient": {
            "care_program": {
                "value": "LIBTAYO SURROUND",
                "confidence": 1.0
            },
            "first_name": {
                "value": "John",
                "confidence": 1.0
            },
            "last_name": {
                "value": "Smith",
                "confidence": 1.0
            },
            "date_of_birth": {
                "value": "04-12-1968",
                "confidence": 1.0
            },
            "phone_number": {
                "value": "9145551213",
                "confidence": 0.99
            },
            "patient_email": {
                "value": "john.smith@email.com",
                "confidence": 0.95
            },
            "street": {
                "value": "3745 Berry Street",
                "confidence": 1.0
            },
            "city": {
                "value": "Woodland Park",
                "confidence": 1.0
            },
            "state": {
                "value": "CO",
                "confidence": 1.0
            },
            "postalcode": {
                "value": "8063",
                "confidence": 0.98
            }
        },
        "Primary_Insurance": {
            "insurance_company_name": {
                "value": "unitdhealth",
                "confidence": 0.85
            },
            "group_number": {
                "value": "GRP100A",
                "confidence": 1.0
            },
            "insurance_phone": {
                "value": "1-800-555-2583",
                "confidence": 1.0
            },
            "policy_number": {
                "value": "BC123456789",
                "confidence": 1.0
            },
            "policy_holder_first_name": {
                "value": "John",
                "confidence": 1.0
            },
            "policy_holder_last_name": {
                "value": "Smith",
                "confidence": 1.0
            }
        },
        "Prescription": {
            "physician_name": {
                "value": "ARDALAN ENKESHAFI",
                "confidence": 1.0
            },
            "physician_specialty": {
                "value": "Medical Oncology",
                "confidence": 1.0
            },
            "phone_number": {
                "value": "443-602-6207",
                "confidence": 1.0
            },
            "npi_number": {
                "value": "1030001269",
                "confidence": 0.95
            },
            "hco_name": {
                "value": "Wrong Hospital Name",
                "confidence": 0.80
            },
            "address": {
                "value": "6410 ROCKLEDGE DR STE 304",
                "confidence": 1.0
            },
            "city": {
                "value": "Bethesda",
                "confidence": 1.0
            },
            "state": {
                "value": "CO",
                "confidence": 0.90
            },
            "postal_code": {
                "value": "20817",
                "confidence": 1.0
            },
            "medication_name": {
                "value": "LIBTAYO",
                "confidence": 1.0
            },
            "strength": {
                "value": "350-mg vial",
                "confidence": 1.0
            },
            "frequency": {
                "value": "Every 2 weeks",
                "confidence": 0.95
            },
            "diagnosis": {
                "value": "C34.01",
                "confidence": 1.0
            },
            "icd_10_code": {
                "value": "C44.01",
                "confidence": 1.0
            },
            "prescribed_date": {
                "value": "10/02/2020",
                "confidence": 1.0
            }
        },
        "Caregiver_Information": {
            "first_name": {
                "value": "Mary",
                "confidence": 1.0
            },
            "last_name": {
                "value": "Smith",
                "confidence": 1.0
            }
        }
    },
    "splited_file_id": [],
    "rotated_file_id": [],
    "Low_Confidence_Fields": [
        {
            "section": "Patient",
            "field": "postalcode",
            "extracted_value": "8063",
            "confidence": 0.98
        },
        {
            "section": "Primary_Insurance",
            "field": "insurance_company_name",
            "extracted_value": "unitdhealth",
            "confidence": 0.85
        },
        {
            "section": "Prescription",
            "field": "npi_number",
            "extracted_value": "1030001269",
            "confidence": 0.95
        },
        {
            "section": "Prescription",
            "field": "state",
            "extracted_value": "CO",
            "confidence": 0.90
        }
    ],
    "Overall_Confidence_Score": "0.9650"
}

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("NESTED FORMAT TEST - JOHN SMITH ENROLLMENT FORM")
    print("=" * 80)
    print("\nTesting with nested {value, confidence} format")
    print("Contains intentional errors for validation:")
    print("  - Patient postal code: 8063 (incorrect)")
    print("  - Physician state: CO (incorrect)")
    print("  - NPI number: 1030001269 (incorrect)")
    print("  - Insurance: unitdhealth (incorrect)")
    print()
    
    start_time = time.time()
    
    # Process form
    result = process_enrollment(test_form)
    
    elapsed = time.time() - start_time
    
    print("\n" + "=" * 80)
    print("RESULT")
    print("=" * 80)
    
    if isinstance(result, dict):
        if "error" in result:
            print(f"\nStatus: FAILED")
            print(f"Error: {result.get('error')}")
            print(f"Message: {result.get('message')}")
        else:
            print(f"\nStatus: SUCCESS")
            
            # Show corrections applied
            print("\nCORRECTIONS APPLIED:")
            info = result.get("Information", {})
            
            patient = info.get("Patient", {})
            if isinstance(patient.get("postalcode"), dict):
                print(f"  ✓ Patient postal code: {patient['postalcode']['value']}")
            
            insurance = info.get("Primary_Insurance", {})
            if isinstance(insurance.get("insurance_company_name"), dict):
                print(f"  ✓ Insurance: {insurance['insurance_company_name']['value']}")
            elif isinstance(insurance.get("insurance_company_name"), str):
                print(f"  ✓ Insurance: {insurance['insurance_company_name']}")
            
            prescription = info.get("Prescription", {})
            if isinstance(prescription.get("state"), dict):
                print(f"  ✓ Physician state: {prescription['state']['value']}")
            elif isinstance(prescription.get("state"), str):
                print(f"  ✓ Physician state: {prescription['state']}")
                
            if isinstance(prescription.get("npi_number"), dict):
                print(f"  ✓ NPI: {prescription['npi_number']['value']}")
            elif isinstance(prescription.get("npi_number"), str):
                print(f"  ✓ NPI: {prescription['npi_number']}")
            
            print(f"\nFull Corrected Form:")
            print(json.dumps(result, indent=2))
    else:
        print(f"\nUnexpected result type: {type(result)}")
    
    print(f"\nProcessing Time: {elapsed:.2f} seconds")
    print("=" * 80)
    
    # Save result to JSON file
    if isinstance(result, dict):
        output_file = "output_nested_format.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\n✓ Result saved to: {output_file}")

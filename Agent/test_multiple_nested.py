"""
Test multiple forms in nested {value, confidence} format
Verifies async parallel processing with nested format
"""

import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline_async import process_enrollment

# Create 3 forms in nested format with different errors
forms = [
    # Form 1: John Smith - wrong postal code, state, NPI, insurance
    {
        "File_name": ["enrollment_001.pdf"],
        "Intent": ["Enrollment Form"],
        "Information": {
            "Patient": {
                "first_name": {"value": "John", "confidence": 1.0},
                "last_name": {"value": "Smith", "confidence": 1.0},
                "date_of_birth": {"value": "04-12-1968", "confidence": 1.0},
                "phone_number": {"value": "9145551213", "confidence": 0.99},
                "street": {"value": "3745 Berry Street", "confidence": 1.0},
                "city": {"value": "Woodland Park", "confidence": 1.0},
                "state": {"value": "CO", "confidence": 1.0},
                "postalcode": {"value": "8063", "confidence": 0.98}
            },
            "Primary_Insurance": {
                "insurance_company_name": {"value": "unitdhealth", "confidence": 0.85},
                "policy_number": {"value": "BC123456789", "confidence": 1.0}
            },
            "Prescription": {
                "physician_name": {"value": "ARDALAN ENKESHAFI", "confidence": 1.0},
                "npi_number": {"value": "1030001269", "confidence": 0.95},
                "address": {"value": "6410 ROCKLEDGE DR STE 304", "confidence": 1.0},
                "city": {"value": "Bethesda", "confidence": 1.0},
                "state": {"value": "CO", "confidence": 0.90},
                "postal_code": {"value": "20817", "confidence": 1.0}
            }
        },
        "splited_file_id": [],
        "rotated_file_id": []
    },
    # Form 2: Jane Doe - wrong city, insurance
    {
        "File_name": ["enrollment_002.pdf"],
        "Intent": ["Enrollment Form"],
        "Information": {
            "Patient": {
                "first_name": {"value": "Jane", "confidence": 1.0},
                "last_name": {"value": "Doe", "confidence": 1.0},
                "date_of_birth": {"value": "05-15-1975", "confidence": 1.0},
                "phone_number": {"value": "5551234567", "confidence": 1.0},
                "street": {"value": "123 Main Street", "confidence": 1.0},
                "city": {"value": "New York", "confidence": 0.95},
                "state": {"value": "NY", "confidence": 1.0},
                "postalcode": {"value": "10001", "confidence": 1.0}
            },
            "Primary_Insurance": {
                "insurance_company_name": {"value": "Aetna", "confidence": 0.88},
                "policy_number": {"value": "AET987654", "confidence": 1.0}
            },
            "Prescription": {
                "physician_name": {"value": "ARDALAN ENKESHAFI", "confidence": 1.0},
                "npi_number": {"value": "1030001269", "confidence": 0.95},
                "address": {"value": "6410 ROCKLEDGE DR STE 304", "confidence": 1.0},
                "city": {"value": "Bethesda", "confidence": 1.0},
                "state": {"value": "MD", "confidence": 1.0},
                "postal_code": {"value": "20817", "confidence": 1.0}
            }
        },
        "splited_file_id": [],
        "rotated_file_id": []
    },
    # Form 3: Bob Johnson - wrong street, insurance
    {
        "File_name": ["enrollment_003.pdf"],
        "Intent": ["Enrollment Form"],
        "Information": {
            "Patient": {
                "first_name": {"value": "Bob", "confidence": 1.0},
                "last_name": {"value": "Johnson", "confidence": 1.0},
                "date_of_birth": {"value": "08-20-1980", "confidence": 1.0},
                "phone_number": {"value": "3105551234", "confidence": 1.0},
                "street": {"value": "456 Oak Avenue", "confidence": 0.92},
                "city": {"value": "Los Angeles", "confidence": 1.0},
                "state": {"value": "CA", "confidence": 1.0},
                "postalcode": {"value": "90001", "confidence": 1.0}
            },
            "Primary_Insurance": {
                "insurance_company_name": {"value": "Blue Cross", "confidence": 0.80},
                "policy_number": {"value": "BC555666", "confidence": 1.0}
            },
            "Prescription": {
                "physician_name": {"value": "ARDALAN ENKESHAFI", "confidence": 1.0},
                "npi_number": {"value": "1030001269", "confidence": 0.95},
                "address": {"value": "6410 ROCKLEDGE DR STE 304", "confidence": 1.0},
                "city": {"value": "Bethesda", "confidence": 1.0},
                "state": {"value": "MD", "confidence": 1.0},
                "postal_code": {"value": "20817", "confidence": 1.0}
            }
        },
        "splited_file_id": [],
        "rotated_file_id": []
    }
]

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("MULTIPLE NESTED FORMAT FORMS - ASYNC PARALLEL PROCESSING TEST")
    print("=" * 80)
    print(f"\nProcessing {len(forms)} forms in nested {{value, confidence}} format")
    print("\nExpected corrections:")
    print("  Form 1 (John Smith): postal code, physician state, NPI, insurance")
    print("  Form 2 (Jane Doe): patient city, NPI, insurance")
    print("  Form 3 (Bob Johnson): patient street, NPI, insurance")
    print()
    
    start_time = time.time()
    
    # Process all forms in parallel
    results = process_enrollment(forms)
    
    elapsed = time.time() - start_time
    
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    
    success_count = 0
    failed_count = 0
    
    for i, result in enumerate(results, 1):
        print(f"\n--- Form {i} ---")
        
        if isinstance(result, dict):
            if "error" in result:
                print(f"Status: ✗ FAILED")
                print(f"Error: {result.get('error')}")
                failed_count += 1
            else:
                print(f"Status: ✓ SUCCESS")
                
                # Extract patient info
                info = result.get("Information", {})
                patient = info.get("Patient", {})
                
                # Handle nested format
                first_name = patient.get("first_name", {})
                last_name = patient.get("last_name", {})
                postalcode = patient.get("postalcode", {})
                
                if isinstance(first_name, dict):
                    first_name = first_name.get("value", "N/A")
                if isinstance(last_name, dict):
                    last_name = last_name.get("value", "N/A")
                if isinstance(postalcode, dict):
                    postalcode = postalcode.get("value", "N/A")
                
                print(f"Patient: {first_name} {last_name}")
                print(f"Postal Code: {postalcode}")
                
                # Check prescription corrections
                prescription = info.get("Prescription", {})
                npi = prescription.get("npi_number", {})
                state = prescription.get("state", {})
                
                if isinstance(npi, dict):
                    npi = npi.get("value", "N/A")
                if isinstance(state, dict):
                    state = state.get("value", "N/A")
                
                print(f"NPI: {npi}")
                print(f"Physician State: {state}")
                
                # Check insurance
                insurance = info.get("Primary_Insurance", {})
                ins_name = insurance.get("insurance_company_name", {})
                if isinstance(ins_name, dict):
                    ins_name = ins_name.get("value", "N/A")
                print(f"Insurance: {ins_name}")
                
                success_count += 1
        else:
            print(f"Status: ✗ EXCEPTION")
            print(f"Error: {str(result)}")
            failed_count += 1
    
    print("\n" + "=" * 80)
    print("FINAL STATISTICS")
    print("=" * 80)
    print(f"Total Forms: {len(forms)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {failed_count}")
    print(f"Total Time: {elapsed:.2f} seconds")
    print(f"Average per form: {elapsed/len(forms):.2f} seconds")
    print("=" * 80)
    
    # Verify format preservation
    print("\n" + "=" * 80)
    print("FORMAT VERIFICATION")
    print("=" * 80)
    
    all_nested = True
    for i, result in enumerate(results, 1):
        if isinstance(result, dict) and "error" not in result:
            info = result.get("Information", {})
            patient = info.get("Patient", {})
            first_name = patient.get("first_name", {})
            
            if isinstance(first_name, dict) and "value" in first_name:
                print(f"Form {i}: ✓ Nested format preserved")
            else:
                print(f"Form {i}: ✗ Format not preserved")
                all_nested = False
    
    if all_nested:
        print("\n✓ All forms maintained nested {value, confidence} format!")
    
    print("=" * 80)
    
    # Save results
    output_file = "output_multiple_nested.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n✓ Results saved to: {output_file}")

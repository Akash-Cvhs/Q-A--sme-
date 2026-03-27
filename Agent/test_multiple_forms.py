"""
Test for multiple forms processing
Processes multiple enrollment forms in parallel through the pipeline
Works dynamically with any number of forms (2, 3, 5, 10, etc.)
"""

import sys
import os
import json
import time

# Set quiet mode if you want clean output (comment out for full logs)
# os.environ['QA_QUIET_MODE'] = '1'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline_async import process_multiple_forms

# Test data - you can add or remove forms dynamically
test_forms = [
    # Form 1
    {
        "File_name": ["enrollment_001.pdf"],
        "Intent": ["Enrollment Form"],
        "Information": {
            "Patient": {
                "first_name": "John",
                "last_name": "Smith",
                "date_of_birth": "04-12-1968",
                "phone_number": "9145551213",
                "street": "3745 Berry Street",
                "city": "Woodland Park",
                "state": "CO",
                "postalcode": "8063"
            },
            "Primary_Insurance": {
                "insurance_company_name": "unitdhealth",
                "policy_number": "BC123456789"
            },
            "Prescription": {
                "physician_name": "ARDALAN ENKESHAFI",
                "npi_number": "1030001269",
                "address": "6410 ROCKLEDGE DR STE 304",
                "city": "Bethesda",
                "state": "CO",
                "postal_code": "20817"
            }
        },
        "splited_file_id": [],
        "rotated_file_id": []
    },
    # Form 2
    {
        "File_name": ["enrollment_002.pdf"],
        "Intent": ["Enrollment Form"],
        "Information": {
            "Patient": {
                "first_name": "Jane",
                "last_name": "Doe",
                "date_of_birth": "05-15-1975",
                "phone_number": "5551234567",
                "street": "123 Main Street",
                "city": "New York",
                "state": "NY",
                "postalcode": "10001"
            },
            "Primary_Insurance": {
                "insurance_company_name": "Aetna",
                "policy_number": "AET987654"
            },
            "Prescription": {
                "physician_name": "ARDALAN ENKESHAFI",
                "npi_number": "1030001269",
                "address": "6410 ROCKLEDGE DR STE 304",
                "city": "Bethesda",
                "state": "MD",
                "postal_code": "20817"
            }
        },
        "splited_file_id": [],
        "rotated_file_id": []
    },
    # Form 3
    {
        "File_name": ["enrollment_003.pdf"],
        "Intent": ["Enrollment Form"],
        "Information": {
            "Patient": {
                "first_name": "Bob",
                "last_name": "Johnson",
                "date_of_birth": "08-20-1980",
                "phone_number": "3105551234",
                "street": "456 Oak Avenue",
                "city": "Los Angeles",
                "state": "CA",
                "postalcode": "90001"
            },
            "Primary_Insurance": {
                "insurance_company_name": "Blue Cross",
                "policy_number": "BC555666"
            },
            "Prescription": {
                "physician_name": "ARDALAN ENKESHAFI",
                "npi_number": "1030001269",
                "address": "6410 ROCKLEDGE DR STE 304",
                "city": "Bethesda",
                "state": "MD",
                "postal_code": "20817"
            }
        },
        "splited_file_id": [],
        "rotated_file_id": []
    }
]

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print(f"MULTIPLE FORMS PROCESSING TEST - {len(test_forms)} FORMS")
    print("=" * 80)
    print(f"\nProcessing {len(test_forms)} forms in parallel...")
    
    start_time = time.time()
    
    # Process all forms in parallel
    results = process_multiple_forms(test_forms)
    
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
                print(f"Status: FAILED")
                print(f"Error: {result.get('error')}")
                failed_count += 1
            else:
                print(f"Status: SUCCESS")
                if "Information" in result:
                    patient = result["Information"].get("Patient", {})
                    print(f"Patient: {patient.get('first_name')} {patient.get('last_name')}")
                    
                    # Show corrections applied
                    prescription = result["Information"].get("Prescription", {})
                    print(f"NPI: {prescription.get('npi_number')}")
                    print(f"State: {prescription.get('state')}")
                success_count += 1
        else:
            print(f"Status: EXCEPTION")
            print(f"Error: {str(result)}")
            failed_count += 1
    
    print("\n" + "=" * 80)
    print("FINAL STATISTICS")
    print("=" * 80)
    print(f"Total Forms: {len(test_forms)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {failed_count}")
    print(f"Total Time: {elapsed:.2f} seconds")
    print(f"Average per form: {elapsed/len(test_forms):.2f} seconds")
    print("=" * 80)
    
    # Save results to file automatically
    output_file = "output_multiple_forms.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n✓ Results saved to: {output_file}")
    
    # Also save individual successful forms
    for i, result in enumerate(results, 1):
        if isinstance(result, dict) and "error" not in result:
            individual_file = f"output_form_{i}.json"
            with open(individual_file, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"✓ Form {i} saved to: {individual_file}")

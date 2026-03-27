"""
Test for single form processing
Processes one enrollment form through the pipeline
"""

import sys
import os
import json
import time

# Set quiet mode if you want clean output (comment out for full logs)
# os.environ['QA_QUIET_MODE'] = '1'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline_async import process_enrollment

# Single form test data
test_form = {
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
}

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("SINGLE FORM PROCESSING TEST")
    print("=" * 80)
    
    start_time = time.time()
    
    # Process single form
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
            print(f"\nCorrected Form:")
            print(json.dumps(result, indent=2))
    else:
        print(f"\nUnexpected result type: {type(result)}")
    
    print(f"\nProcessing Time: {elapsed:.2f} seconds")
    print("=" * 80)
    
    # Save result to JSON file
    if isinstance(result, dict) and "error" not in result:
        output_file = "output_single_form.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\n✓ Result saved to: {output_file}")
    else:
        print("\n✗ Result not saved (error occurred)")

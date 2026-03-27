"""
Healthcare Enrollment Form Processing Pipeline - Asynchronous Version
Processes multiple forms in parallel while maintaining dependencies
Supports both flat and nested {value, confidence} input formats
"""

import json
import sys
import os
import asyncio
import time
from typing import Dict, Any, List

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import from agent modules
from qa_agent.qa_agent_async import validate_enrollment_async
from sme_agent.sme_agent import SMEAgent
from qa_agent.format_converter import convert_input, convert_output


async def process_enrollment_async(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Asynchronous enrollment form processing.
    Supports both flat and nested {value, confidence} formats.
    
    Flow:
    1. Convert input format (if nested)
    2. QA Agent validates the form (async with parallel tools)
    3. SME Agent applies corrections (sync)
    4. Convert output back to original format
    
    Args:
        form_data: Input enrollment form dictionary (any format)
    
    Returns:
        dict: Corrected enrollment form in same format as input
    """
    
    # ============================================================
    # STEP 0: FORMAT CONVERSION (if needed)
    # ============================================================
    flat_form, metadata, was_nested = convert_input(form_data)
    
    # ============================================================
    # STEP 1: Q/A VALIDATION (ASYNC)
    # ============================================================
    try:
        qa_result = await validate_enrollment_async(flat_form)
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
    
    # If no issues, convert back to original format and return
    if not has_issues:
        return convert_output(qa_result, metadata, was_nested)
    
    # ============================================================
    # STEP 2: SME CORRECTION (SYNC)
    # ============================================================
    try:
        # Run SME in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        sme_agent = SMEAgent()
        corrected_form = await loop.run_in_executor(None, sme_agent.run, qa_result)
    except Exception as e:
        print(f"\nSME Correction Failed: {str(e)}")
        return {
            "error": "SME_CORRECTION_FAILED",
            "message": f"SME correction error: {str(e)}",
            "qa_result": qa_result
        }
    
    # Check if SME returned an error
    if isinstance(corrected_form, dict) and "error" in corrected_form:
        return {
            **corrected_form,
            "qa_result": qa_result
        }
    
    # ============================================================
    # STEP 3: RESTORE ORIGINAL FORMAT
    # ============================================================
    return convert_output(corrected_form, metadata, was_nested)


async def process_multiple_forms_async(forms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Process multiple enrollment forms in parallel.
    
    Args:
        forms: List of enrollment form dictionaries
    
    Returns:
        List of corrected forms or error dicts
    """
    print("=" * 60)
    print(f"PROCESSING {len(forms)} FORMS IN PARALLEL")
    print("=" * 60)
    
    start_time = time.time()
    
    # Create tasks for all forms
    tasks = [process_enrollment_async(form) for form in forms]
    
    # Execute all tasks in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    end_time = time.time()
    elapsed = end_time - start_time
    
    print("\n" + "=" * 60)
    print(f"PARALLEL PROCESSING COMPLETE")
    print(f"Total Time: {elapsed:.2f} seconds")
    print(f"Average per form: {elapsed/len(forms):.2f} seconds")
    print("=" * 60)
    
    return results


def process_enrollment(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Synchronous wrapper for single form processing.
    
    Args:
        form_data: Input enrollment form dictionary
    
    Returns:
        dict: Corrected enrollment form or error dict
    """
    return asyncio.run(process_enrollment_async(form_data))


def process_multiple_forms(forms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Synchronous wrapper for multiple form processing.
    
    Args:
        forms: List of enrollment form dictionaries
    
    Returns:
        List of corrected forms or error dicts
    """
    return asyncio.run(process_multiple_forms_async(forms))


# ============================================================
# TEST RUNNER - Demonstrates parallel processing
# ============================================================

if __name__ == "__main__":
    # Create 3 test forms with different data
    test_forms = [
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
    
    print("\n" + "=" * 60)
    print("ASYNC PIPELINE TEST - PROCESSING 3 FORMS IN PARALLEL")
    print("=" * 60)
    
    # Process all forms in parallel
    results = process_multiple_forms(test_forms)
    
    # Display results
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    
    for i, result in enumerate(results, 1):
        print(f"\nForm {i}:")
        if isinstance(result, dict):
            if "error" in result:
                print(f"  Status: FAILED")
                print(f"  Error: {result.get('error')}")
            else:
                print(f"  Status: SUCCESS")
                if "Information" in result:
                    patient = result["Information"].get("Patient", {})
                    print(f"  Patient: {patient.get('first_name')} {patient.get('last_name')}")
        else:
            print(f"  Status: EXCEPTION")
            print(f"  Error: {str(result)}")
    
    print("\n" + "=" * 60)
    print("Note: With caching, subsequent runs will be much faster!")
    print("=" * 60)

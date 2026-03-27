"""
QA Validation Agent - Asynchronous Version
Enhanced with parallel processing while preserving dependencies
"""

import asyncio
import os
from typing import Dict
from dotenv import load_dotenv

# Quiet mode helper
def qprint(*args, **kwargs):
    """Print only if not in quiet mode"""
    if not os.environ.get('QA_QUIET_MODE'):
        print(*args, **kwargs)

from .qa_tools import (
    qa_detect_missing_fields,
    qa_validate_patient_address,
    qa_validate_physician_address,
    qa_validate_insurance_names,
    qa_validate_npi_and_check_fields
)

from .schemas import (
    EnrollmentForm,
    QAValidationOutput
)

load_dotenv()


async def run_tool_async(tool, form_data: dict):
    """
    Run a synchronous tool in async context using thread pool.
    
    Args:
        tool: The tool function to run
        form_data: Form data to validate
        
    Returns:
        Tool execution result
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: tool.invoke({"form_json": form_data}))


async def validate_enrollment_async(form_data: dict) -> dict:
    """
    Asynchronous validation of healthcare enrollment form.
    
    Runs independent validations in parallel while preserving dependencies:
    - Patient address, insurance, and missing fields run in parallel
    - Physician address runs after (to correct before NPI)
    - NPI validation runs last (uses corrected physician address)
    
    Args:
        form_data: Raw enrollment form data
        
    Returns:
        dict: Validated output with missing_fields and incorrect_fields
    """
    
    # ============================================================
    # STEP 1: VALIDATE INPUT
    # ============================================================
    try:
        validated_form = EnrollmentForm(**form_data)
        qprint("Input form structure validated")
    except Exception as e:
        qprint(f"Input validation warning: {e}")
    
    qprint("=" * 60)
    qprint("Starting Q/A validation workflow (ASYNC)...")
    qprint("=" * 60)
    
    qa_results = {}
    
    try:
        # ============================================================
        # PHASE 1: Run independent validations in PARALLEL
        # ============================================================
        qprint("[PHASE 1] Running independent validations in parallel...")
        
        parallel_tasks = [
            run_tool_async(qa_detect_missing_fields, form_data),
            run_tool_async(qa_validate_patient_address, form_data),
            run_tool_async(qa_validate_insurance_names, form_data)
        ]
        
        results = await asyncio.gather(*parallel_tasks)
        
        qa_results["qa_detect_missing_fields"] = results[0]
        qa_results["qa_validate_patient_address"] = results[1]
        qa_results["qa_validate_insurance_names"] = results[2]
        
        qprint("Phase 1 complete (parallel execution)")
        
        # ============================================================
        # PHASE 2: Physician address validation (SEQUENTIAL)
        # ============================================================
        qprint("\n[PHASE 2] Validating physician address...")
        
        qa_results["qa_validate_physician_address"] = await run_tool_async(
            qa_validate_physician_address, 
            form_data
        )
        
        # Apply corrected physician address BEFORE NPI validation
        physician_addr_result = qa_results.get("qa_validate_physician_address", {})
        if not physician_addr_result.get("address_valid", True):
            corrected_fields = physician_addr_result.get("incorrect_fields", {})
            prescription = form_data.get("Information", {}).get("Prescription", {})
            
            qprint("  Applying corrected physician address for NPI validation...")
            
            if "street" in corrected_fields and corrected_fields["street"].get("expected"):
                prescription["address"] = corrected_fields["street"]["expected"]
                qprint(f"     Street: {corrected_fields['street']['expected']}")
            
            if "city" in corrected_fields and corrected_fields["city"].get("expected"):
                prescription["city"] = corrected_fields["city"]["expected"]
                qprint(f"     City: {corrected_fields['city']['expected']}")
            
            if "state" in corrected_fields and corrected_fields["state"].get("expected"):
                prescription["state"] = corrected_fields["state"]["expected"]
                qprint(f"     State: {corrected_fields['state']['expected']}")
            
            if "postalcode" in corrected_fields and corrected_fields["postalcode"].get("expected"):
                prescription["postal_code"] = corrected_fields["postalcode"]["expected"]
                qprint(f"     Postal Code: {corrected_fields['postalcode']['expected']}")
        
        qprint("Phase 2 complete")
        
        # ============================================================
        # PHASE 3: NPI validation (SEQUENTIAL - depends on Phase 2)
        # ============================================================
        qprint("\n[PHASE 3] Validating NPI with corrected address...")
        
        qa_results["qa_validate_npi_and_check_fields"] = await run_tool_async(
            qa_validate_npi_and_check_fields,
            form_data
        )
        
        qprint("Phase 3 complete")
        
    except Exception as e:
        qprint(f"Tool execution error: {e}")
        import traceback
        traceback.print_exc()
    
    qprint(f"\nQ/A tools executed: {list(qa_results.keys())}")
    
    # ============================================================
    # AGGREGATE RESULTS
    # ============================================================
    missing_fields = qa_results.get("qa_detect_missing_fields", {}).get("missing_fields", {})
    
    patient_addr_result = qa_results.get("qa_validate_patient_address", {})
    physician_addr_result = qa_results.get("qa_validate_physician_address", {})
    insurance_result = qa_results.get("qa_validate_insurance_names", {})
    npi_result = qa_results.get("qa_validate_npi_and_check_fields", {})
    
    # Build single incorrect_fields dictionary
    incorrect_fields = {}

    # 1. NPI validation results
    incorrect_fields.update(npi_result.get("incorrect_fields", {}))

    # 2. Patient address validation results
    patient_incorrect = patient_addr_result.get("incorrect_fields", {})
    if patient_incorrect:
        for field, details in patient_incorrect.items():
            incorrect_fields[f"patient_{field}"] = details

    # 3. Physician address validation results
    physician_incorrect = physician_addr_result.get("incorrect_fields", {})
    if physician_incorrect:
        for field, details in physician_incorrect.items():
            incorrect_fields[f"physician_{field}"] = details

    # 4. Insurance validation results
    incorrect_fields.update(insurance_result.get("incorrect_fields", {}))

    # ============================================================
    # BUILD FINAL OUTPUT
    # ============================================================
    output_dict = {
        "form_data": form_data,
        "missing_fields": missing_fields if missing_fields else None,
        "incorrect_fields": incorrect_fields if incorrect_fields else None
    }
    
    # ============================================================
    # VALIDATE OUTPUT STRUCTURE
    # ============================================================
    try:
        validated_output = QAValidationOutput(**output_dict)
        qprint("Output structure validated")
        output = validated_output.model_dump(exclude_none=False)
    except Exception as e:
        qprint(f"Output validation error: {e}")
        output = output_dict
    
    if not output["missing_fields"] and not output["incorrect_fields"]:
        return output["form_data"]
    
    return output


# Synchronous wrapper for backward compatibility
def validate_enrollment(form_data: dict) -> dict:
    """
    Synchronous wrapper for async validation.
    Uses asyncio.run() to execute async function.
    """
    return asyncio.run(validate_enrollment_async(form_data))

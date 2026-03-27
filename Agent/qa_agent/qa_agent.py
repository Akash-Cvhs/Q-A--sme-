"""
QA Validation Agent - Enhanced with Cross-Field Address Validation
"""

from dotenv import load_dotenv
from typing import Dict

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

# ============================================================
# MAIN VALIDATION FUNCTION
# ============================================================

def validate_enrollment(form_data: dict) -> dict:
    """
    Validate healthcare enrollment form (no auto-correction)
    Calls all Q/A tools directly without LangGraph
    
    IMPORTANT: Physician address validation runs BEFORE NPI validation.
    The corrected physician address is applied to form_data before NPI lookup
    to ensure accurate fuzzy matching in the NPPES registry.
    
    Args:
        form_data (dict): Raw enrollment form data
        
    Returns:
        dict: Validated output with missing_fields and incorrect_fields
        
    Raises:
        ValidationError: If output structure doesn't match QAValidationOutput schema
    """
    
    # ============================================================
    # STEP 1: VALIDATE INPUT (Optional but recommended)
    # ============================================================
    try:
        # Validate input structure (will raise ValidationError if invalid)
        validated_form = EnrollmentForm(**form_data)
        print("✓ Input form structure validated")
    except Exception as e:
        print(f"⚠️ Input validation warning: {e}")
        # Continue anyway - validation is informational
    
    
    print("=" * 60)
    print("Starting Q/A validation workflow...")
    print("=" * 60)
    
    # Execute all tools directly
    qa_results = {}
    
    try:
        # Tool 1: Detect missing fields
        print("  🔧 Executing tool: qa_detect_missing_fields")
        qa_results["qa_detect_missing_fields"] = qa_detect_missing_fields.invoke({"form_json": form_data})
        
        # Tool 2: Validate patient address
        print("  🔧 Executing tool: qa_validate_patient_address")
        qa_results["qa_validate_patient_address"] = qa_validate_patient_address.invoke({"form_json": form_data})
        
        
        # Tool 3: Validate physician address
        print("  🔧 Executing tool: qa_validate_physician_address")
        qa_results["qa_validate_physician_address"] = qa_validate_physician_address.invoke({"form_json": form_data})
        
        # 🔥 CRITICAL: Apply corrected physician address BEFORE NPI validation
        physician_addr_result = qa_results.get("qa_validate_physician_address", {})
        if not physician_addr_result.get("address_valid", True):
            corrected_fields = physician_addr_result.get("incorrect_fields", {})
            prescription = form_data.get("Information", {}).get("Prescription", {})
            
            print("  🔄 Applying corrected physician address for NPI validation...")
            
            # Update form_data with corrected address
            if "street" in corrected_fields and corrected_fields["street"].get("expected"):
                prescription["address"] = corrected_fields["street"]["expected"]
                print(f"     ✓ Street: {corrected_fields['street']['expected']}")
            
            if "city" in corrected_fields and corrected_fields["city"].get("expected"):
                prescription["city"] = corrected_fields["city"]["expected"]
                print(f"     ✓ City: {corrected_fields['city']['expected']}")
            
            if "state" in corrected_fields and corrected_fields["state"].get("expected"):
                prescription["state"] = corrected_fields["state"]["expected"]
                print(f"     ✓ State: {corrected_fields['state']['expected']}")
            
            if "postalcode" in corrected_fields and corrected_fields["postalcode"].get("expected"):
                prescription["postal_code"] = corrected_fields["postalcode"]["expected"]
                print(f"     ✓ Postal Code: {corrected_fields['postalcode']['expected']}")

        # Tool 4: Validate insurance names
        print("  🔧 Executing tool: qa_validate_insurance_names")
        qa_results["qa_validate_insurance_names"] = qa_validate_insurance_names.invoke({"form_json": form_data})
        
        # Tool 5: Validate NPI (now using corrected physician address)
        print("  🔧 Executing tool: qa_validate_npi_and_check_fields")
        qa_results["qa_validate_npi_and_check_fields"] = qa_validate_npi_and_check_fields.invoke({"form_json": form_data})
        
        
    except Exception as e:
        print(f"⚠️ Tool execution error: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n✅ Q/A tools executed: {list(qa_results.keys())}")
    
    # ============================================================
    # AGGREGATE RESULTS - Single Source of Truth
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
    # BUILD FINAL OUTPUT - Clean Structure
    # ============================================================
    output_dict = {
        "form_data": form_data,
        "missing_fields": missing_fields if missing_fields else None,
        "incorrect_fields": incorrect_fields if incorrect_fields else None
    }
    
    # ============================================================
    # STEP 3: VALIDATE OUTPUT STRUCTURE
    # ============================================================
    try:
        # Validate output matches expected schema
        validated_output = QAValidationOutput(**output_dict)
        print("Output structure validated")
        
        # Convert back to dict for return (maintains compatibility)
        output = validated_output.model_dump(exclude_none=False)
    except Exception as e:
        print(f"Output validation error: {e}")
        # Return unvalidated output if validation fails
        output = output_dict
    
  
    
    if not output["missing_fields"] and not output["incorrect_fields"]:
        return output["form_data"]
    
    return output

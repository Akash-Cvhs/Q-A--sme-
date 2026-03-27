"""
SME (Subject Matter Expert) Engine
====================================
Applies corrections from QA validation output to the enrollment form.

Takes QA output with incorrect_fields and applies the 'expected' values
back to the original form data.
"""

import copy


class SMEAgent:
    """
    SME Agent that applies QA corrections to enrollment forms.
    
    Handles field corrections from QA validation output including:
    - Patient address corrections (patient_*)
    - Physician address corrections (physician_*)
    - NPI and physician details
    - Insurance company names
    """
    
    # QA field prefix → form path mapping
    FIELD_MAPPING = {
        # Patient fields
        "patient_street": "Information.Patient.street",
        "patient_city": "Information.Patient.city",
        "patient_state": "Information.Patient.state",
        "patient_postalcode": "Information.Patient.postalcode",
        
        # Physician fields
        "physician_street": "Information.Prescription.address",
        "physician_city": "Information.Prescription.city",
        "physician_state": "Information.Prescription.state",
        "physician_postalcode": "Information.Prescription.postal_code",
        
        # NPI and physician details
        "npi_number": "Information.Prescription.npi_number",
        "physician_name": "Information.Prescription.physician_name",
        "physician_address": "Information.Prescription.address",
        
        # Insurance
        "primary_insurance_company_name": "Information.Primary_Insurance.insurance_company_name",
        "secondary_insurance_company_name": "Information.Secondary_Insurance.insurance_company_name",
    }
    
    def __init__(self):
        """Initialize SME Agent"""
        pass
    
    def _get_nested(self, data: dict, path: str):
        """Get value from nested dict using dot notation path"""
        keys = path.split(".")
        current = data
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
        return current
    
    def _set_nested(self, data: dict, path: str, value) -> bool:
        """Set value in nested dict using dot notation path"""
        keys = path.split(".")
        current = data
        
        # Navigate to parent
        for key in keys[:-1]:
            if not isinstance(current, dict):
                return False
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # Set final value
        if isinstance(current, dict):
            current[keys[-1]] = value
            return True
        return False
    
    def _apply_correction(self, form_data: dict, field_key: str, correction: dict) -> bool:
        """
        Apply a single correction to the form data.
        
        Args:
            form_data: The enrollment form dictionary
            field_key: The QA field key (e.g., "patient_postalcode")
            correction: The correction dict with 'expected' value
            
        Returns:
            bool: True if correction was applied, False otherwise
        """
        expected = correction.get("expected")
        
        # Skip if no expected value
        if expected is None:
            print(f"  ⚠️  Skipping {field_key}: No expected value")
            return False
        
        # Get the form path for this field
        form_path = self.FIELD_MAPPING.get(field_key)
        
        if not form_path:
            print(f"  ⚠️  Skipping {field_key}: No mapping defined")
            return False
        
        # Get current value
        current_value = self._get_nested(form_data, form_path)
        
        # Apply correction
        if self._set_nested(form_data, form_path, expected):
            submitted = correction.get("submitted", current_value)
            print(f"  ✓ {field_key}: '{submitted}' → '{expected}'")
            return True
        else:
            print(f"  ✗ Failed to apply {field_key}")
            return False
    
    def run(self, qa_output: dict) -> dict:
        """
        Apply QA corrections to the enrollment form.
        
        Args:
            qa_output: QA validation output containing:
                - form_data: Original form data
                - incorrect_fields: Dict of field corrections
                - missing_fields: Dict of missing fields (not corrected)
        
        Returns:
            dict: Corrected enrollment form
        """
        print("\n" + "=" * 60)
        print("SME Agent: Applying Corrections")
        print("=" * 60)
        
        # Extract data from QA output
        form_data = qa_output.get("form_data")
        incorrect_fields = qa_output.get("incorrect_fields", {})
        
        if not form_data:
            print("❌ Error: No form_data in QA output")
            return {
                "error": "INVALID_QA_OUTPUT",
                "message": "QA output missing 'form_data' key"
            }
        
        # Create a deep copy to avoid modifying original
        corrected_form = copy.deepcopy(form_data)
        
        if not incorrect_fields:
            print("\n✓ No corrections needed - form is valid")
            return corrected_form
        
        print(f"\n📋 Applying {len(incorrect_fields)} corrections...\n")
        
        # Apply each correction
        applied_count = 0
        skipped_count = 0
        
        for field_key, correction in incorrect_fields.items():
            if self._apply_correction(corrected_form, field_key, correction):
                applied_count += 1
            else:
                skipped_count += 1
        
        # Summary
        print("\n" + "-" * 60)
        print(f"✅ Applied: {applied_count} corrections")
        if skipped_count > 0:
            print(f"⚠️  Skipped: {skipped_count} corrections")
        print("-" * 60)
        
        return corrected_form


# Backward compatibility: Keep the function interface
def run_sme(qa_output: dict, qa_input: dict = None) -> dict:
    """
    Legacy function interface for backward compatibility.
    
    Args:
        qa_output: QA validation output
        qa_input: Original form (optional, ignored if form_data in qa_output)
    
    Returns:
        dict: Corrected enrollment form
    """
    agent = SMEAgent()
    
    # If qa_input provided and no form_data in qa_output, use qa_input
    if qa_input and "form_data" not in qa_output:
        qa_output = {**qa_output, "form_data": qa_input}
    
    return agent.run(qa_output)
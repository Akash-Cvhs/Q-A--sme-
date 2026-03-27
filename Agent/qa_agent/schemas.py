"""
Pydantic Schemas for QA Validation Agent
Provides type safety, validation, and clear data structures
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List


# ============================================================
# CORE VALIDATION SCHEMAS
# ============================================================

class FieldCorrection(BaseModel):
    """
    Standard structure for reporting incorrect fields
    Used across all validation tools (NPI, Address, Insurance)
    """
    submitted: Optional[str] = None
    expected: Optional[str] = None
    confidence: float = Field(ge=0, le=100, description="Confidence score 0-100")
    reason: str = Field(description="Explanation of why field is incorrect")
    suggestions: Optional[List[Dict[str, Any]]] = None  # For insurance no-match scenarios
    
    class Config:
        json_schema_extra = {
            "example": {
                "submitted": "unitdhealth",
                "expected": "UnitedHealth Group Incorporated",
                "confidence": 65.8,
                "reason": "fuzzy_match_high_confidence"
            }
        }


# ============================================================
# TOOL RESPONSE SCHEMAS
# ============================================================

class MissingFieldsResponse(BaseModel):
    """Response from qa_detect_missing_fields tool"""
    missing_fields: Dict[str, List[str]] = Field(default_factory=dict)
    error: Optional[str] = None


class AddressValidationResponse(BaseModel):
    """Response from address validation tools (patient/physician)"""
    address_valid: bool
    incorrect_fields: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    error: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "address_valid": False,
                "incorrect_fields": {
                    "postalcode": {
                        "submitted": "8063",
                        "expected": "80863",
                        "reason": "zip_not_inferred"
                    }
                }
            }
        }


class InsuranceValidationResponse(BaseModel):
    """Response from qa_validate_insurance_names tool"""
    valid: bool
    incorrect_fields: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    error: Optional[str] = None


class NPIValidationResponse(BaseModel):
    """Response from qa_validate_npi_and_check_fields tool"""
    incorrect_fields: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    error: Optional[str] = None


# ============================================================
# INPUT FORM SCHEMAS (for validation)
# ============================================================

class PatientInfo(BaseModel):
    """Patient information section of enrollment form"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    phone_number: Optional[str] = None
    patient_email: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postalcode: Optional[str] = None
    care_program: Optional[str] = None
    
    class Config:
        extra = "allow"  # Allow additional fields not defined


class PrescriptionInfo(BaseModel):
    """Prescription/Physician information section"""
    npi_number: Optional[str] = None
    physician_name: Optional[str] = None
    physician_specialty: Optional[str] = None
    phone_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    medication_name: Optional[str] = None
    diagnosis: Optional[str] = None
    hco_name: Optional[str] = None
    
    class Config:
        extra = "allow"


class InsuranceInfo(BaseModel):
    """Insurance information (primary/secondary)"""
    insurance_company_name: Optional[str] = None
    policy_number: Optional[str] = None
    group_number: Optional[str] = None
    insurance_phone: Optional[str] = None
    policy_holder_first_name: Optional[str] = None
    policy_holder_last_name: Optional[str] = None
    
    class Config:
        extra = "allow"


class EnrollmentFormInformation(BaseModel):
    """Information section of enrollment form"""
    Patient: Optional[PatientInfo] = None
    Prescription: Optional[PrescriptionInfo] = None
    Primary_Insurance: Optional[InsuranceInfo] = None
    Secondary_Insurance: Optional[InsuranceInfo] = None
    Caregiver_Information: Optional[Dict[str, Any]] = None
    HCP_Consent: Optional[Dict[str, Any]] = None
    Patient_Consent: Optional[Dict[str, Any]] = None
    
    class Config:
        extra = "allow"


class EnrollmentForm(BaseModel):
    """Complete enrollment form structure"""
    File_name: Optional[List[str]] = None
    Intent: Optional[List[str]] = None
    Information: Optional[EnrollmentFormInformation] = None
    splited_file_id: Optional[List[Any]] = Field(default_factory=list)
    rotated_file_id: Optional[List[Any]] = Field(default_factory=list)
    
    class Config:
        extra = "allow"


# ============================================================
# FINAL OUTPUT SCHEMA
# ============================================================

class QAValidationOutput(BaseModel):
    """
    Final output from validate_enrollment function
    Single source of truth for QA validation results
    """
    form_data: Dict[str, Any] = Field(description="Original form data (potentially with corrections)")
    missing_fields: Optional[Dict[str, List[str]]] = Field(
        None, 
        description="Fields that are required but missing"
    )
    incorrect_fields: Optional[Dict[str, Dict[str, Any]]] = Field(
        None,
        description="Fields that are incorrect with submitted/expected values"
    )
    
    @validator('incorrect_fields')
    def validate_incorrect_fields_structure(cls, v):
        """Ensure all incorrect fields have required keys"""
        if v:
            for field_name, field_data in v.items():
                if not isinstance(field_data, dict):
                    raise ValueError(f"Field {field_name} must be a dictionary")
                if 'submitted' not in field_data:
                    raise ValueError(f"Field {field_name} missing 'submitted' key")
                if 'reason' not in field_data:
                    raise ValueError(f"Field {field_name} missing 'reason' key")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "form_data": {"File_name": ["test.pdf"], "Information": {}},
                "missing_fields": {
                    "Patient": ["first_name", "last_name"]
                },
                "incorrect_fields": {
                    "patient_postalcode": {
                        "submitted": "8063",
                        "expected": "80863",
                        "confidence": 85,
                        "reason": "zip_not_inferred"
                    },
                    "primary_insurance_company_name": {
                        "submitted": "unitdhealth",
                        "expected": "UnitedHealth Group Incorporated",
                        "confidence": 65.8,
                        "reason": "fuzzy_match_high_confidence"
                    }
                }
            }
        }


# ============================================================
# LEGACY SCHEMAS (kept for backward compatibility)
# ============================================================

class AddressValidation(BaseModel):
    """Legacy schema - consider migrating to AddressValidationResponse"""
    address_valid: bool
    incorrect_fields: Dict[str, FieldCorrection]
    ground_truth: Dict[str, Any]
    confidence: float = Field(ge=0, le=100)
    anchor_used: str
    manual_review_required: bool
    skipped: bool


class QAResponse(BaseModel):
    """Legacy schema - consider migrating to QAValidationOutput"""
    incorrect_fields: Dict[str, FieldCorrection]
    missing_fields: Optional[Dict[str, Any]] = None
    patient_address: Optional[AddressValidation] = None
    physician_address: Optional[AddressValidation] = None
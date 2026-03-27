import json
from qa_agent import validate_enrollment

# ------------------------------------------------------------
# SAMPLE TEST INPUT (Updated with test_form data)
# ------------------------------------------------------------

test_payload = {
    "File_name": ["enrollment_test_001.pdf"],
    "Intent": ["Enrollment Form"],
    "Information": {
        "Patient": {
            "care_program": "LIBTAYO SURROUND",
            "first_name": "",
            "last_name": "",
            "date_of_birth": "04-12-1968",
            "phone_number": "",
            "patient_email": "john.smith@email.com",
            "street": "3745 Berry Street",
            "city": "Woodland Park",
            "state": "CO",  # ← WRONG - should be CO
            "postalcode": "8063"
        },
        "Primary_Insurance": {
            "insurance_company_name": "unitdhealth",
            "group_number": "GRP100A",
            "insurance_phone": "1-800-555-2583",
            "policy_number": "BC123456789",
            "policy_holder_first_name": "John",
            "policy_holder_last_name": "Smith"
        },
        "Prescription": {
            "physician_name": "ARDALAN ENKESHAFI",
            "physician_specialty": "Medical Oncology",
            "phone_number": "443-602-6207",
            "npi_number": "1030001269",
            "hco_name": "Wrong Hospital Name",
            "address": "6410 ROCKLEDGE DR STE 304",
            "city": "Bethesda",
            "state": "CO",
            "postal_code": "20817",
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

# ------------------------------------------------------------
# RUN TEST
# ------------------------------------------------------------

if __name__ == "__main__":
    print("\n🚀 Running QA Validation Test (Enrollment Form)...\n")

    # Passing the new test_payload to your validation function
    result = validate_enrollment(test_payload)

    print("\n" + "=" * 60)
    print("📊 FINAL OUTPUT")
    print("=" * 60)

    print(json.dumps(result, indent=2))

# import json
# from sme_agent import SMEAgent, build_final_output

# # ------------------------------------------------------------
# # SAMPLE INPUT (USE YOUR QA OUTPUT HERE)
# # ------------------------------------------------------------

# qa_output = {
#     "Information": {
#         "Patient": {
#             "first_name": "John",
#             "last_name": "Doe",
#             "date_of_birth": "1990-05-15",
#             "phone_number": "1234567890",
#             "street": "123 Fake St",
#             "city": "New Yrok",  # typo
#             "state": "NY",
#             "postalcode": "1234"  # invalid ZIP
#         },
#         "Prescription": {
#             "npi_number": "1234567890",  # invalid
#             "physician_name": "Dr Smith",
#             "medication_name": "Drug A",
#             "diagnosis": "Condition X",
#             "address": "456 Medical Rd",
#             "city": "Boston",
#             "state": "MA",
#             "postal_code": "02115"
#         },
#         "Primary_Insurance": {
#             "insurance_company_name": "Fake Insurance Co",
#             "policy_number": "POL123"
#         },
#         "Secondary_Insurance": {
#             "insurance_company_name": "Another Fake Insurance"
#         },
#         "HCP_Consent": {},
#         "Patient_Consent": {}
#     },

#     # 👇 These come from QA agent (IMPORTANT)
#     "incorrect_fields": {
#         "primary_insurance_company_name": {
#             "submitted": "Fake Insurance Co"
#         }
#     },
#     "patient_address": {
#         "address_valid": False,
#         "confidence": 80,
#         "incorrect_fields": {
#             "city": {
#                 "submitted": "New Yrok",
#                 "expected": "New York",
#                 "reason": "Corrected by Google"
#             },
#             "postalcode": {
#                 "submitted": "1234",
#                 "expected": "12345",
#                 "reason": "Invalid ZIP"
#             }
#         },
#         "ground_truth": {
#             "city": "New York",
#             "postalcode": "12345"
#         }
#     },
#     "physician_address": {
#         "address_valid": True
#     }
# }

# # ------------------------------------------------------------
# # RUN SME TEST
# # ------------------------------------------------------------

# if __name__ == "__main__":
#     print("\n🚀 Running SME Agent Test...\n")

#     try:
#         sme = SMEAgent()

#         # Step 1: Run SME correction
#         sme_output = sme.run(qa_output)

#         # Step 2: Normalize final structure
#         final_output = build_final_output(sme_output)

#         print("\n" + "=" * 60)
#         print("📊 FINAL SME OUTPUT")
#         print("=" * 60)

#         print(json.dumps(final_output, indent=2))

#     except Exception as e:
#         print(f"\n❌ ERROR running SME test: {e}")
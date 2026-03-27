import json
from helpers import cross_validate_address_fields

# ------------------------
# TEST CASES
# ------------------------
test_cases = [
    {
        "name": "✅ Perfect Address",
        "input": {
            "street": "1600 Amphitheatre Parkway",
            "city": "Mountain View",
            "state": "my",
            "zip_code": "94043"
        }
    },
    {
        "name": "❌ Street Typo (Fuzzy Fix)",
        "input": {
            "street": "1600 Amphi Pkwy",
            "city": "Mountain View",
            "state": "CA",
            "zip_code": "94043"
        }
    },
    {
        "name": "❌ City Typo",
        "input": {
            "street": "1600 Amphitheatre Parkway",
            "city": "Mtn View",
            "state": "CA",
            "zip_code": "94043"
        }
    },
    {
        "name": "⚠️ Partial ZIP (Your Current Bug Case)",
        "input": {
            "street": "3745 Berry Street",
            "city": "Woodland Park",
            "state": "CO",
            "zip_code": "8086"
        }
    },
    {
        "name": "❌ Invalid ZIP (Alpha)",
        "input": {
            "street": "1600 Amphitheatre Parkway",
            "city": "Mountain View",
            "state": "CA",
            "zip_code": "94AB3"
        }
    },
    {
        "name": "❌ Wrong ZIP",
        "input": {
            "street": "1600 Amphitheatre Parkway",
            "city": "Mountain View",
            "state": "CA",
            "zip_code": "12345"
        }
    },
    {
        "name": "⚠️ Missing ZIP",
        "input": {
            "street": "1600 Amphitheatre Parkway",
            "city": "Mountain View",
            "state": "CA",
            "zip_code": ""
        }
    },
    {
        "name": "💥 Garbage Input",
        "input": {
            "street": "xyz 123 unknown",
            "city": "abc",
            "state": "ZZ",
            "zip_code": "00000"
        }
    }
]

# ------------------------
# RUN TESTS
# ------------------------
for case in test_cases:
    print("\n" + "=" * 70)
    print(f"🧪 TEST: {case['name']}")
    print("=" * 70)

    result = cross_validate_address_fields(case["input"])

    print("\n📥 INPUT:")
    print(json.dumps(case["input"], indent=2))

    print("\n📤 OUTPUT:")
    print(json.dumps(result, indent=2))

    
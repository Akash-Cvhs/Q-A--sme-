# View cache stats
cd Agent/qa_agent
python cache_stats.py stats

# Clear cache
python cache_stats.py clear

# Cleanup expired entries
python cache_stats.py cleanup


process_multiple_forms_async([Form1, Form2, Form3])
│
├─ Form 1 (async) ──────────────────────────┐
│  ├─ PHASE 1 (parallel)                    │
│  │  ├─ Patient Address ──┐                │
│  │  ├─ Insurance ────────┼─→ Parallel     │
│  │  └─ Missing Fields ───┘                │
│  ├─ PHASE 2 (sequential)                  │
│  │  └─ Physician Address                  │
│  └─ PHASE 3 (sequential)                  │
│     └─ NPI Validation                     │
│                                            │
├─ Form 2 (async) ──────────────────────────┼─→ All forms parallel
│  ├─ PHASE 1 (parallel)                    │
│  │  ├─ Patient Address ──┐                │
│  │  ├─ Insurance ────────┼─→ Parallel     │
│  │  └─ Missing Fields ───┘                │
│  ├─ PHASE 2 (sequential)                  │
│  │  └─ Physician Address                  │
│  └─ PHASE 3 (sequential)                  │
│     └─ NPI Validation                     │
│                                            │
└─ Form 3 (async) ──────────────────────────┘
   ├─ PHASE 1 (parallel)
   │  ├─ Patient Address ──┐
   │  ├─ Insurance ────────┼─→ Parallel
   │  └─ Missing Fields ───┘
   ├─ PHASE 2 (sequential)
   │  └─ Physician Address
   └─ PHASE 3 (sequential)
      └─ NPI Validation

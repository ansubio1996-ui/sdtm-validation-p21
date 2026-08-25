# SDTM Validation Toolkit (Pinnacle 21-style)

A Python-based validation toolkit for CDISC SDTM-formatted clinical trial datasets. Inspired by Pinnacle 21 Community, this tool performs automated SDTM compliance checks and generates interactive HTML + CSV issue reports.

## Features

- **Required Variable Check** — verifies all mandatory SDTM variables are present per domain (DM, AE, LB, PD, DS, SV, MH)
- **Non-Null Check** — flags null/empty values on key fields
- **Date Format Validation** — ensures all `\*DTC` fields follow ISO 8601 (`YYYY-MM-DD`)
- **Referential Integrity** — confirms every `USUBJID` in child domains exists in DM
- **Sequence Integrity** — detects duplicate SEQ values per subject
- **AE Business Rules** — validates severity codes, date logic (end ≥ start), and SAE outcome completeness
- **LB Reference Range Check** — flags lab values outside `LBSTNRLO`–`LBSTNRHI`
- **DM Business Rules** — age plausibility, controlled terminology for RACE

## Project Structure

```
sdtm-validation-p21/
├── data/                  # Synthetic SDTM demo datasets (CSV)
│   ├── dm.csv             # Demographics
│   ├── ae.csv             # Adverse Events
│   ├── lb.csv             # Laboratory
│   ├── pd.csv             # Protocol Deviations
│   ├── ds.csv             # Disposition
│   ├── sv.csv             # Subject Visits
│   └── mh.csv             # Medical History
├── src/
│   └── sdtm_validator.py  # Main validation engine
├── results/               # Generated reports (HTML + CSV)
├── tests/
│   └── test_validator.py  # Unit tests
├── requirements.txt
└── README.md
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run validation
python src/sdtm_validator.py --data-dir data/ --output-dir results/

# View the HTML report
open results/validation_report.html
```

## Sample Output

```
=== Running SDTM Validation Checks ===

  Loaded DM: 120 records
  Loaded AE: 187 records
  Loaded LB: 5760 records
  ...
  Running: Required Variables...
  Running: Non-Null Checks...
  Running: Date Format Checks...
  ...

============================================================
VALIDATION SUMMARY
============================================================
  Total issues found: 12
  High severity:   2
  Medium severity: 5
  Low severity:    5
============================================================
```

## Validation Rules

| Rule ID | Domain | Description | Severity |
|---|---|---|---|
| MISSING_REQUIRED_VAR | All | Required SDTM variable not present | HIGH |
| NULL_VALUE | All | Key variable has null/empty values | MEDIUM |
| INVALID_DATE_FORMAT | All | Date field not in ISO 8601 format | MEDIUM |
| REFERENTIAL_INTEGRITY | All | USUBJID not found in DM domain | HIGH |
| DUPLICATE_SEQUENCE | AE/LB/PD/DS/MH | SEQ not unique per subject | MEDIUM |
| INVALID_SEVERITY | AE | AESEV not in {MILD, MODERATE, SEVERE} | HIGH |
| DATE_LOGIC | AE | AE end date before start date | HIGH |
| MISSING_SAE_OUTCOME | AE | SAE record missing AEOUT | HIGH |
| ABNORMAL_VALUES | LB | Lab value outside reference range | LOW |
| INVALID_AGE | DM | Age outside plausible range (18-100) | MEDIUM |
| INVALID_RACE | DM | RACE not in CDISC controlled terminology | LOW |

## Demo Data

All datasets in `data/` are **100% synthetic** and do not represent any real clinical trial or patient data. They are generated for portfolio demonstration purposes.

## Tech Stack

- Python 3.9+
- pandas
- argparse (CLI)

## Author

**Ansuman Mohapatra** — Clinical Data Specialist | 6+ years CDM experience
- LinkedIn: [ansuman-mohapatra9b663116](https://linkedin.com/in/ansuman-mohapatra9b663116)
- Email: ansubio1996@gmail.com

## License

MIT License — feel free to use for learning and portfolio purposes.

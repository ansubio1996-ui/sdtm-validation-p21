"""
SDTM Dataset Validator — Pinnacle 21-style validation toolkit.

Performs automated checks on CDISC SDTM-formatted clinical trial datasets:
  - Required variable presence
  - Missing / null values on key fields
  - Date format & sequence integrity
  - Cross-domain referential integrity (USUBJID)
  - Domain-specific business rules (AE severity, LB reference ranges, etc.)
  - Generates an HTML + CSV issue report

Usage:
    python src/sdtm_validator.py --data-dir data/ --output-dir results/
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


# ──────────────────────────────────────────────
# Validation rule definitions
# ──────────────────────────────────────────────

REQUIRED_VARS = {
    "DM": ["STUDYID", "DOMAIN", "USUBJID", "SUBJID", "AGE", "SEX", "ARM"],
    "AE": ["STUDYID", "DOMAIN", "USUBJID", "AESEQ", "AETERM", "AESEV", "AESTDTC"],
    "LB": ["STUDYID", "DOMAIN", "USUBJID", "LBSEQ", "LBTEST", "LBORRES", "LBDTC"],
    "PD": ["STUDYID", "DOMAIN", "USUBJID", "PDSEQ", "PDTERM", "PDDTC"],
    "DS": ["STUDYID", "DOMAIN", "USUBJID", "DSSEQ", "DSTERM", "DSDECOD"],
    "SV": ["STUDYID", "DOMAIN", "USUBJID", "VISITNUM", "VISIT", "SVSTDTC"],
    "MH": ["STUDYID", "DOMAIN", "USUBJID", "MHSEQ", "MHTERM"],
}

NON_NULL_VARS = {
    "DM": ["USUBJID", "AGE", "SEX", "ARM"],
    "AE": ["USUBJID", "AESEQ", "AETERM", "AESEV", "AESTDTC"],
    "LB": ["USUBJID", "LBSEQ", "LBTEST", "LBORRES", "LBDTC"],
    "PD": ["USUBJID", "PDSEQ", "PDTERM", "PDDTC"],
    "DS": ["USUBJID", "DSSEQ", "DSTERM", "DSDECOD"],
    "SV": ["USUBJID", "VISITNUM", "VISIT", "SVSTDTC"],
    "MH": ["USUBJID", "MHSEQ", "MHTERM"],
}

VALID_SEVERITY = {"MILD", "MODERATE", "SEVERE"}
VALID_AE_OUTCOME = {
    "RECOVERED/RESOLVED",
    "RECOVERING/RESOLVING",
    "NOT RECOVERED/NOT RESOLVED",
    "RECOVERED/RESOLVED WITH SEQUELAE",
    "FATAL",
}
VALID_RACES = {
    "WHITE",
    "BLACK OR AFRICAN AMERICAN",
    "ASIAN",
    "AMERICAN INDIAN OR ALASKA NATIVE",
    "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER",
    "MULTIPLE",
    "OTHER",
    "UNKNOWN",
}


class SDTMValidator:
    """Runs validation checks on SDTM datasets and collects issues."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.issues = []
        self.datasets = {}
        self.stats = {}

    # ── loading ──────────────────────────────
    def load_datasets(self):
        """Load all SDTM CSV files from the data directory."""
        domain_files = {
            "DM": "dm.csv", "AE": "ae.csv", "LB": "lb.csv",
            "PD": "pd.csv", "DS": "ds.csv", "SV": "sv.csv", "MH": "mh.csv",
        }
        for domain, fname in domain_files.items():
            fpath = self.data_dir / fname
            if fpath.exists():
                self.datasets[domain] = pd.read_csv(fpath)
                self.stats[domain] = len(self.datasets[domain])
                print(f"  Loaded {domain}: {len(self.datasets[domain])} records")
            else:
                self._add_issue("GLOBAL", fname, "MISSING_DATASET",
                                f"Dataset file {fname} not found", severity="HIGH")

    # ── individual checks ────────────────────
    def check_required_variables(self):
        """Check 1 — Required SDTM variables are present."""
        for domain, df in self.datasets.items():
            required = REQUIRED_VARS.get(domain, [])
            missing = [v for v in required if v not in df.columns]
            if missing:
                self._add_issue(domain, "ALL", "MISSING_REQUIRED_VAR",
                                f"Missing required variables: {', '.join(missing)}",
                                severity="HIGH")

    def check_non_null(self):
        """Check 2 — Key variables must not be null/empty."""
        for domain, df in self.datasets.items():
            non_null = NON_NULL_VARS.get(domain, [])
            for var in non_null:
                if var in df.columns:
                    null_mask = df[var].isna() | (df[var].astype(str).str.strip() == "")
                    null_count = null_mask.sum()
                    if null_count > 0:
                        self._add_issue(domain, var, "NULL_VALUE",
                                        f"{null_count} null/empty values in {var}",
                                        severity="MEDIUM",
                                        affected_records=int(null_count))

    def check_date_formats(self):
        """Check 3 — Date fields should be valid ISO 8601 (YYYY-MM-DD)."""
        date_cols = {
            "DM": ["RFSTDTC", "RFENDTC", "DMDTC"],
            "AE": ["AESTDTC", "AEENDTC"],
            "LB": ["LBDTC"],
            "PD": ["PDDTC"],
            "DS": ["DSDTC"],
            "SV": ["SVSTDTC", "SVENDTC"],
            "MH": ["MHSTDTC", "MHDTC"],
        }
        for domain, cols in date_cols.items():
            df = self.datasets.get(domain)
            if df is None:
                continue
            for col in cols:
                if col not in df.columns:
                    continue
                for idx, val in df[col].items():
                    if pd.isna(val) or str(val).strip() == "":
                        continue
                    try:
                        datetime.strptime(str(val), "%Y-%m-%d")
                    except (ValueError, TypeError):
                        self._add_issue(domain, col, "INVALID_DATE_FORMAT",
                                        f"Invalid date '{val}' at row {idx + 2}",
                                        severity="MEDIUM", affected_records=1)

    def check_referential_integrity(self):
        """Check 4 — USUBJID in all domains must exist in DM."""
        dm = self.datasets.get("DM")
        if dm is None:
            return
        dm_subjects = set(dm["USUBJID"].unique())
        for domain, df in self.datasets.items():
            if domain == "DM" or "USUBJID" not in df.columns:
                continue
            orphans = df[~df["USUBJID"].isin(dm_subjects)]
            if len(orphans) > 0:
                self._add_issue(domain, "USUBJID", "REFERENTIAL_INTEGRITY",
                                f"{len(orphans)} records have USUBJID not in DM",
                                severity="HIGH", affected_records=len(orphans))

    def check_sequence_integrity(self):
        """Check 5 — SEQ variables should be unique per subject."""
        seq_map = {"AE": "AESEQ", "LB": "LBSEQ", "PD": "PDSEQ", "DS": "DSSEQ", "MH": "MHSEQ"}
        for domain, seq_col in seq_map.items():
            df = self.datasets.get(domain)
            if df is None or seq_col not in df.columns:
                continue
            dupes = df.duplicated(subset=["USUBJID", seq_col], keep=False)
            if dupes.sum() > 0:
                self._add_issue(domain, seq_col, "DUPLICATE_SEQUENCE",
                                f"{dupes.sum()} duplicate sequence numbers found",
                                severity="MEDIUM", affected_records=int(dupes.sum()))

    def check_ae_business_rules(self):
        """Check 6 — AE domain business rules."""
        ae = self.datasets.get("AE")
        if ae is None:
            return

        # 6a — Severity must be valid
        if "AESEV" in ae.columns:
            invalid_sev = ae[~ae["AESEV"].isin(VALID_SEVERITY)]
            if len(invalid_sev) > 0:
                self._add_issue("AE", "AESEV", "INVALID_SEVERITY",
                                f"{len(invalid_sev)} records with invalid AESEV value",
                                severity="HIGH", affected_records=len(invalid_sev))

        # 6b — End date must be >= start date
        if "AESTDTC" in ae.columns and "AEENDTC" in ae.columns:
            ae_dated = ae[(ae["AESTDTC"].notna()) & (ae["AEENDTC"].notna()) &
                          (ae["AESTDTC"].astype(str).str.strip() != "") &
                          (ae["AEENDTC"].astype(str).str.strip() != "")].copy()
            ae_dated["AESTDTC"] = pd.to_datetime(ae_dated["AESTDTC"], errors="coerce")
            ae_dated["AEENDTC"] = pd.to_datetime(ae_dated["AEENDTC"], errors="coerce")
            bad_dates = ae_dated[ae_dated["AEENDTC"] < ae_dated["AESTDTC"]]
            if len(bad_dates) > 0:
                self._add_issue("AE", "AEENDTC", "DATE_LOGIC",
                                f"{len(bad_dates)} AE records where end date < start date",
                                severity="HIGH", affected_records=len(bad_dates))

        # 6c — Serious AEs should have valid outcome
        if "AESER" in ae.columns and "AEOUT" in ae.columns:
            sae = ae[ae["AESER"] == "Y"]
            sae_no_outcome = sae[sae["AEOUT"].isna() | (sae["AEOUT"].astype(str).str.strip() == "")]
            if len(sae_no_outcome) > 0:
                self._add_issue("AE", "AEOUT", "MISSING_SAE_OUTCOME",
                                f"{len(sae_no_outcome)} SAE records missing outcome",
                                severity="HIGH", affected_records=len(sae_no_outcome))

    def check_lb_reference_ranges(self):
        """Check 7 — LB values should be within reference range (flag abnormals)."""
        lb = self.datasets.get("LB")
        if lb is None:
            return
        if not all(c in lb.columns for c in ["LBSTRESC", "LBSTNRLO", "LBSTNRHI"]):
            return

        abnormals = 0
        for idx, row in lb.iterrows():
            try:
                val = float(row["LBSTRESC"])
                lo = float(row["LBSTNRLO"])
                hi = float(row["LBSTNRHI"])
                if val < lo or val > hi:
                    abnormals += 1
            except (ValueError, TypeError):
                continue

        if abnormals > 0:
            self._add_issue("LB", "LBSTRESC", "ABNORMAL_VALUES",
                            f"{abnormals} lab values outside reference range",
                            severity="LOW", affected_records=abnormals)

    def check_dm_business_rules(self):
        """Check 8 — DM domain business rules."""
        dm = self.datasets.get("DM")
        if dm is None:
            return

        # 8a — Age within plausible range
        if "AGE" in dm.columns:
            bad_age = dm[(dm["AGE"] < 18) | (dm["AGE"] > 100)]
            if len(bad_age) > 0:
                self._add_issue("DM", "AGE", "INVALID_AGE",
                                f"{len(bad_age)} subjects with age outside 18-100",
                                severity="MEDIUM", affected_records=len(bad_age))

        # 8b — Race should be from controlled terminology
        if "RACE" in dm.columns:
            invalid_race = dm[~dm["RACE"].isin(VALID_RACES)]
            if len(invalid_race) > 0:
                self._add_issue("DM", "RACE", "INVALID_RACE",
                                f"{len(invalid_race)} subjects with invalid RACE value",
                                severity="LOW", affected_records=len(invalid_race))

    # ── helpers ──────────────────────────────
    def _add_issue(self, domain, variable, rule_id, message, severity="MEDIUM",
                   affected_records=0):
        self.issues.append({
            "DOMAIN": domain,
            "VARIABLE": variable,
            "RULE_ID": rule_id,
            "SEVERITY": severity,
            "MESSAGE": message,
            "AFFECTED_RECORDS": affected_records,
        })

    # ── run all checks ───────────────────────
    def run_all_checks(self):
        """Execute all validation checks in sequence."""
        print("\n=== Running SDTM Validation Checks ===\n")
        checks = [
            ("Required Variables", self.check_required_variables),
            ("Non-Null Checks", self.check_non_null),
            ("Date Format Checks", self.check_date_formats),
            ("Referential Integrity", self.check_referential_integrity),
            ("Sequence Integrity", self.check_sequence_integrity),
            ("AE Business Rules", self.check_ae_business_rules),
            ("LB Reference Ranges", self.check_lb_reference_ranges),
            ("DM Business Rules", self.check_dm_business_rules),
        ]
        for name, func in checks:
            print(f"  Running: {name}...")
            func()

    # ── reporting ────────────────────────────
    def generate_csv_report(self, output_dir: str):
        """Write issues to CSV."""
        os.makedirs(output_dir, exist_ok=True)
        issues_df = pd.DataFrame(self.issues)
        report_path = os.path.join(output_dir, "validation_issues.csv")
        issues_df.to_csv(report_path, index=False)
        print(f"\n  CSV report saved: {report_path}")
        return report_path

    def generate_html_report(self, output_dir: str):
        """Generate a styled HTML validation report."""
        os.makedirs(output_dir, exist_ok=True)

        high = sum(1 for i in self.issues if i["SEVERITY"] == "HIGH")
        medium = sum(1 for i in self.issues if i["SEVERITY"] == "MEDIUM")
        low = sum(1 for i in self.issues if i["SEVERITY"] == "LOW")

        rows_html = ""
        for issue in self.issues:
            sev_class = issue["SEVERITY"].lower()
            rows_html += f"""
            <tr class="{sev_class}">
                <td>{issue['DOMAIN']}</td>
                <td>{issue['VARIABLE']}</td>
                <td>{issue['RULE_ID']}</td>
                <td><span class="badge {sev_class}">{issue['SEVERITY']}</span></td>
                <td>{issue['MESSAGE']}</td>
                <td>{issue['AFFECTED_RECORDS']}</td>
            </tr>"""

        stats_rows = ""
        for domain, count in self.stats.items():
            stats_rows += f"<tr><td>{domain}</td><td>{count}</td></tr>"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SDTM Validation Report</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; background: #f5f7fa; color: #333; }}
  h1 {{ color: #1a3a5c; border-bottom: 3px solid #1a3a5c; padding-bottom: 10px; }}
  h2 {{ color: #2c5282; margin-top: 30px; }}
  .summary {{ display: flex; gap: 20px; margin: 20px 0; }}
  .card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); flex: 1; text-align: center; }}
  .card .num {{ font-size: 2em; font-weight: bold; }}
  .card.high .num {{ color: #e53e3e; }}
  .card.medium .num {{ color: #dd6b20; }}
  .card.low .num {{ color: #38a169; }}
  table {{ border-collapse: collapse; width: 100%; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
  th {{ background: #1a3a5c; color: white; padding: 12px; text-align: left; }}
  td {{ padding: 10px; border-bottom: 1px solid #e2e8f0; }}
  tr.high {{ background: #fff5f5; }}
  tr.medium {{ background: #fffaf0; }}
  tr.low {{ background: #f0fff4; }}
  .badge {{ padding: 3px 10px; border-radius: 12px; font-size: 0.85em; font-weight: bold; }}
  .badge.high {{ background: #fed7d7; color: #c53030; }}
  .badge.medium {{ background: #feebc8; color: #c05621; }}
  .badge.low {{ background: #c6f6d5; color: #276749; }}
  .footer {{ margin-top: 30px; color: #999; font-size: 0.85em; }}
</style>
</head>
<body>
<h1>SDTM Validation Report</h1>
<p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>

<div class="summary">
  <div class="card high"><div class="num">{high}</div><div>High Severity</div></div>
  <div class="card medium"><div class="num">{medium}</div><div>Medium Severity</div></div>
  <div class="card low"><div class="num">{low}</div><div>Low Severity</div></div>
</div>

<h2>Dataset Statistics</h2>
<table>
<tr><th>Domain</th><th>Records</th></tr>
{stats_rows}
</table>

<h2>Validation Issues ({len(self.issues)} total)</h2>
<table>
<tr><th>Domain</th><th>Variable</th><th>Rule ID</th><th>Severity</th><th>Message</th><th>Affected Records</th></tr>
{rows_html}
</table>

<div class="footer">
  SDTM Validation Toolkit | Demo data for portfolio showcase | Based on CDISC SDTMIG standards
</div>
</body>
</html>"""
        report_path = os.path.join(output_dir, "validation_report.html")
        with open(report_path, "w") as f:
            f.write(html)
        print(f"  HTML report saved: {report_path}")
        return report_path

    def print_summary(self):
        """Print a console summary."""
        print(f"\n{'='*60}")
        print(f"VALIDATION SUMMARY")
        print(f"{'='*60}")
        print(f"  Total issues found: {len(self.issues)}")
        high = [i for i in self.issues if i["SEVERITY"] == "HIGH"]
        medium = [i for i in self.issues if i["SEVERITY"] == "MEDIUM"]
        low = [i for i in self.issues if i["SEVERITY"] == "LOW"]
        print(f"  High severity:   {len(high)}")
        print(f"  Medium severity: {len(medium)}")
        print(f"  Low severity:    {len(low)}")
        if high:
            print(f"\n  HIGH severity issues:")
            for issue in high:
                print(f"    [{issue['DOMAIN']}] {issue['MESSAGE']}")
        print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="SDTM Dataset Validator")
    parser.add_argument("--data-dir", default="data/", help="Path to SDTM CSV files")
    parser.add_argument("--output-dir", default="results/", help="Output directory for reports")
    args = parser.parse_args()

    validator = SDTMValidator(args.data_dir)
    validator.load_datasets()
    validator.run_all_checks()
    validator.print_summary()
    validator.generate_csv_report(args.output_dir)
    validator.generate_html_report(args.output_dir)
    print("\nValidation complete. Check results/ directory for reports.\n")


if __name__ == "__main__":
    main()

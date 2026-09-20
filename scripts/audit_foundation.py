"""Run the full foundation consistency audit and print a pass/fail report.

Usage: python scripts/audit_foundation.py
Exit code 0 = all checks pass; 1 = at least one problem.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS
from src.foundation_audit import run_all


def main() -> int:
    results = run_all(SETTINGS.kb_path, SETTINGS.vocabulary_path, SETTINGS.queries_seed_path)
    failed = False
    for check, problems in results.items():
        status = "PASS" if not problems else f"FAIL ({len(problems)})"
        print(f"{check:24s} {status}")
        for p in problems:
            failed = True
            print(f"    - {p}")
    print("\nRESULT:", "ALL CHECKS PASS" if not failed else "PROBLEMS FOUND")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

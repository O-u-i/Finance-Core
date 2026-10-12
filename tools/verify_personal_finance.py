"""Run synthetic, deterministic accounting acceptance without opening a production Vault."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--basetemp', type=Path, required=True, help='A fresh directory inside this repository .tmp; never an existing run.')
    args = parser.parse_args()
    temporary = args.basetemp.resolve()
    if (ROOT / '.tmp').resolve() not in temporary.parents or temporary.exists():
        parser.error('Use a new, non-existing repository-local .tmp child; pytest may clean its base directory.')
    # No provider, bank, broker, market, production connection or source-data input.
    command = [sys.executable, '-X', 'utf8', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
               'backend/tests/test_personal_finance.py', 'backend/tests/test_personal_finance_temporal.py',
               'backend/tests/test_personal_finance_integrity.py',
               'backend/tests/test_recorded_balances.py',
               '--basetemp=' + str(temporary)]
    return subprocess.call(command, cwd=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())

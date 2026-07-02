#!/usr/bin/env python3
"""Standalone independent constraint audit for a result JSON.

Usage:  python tools/audit.py result.json

Recomputes every constraint from the reported geometry (see
``post_opt.audit``) without reusing optimizer internals, and reports PASS/FAIL.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from post_opt.audit import audit_file  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    return 0 if audit_file(sys.argv[1]) else 2


if __name__ == "__main__":
    raise SystemExit(main())

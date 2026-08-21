#!/usr/bin/env python3
"""Lance toute la suite de tests.

    python3 run_tests.py            tous les tests
    python3 run_tests.py -v         mode detaille
    python3 run_tests.py risk       uniquement les tests de money management
"""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(ROOT, "tests")
sys.path.insert(0, ROOT)
sys.path.insert(0, TESTS)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    verbosity = 2 if "-v" in sys.argv or "--verbose" in sys.argv else 1

    pattern = f"test_{args[0]}.py" if args else "test_*.py"
    suite = unittest.defaultTestLoader.discover(TESTS, pattern=pattern)

    # Les logs des modules pollueraient la sortie des tests.
    import logging
    logging.disable(logging.CRITICAL)

    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())

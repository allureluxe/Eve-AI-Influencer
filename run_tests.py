#!/usr/bin/env python3
"""Lance toute la suite de tests.

    python3 run_tests.py            tous les tests
    python3 run_tests.py -v         mode detaille
    python3 run_tests.py risk       uniquement les tests de money management
"""
from __future__ import annotations

import os
import pathlib
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(ROOT, "tests")
sys.path.insert(0, ROOT)
sys.path.insert(0, TESTS)


def fichiers_ignores_par_unittest() -> list[str]:
    """Fichiers de test qu'`unittest` ne sait pas executer.

    `unittest` ne decouvre que les classes heritant de TestCase. Les tests
    ecrits en style pytest — classes simples, fixtures `tmp_path`,
    `pytest.approx` — sont donc ignores EN SILENCE. Un lanceur qui saute
    la moitie de la suite sans le dire est pire que pas de lanceur du
    tout : il donne une confiance que rien ne justifie.
    """
    ignores = []
    for chemin in sorted(pathlib.Path(TESTS).glob("test_*.py")):
        texte = chemin.read_text(encoding="utf-8", errors="replace")
        # Le critere qui compte est l'absence de TestCase : sans elle,
        # unittest charge le module et n'y collecte aucun test. Se fier a
        # la presence de « import pytest » raterait les fichiers qui
        # n'utilisent que des assertions simples.
        if "TestCase" not in texte:
            ignores.append(chemin.name)
    return ignores


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    verbosity = 2 if "-v" in sys.argv or "--verbose" in sys.argv else 1

    # Les logs des modules pollueraient la sortie des tests.
    import logging
    logging.disable(logging.CRITICAL)

    # pytest execute TOUTE la suite ; unittest n'en execute qu'une partie.
    # On le prefere donc des qu'il est disponible.
    try:
        import pytest  # noqa: F401
    except ImportError:
        pass
    else:
        cible = os.path.join(TESTS, f"test_{args[0]}.py") if args else TESTS
        return pytest.main([cible, "-q" if verbosity == 1 else "-v"])

    pattern = f"test_{args[0]}.py" if args else "test_*.py"
    suite = unittest.defaultTestLoader.discover(TESTS, pattern=pattern)
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)

    ignores = fichiers_ignores_par_unittest()
    if ignores:
        print()
        print("=" * 68)
        print("ATTENTION : pytest est absent, une partie de la suite n'a PAS")
        print("ete executee. Fichiers ignores en silence par unittest :")
        for nom in ignores:
            print(f"    {nom}")
        print()
        print("    pip3 install pytest      puis relancer")
        print("=" * 68)
        return 1 if result.wasSuccessful() else 1

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())

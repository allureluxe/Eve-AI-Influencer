#!/usr/bin/env python3
"""Démarrage en une commande :  python3 demarrer.py

Installe ce qu'il faut, vérifie l'environnement, puis lance l'agent.
Volontairement sans dépendance : ce fichier doit tourner sur une machine
où rien n'est encore installé.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OK, KO, WARN = "✅", "❌", "⚠️ "


def etape(n: int, titre: str) -> None:
    print(f"\n{'─' * 58}\n  ÉTAPE {n} · {titre}\n{'─' * 58}")


def dependances_presentes() -> list[str]:
    """Modules indispensables réellement importables."""
    import importlib.util

    requis = {"requests": "requests", "yaml": "PyYAML", "PIL": "Pillow"}
    return [paquet for module, paquet in requis.items()
            if importlib.util.find_spec(module) is None]


def installer_dependances() -> bool:
    etape(1, "Installation des dépendances Python")
    resultat = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")],
        capture_output=True, text=True)

    if resultat.returncode == 0:
        print(f"{OK} Dépendances installées.")
        return True

    # pip peut échouer alors que tout est déjà présent (paquets système,
    # environnement géré). On tranche sur ce qui est réellement importable.
    manquants = dependances_presentes()
    if not manquants:
        print(f"{WARN}pip a signalé une erreur, mais tout le nécessaire est déjà présent.")
        return True

    print(f"{KO} Modules manquants : {', '.join(manquants)}")
    print((resultat.stderr or resultat.stdout).strip()[-400:])
    print("\n   À essayer, dans l'ordre :")
    print("     pip install -r requirements.txt")
    print("     pip install --user -r requirements.txt")
    print("     python3 -m venv .venv && source .venv/bin/activate && "
          "pip install -r requirements.txt")
    return False


def verifier_ffmpeg() -> None:
    etape(2, "Vérification de ffmpeg (montage vidéo)")
    if shutil.which("ffmpeg"):
        print(f"{OK} ffmpeg est installé.")
        return
    commandes = {
        "linux": "sudo apt install ffmpeg",
        "darwin": "brew install ffmpeg",
        "win32": "winget install Gyan.FFmpeg",
    }
    cmd = commandes.get(sys.platform, commandes["linux"])
    print(f"{WARN}ffmpeg est absent : les vidéos ne seront pas montées.")
    print(f"   Installe-le avec :  {cmd}")
    print("   (les images, la voix et les sous-titres seront produits quand même)")


def lancer_agent() -> int:
    etape(3, "Lancement de l'agent")
    return subprocess.run([sys.executable, "-m", "eve.cli", "go"], cwd=ROOT).returncode


def main() -> int:
    print("""
╔══════════════════════════════════════════════════════════╗
║   EVE — coach sportive virtuelle, TikTok & Instagram     ║
║   Démarrage automatique. Rien ne sera publié.            ║
╚══════════════════════════════════════════════════════════╝""")
    if sys.version_info < (3, 10):
        print(f"{KO} Python 3.10 ou plus récent est requis "
              f"(tu utilises {sys.version.split()[0]}).")
        return 1
    if not installer_dependances():
        return 1
    verifier_ffmpeg()
    return lancer_agent()


if __name__ == "__main__":
    sys.exit(main())

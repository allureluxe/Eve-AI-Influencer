"""Le chien de garde doit couper le service qui trade VRAIMENT.

LE 1ER OCTOBRE 2026, en reliant le VPS : `robot-dual-live` etait arrete
depuis le 27 septembre, et c'etait `robot-trading` (run_bot.py +
robot.bitvavo.json) qui passait les ordres reels. Le chien de garde, lui,
ne connaissait que `robot-dual-live` : sous le plancher, il aurait coupe
un service deja mort et laisse trader l'autre.

Le meme jour : les alertes du robot reel (`is_demo=false`) arrivaient
dans `alluxe_bot_alertes` sous compte="demo", parce que le canal prenait
"demo" par defaut et que run_bot.py ne precise rien.
"""
from __future__ import annotations

import subprocess

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

import ops.chien_de_garde as garde
from gold_bot.notifiers import AlluxeBotChannel


class _Resultat:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


class TestLeChienDeGardeCouvreLeServiceQuiTrade:

    def test_robot_trading_est_surveille(self):
        assert "robot-trading" in garde.SERVICES
        assert "robot-dual-live" in garde.SERVICES

    def test_sous_le_plancher_il_coupe_chaque_service_actif(self, monkeypatch, tmp_path):
        arrets = []

        def faux_run(cmd, **_):
            if cmd[:2] == ["systemctl", "is-active"]:
                return _Resultat("active\n" if cmd[2] == "robot-trading" else "inactive\n")
            if cmd[:4] == ["sudo", "-n", "systemctl", "stop"]:
                arrets.append(cmd[4])
                return _Resultat()
            raise AssertionError(f"commande inattendue : {cmd}")

        monkeypatch.setattr(subprocess, "run", faux_run)
        monkeypatch.setattr(garde, "TEMOIN", str(tmp_path / "temoin"))
        monkeypatch.setattr(garde, "JOURNAL", str(tmp_path / "journal.log"))
        monkeypatch.setattr(garde, "REFERENCE", str(tmp_path / "ref.json"))
        monkeypatch.setattr(garde, "_lire_equite", lambda: 100.0)
        monkeypatch.setattr(garde, "_reference", lambda equite: 1000.0)
        monkeypatch.setattr(garde, "CONFIRMATION_S", 0)
        monkeypatch.setattr(garde.sys, "argv", ["chien_de_garde.py"])

        assert garde.main() == 0
        assert arrets == ["robot-trading"], (
            "le service qui trade n'a pas ete coupe")
        assert (tmp_path / "temoin").exists()

    def test_une_lecture_fausse_isolee_ne_coupe_rien(self, monkeypatch, tmp_path):
        """4 oct. : une lecture a 1,07 EUR pendant un retrait a coupe le
        robot et l'a laisse sans chien de garde 5 jours. La 2e lecture,
        normale, doit annuler la coupure."""
        arrets, lectures = [], iter([1.07, 493.0])

        def faux_run(cmd, **_):
            if cmd[:2] == ["systemctl", "is-active"]:
                return _Resultat("active\n" if cmd[2] == "robot-trading" else "inactive\n")
            if cmd[:4] == ["sudo", "-n", "systemctl", "stop"]:
                arrets.append(cmd[4])
                return _Resultat()
            raise AssertionError(f"commande inattendue : {cmd}")

        monkeypatch.setattr(subprocess, "run", faux_run)
        monkeypatch.setattr(garde, "TEMOIN", str(tmp_path / "temoin"))
        monkeypatch.setattr(garde, "JOURNAL", str(tmp_path / "journal.log"))
        monkeypatch.setattr(garde, "REFERENCE", str(tmp_path / "ref.json"))
        monkeypatch.setattr(garde, "_lire_equite", lambda: next(lectures))
        monkeypatch.setattr(garde, "_reference", lambda equite: 493.0)
        monkeypatch.setattr(garde, "CONFIRMATION_S", 0)
        monkeypatch.setattr(garde.sys, "argv", ["chien_de_garde.py"])

        assert garde.main() == 0
        assert arrets == [], "une lecture fausse isolee a coupe le robot"
        assert not (tmp_path / "temoin").exists()


class TestLesAlertesDuReelSontRangeesSousReel:

    def test_le_robot_reel_publie_sous_reel(self):
        assert AlluxeBotChannel().compte == "reel"

    def test_une_simulation_reste_sous_demo(self):
        assert AlluxeBotChannel(est_demo=True).compte == "demo"

    def test_un_compte_explicite_l_emporte(self):
        assert AlluxeBotChannel(est_demo=True, compte="demo2").compte == "demo2"

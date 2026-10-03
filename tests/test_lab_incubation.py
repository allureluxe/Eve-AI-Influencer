"""Une strategie en INCUBATION est reexaminee chaque semaine (3 oct. 2026).

Avant, rien ne la reprenait : bon backtest, forward trop court, et elle
attendait pour toujours alors que la periode recente avance chaque jour.
"""
import json
import time

from helpers import *  # noqa: F401,F403 - insere le chemin du projet

from gold_bot import lab


def _labo(tmp_path, monkeypatch, lignes):
    livre = tmp_path / "lab-book.jsonl"
    livre.write_text("\n".join(json.dumps(l) for l in lignes) + "\n")
    monkeypatch.setattr(lab, "LAB_BOOK", livre)
    l = object.__new__(lab.StrategyLab)
    l.state = {}
    return l


def _r(id_, stage, age_jours):
    return {"id": id_, "stage": stage, "created_at": time.time() - age_jours * 86400,
            "params": {"name": id_}}


def test_une_incubation_de_plus_de_7_jours_est_reprise(tmp_path, monkeypatch):
    l = _labo(tmp_path, monkeypatch, [_r("a", "INCUBATION", 8), _r("b", "ARCHIVED-WEAK", 30)])
    assert l._incubation_a_revoir()["id"] == "a"


def test_une_incubation_recente_attend(tmp_path, monkeypatch):
    l = _labo(tmp_path, monkeypatch, [_r("a", "INCUBATION", 2)])
    assert l._incubation_a_revoir() is None


def test_seul_le_dernier_etat_compte(tmp_path, monkeypatch):
    l = _labo(tmp_path, monkeypatch, [_r("a", "INCUBATION", 9), _r("a", "VALIDATED", 1)])
    assert l._incubation_a_revoir() is None


def test_une_incubation_revue_n_est_pas_reprise_avant_7_jours(tmp_path, monkeypatch):
    l = _labo(tmp_path, monkeypatch, [_r("a", "INCUBATION", 30)])
    l.state["incubations_revues"] = {"a": time.time() - 86400}
    assert l._incubation_a_revoir() is None

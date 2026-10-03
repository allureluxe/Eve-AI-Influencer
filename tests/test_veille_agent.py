"""La veille de l'agent previent sans rien modifier (decision du 3 oct. 2026)."""
import sys
from pathlib import Path

from helpers import *  # noqa: F401,F403 - insere le chemin du projet

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops"))
import veille_agent as va  # noqa: E402

T = 1_790_000_000.0
NOM = {"NOMUSD": {"volume": 14709.0, "stop_loss": 0.0021311}}


def _ctl(etat=None, actif=lambda s: True, bids=None, mem=4000, disque=40, lab=T, deja=None):
    return va.controler(etat or {"last_cycle": T}, T, actif, bids or {}, mem, disque, lab, deja or set())


def test_tout_va_bien_aucune_alerte():
    assert _ctl()[0] == []


def test_robot_reel_arrete_est_critique():
    alertes, _ = _ctl(actif=lambda s: s != "robot-trading")
    assert [a.cle for a in alertes] == ["reel-arrete"] and alertes[0].niveau == "critical"


def test_robot_fige():
    alertes, _ = _ctl(etat={"last_cycle": T - 3600})
    assert alertes[0].cle == "reel-fige"


def test_sous_le_stop_seulement_au_deuxieme_controle():
    etat = {"last_cycle": T, "position_meta": NOM}
    bids = {"NOM-EUR": 0.00204}
    a1, vus = _ctl(etat=etat, bids=bids)
    assert a1 == [] and vus == {"NOM"}
    a2, _ = _ctl(etat=etat, bids=bids, deja=vus)
    assert a2 and a2[0].niveau == "critical" and "NOM" in a2[0].corps


def test_memoire_disque_lab():
    cles = {a.cle for a in _ctl(mem=300, disque=90, lab=T - 7 * 3600)[0]}
    assert cles == {"memoire", "disque", "lab-bloque"}


def test_une_alerte_n_est_repetee_qu_apres_6h(monkeypatch):
    recus = []
    v = va.Veille(recus.append)
    monkeypatch.setattr(va, "controler", lambda *a, **k: ([va.Alerte("x", "warning", "t", "c")], set()))
    monkeypatch.setattr(va, "_bids", lambda: {})
    v.passer(); v.passer()
    assert len(recus) == 1


def test_sauvegarde_en_retard():
    alertes, _ = va.controler({"last_cycle": T}, T, lambda s: True, {}, 4000, 40, T, set(),
                              sauvegarde_maj=T - 40 * 3600)
    assert [a.cle for a in alertes] == ["sauvegarde"]

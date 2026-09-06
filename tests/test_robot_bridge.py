"""Le pont robot → récit : les chiffres viennent du fichier, jamais d'ailleurs."""
import json
import time

import pytest

from eve.content import robot_bridge as pont
from eve.content.story import load_journal


def _trades(tmp_path, profits, depart_jours=9):
    base = time.time() - depart_jours * 86400
    chemin = tmp_path / "trades.jsonl"
    chemin.write_text("\n".join(
        json.dumps({"closed_at": base + i * 86400, "profit": p, "symbol": "BTC-EUR"})
        for i, p in enumerate(profits)), encoding="utf-8")
    return chemin


def test_sans_fichier_aucun_journal(tmp_path):
    assert pont.lire_trades(tmp_path / "absent.jsonl") == []
    assert pont.journal_depuis_robot(100, tmp_path / "absent.jsonl") is None


def test_le_solde_suit_les_profits_reels(tmp_path):
    journal = pont.journal_depuis_robot(100, _trades(tmp_path, [1.2, -0.8, 2.6]))
    assert journal.solde_actuel == 103.0
    assert journal.variation_eur == 3.0


def test_la_baisse_apparait_dans_le_resume(tmp_path):
    journal = pont.journal_depuis_robot(100, _trades(tmp_path, [-5.0, -3.0, 6.0]))
    resume = journal.resume_chiffre()
    assert journal.plus_bas_eur == 92.0
    assert "plus bas" in resume, "une baisse ne peut pas être masquée"


def test_une_ligne_illisible_nempeche_pas_la_lecture(tmp_path):
    chemin = _trades(tmp_path, [1.0, 2.0])
    chemin.write_text(chemin.read_text() + "\nligne cassée\n", encoding="utf-8")
    assert len(pont.lire_trades(chemin)) == 2


def test_les_prises_partielles_ne_comptent_pas_comme_trades(tmp_path):
    chemin = tmp_path / "trades.jsonl"
    base = time.time() - 5 * 86400
    chemin.write_text("\n".join([
        json.dumps({"closed_at": base, "profit": 2.0, "partial": True}),
        json.dumps({"closed_at": base + 86400, "profit": 1.0}),
    ]), encoding="utf-8")
    journal = pont.journal_depuis_robot(100, chemin)
    assert journal.solde_actuel == 101.0


def test_un_trade_date_du_futur_est_ignore(tmp_path):
    chemin = tmp_path / "trades.jsonl"
    chemin.write_text("\n".join([
        json.dumps({"closed_at": time.time() - 86400, "profit": 5.0}),
        json.dumps({"closed_at": time.time() + 10 * 86400, "profit": 500.0}),
    ]), encoding="utf-8")
    journal = pont.journal_depuis_robot(100, chemin)
    assert journal.solde_actuel == 105.0, "le futur ne peut pas entrer dans le récit"


def test_le_journal_manuel_reste_prioritaire(tmp_path, monkeypatch):
    from datetime import date, timedelta

    from eve.content import story

    manuel = tmp_path / "journal.json"
    hier = (date.today() - timedelta(days=1)).isoformat()
    manuel.write_text(json.dumps({"capital_depart_eur": 100, "entrees": [
        {"date": hier, "etape": "cent_euros", "solde_eur": 150.0}]}), encoding="utf-8")
    monkeypatch.setattr(story, "JOURNAL_PATH", manuel)
    monkeypatch.setattr(pont, "chemin_trades", lambda: _trades(tmp_path, [1.0]))

    assert load_journal().solde_actuel == 150.0


def test_sans_journal_manuel_on_lit_le_robot(tmp_path, monkeypatch):
    from eve.content import story

    monkeypatch.setattr(story, "JOURNAL_PATH", tmp_path / "absent.json")
    monkeypatch.setattr(pont, "chemin_trades", lambda: _trades(tmp_path, [4.0, -1.0]))
    journal = load_journal()
    assert journal is not None and journal.solde_actuel == 103.0

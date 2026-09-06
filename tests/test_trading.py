"""Le module trading n'a qu'un seul travail : ne jamais inventer un chiffre."""
import json
import random
from datetime import date, timedelta

import pytest

from eve.content.scripts import build_piece
from eve.content.trading import (
    METHODE_TOPICS, TradingDataError, build_work_content, load_results,
)
from eve.persona.persona import load_persona
from eve.safety.policy import review_post


def _resultats(**surcharges) -> dict:
    base = {
        "system_name": "Système A",
        "period": {"start": "2026-01-01", "end": "2026-06-30"},
        "metrics": {"return_pct": 9.4, "max_drawdown_pct": 6.2, "trades": 310},
    }
    base.update(surcharges)
    return base


def _ecrire(tmp_path, data) -> "object":
    path = tmp_path / "results.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_absence_de_fichier_ne_leve_pas(tmp_path):
    assert load_results(tmp_path / "inexistant.json") is None


def test_sans_donnees_le_contenu_reste_sur_la_methode():
    rng = random.Random(0)
    titres = {build_work_content(None, rng)[0] for _ in range(30)}
    assert titres <= {t for t, _, _ in METHODE_TOPICS}


def test_drawdown_obligatoire(tmp_path):
    data = _resultats()
    data["metrics"].pop("max_drawdown_pct")
    with pytest.raises(TradingDataError, match="max_drawdown_pct"):
        load_results(_ecrire(tmp_path, data))


def test_periode_future_refusee(tmp_path):
    demain = (date.today() + timedelta(days=30)).isoformat()
    data = _resultats(period={"start": "2026-01-01", "end": demain})
    with pytest.raises(TradingDataError, match="futur"):
        load_results(_ecrire(tmp_path, data))


def test_json_invalide_refuse(tmp_path):
    path = tmp_path / "results.json"
    path.write_text("{ pas du json", encoding="utf-8")
    with pytest.raises(TradingDataError):
        load_results(path)


def test_les_chiffres_publies_sont_ceux_du_fichier(tmp_path):
    results = load_results(_ecrire(tmp_path, _resultats()))
    ligne = results.ligne_chiffres()
    assert "+9.4 %" in ligne and "6.2 %" in ligne and "310" in ligne
    assert "drawdown" in ligne, "le risque doit apparaître avec le rendement"


def test_un_post_chiffre_passe_la_conformite(tmp_path, monkeypatch):
    import eve.content.trading as mod

    monkeypatch.setattr(mod, "RESULTS_PATH", _ecrire(tmp_path, _resultats()))
    persona = load_persona()
    # On force la branche chiffrée en épuisant les seeds jusqu'à l'obtenir.
    for jour in range(1, 28):
        piece = build_piece(persona, day=date(2026, 5, jour), slot="18:00", pillar="work")
        if piece.title.startswith("Les chiffres"):
            texte = piece.voiceover_text.lower()
            assert "drawdown" in texte
            assert "conseil en investissement" in texte
            _, res = review_post(persona, caption=piece.full_caption(), pillar="work")
            assert res.ok, res.report()
            return
    pytest.skip("aucun post chiffré tiré sur la fenêtre testée")

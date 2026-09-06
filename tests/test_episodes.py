"""Le fil narratif : écrit d'avance, publié seulement quand c'est vrai."""
import json
from datetime import date, timedelta

import pytest

from eve.agent.orchestrator import EveAgent
from eve.agent.state import Store
from eve.content import episodes as ep
from eve.content.scripts import build_episode
from eve.content.story import load_journal
from eve.persona.persona import load_persona
from eve.safety.policy import review_post


@pytest.fixture(scope="module")
def persona():
    return load_persona()


def _journal(tmp_path, etapes) -> "object":
    hier = (date.today() - timedelta(days=2)).isoformat()
    chemin = tmp_path / "journal.json"
    chemin.write_text(json.dumps({
        "capital_depart_eur": 100,
        "entrees": [{"date": hier, "etape": e, "solde_eur": None} for e in etapes],
    }), encoding="utf-8")
    return chemin


def test_les_episodes_sont_numerotes_dans_l_ordre():
    assert [e.numero for e in ep.EPISODES] == list(range(1, len(ep.EPISODES) + 1))
    assert len({e.cle for e in ep.EPISODES}) == len(ep.EPISODES)


def test_chaque_episode_a_une_accroche_courte():
    for episode in ep.EPISODES:
        assert episode.hook, episode.cle
        assert len(episode.hook) <= 90, f"{episode.cle} : accroche trop longue pour 3 secondes"


def test_sans_journal_seul_le_premier_episode_est_publiable(persona):
    prets = ep.prets_a_publier(persona, None)
    assert [e.cle for e in prets] == ["pourquoi"]
    assert len(ep.bloques(persona, None)) == len(ep.EPISODES) - 1


def test_une_etape_franchie_ouvre_son_episode(persona, tmp_path):
    journal = load_journal(_journal(tmp_path, ["premieres_lignes", "backtest"]))
    ouverts = {e.cle for e in ep.prets_a_publier(persona, journal)}
    assert ouverts == {"pourquoi", "premieres_lignes", "backtest"}
    assert "cent_euros" not in ouverts


@pytest.mark.parametrize("episode", ep.EPISODES, ids=lambda e: e.cle)
def test_chaque_episode_produit_un_script_publiable(persona, episode):
    piece = build_episode(persona, episode, day=date(2026, 1, 6), slot="08:00")
    assert 15 <= piece.duration_s <= 75, "une vidéo courte doit rester regardable"
    assert piece.hook == episode.hook
    assert piece.assets["episode"] == episode.cle
    texte = piece.voiceover_text.lower()
    assert "pas un conseil" in texte, "l'avertissement doit clore chaque épisode"


@pytest.mark.parametrize("episode", ep.EPISODES, ids=lambda e: e.cle)
def test_chaque_legende_passe_la_conformite(persona, episode):
    piece = build_episode(persona, episode, day=date(2026, 1, 6), slot="08:00")
    _, res = review_post(persona, caption=piece.full_caption(),
                         visual_prompts=piece.shot_prompts, pillar="journal")
    assert res.ok, f"{episode.cle} : {res.report()}"


def test_un_episode_non_franchi_est_bloque_a_la_publication(persona, tmp_path, monkeypatch):
    from eve.config import settings
    from eve.content import story

    monkeypatch.setattr(settings, "dry_run", False)
    monkeypatch.setattr(story, "JOURNAL_PATH", _journal(tmp_path, ["premieres_lignes"]))

    agent = EveAgent(persona=persona, store=Store(tmp_path / "t.db"))
    piece = build_episode(persona, ep.PAR_CLE["cent_euros"], day=date(2026, 1, 6), slot="08:00")
    piece.assets["video"] = str(tmp_path / "v.mp4")

    resultats = agent.publish(piece)
    assert resultats and all("BLOQUÉ" in r for r in resultats)
    assert "journal.json" in resultats[0]


def test_un_episode_franchi_passe_le_verrou(persona, tmp_path, monkeypatch):
    from eve.config import settings
    from eve.content import story

    monkeypatch.setattr(settings, "dry_run", True)
    monkeypatch.setattr(story, "JOURNAL_PATH", _journal(tmp_path, ["premieres_lignes"]))

    agent = EveAgent(persona=persona, store=Store(tmp_path / "t2.db"))
    piece = build_episode(persona, ep.PAR_CLE["premieres_lignes"],
                          day=date(2026, 1, 6), slot="08:00")
    piece.assets["video"] = str(tmp_path / "v.mp4")

    resultats = agent.publish(piece)
    assert resultats and not any("BLOQUÉ" in r for r in resultats)

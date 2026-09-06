"""Stories : le message tient dans l'image, et les chiffres restent réels."""
import json
from datetime import date, timedelta

import pytest

from eve.content import stories
from eve.content.story import load_journal
from eve.persona.persona import load_persona


@pytest.fixture(scope="module")
def persona():
    return load_persona()


def _journal(tmp_path, solde):
    hier = (date.today() - timedelta(days=1)).isoformat()
    chemin = tmp_path / "journal.json"
    chemin.write_text(json.dumps({"capital_depart_eur": 100, "entrees": [
        {"date": hier, "etape": "cent_euros", "solde_eur": solde}]}), encoding="utf-8")
    return load_journal(chemin)


def test_sans_chiffres_la_story_chiffree_est_ecartee():
    disponibles = {s.cle for s in stories.disponibles(None)}
    assert "chiffres" not in disponibles
    assert disponibles, "il reste toujours des stories publiables"


def test_avec_chiffres_la_story_chiffree_apparait(tmp_path):
    journal = _journal(tmp_path, 105.2)
    assert "chiffres" in {s.cle for s in stories.disponibles(journal)}


def test_le_texte_chiffre_vient_du_journal(tmp_path):
    journal = _journal(tmp_path, 105.2)
    story = stories.STORIES[-1]
    texte = stories.texte(story, journal)
    assert "105,20 €" in texte and "+5,2 %" in texte


def test_aucun_chiffre_invente_sans_journal():
    story = stories.STORIES[-1]
    assert stories.texte(story, None) == ""


def test_le_tirage_est_stable_pour_un_jour_donne(persona):
    a, _ = stories.choisir(persona, "2026-09-08", None)
    b, _ = stories.choisir(persona, "2026-09-08", None)
    assert a.cle == b.cle


def test_chaque_story_porte_un_texte_court_et_une_scene(persona):
    for story in stories.STORIES:
        assert story.scene
        if not story.besoin_chiffres:
            assert story.texte_ecran
            plus_longue = max(len(l) for l in story.texte_ecran.splitlines())
            assert plus_longue <= 30, f"{story.cle} : ligne trop longue pour une Story"
        assert persona.identity_lock[:60] in stories.prompt_image(persona, story)

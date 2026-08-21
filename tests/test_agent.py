import json
from datetime import date

import pytest

from eve.agent.orchestrator import EveAgent, _piece_from_row
from eve.agent.state import Store
from eve.analytics.collector import normalize
from eve.analytics.optimizer import suggest_weights
from eve.monetization.links import Offer, monetization_line, pick_offer
from eve.monetization.products import build_program_markdown, export_program
from eve.monetization.revenue import project_monthly
from eve.persona.persona import load_persona


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.db")


@pytest.fixture(scope="module")
def persona():
    return load_persona()


def test_store_round_trip(store):
    store.save_piece("p1", "2026-01-01", "07:00", "nutrition", {"a": 1}, "approved")
    assert store.get_piece("p1")["pillar"] == "nutrition"
    assert store.due_pieces("2026-01-02")[0]["id"] == "p1"


def test_publication_is_idempotent(store):
    store.save_piece("p1", "2026-01-01", "07:00", "nutrition", {})
    store.record_publication("p1", "tiktok", True, post_id="a")
    store.record_publication("p1", "tiktok", True, post_id="b")
    assert len(store.publications()) == 1
    assert store.is_published("p1", "tiktok")


def test_piece_survives_a_database_round_trip(persona, store):
    agent = EveAgent(persona=persona, store=store)
    piece = agent.plan(start=date(2026, 1, 1), days=1)[0]
    restored = _piece_from_row(store.get_piece(piece.id))
    assert restored.beats[0].voiceover == piece.beats[0].voiceover
    assert restored.duration_s == piece.duration_s


def test_planning_never_duplicates(persona, store):
    agent = EveAgent(persona=persona, store=store)
    first = agent.plan(start=date(2026, 1, 1), days=2)
    second = agent.plan(start=date(2026, 1, 1), days=2)
    assert first and not second


def test_metrics_normalisation_across_platforms():
    tiktok = normalize({"view_count": 1000, "like_count": 80, "comment_count": 20})
    instagram = normalize({"views": 1000, "likes": 80, "comments": 20})
    assert tiktok["engagement_rate"] == instagram["engagement_rate"] == 0.1


def test_optimizer_favours_the_best_pillar(persona, store):
    for i in range(12):
        pillar = "quick_workout" if i % 2 else "lifestyle"
        store.save_piece(f"m{i}", "2026-01-01", "07:00", pillar, {})
        store.record_metrics(f"m{i}", "tiktok", {
            "views": 9000 if pillar == "quick_workout" else 300,
            "engagement_rate": 0.09 if pillar == "quick_workout" else 0.01})
    weights = suggest_weights(persona, store)
    base = {p.key: p.share for p in persona.pillars}
    assert weights["quick_workout"] > base["quick_workout"]
    assert weights["lifestyle"] < base["lifestyle"]
    assert all(v > 0 for v in weights.values()), "aucun pilier ne doit tomber à zéro"
    assert abs(sum(weights.values()) - 1) < 0.01


def test_affiliate_links_carry_the_legal_disclosure():
    offer = Offer("gear", "Matériel", "affiliate", "https://x.test/p",
                  ("quick_workout",), "Mes élastiques.", requires_disclosure=True)
    line = monetization_line(offer, "instagram", "camp")
    assert "#ad" in line and "utm_campaign=camp" in line


def test_no_offer_when_pillar_does_not_match():
    offer = Offer("gear", "Matériel", "affiliate", "https://x.test/p",
                  ("quick_workout",), "…")
    assert pick_offer("qa", [offer]) is None
    assert monetization_line(None, "tiktok", "c") == ""


def test_revenue_projection_is_ordered_and_positive():
    proj = project_monthly(10_000, 300_000)
    for low, high in proj.values():
        assert 0 <= low <= high


def test_program_export_contains_disclaimer_and_ai_notice(persona, tmp_path):
    md = build_program_markdown(persona)
    assert "intelligence artificielle" in md
    assert "avis médical" in md
    paths = export_program(persona, tmp_path)
    assert paths["html"].read_text(encoding="utf-8").startswith("<!doctype html>")


def test_dry_run_publish_records_but_does_not_go_live(persona, store, monkeypatch):
    from eve.config import settings
    monkeypatch.setattr(settings, "dry_run", True)
    agent = EveAgent(persona=persona, store=store)
    piece = agent.plan(start=date(2026, 2, 1), days=1)[0]
    piece.assets["video"] = "/tmp/fake.mp4"
    results = agent.publish(piece)
    assert results and all("DRY-RUN" in r for r in results)
    assert json.loads(store.get_piece(piece.id)["payload"])
    assert store.publications(only_live=True) == []

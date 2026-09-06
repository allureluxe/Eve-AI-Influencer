"""Le CLI est la seule surface utilisée par un humain : il doit rester simple."""
import pytest

from eve.cli import build_parser, main


def test_go_is_the_documented_entry_point():
    parser = build_parser()
    args = parser.parse_args(["go"])
    assert args.func.__name__ == "cmd_go"
    assert args.days >= 1 and args.videos >= 1


@pytest.mark.parametrize("command", ["doctor", "preview", "plan", "produce", "approve",
                                     "publish", "run", "loop", "metrics", "product",
                                     "revenue", "persona"])
def test_every_command_parses(command):
    assert build_parser().parse_args([command]).func is not None


def test_unknown_command_exits_cleanly():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["inexistant"])


def test_preview_runs_without_touching_the_network_or_disk(capsys):
    assert main(["preview", "--pillar", "build"]) == 0
    out = capsys.readouterr().out
    assert "Légende tiktok" in out and "Légende instagram" in out


def test_revenue_projection_is_printed(capsys):
    assert main(["revenue", "--followers", "5000", "--views", "100000"]) == 0
    assert "Projection mensuelle" in capsys.readouterr().out


def test_bios_respect_platform_limits():
    from eve.content.launch import IG_BIO_LIMIT, TIKTOK_BIO_LIMIT, build_bios
    from eve.persona.persona import load_persona

    persona = load_persona()
    bios = build_bios(persona)
    assert len(bios["instagram"]) <= IG_BIO_LIMIT
    assert len(bios["tiktok"]) <= TIKTOK_BIO_LIMIT
    for bio in bios.values():
        assert bio.splitlines()[0].startswith("🤖"), "la mention IA doit ouvrir la bio"


def test_launch_kit_command_is_registered():
    assert build_parser().parse_args(["lancement"]).func.__name__ == "cmd_lancement"


def test_pas_de_compteur_dans_la_bio_sans_compte_reel(monkeypatch, tmp_path):
    """Une bio ne doit jamais afficher un chiffre inventé."""
    from eve.content import robot_bridge, story
    from eve.content.launch import build_bios, ligne_compteur
    from eve.persona.persona import load_persona

    # Aucune des deux sources : ni journal manuel, ni journal du robot.
    monkeypatch.setattr(story, "JOURNAL_PATH", tmp_path / "absent.json")
    monkeypatch.setattr(robot_bridge, "chemin_trades", lambda: None)
    assert ligne_compteur() == ""
    bio = build_bios(load_persona())["instagram"]
    assert "Jour" not in bio and "€" in bio


def test_le_compteur_est_calcule_depuis_le_journal(monkeypatch, tmp_path):
    import json
    from datetime import date, timedelta

    from eve.content import story
    from eve.content.launch import build_bios, ligne_compteur
    from eve.persona.persona import load_persona

    ouverture = (date.today() - timedelta(days=25)).isoformat()
    dernier = (date.today() - timedelta(days=1)).isoformat()
    chemin = tmp_path / "journal.json"
    chemin.write_text(json.dumps({"capital_depart_eur": 100, "entrees": [
        {"date": ouverture, "etape": "cent_euros", "solde_eur": 100.0},
        {"date": dernier, "etape": "premiere_semaine", "solde_eur": 112.35}]}),
        encoding="utf-8")
    monkeypatch.setattr(story, "JOURNAL_PATH", chemin)

    assert ligne_compteur() == "Jour 24 : 112,35 €"
    bio = build_bios(load_persona())["instagram"]
    assert "Jour 24 : 112,35 €" in bio
    assert len(bio) <= 150

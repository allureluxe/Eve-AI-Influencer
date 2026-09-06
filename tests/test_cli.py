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

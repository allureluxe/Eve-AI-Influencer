"""9 oct. 2026 : une crypto rachetee n'apparaissait jamais dans l'application.

`signals.reference` est unique ; elle valait « PARTIUSD:1 » a chaque achat
de PARTI. Le 2e achat etait refuse par Supabase, sans erreur visible.
"""
from helpers import *  # noqa: F401,F403

from gold_bot.signal_publisher import BASCULE_REFERENCE_UNIQUE, reference_signal


def test_deux_achats_de_la_meme_crypto_ont_deux_references():
    a = reference_signal("PARTIUSD", BASCULE_REFERENCE_UNIQUE + 10, 1)
    b = reference_signal("PARTIUSD", BASCULE_REFERENCE_UNIQUE + 90_000, 1)
    assert a != b


def test_l_etage_reste_apres_le_dernier_deux_points():
    """L'application lit l'etage ainsi (positionsTri.ts, format.ts)."""
    ref = reference_signal("ATOMUSD", BASCULE_REFERENCE_UNIQUE + 5, 3)
    assert ref.split(":")[-1] == "3" and ref.split(":")[1] == "3"
    assert ref.count(":") == 1


def test_une_position_d_avant_la_bascule_garde_son_ancienne_reference():
    """Sinon sa cloture ne retrouverait plus la ligne publiee."""
    assert reference_signal("ATOMUSD", BASCULE_REFERENCE_UNIQUE - 1, 2) == "ATOMUSD:2"


def test_les_etages_d_une_meme_pyramide_partagent_la_base():
    ouverte = BASCULE_REFERENCE_UNIQUE + 100
    refs = [reference_signal("SOLUSD", ouverte, e) for e in (1, 2, 3)]
    assert len({r.rsplit(":", 1)[0] for r in refs}) == 1

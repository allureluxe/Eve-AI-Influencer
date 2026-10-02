"""Tout l'affichage du reel part d'UNE periode (decision du 2 oct. 2026).

L'historique repartait du capital a ~600 EUR mais « encaisse » se
calculait sur les depots nets depuis le 25 sept. : -76,90 EUR a cote d'un
historique a -16 EUR. Le capital de depart suit desormais la meme periode.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest import mock

from helpers import *  # noqa: F401,F403 - insere le chemin du projet

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops"))
import battement_comptes as bc  # noqa: E402


def _bitvavo(depots, retraits):
    def faux(req, timeout=30):
        lignes = depots if "deposit" in req.full_url else retraits
        return io.BytesIO(json.dumps(lignes).encode())
    return faux


def _ligne(ts_s, montant):
    return {"symbol": "EUR", "status": "completed",
            "timestamp": int(ts_s * 1000), "amount": str(montant)}


def test_le_depart_suit_la_periode_et_les_virements_posterieurs():
    avant = bc.PERIODE_REEL_DEPUIS - 86400
    apres = bc.PERIODE_REEL_DEPUIS + 3600
    with mock.patch.object(bc, "_signer_bitvavo", return_value={}), \
         mock.patch.object(bc.urllib.request, "urlopen",
                           _bitvavo([_ligne(avant, 2400), _ligne(apres, 50)],
                                    [_ligne(avant, 1610), _ligne(apres, 12)])):
        depart = bc._depart_reel()
    assert depart == round(bc.PERIODE_REEL_CAPITAL + 50 - 12, 2), (
        "les virements d'avant la periode ne doivent plus compter")


def test_l_historique_et_le_depart_partagent_la_meme_date():
    assert bc.HISTORIQUE_REEL_DEPUIS == bc.PERIODE_REEL_DEPUIS

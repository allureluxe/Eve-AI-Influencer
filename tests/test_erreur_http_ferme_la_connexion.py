"""Une reponse d'erreur HTTP doit refermer sa connexion.

2 oct. 2026 : la demo 1 accumulait ~150 sockets par minute en CLOSE-WAIT
vers une source de prix qui repond 400 pour chaque crypto qu'il ne cote
pas. `http_get` gardait l'erreur sans la fermer : la limite de 1 024
fichiers ouverts du processus tombait en quelques minutes.
"""
from __future__ import annotations

import io
import urllib.error
from unittest import mock

from helpers import *  # noqa: F401,F403 - insere le chemin du projet

from gold_bot.datasources import base


class _Corps(io.BytesIO):
    ferme = False

    def close(self):
        _Corps.ferme = True
        super().close()


def test_http_get_ferme_la_reponse_d_erreur():
    _Corps.ferme = False
    erreur = urllib.error.HTTPError(
        "https://exemple.test/x", 400, "Bad Request", {}, _Corps(b"{}"))
    with mock.patch.object(base.urllib.request, "urlopen", side_effect=erreur):
        try:
            base.http_get("https://exemple.test/x", retries=0)
        except Exception:  # noqa: BLE001 - seul le close() nous interesse
            pass
    assert _Corps.ferme, "la connexion de la reponse d'erreur reste ouverte"

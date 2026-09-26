"""Kling : le fournisseur video retenu apres le blocage de Runway.

Le risque ici n'est pas l'API : c'est l'authentification. Kling n'accepte
pas un bearer ordinaire mais un JWT HS256 refabrique a chaque appel, avec
trois champs imposes. Un jeton mal forme donne un 401 que rien dans le
message ne relie a l'horloge ou a la signature.
"""
from __future__ import annotations

import base64
import json

import pytest

from luna.media import KlingVideo, MediaErreur, RunwayVideo, SoraVideo, fournisseur_video


def _partie(jeton: str, index: int) -> dict:
    morceau = jeton.split(".")[index]
    return json.loads(base64.urlsafe_b64decode(
        morceau + "=" * (-len(morceau) % 4)))


@pytest.fixture
def kling(monkeypatch):
    monkeypatch.setenv("KLING_ACCESS_KEY", "ak-essai")
    monkeypatch.setenv("KLING_SECRET_KEY", "sk-essai")
    return KlingVideo()


class TestLeJetonEstBienForme:
    def test_trois_morceaux_et_un_entete_hs256(self, kling):
        jeton = kling._jeton()
        assert jeton.count(".") == 2
        assert _partie(jeton, 0) == {"alg": "HS256", "typ": "JWT"}

    def test_la_cle_publique_va_dans_iss(self, kling):
        assert _partie(kling._jeton(), 1)["iss"] == "ak-essai"

    def test_il_demarre_AVANT_maintenant(self, kling):
        # LES CINQ SECONDES DE RECUL NE SONT PAS DU CONFORT. Sans elles,
        # le moindre decalage d'horloge entre le VPS et les serveurs de
        # Kling fait rejeter un jeton tout neuf, avec un 401 qui ressemble
        # a une mauvaise cle.
        charge = _partie(kling._jeton(), 1)
        assert charge["exp"] - charge["nbf"] == 1805

    def test_la_signature_change_avec_le_secret(self, kling, monkeypatch):
        premier = kling._jeton().split(".")[2]
        monkeypatch.setenv("KLING_SECRET_KEY", "sk-different")
        assert KlingVideo()._jeton().split(".")[2] != premier


class TestIlTraduitVersCeQueKlingAccepte:
    def test_trois_proportions_seulement(self, kling):
        assert kling._ratio("9:16") == "9:16"
        assert kling._ratio("16:9") == "16:9"
        # Le reste retombe sur le vertical : c'est le format des Reels.
        assert kling._ratio("4:3") == "9:16"

    def test_cinq_ou_dix_secondes_rien_d_autre(self, kling):
        assert kling._duree(3) == "5"
        assert kling._duree(7) == "5"
        assert kling._duree(8) == "10"
        assert kling._duree(30) == "10"


class TestLaFabriqueLeChoisitEnPREMIER:
    def test_kling_avant_runway(self, monkeypatch):
        # Runway a refuse DEUX fois d'animer Luna le 26 septembre, et sa
        # documentation suspend les comptes qui insistent. Un moteur qui
        # refuse le sujet ne sert a rien, quelle que soit sa qualite.
        monkeypatch.setenv("KLING_ACCESS_KEY", "ak")
        monkeypatch.setenv("KLING_SECRET_KEY", "sk")
        monkeypatch.setenv("RUNWAYML_API_SECRET", "rw")
        assert fournisseur_video().nom == "kling"

    def test_runway_quand_kling_n_est_pas_configure(self, monkeypatch):
        monkeypatch.delenv("KLING_ACCESS_KEY", raising=False)
        monkeypatch.setenv("RUNWAYML_API_SECRET", "rw")
        assert fournisseur_video().nom == "runway"

    def test_les_trois_repondent_a_la_meme_interface(self):
        # C'est ce qui permet au worker de n'avoir qu'un seul chemin.
        for classe in (KlingVideo, SoraVideo, RunwayVideo):
            for methode in ("creer", "resultat", "entetes_telechargement"):
                assert callable(getattr(classe, methode, None)), \
                    f"{classe.__name__} n'expose pas {methode}"
            assert getattr(classe, "nom", "")


class TestIlRefusePlutotQueDeProduireUneInconnue:
    def test_sans_image_de_depart_il_echoue(self, kling):
        with pytest.raises(MediaErreur, match="image de depart"):
            kling.creer("", "elle marche", "9:16", 5)

    def test_sans_les_deux_cles_il_le_dit(self, monkeypatch):
        monkeypatch.delenv("KLING_ACCESS_KEY", raising=False)
        monkeypatch.delenv("KLING_SECRET_KEY", raising=False)
        with pytest.raises(MediaErreur, match="KLING_ACCESS_KEY"):
            KlingVideo()._appel("GET", "/v1/videos/image2video/x")


class TestUn200QuiRefuseResteUnRefus:
    def test_le_code_dans_le_corps_est_lu(self, kling, monkeypatch):
        """Kling rend 200 meme quand il refuse — le verdict est dans `code`.

        Ne pas le lire ferait attendre indefiniment une tache qui n'a
        jamais ete creee : exactement le mode de panne silencieuse que ce
        depot a deja rencontre cinq fois.
        """
        class _Faux:
            def read(self):
                return json.dumps({"code": 1103,
                                   "message": "quota insuffisant"}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Faux())
        with pytest.raises(MediaErreur, match="1103"):
            kling._appel("GET", "/v1/videos/image2video/x")

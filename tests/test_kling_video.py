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

    def test_sans_aucun_identifiant_il_le_dit(self, monkeypatch):
        for n in ("KLING_API_KEY", "KLING_ACCESS_KEY", "KLING_SECRET_KEY"):
            monkeypatch.delenv(n, raising=False)
        with pytest.raises(MediaErreur, match="KLING_API_KEY"):
            KlingVideo()._appel("GET", "/v1/videos/image2video/x")


class TestLesDeuxGenerationsDIdentifiants:
    """Kling a change de systeme : la nouvelle console donne UNE cle.

    L'ancienne donnait une paire et exigeait un JWT signe ; la nouvelle
    « API Platform » rend une seule cle `api-key-kling-...` en bearer
    ordinaire. L'operateur a cree la sienne sur la nouvelle le
    26 septembre et n'en a recu qu'une, alors que le code en reclamait
    deux. On accepte les deux formes : un fournisseur qui change
    d'authentification est une panne certaine, et elle tombe toujours un
    jour ou l'on n'a pas le temps.
    """

    def test_une_seule_cle_suffit(self, monkeypatch):
        for n in ("KLING_ACCESS_KEY", "KLING_SECRET_KEY"):
            monkeypatch.delenv(n, raising=False)
        monkeypatch.setenv("KLING_API_KEY", "api-key-kling-GGXdlasw")
        k = KlingVideo()
        assert k.disponible
        # Presentee telle quelle, sans passer par le JWT.
        assert k._entetes()["Authorization"] == "Bearer api-key-kling-GGXdlasw"

    def test_la_paire_ancienne_passe_toujours_par_le_jwt(self, monkeypatch):
        monkeypatch.delenv("KLING_API_KEY", raising=False)
        monkeypatch.setenv("KLING_ACCESS_KEY", "ak-essai")
        monkeypatch.setenv("KLING_SECRET_KEY", "sk-essai")
        porteur = KlingVideo()._entetes()["Authorization"]
        assert porteur.count(".") == 2, "un JWT a trois morceaux"

    def test_la_cle_unique_l_emporte_si_les_deux_sont_posees(self, monkeypatch):
        monkeypatch.setenv("KLING_API_KEY", "api-key-kling-neuve")
        monkeypatch.setenv("KLING_ACCESS_KEY", "ak-vieille")
        monkeypatch.setenv("KLING_SECRET_KEY", "sk-vieille")
        assert "api-key-kling-neuve" in KlingVideo()._entetes()["Authorization"]


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

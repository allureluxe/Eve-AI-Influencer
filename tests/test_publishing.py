"""Les trois briques qui font tourner l'agent sans personne derrière."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from eve.agent.state import Store
from eve.publishing.base import PublishRequest
from eve.publishing.hosting import GitHubReleaseHost, HostedFile, HostingError


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "t.db")


# ------------------------------------------------------------- hébergement
def test_hebergement_non_configure_le_dit_clairement(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    host = GitHubReleaseHost()
    assert not host.configured
    with pytest.raises(HostingError, match="GITHUB_REPOSITORY"):
        host.upload(tmp_path / "v.mp4")


def test_depot_prive_est_signale_avant_publication(monkeypatch):
    host = GitHubReleaseHost(repo="moi/projet", token="x")

    class Reponse:
        status_code = 200

        @staticmethod
        def json():
            return {"private": True}

    monkeypatch.setattr("eve.publishing.hosting.requests.get", lambda *a, **k: Reponse())
    ok, message = host.check_public_access()
    assert not ok
    assert "privé" in message and "404" in message


def test_video_absente_refusee(tmp_path):
    host = GitHubReleaseHost(repo="moi/projet", token="x")
    with pytest.raises(HostingError, match="introuvable"):
        host.upload(tmp_path / "absent.mp4")


# ------------------------------------------------------------------ jetons
def test_un_jeton_encore_valide_nest_pas_renouvele(store, monkeypatch):
    from eve.publishing import tokens

    futur = datetime.now(timezone.utc) + timedelta(days=45)
    store.set_kv("token_instagram", {"valeur": "frais", "expire_le": futur.isoformat()})

    def interdit(*a, **k):
        raise AssertionError("aucun appel réseau ne devait avoir lieu")

    monkeypatch.setattr("eve.publishing.tokens.requests.get", interdit)
    etat = tokens.refresh_instagram(store)
    assert etat.valeur == "frais" and etat.source == "état"


def test_un_jeton_proche_de_lecheance_est_renouvele(store, monkeypatch):
    from eve.publishing import tokens

    proche = datetime.now(timezone.utc) + timedelta(days=2)
    store.set_kv("token_instagram", {"valeur": "vieux", "expire_le": proche.isoformat()})

    class Reponse:
        status_code = 200

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"access_token": "nouveau", "expires_in": 5184000}

    monkeypatch.setattr("eve.publishing.tokens.requests.get", lambda *a, **k: Reponse())
    etat = tokens.refresh_instagram(store, app_id="1", app_secret="2")
    assert etat.valeur == "nouveau" and etat.source == "renouvelé"
    assert store.get_kv("token_instagram")["valeur"] == "nouveau"


def test_un_echec_de_renouvellement_ne_perd_pas_le_jeton(store, monkeypatch):
    from eve.publishing import tokens

    proche = datetime.now(timezone.utc) + timedelta(days=1)
    store.set_kv("token_instagram", {"valeur": "vieux", "expire_le": proche.isoformat()})

    def boum(*a, **k):
        raise RuntimeError("réseau coupé")

    monkeypatch.setattr("eve.publishing.tokens.requests.get", boum)
    etat = tokens.refresh_instagram(store, app_id="1", app_secret="2")
    assert etat.valeur == "vieux", "on garde le jeton existant plutôt que de tout perdre"


def test_une_echeance_proche_remonte_une_alerte(store):
    from eve.publishing import tokens

    # +1 h de marge : le calcul en jours pleins arrondit vers le bas, ce qui
    # est le bon sens pour une alerte (on annonce moins de temps, jamais plus).
    proche = datetime.now(timezone.utc) + timedelta(days=3, hours=1)
    etats = {"instagram": tokens.TokenState("v", proche, "secret")}
    messages = tokens.alertes(etats)
    assert messages and "expire dans 3 jour" in messages[0]


def test_aucune_alerte_quand_le_jeton_est_loin_de_lecheance(store):
    from eve.publishing import tokens

    loin = datetime.now(timezone.utc) + timedelta(days=50)
    assert tokens.alertes({"instagram": tokens.TokenState("v", loin, "renouvelé")}) == []


# ------------------------------------------------------------ TikTok draft
def test_le_mode_brouillon_passe_par_la_boite_de_reception(tmp_path, monkeypatch):
    from eve.config import settings
    from eve.publishing.tiktok import TikTokPublisher

    video = tmp_path / "v.mp4"
    video.write_bytes(b"0" * 2048)
    monkeypatch.setattr(settings, "dry_run", False)
    monkeypatch.setattr(settings.publishing, "tiktok_draft_mode", True)

    appels = []
    pub = TikTokPublisher(access_token="jeton")
    monkeypatch.setattr(pub, "_init_inbox", lambda p: (appels.append("inbox") or ("id1", "http://u")))
    monkeypatch.setattr(pub, "_upload", lambda p, u: appels.append("upload"))
    monkeypatch.setattr(pub, "_wait_publish", lambda pid: {"status": "SEND_TO_USER_INBOX"})
    monkeypatch.setattr(pub, "_init_upload", lambda *a: pytest.fail("ne doit pas publier directement"))

    resultat = pub.publish(PublishRequest(caption="x", video_path=video))
    assert resultat.ok and appels == ["inbox", "upload"]
    assert "valider dans l'application" in resultat.detail


def test_une_story_instagram_utilise_son_propre_type(monkeypatch):
    from eve.config import settings
    from eve.publishing.instagram import InstagramPublisher

    monkeypatch.setattr(settings, "dry_run", False)
    pub = InstagramPublisher(user_id="1", token="t")
    envoye = {}

    def faux_post(path, data):
        envoye.update(data)
        return {"id": "container"}

    monkeypatch.setattr(pub, "_post", faux_post)
    monkeypatch.setattr(pub, "_wait_container", lambda cid: None)
    monkeypatch.setattr(pub, "_get", lambda p, params: {"permalink": "http://x"})

    pub.publish(PublishRequest(caption="ignorée", kind="story",
                               video_url="https://x/v.mp4"))
    assert envoye["media_type"] == "STORIES"
    assert "caption" not in envoye, "une Story ne porte pas de légende"

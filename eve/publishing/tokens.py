"""Renouvellement des jetons d'accès.

Sans ce module, la publication s'arrête silencieusement : le jeton Instagram
expire au bout de 60 jours, celui de TikTok au bout de 24 heures. L'agent
continue de tourner, les publications échouent, et rien ne dit pourquoi.

Les jetons renouvelés sont conservés dans l'état SQLite plutôt que réécrits
dans les secrets du dépôt : mettre à jour un secret GitHub demande un jeton
personnel élargi, ce qui serait un plus grand risque que le problème résolu.
Quand un renouvellement devient impossible, le rapport d'exécution le dit
explicitement, avec la marche à suivre.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

from eve.agent.state import Store
from eve.config import settings

log = logging.getLogger(__name__)

# On renouvelle avant l'échéance : un jeton qui expire pendant une
# publication fait perdre la vidéo.
MARGE_INSTAGRAM = timedelta(days=10)
MARGE_TIKTOK = timedelta(hours=2)


@dataclass
class TokenState:
    valeur: str
    expire_le: datetime | None
    source: str          # "secret" | "renouvelé" | "état"

    @property
    def expire_bientot(self) -> bool:
        if self.expire_le is None:
            return False
        return self.expire_le - datetime.now(timezone.utc) < MARGE_INSTAGRAM


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def _lire(store: Store, cle: str) -> tuple[str, datetime | None]:
    brut = store.get_kv(cle) or {}
    expire = brut.get("expire_le")
    return brut.get("valeur", ""), datetime.fromisoformat(expire) if expire else None


def _ecrire(store: Store, cle: str, valeur: str, expire_le: datetime | None) -> None:
    store.set_kv(cle, {"valeur": valeur,
                       "expire_le": expire_le.isoformat() if expire_le else None,
                       "maj": _maintenant().isoformat()})


# ------------------------------------------------------------------ Instagram
def refresh_instagram(store: Store, app_id: str = "", app_secret: str = "") -> TokenState:
    """Échange le jeton longue durée contre un jeton frais (60 jours).

    Nécessite l'identifiant et le secret de l'app Meta. Sans eux, on rend le
    jeton du secret tel quel et on signale qu'il faudra le remplacer à la main.
    """
    cle = "token_instagram"
    stocke, expire = _lire(store, cle)
    courant = stocke or settings.publishing.instagram_token
    if not courant:
        return TokenState("", None, "secret")

    if expire and expire - _maintenant() > MARGE_INSTAGRAM:
        return TokenState(courant, expire, "état")

    app_id = app_id or settings.publishing.meta_app_id
    app_secret = app_secret or settings.publishing.meta_app_secret
    if not (app_id and app_secret):
        log.warning("META_APP_ID / META_APP_SECRET absents : jeton Instagram non renouvelable.")
        return TokenState(courant, expire, "secret")

    try:
        r = requests.get(
            f"https://graph.facebook.com/{settings.publishing.graph_api_version}/oauth/access_token",
            params={"grant_type": "fb_exchange_token", "client_id": app_id,
                    "client_secret": app_secret, "fb_exchange_token": courant},
            timeout=60)
        r.raise_for_status()
        data = r.json()
        nouveau = data["access_token"]
        duree = int(data.get("expires_in", 60 * 24 * 3600))
        echeance = _maintenant() + timedelta(seconds=duree)
        _ecrire(store, cle, nouveau, echeance)
        log.info("Jeton Instagram renouvelé, valable jusqu'au %s.", echeance.date())
        return TokenState(nouveau, echeance, "renouvelé")
    except Exception as exc:
        log.error("Renouvellement Instagram impossible : %s", exc)
        return TokenState(courant, expire, "secret")


# --------------------------------------------------------------------- TikTok
def refresh_tiktok(store: Store) -> TokenState:
    """Le jeton TikTok vit 24 h ; le refresh_token, un an."""
    cle = "token_tiktok"
    stocke, expire = _lire(store, cle)
    courant = stocke or settings.publishing.tiktok_access_token

    if expire and expire - _maintenant() > MARGE_TIKTOK:
        return TokenState(courant, expire, "état")

    cfg = settings.publishing
    refresh = (store.get_kv("tiktok_refresh_token")
               or cfg.tiktok_refresh_token)
    if not (cfg.tiktok_client_key and cfg.tiktok_client_secret and refresh):
        if not courant:
            return TokenState("", None, "secret")
        log.warning("TIKTOK_REFRESH_TOKEN ou identifiants d'app absents : "
                    "jeton TikTok non renouvelable.")
        return TokenState(courant, expire, "secret")

    try:
        r = requests.post(
            "https://open.tiktokapis.com/v2/oauth/token/",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"client_key": cfg.tiktok_client_key,
                  "client_secret": cfg.tiktok_client_secret,
                  "grant_type": "refresh_token", "refresh_token": refresh},
            timeout=60)
        r.raise_for_status()
        data = r.json()
        if "access_token" not in data:
            raise RuntimeError(str(data)[:200])
        echeance = _maintenant() + timedelta(seconds=int(data.get("expires_in", 86400)))
        _ecrire(store, cle, data["access_token"], echeance)
        if data.get("refresh_token"):
            store.set_kv("tiktok_refresh_token", data["refresh_token"])
        log.info("Jeton TikTok renouvelé, valable %s h.",
                 round(int(data.get("expires_in", 86400)) / 3600))
        return TokenState(data["access_token"], echeance, "renouvelé")
    except Exception as exc:
        log.error("Renouvellement TikTok impossible : %s", exc)
        return TokenState(courant, expire, "secret")


def refresh_all(store: Store) -> dict[str, TokenState]:
    return {"instagram": refresh_instagram(store), "tiktok": refresh_tiktok(store)}


def alertes(etats: dict[str, TokenState]) -> list[str]:
    """Messages à faire remonter dans le rapport d'exécution."""
    messages: list[str] = []
    for plateforme, etat in etats.items():
        if not etat.valeur:
            continue
        if etat.expire_le is None and etat.source == "secret":
            messages.append(
                f"{plateforme} : échéance du jeton inconnue et renouvellement non "
                "configuré. Ajouter les identifiants d'app pour éviter une coupure.")
        elif etat.expire_bientot:
            jours = (etat.expire_le - _maintenant()).days
            messages.append(
                f"{plateforme} : le jeton expire dans {jours} jour(s) et n'a pas pu "
                "être renouvelé. Le remplacer dans les secrets du dépôt.")
    return messages

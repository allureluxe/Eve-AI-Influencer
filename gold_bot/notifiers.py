"""Alertes et journal de bord."""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)
LEVEL_ORDER = {"debug": 10, "info": 20, "trade": 25, "warning": 30, "critical": 40}


def http_json(url: str, method: str = "POST", payload: Optional[dict] = None,
              headers: Optional[dict[str, str]] = None, timeout: float = 10.0) -> Any:
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    hdrs = {"Content-Type": "application/json", "Accept": "application/json",
            "User-Agent": "gold-bot/1.0"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"HTTP notification indisponible: {exc}") from exc
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


@dataclass(slots=True)
class Notification:
    level: str
    title: str
    body: str = ""
    data: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    @property
    def stamp(self) -> str:
        return datetime.fromtimestamp(self.ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    def as_text(self) -> str:
        icon = {"trade": "[TRADE]", "warning": "[ALERTE]", "critical": "[CRITIQUE]"}.get(self.level, "[INFO]")
        return f"{icon} {self.stamp} — {self.title}" + (f"\n{self.body}" if self.body else "")


class Channel(ABC):
    name = "abstract"
    min_level = "info"

    def enabled(self) -> bool:
        return True

    def accepts(self, level: str) -> bool:
        return LEVEL_ORDER.get(level, 20) >= LEVEL_ORDER.get(self.min_level, 20)

    @abstractmethod
    def send(self, note: Notification) -> None:
        ...


class ConsoleChannel(Channel):
    name = "console"

    def __init__(self, min_level: str = "info") -> None:
        self.min_level = min_level

    def send(self, note: Notification) -> None:
        fn = {"critical": logger.error, "warning": logger.warning}.get(note.level, logger.info)
        fn("%s", note.as_text())


class FileChannel(Channel):
    name = "fichier"

    def __init__(self, path: str = "", min_level: str = "debug") -> None:
        self.path = path or os.getenv("GB_JOURNAL_FILE", "data/journal.jsonl")
        self.min_level = min_level

    def send(self, note: Notification) -> None:
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": note.ts, "date": note.stamp, "niveau": note.level,
                                     "titre": note.title, "detail": note.body,
                                     "donnees": note.data}, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("journal non ecrit : %s", exc)


class TelegramChannel(Channel):
    name = "telegram"

    def __init__(self, min_level: str = "trade") -> None:
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.min_level = min_level

    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, note: Notification) -> None:
        # LE TELEPHONE N'EST PAS LE JOURNAL.
        #
        # Decision de l'operateur, 10 septembre 2026 : il veut etre
        # prevenu quand une position s'ouvre, quand elle se ferme, quand
        # le robot s'arrete et quand il y a un vrai probleme — « pas a
        # chaque fois qu'un ordre est refuse ».
        #
        # Un refus de courtier est ordinaire : il se reproduit a chaque
        # cycle tant que la cause dure, et une rafale de dix messages en
        # une minute apprend a ignorer les alertes. Or la seule alerte qui
        # compte vraiment — le chien de garde — arrive par le meme canal.
        # Noyer les alertes, c'est les desarmer.
        #
        # Ces evenements restent dans le journal (canal fichier, niveau
        # debug) et dans la console. Seul le telephone les ignore, et
        # c'est marque a l'appel pour que l'intention se voie : le niveau
        # de gravite ne ment pas, il n'est simplement pas destine ici.
        if note.data.get("telephone") is False:
            return
        try:
            http_json(f"https://api.telegram.org/bot{self.token}/sendMessage", "POST",
                      {"chat_id": self.chat_id, "text": note.as_text(),
                       "disable_web_page_preview": True}, timeout=10)
        except Exception as exc:
            logger.warning("telegram indisponible : %s", str(exc)[:120])


class AlluxeBotChannel(Channel):
    """Alertes dans l'application Alluxe Bot -- remplace Telegram.

    Decision de l'operateur, 15 sept. 2026 : « tout ce que le robot fait
    sur Telegram, il le fait sur l'application Alluxe Bot, plus besoin de
    Telegram ». Meme seuil que TelegramChannel (`min_level="trade"`) et
    meme garde-fou (`telephone=False` pour les refus ordinaires de
    courtier, voir TelegramChannel plus haut) : c'est le meme public, la
    meme discipline anti-spam.

    Ecrit directement dans la table `alluxe_bot_alertes` via l'API REST
    de Supabase (service_role, comme les autres publieurs `ops/*.py`) --
    pas de serveur intermediaire a maintenir.
    """
    name = "alluxe_bot"

    def __init__(self, min_level: str = "trade") -> None:
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.cle = os.getenv("SUPABASE_SERVICE_KEY", "")
        self.min_level = min_level

    def enabled(self) -> bool:
        return bool(self.url and self.cle)

    def send(self, note: Notification) -> None:
        # Meme garde-fou que Telegram : un refus de courtier ordinaire ne
        # doit pas noyer l'operateur.
        if note.data.get("telephone") is False:
            return
        try:
            http_json(
                f"{self.url}/rest/v1/alluxe_bot_alertes", "POST",
                {"niveau": note.level, "titre": note.title,
                 "corps": note.body, "donnees": note.data},
                headers={"apikey": self.cle, "Authorization": f"Bearer {self.cle}",
                         "Prefer": "return=minimal"},
                timeout=10)
        except Exception as exc:
            logger.warning("alluxe bot indisponible : %s", str(exc)[:120])


class FirebasePushChannel(Channel):
    """Vraie notification push sur le telephone -- pas juste un onglet a
    ouvrir. Demande explicite de l'operateur, 15 sept. 2026 : « je veux
    qu'il envoie une notification quand il y a un achat, une vente ou le
    robot suspendu ».

    Passe par Firebase Cloud Messaging directement (HTTP v1), pas par le
    service push d'Expo : le projet Firebase existe deja pour Allure
    (allure-bot-d5a4c), Alluxe Bot y est enregistre comme 2e application
    Android. Le jeton d'acces OAuth2 est obtenu en signant un JWT avec la
    cle privee du compte de service (RS256) -- import de `jwt` fait a
    l'interieur de `_jeton_oauth`, jamais au sommet du fichier, pour
    qu'une dependance manquante ne puisse jamais faire planter tout le
    robot au demarrage : au pire, ce seul canal reste indisponible.
    """
    name = "firebase_push"

    def __init__(self, min_level: str = "trade") -> None:
        self.fichier_cle = os.getenv("FIREBASE_SERVICE_ACCOUNT_FILE", "")
        self.url_supabase = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.cle_supabase = os.getenv("SUPABASE_SERVICE_KEY", "")
        self.min_level = min_level
        self._jeton_acces = ""
        self._expire_le = 0.0

    def enabled(self) -> bool:
        return bool(self.fichier_cle and os.path.exists(self.fichier_cle)
                     and self.url_supabase and self.cle_supabase)

    def _jeton_oauth(self) -> str:
        if self._jeton_acces and time.time() < self._expire_le - 60:
            return self._jeton_acces
        import jwt  # noqa: PLC0415 -- import tardif, voir la docstring
        with open(self.fichier_cle, "r", encoding="utf-8") as f:
            info = json.load(f)
        maintenant = int(time.time())
        charge = {
            "iss": info["client_email"],
            "scope": "https://www.googleapis.com/auth/firebase.messaging",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": maintenant,
            "exp": maintenant + 3600,
        }
        assertion = jwt.encode(charge, info["private_key"], algorithm="RS256")
        corps = urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }).encode("utf-8")
        requete = urllib.request.Request(
            "https://oauth2.googleapis.com/token", data=corps, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(requete, timeout=15) as r:
            reponse = json.loads(r.read())
        self._jeton_acces = reponse["access_token"]
        self._expire_le = maintenant + int(reponse.get("expires_in", 3600))
        return self._jeton_acces

    def _jeton_appareil(self) -> str:
        requete = urllib.request.Request(
            f"{self.url_supabase}/rest/v1/alluxe_bot_prive?id=eq.robot&select=push_token",
            headers={"apikey": self.cle_supabase,
                     "Authorization": f"Bearer {self.cle_supabase}"})
        with urllib.request.urlopen(requete, timeout=10) as r:
            lignes = json.loads(r.read())
        return lignes[0]["push_token"] if lignes and lignes[0].get("push_token") else ""

    def send(self, note: Notification) -> None:
        if note.data.get("telephone") is False:
            return
        try:
            with open(self.fichier_cle, "r", encoding="utf-8") as f:
                projet = json.load(f)["project_id"]
            jeton_appareil = self._jeton_appareil()
            if not jeton_appareil:
                logger.warning("firebase push : aucun jeton d'appareil enregistre")
                return
            jeton_oauth = self._jeton_oauth()
            http_json(
                f"https://fcm.googleapis.com/v1/projects/{projet}/messages:send",
                "POST",
                {"message": {"token": jeton_appareil,
                             "notification": {"title": note.title, "body": note.body},
                             "android": {"priority": "high"}}},
                headers={"Authorization": f"Bearer {jeton_oauth}"},
                timeout=15)
        except Exception as exc:
            logger.warning("firebase push indisponible : %s", str(exc)[:150])


class WebhookChannel(Channel):
    name = "webhook"

    def __init__(self, url: str = "", min_level: str = "trade") -> None:
        self.url = url or os.getenv("GB_WEBHOOK_URL", "")
        self.min_level = min_level

    def enabled(self) -> bool:
        return bool(self.url)

    def send(self, note: Notification) -> None:
        text = note.as_text()
        payload = {"content": text, "text": text, "titre": note.title,
                   "niveau": note.level, "donnees": note.data}
        try:
            http_json(self.url, "POST", payload, timeout=10)
        except Exception as exc:
            logger.warning("webhook indisponible : %s", str(exc)[:120])


class OutboxChannel(Channel):
    name = "boite_envoi"

    def __init__(self, path: str = "", recipient: str = "", min_level: str = "warning") -> None:
        self.path = path or os.getenv("GB_OUTBOX_FILE", "data/outbox.jsonl")
        self.recipient = recipient or os.getenv("GB_ALERT_EMAIL", "")
        self.min_level = min_level

    def enabled(self) -> bool:
        return bool(self.recipient)

    def send(self, note: Notification) -> None:
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": note.ts, "destinataire": self.recipient,
                                     "sujet": f"[Robot] {note.title}", "corps": note.as_text(),
                                     "niveau": note.level, "envoye": False}, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("boite d'envoi non ecrite : %s", exc)


class Notifier:
    """Diffuse un evenement sur tous les canaux actifs avec anti-spam optionnel."""

    def __init__(self, channels: Optional[list[Channel]] = None) -> None:
        if channels is None:
            channels = [ConsoleChannel(), FileChannel(), TelegramChannel(),
                        AlluxeBotChannel(), FirebasePushChannel(),
                        WebhookChannel(), OutboxChannel()]
        self.channels = [c for c in channels if c.enabled()]
        self._last_sent: dict[str, float] = {}

    def active_channels(self) -> list[str]:
        return [channel.name for channel in self.channels]

    def send(self, note: Notification, throttle_key: str = "", throttle_seconds: float = 0.0) -> None:
        if throttle_key and throttle_seconds > 0:
            now = time.time()
            previous = self._last_sent.get(throttle_key, 0.0)
            if now - previous < throttle_seconds:
                return
            self._last_sent[throttle_key] = now
        for channel in self.channels:
            if channel.accepts(note.level):
                try:
                    channel.send(note)
                except Exception as exc:
                    logger.warning("notification %s indisponible : %s", channel.name, str(exc)[:120])

    def notify(self, level: str, title: str, body: str = "", data: Optional[dict] = None,
               throttle_key: str = "", throttle_seconds: float = 0.0) -> None:
        self.send(Notification(level=level, title=title, body=body, data=data or {}),
                  throttle_key=throttle_key, throttle_seconds=throttle_seconds)

    def debug(self, title: str, body: str = "", data: Optional[dict] = None, **kwargs) -> None:
        self.notify("debug", title, body, data, **kwargs)

    def info(self, title: str, body: str = "", data: Optional[dict] = None, **kwargs) -> None:
        self.notify("info", title, body, data, **kwargs)

    def trade(self, title: str, body: str = "", data: Optional[dict] = None, **kwargs) -> None:
        self.notify("trade", title, body, data, **kwargs)

    def warning(self, title: str, body: str = "", data: Optional[dict] = None, **kwargs) -> None:
        self.notify("warning", title, body, data, **kwargs)

    def critical(self, title: str, body: str = "", data: Optional[dict] = None, **kwargs) -> None:
        self.notify("critical", title, body, data, **kwargs)

    def error(self, title: str, body: str = "", data: Optional[dict] = None, **kwargs) -> None:
        self.notify("critical", title, body, data, **kwargs)


__all__ = ["Notification", "Notifier", "Channel", "ConsoleChannel", "FileChannel",
           "TelegramChannel", "WebhookChannel", "OutboxChannel", "http_json"]

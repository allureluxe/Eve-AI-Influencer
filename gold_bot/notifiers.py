"""Alertes et journal de bord.

Le robot tourne sans surveillance : il doit rendre des comptes. Chaque
evenement important (ouverture, extension d'objectif, cloture, coupe-circuit,
panne de source) part vers les canaux configures.

Canaux disponibles :
  - console      : toujours actif ;
  - fichier      : journal JSON Lines, exploitable pour l'analyse ;
  - Telegram     : alertes temps reel sur mobile (TELEGRAM_BOT_TOKEN + CHAT_ID) ;
  - webhook      : Discord, Slack ou n'importe quel endpoint (GB_WEBHOOK_URL) ;
  - boite d'envoi: fichier consomme par un connecteur mail (Gmail via MCP).
"""
from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .brokers.moonx import http_json

logger = logging.getLogger(__name__)

LEVEL_ORDER = {"debug": 10, "info": 20, "trade": 25, "warning": 30, "critical": 40}


@dataclass(slots=True)
class Notification:
    """Un evenement a diffuser."""

    level: str               # debug | info | trade | warning | critical
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
    """Journal JSON Lines : une ligne par evenement, facile a rejouer."""

    name = "fichier"

    def __init__(self, path: str = "", min_level: str = "debug") -> None:
        self.path = path or os.getenv("GB_JOURNAL_FILE", "data/journal.jsonl")
        self.min_level = min_level

    def send(self, note: Notification) -> None:
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "ts": note.ts, "date": note.stamp, "niveau": note.level,
                    "titre": note.title, "detail": note.body, "donnees": note.data,
                }, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("journal non ecrit : %s", exc)


class TelegramChannel(Channel):
    """Alertes mobiles. Variables : TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID."""

    name = "telegram"

    def __init__(self, min_level: str = "trade") -> None:
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.min_level = min_level

    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, note: Notification) -> None:
        try:
            http_json(f"https://api.telegram.org/bot{self.token}/sendMessage", "POST",
                      {"chat_id": self.chat_id, "text": note.as_text(),
                       "disable_web_page_preview": True}, timeout=10)
        except Exception as exc:  # noqa: BLE001
            logger.warning("telegram indisponible : %s", str(exc)[:120])


class WebhookChannel(Channel):
    """Webhook generique (Discord, Slack, n'importe quel endpoint HTTP)."""

    name = "webhook"

    def __init__(self, url: str = "", min_level: str = "trade") -> None:
        self.url = url or os.getenv("GB_WEBHOOK_URL", "")
        self.min_level = min_level

    def enabled(self) -> bool:
        return bool(self.url)

    def send(self, note: Notification) -> None:
        text = note.as_text()
        payload = {"content": text, "text": text,
                   "titre": note.title, "niveau": note.level, "donnees": note.data}
        try:
            http_json(self.url, "POST", payload, timeout=10)
        except Exception as exc:  # noqa: BLE001
            logger.warning("webhook indisponible : %s", str(exc)[:120])


class OutboxChannel(Channel):
    """Boite d'envoi fichier, consommee par un connecteur mail externe.

    Le robot n'a pas d'acces direct a une messagerie : il depose ses
    messages ici, et un connecteur (Gmail via MCP, script cron, etc.) les
    expedie. Cela evite de stocker des identifiants mail dans le robot.
    """

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
                fh.write(json.dumps({
                    "ts": note.ts, "destinataire": self.recipient,
                    "sujet": f"[Robot] {note.title}", "corps": note.as_text(),
                    "niveau": note.level, "envoye": False,
                }, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("boite d'envoi non ecrite : %s", exc)


class Notifier:
    """Diffuse un evenement sur tous les canaux actifs."""

    def __init__(self, channels: Optional[list[Channel]] = None) -> None:
        if channels is None:
            channels = [ConsoleChannel(), FileChannel(), TelegramChannel(),
                        WebhookChannel(), OutboxChannel()]
        self.channels = [c for c in channels if c.enabled()]
        self._throttle: dict[str, float] = {}

    def active_channels(self) -> list[str]:
        return [c.name for c in self.channels]

    def notify(self, level: str, title: str, body: str = "",
               data: Optional[dict] = None, throttle_key: str = "",
               throttle_seconds: float = 0.0) -> None:
        """Diffuse un evenement. `throttle_key` evite les alertes en rafale."""
        if throttle_key and throttle_seconds > 0:
            last = self._throttle.get(throttle_key, 0.0)
            if time.time() - last < throttle_seconds:
                return
            self._throttle[throttle_key] = time.time()

        note = Notification(level=level, title=title, body=body, data=data or {})
        for channel in self.channels:
            if not channel.accepts(level):
                continue
            try:
                channel.send(note)
            except Exception as exc:  # noqa: BLE001 - une alerte ne doit jamais casser le robot
                logger.warning("canal %s en echec : %s", channel.name, str(exc)[:120])

    # Raccourcis
    def info(self, title: str, body: str = "", **kw) -> None:
        self.notify("info", title, body, **kw)

    def trade(self, title: str, body: str = "", **kw) -> None:
        self.notify("trade", title, body, **kw)

    def warning(self, title: str, body: str = "", **kw) -> None:
        self.notify("warning", title, body, **kw)

    def critical(self, title: str, body: str = "", **kw) -> None:
        self.notify("critical", title, body, **kw)

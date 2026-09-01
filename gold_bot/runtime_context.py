"""Contexte d'execution : instance, chemins et verrou de session."""
from __future__ import annotations

import json
import os
import re
import socket
import time
from dataclasses import dataclass
from typing import Optional

from .settings import BotConfig, RACINE
from .state import ancrer, chemin_par_instance

try:  # pragma: no cover - specifique POSIX
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


def _fragment_instance(value: str) -> str:
    propre = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip())
    return propre.strip("-._")


def instance_key(config: BotConfig) -> str:
    broker = (config.engine.broker or "broker").strip()
    custom = _fragment_instance(getattr(config.engine, "instance_id", ""))
    return broker if not custom else f"{broker}-{custom}"


@dataclass(slots=True)
class RuntimePaths:
    instance: str
    state: str
    trades: str
    objectives: str
    journal: str
    lock: str


def runtime_paths(config: BotConfig) -> RuntimePaths:
    instance = instance_key(config)
    return RuntimePaths(
        instance=instance,
        state=chemin_par_instance("data/state.json", "GB_STATE_FILE", instance),
        trades=chemin_par_instance("data/trades.jsonl", "GB_TRADES_FILE", instance),
        objectives=chemin_par_instance("data/objectives.json", "GB_OBJECTIVE_FILE", instance),
        journal=ancrer(os.getenv("GB_JOURNAL_FILE", "data/journal.jsonl")),
        lock=ancrer(os.getenv("GB_LOCK_FILE", f"data/runtime-{instance}.lock")),
    )


def runtime_report(config: BotConfig, trades_count: int = 0) -> dict[str, object]:
    paths = runtime_paths(config)
    return {
        "cwd": os.getcwd(),
        "project_root": RACINE,
        "config_source": config.source_path or "<inconnue>",
        "gb_config": os.getenv("GB_CONFIG", ""),
        "gb_config_file": os.getenv("GB_CONFIG_FILE", ""),
        "broker": config.engine.broker,
        "instance_id": getattr(config.engine, "instance_id", ""),
        "instance": paths.instance,
        "state_path": paths.state,
        "trades_path": paths.trades,
        "objectives_path": paths.objectives,
        "journal_path": paths.journal,
        "lock_path": paths.lock,
        "trades_count": trades_count,
        "host": socket.gethostname(),
        "pid": os.getpid(),
    }


class RunLock:
    """Empêche deux robots d'écrire dans les mêmes fichiers d'instance."""

    def __init__(self, path: str, metadata: Optional[dict[str, object]] = None) -> None:
        self.path = path
        self.metadata = metadata or {}
        self._fh = None

    def acquire(self) -> None:
        if fcntl is None:  # pragma: no cover - l'environnement CI est POSIX
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._fh = open(self.path, "a+", encoding="utf-8")
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            holder = self.read_metadata() or {}
            detail = ", ".join(f"{k}={v}" for k, v in holder.items() if v not in ("", None)) or "verrou deja pris"
            raise RuntimeError(f"instance deja active ({detail}) — lock {self.path}") from exc
        self._fh.seek(0)
        self._fh.truncate()
        contenu = dict(self.metadata)
        contenu.setdefault("pid", os.getpid())
        contenu.setdefault("host", socket.gethostname())
        contenu.setdefault("cwd", os.getcwd())
        contenu.setdefault("acquired_at", int(time.time()))
        self._fh.write(json.dumps(contenu, ensure_ascii=False, indent=2))
        self._fh.flush()

    def read_metadata(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError, TypeError):
            return {}

    def release(self) -> None:
        if self._fh is None or fcntl is None:  # pragma: no cover - garde de confort
            return
        try:
            self._fh.close()
        finally:
            self._fh = None

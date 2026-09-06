"""Couche LLM avec repli automatique.

Le provider par défaut est `template` : aucune clé, aucun réseau, contenu
généré à partir de la bibliothèque locale. Les providers gratuits (Groq,
Google AI Studio, Ollama local) s'activent en posant une variable
d'environnement. En cas d'erreur réseau ou de quota, on retombe
silencieusement sur `template` — l'agent ne doit jamais s'arrêter pour ça.
"""
from __future__ import annotations

import json
import logging

import requests

from eve.config import settings

log = logging.getLogger(__name__)

TIMEOUT = 60


class LLMUnavailable(RuntimeError):
    pass


class BaseLLM:
    name = "base"

    def complete(self, system: str, user: str, *, max_tokens: int = 700) -> str:
        raise NotImplementedError

    def json_complete(self, system: str, user: str, *, max_tokens: int = 900) -> dict | list:
        raw = self.complete(system, user + "\n\nRéponds UNIQUEMENT en JSON valide, sans texte autour.",
                            max_tokens=max_tokens)
        return _parse_json(raw)


class TemplateLLM(BaseLLM):
    """Provider nul : signale simplement qu'aucun LLM n'est disponible.

    Les générateurs (`scripts.py`, `captions.py`) savent produire du contenu
    complet sans LLM ; ils n'appellent celui-ci que s'il existe.
    """

    name = "template"

    def complete(self, system: str, user: str, *, max_tokens: int = 700) -> str:
        raise LLMUnavailable("Aucun LLM configuré (mode template hors-ligne).")


class OllamaLLM(BaseLLM):
    name = "ollama"

    def __init__(self, url: str, model: str):
        self.url = url.rstrip("/")
        self.model = model or "llama3.1:8b"

    def complete(self, system: str, user: str, *, max_tokens: int = 700) -> str:
        r = requests.post(
            f"{self.url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "options": {"temperature": 0.8, "num_predict": max_tokens},
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json()["message"]["content"].strip()


class GroqLLM(BaseLLM):
    """Palier gratuit généreux, compatible OpenAI."""

    name = "groq"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model or "llama-3.3-70b-versatile"

    def complete(self, system: str, user: str, *, max_tokens: int = 700) -> str:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "temperature": 0.8,
                "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


class GeminiLLM(BaseLLM):
    """Google AI Studio — palier gratuit."""

    name = "gemini"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model or "gemini-3.6-flash"

    def complete(self, system: str, user: str, *, max_tokens: int = 700) -> str:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.api_key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0.8, "maxOutputTokens": max_tokens},
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


class AnthropicLLM(BaseLLM):
    """Payant, mais la meilleure qualité de script. Optionnel."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model or "claude-sonnet-5"

    def complete(self, system: str, user: str, *, max_tokens: int = 700) -> str:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            json={
                "model": self.model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json()["content"]).strip()


def get_llm() -> BaseLLM:
    g = settings.generation
    provider = (g.llm_provider or "template").lower()
    try:
        if provider == "ollama":
            return OllamaLLM(g.ollama_url, g.llm_model)
        if provider == "groq" and g.groq_api_key:
            return GroqLLM(g.groq_api_key, g.llm_model)
        if provider == "gemini" and g.gemini_api_key:
            return GeminiLLM(g.gemini_api_key, g.llm_model)
        if provider == "anthropic" and g.anthropic_api_key:
            return AnthropicLLM(g.anthropic_api_key, g.llm_model)
    except Exception as exc:  # pragma: no cover - défensif
        log.warning("Init LLM %s impossible (%s) — repli template.", provider, exc)
    if provider not in {"template", ""}:
        log.warning("Provider LLM « %s » demandé mais non configuré — repli template.", provider)
    return TemplateLLM()


def try_complete(llm: BaseLLM, system: str, user: str, *, max_tokens: int = 700) -> str | None:
    """Appel best-effort : renvoie None au lieu de lever."""
    try:
        text = llm.complete(system, user, max_tokens=max_tokens)
        return text or None
    except LLMUnavailable:
        return None
    except Exception as exc:
        log.warning("Appel LLM échoué (%s) — repli sur la génération locale.", exc)
        return None


def _parse_json(raw: str) -> dict | list:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
    start = min((i for i in (raw.find("{"), raw.find("[")) if i != -1), default=-1)
    if start == -1:
        raise ValueError("Aucun JSON trouvé dans la réponse du LLM.")
    end = max(raw.rfind("}"), raw.rfind("]"))
    return json.loads(raw[start:end + 1])

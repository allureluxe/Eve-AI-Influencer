#!/usr/bin/env python3
"""Alluxe MCP bridge.

A deliberately small stdio MCP server for ChatGPT. It does not expose a shell
or secrets. It talks to the existing Alluxe agent through the existing
Supabase message queue, so the VPS keeps its current guardrails and Claude/
OpenAI orchestration.

Environment:
  SUPABASE_URL
  SUPABASE_SERVICE_KEY
  ALLUXE_MCP_POLL_SECONDS (optional, default 1)
  ALLUXE_MCP_TIMEOUT_SECONDS (optional, default 120)
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request

PROTOCOL_VERSION = "2025-06-18"
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
POLL = float(os.environ.get("ALLUXE_MCP_POLL_SECONDS", "1"))
TIMEOUT = float(os.environ.get("ALLUXE_MCP_TIMEOUT_SECONDS", "120"))

TOOLS = [
    {
        "name": "alluxe_status",
        "description": "Ask the existing Alluxe agent for its current status and health. No system changes.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "alluxe_ask",
        "description": "Send a request to the existing Alluxe master agent on the VPS and wait for its verified answer. The existing Agent guardrails remain in force.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The request to Alluxe."}
            },
            "required": ["message"],
        },
    },
    {
        "name": "alluxe_recent",
        "description": "Return recent Alluxe conversation messages from Supabase. Does not execute anything.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10}
            },
        },
    },
]


def fail(msg: str) -> None:
    raise RuntimeError(msg)


def rest(method: str, path: str, body: dict | None = None) -> list | dict:
    if not SUPABASE_URL or not SUPABASE_KEY:
        fail("SUPABASE_URL or SUPABASE_SERVICE_KEY is missing")
    data = None
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(SUPABASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else []
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        fail(f"Supabase HTTP {e.code}: {detail}")


def latest_messages(limit: int) -> list:
    q = (
        "/rest/v1/alluxe_agent_messages"
        "?select=id,created_at,role,contenu,traite,outils"
        f"&order=id.desc&limit={int(limit)}"
    )
    return rest("GET", q)


def ask_agent(message: str) -> str:
    if not message.strip():
        fail("message is empty")

    # Unique marker makes the request auditable in the existing queue.
    request_id = uuid.uuid4().hex
    payload = (
        f"[MCP request {request_id}]\\n"
        "Traite cette demande exactement comme une demande normale de Monsieur. "
        "Ne reponds pas au marqueur ; il sert uniquement a identifier la requete.\\n"
        + message.strip()
    )
    inserted = rest("POST", "/rest/v1/alluxe_agent_messages?select=id,created_at", {
        "role": "user",
        "contenu": payload,
        "traite": False,
        "outils": [],
    })
    if not inserted:
        fail("Alluxe did not accept the message")
    request_row = inserted[0]
    request_id_db = int(request_row["id"])
    deadline = time.monotonic() + TIMEOUT

    while time.monotonic() < deadline:
        rows = rest(
            "GET",
            "/rest/v1/alluxe_agent_messages"
            "?select=id,role,contenu,traite,outils"
            f"&id=gt.{request_id_db}&role=eq.assistant&order=id.asc&limit=1",
        )
        if rows:
            return str(rows[0].get("contenu") or "")
        time.sleep(POLL)

    fail(f"Timed out waiting for Alluxe (request database id {request_id_db})")


def handle(req: dict) -> dict | None:
    method = req.get("method")
    rid = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "alluxe-vps", "version": "1.0.0"},
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            if name == "alluxe_status":
                answer = ask_agent("Donne uniquement ton état actuel, les services importants en erreur éventuelle, et ce qui est en cours. Ne modifie rien.")
            elif name == "alluxe_ask":
                answer = ask_agent(str(args.get("message", "")))
            elif name == "alluxe_recent":
                limit = max(1, min(20, int(args.get("limit", 10))))
                rows = latest_messages(limit)
                answer = json.dumps(rows, ensure_ascii=False, indent=2)
            else:
                fail(f"unknown tool: {name}")
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "result": {"content": [{"type": "text", "text": answer}], "isError": False},
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "result": {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            }

    # Unknown notifications may be ignored; unknown requests get a JSON-RPC error.
    if rid is not None:
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    return None


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            response = handle(req)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            # JSON-RPC parse/transport errors are returned without exposing env.
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": str(exc)},
            }) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

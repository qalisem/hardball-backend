"""All HTTP routes live here.

Three concerns, three routes:
  GET  /api/health          - liveness probe for Elastic Beanstalk
  GET  /api/teams           - list of team summaries
  GET  /api/teams/<abbr>    - full team detail
  POST /api/chat            - proxy to Anthropic, keeps API key server-side
"""
import json
import os
import time
from pathlib import Path

import requests
from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("api", __name__, url_prefix="/api")

# ─── Team data ───────────────────────────────────────────────────────────────

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "teams.json"
with open(DATA_PATH, "r", encoding="utf-8") as f:
    _DATA = json.load(f)

TEAMS = {k: v for k, v in _DATA.items() if not k.startswith("_")}
META = _DATA.get("_meta", {})


# ─── Anthropic config ────────────────────────────────────────────────────────

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MAX_TOKENS = 1000
MAX_HISTORY = 30

SYSTEM_PROMPT = """You are Hardball, an NBA salary cap and CBA analyst. Answer
questions about contracts, the cap, the luxury tax, and the first/second apron
using real dollar figures. Use **bold** for key figures and team names. End
each answer with a single follow-up question prefixed with `→ `."""


# ─── Routes ──────────────────────────────────────────────────────────────────

@bp.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "hardball-api",
        "ts": int(time.time()),
        "season": META.get("season", "2025-26"),
        "data_as_of": META.get("as_of"),
        "team_count": len(TEAMS),
    })


@bp.route("/teams", methods=["GET"])
def list_teams():
    summaries = [
        {
            "abbr": t["abbr"],
            "name": t["name"],
            "payroll": t["payroll"],
            "status": t["status"],
            "summary": t["summary"],
        }
        for t in TEAMS.values()
    ]
    summaries.sort(key=lambda x: x["payroll"], reverse=True)
    return jsonify({
        "teams": summaries,
        "season": META.get("season"),
        "thresholds": META.get("thresholds", {}),
    })


@bp.route("/teams/<abbr>", methods=["GET"])
def get_team(abbr):
    team = TEAMS.get(abbr.upper())
    if not team:
        return jsonify({"error": "team_not_found", "abbr": abbr}), 404
    return jsonify(team)


@bp.route("/chat", methods=["POST"])
def chat():
    """Proxy to Anthropic. The whole reason this backend exists.

    Frontend sends: {"messages": [{"role": "user", "content": "..."}, ...]}
    We add the system prompt, the API key, and forward to Anthropic.
    The key never touches the browser.
    """
    body = request.get_json(silent=True) or {}
    messages = body.get("messages")

    # Validate input shape — never blindly forward whatever the client sent
    if not isinstance(messages, list) or not messages:
        return jsonify({"error": "messages_required"}), 400
    if len(messages) > MAX_HISTORY:
        messages = messages[-MAX_HISTORY:]

    cleaned = []
    for m in messages:
        if not isinstance(m, dict):
            return jsonify({"error": "bad_message_shape"}), 400
        role = m.get("role")
        content = m.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            return jsonify({"error": "bad_message_shape"}), 400
        if not content.strip():
            continue
        cleaned.append({"role": role, "content": content[:8000]})

    if not cleaned:
        return jsonify({"error": "empty_messages"}), 400

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or not api_key.strip():
        current_app.logger.error("ANTHROPIC_API_KEY not configured")
        return jsonify({"error": "server_misconfigured"}), 500

    payload = {
        "model": os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": cleaned,
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
    }

    try:
        r = requests.post(ANTHROPIC_URL, json=payload, headers=headers, timeout=60)
    except requests.RequestException as e:
        current_app.logger.warning("Anthropic request failed: %s", e)
        return jsonify({"error": "upstream_unreachable"}), 502

    if r.status_code != 200:
        current_app.logger.warning(
            "Anthropic non-200: status=%s body=%s", r.status_code, r.text[:300]
        )
        return jsonify({"error": "upstream_error", "status": r.status_code}), 502

    data = r.json()
    text = "\n".join(
        block.get("text", "")
        for block in data.get("content", [])
        if block.get("type") == "text"
    ).strip()

    if not text:
        return jsonify({"error": "empty_response"}), 502

    return jsonify({
        "reply": text,
        "model": data.get("model"),
        "usage": data.get("usage"),
    })

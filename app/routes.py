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
# Loaded once at import time from data/teams.json.
# In a future iteration, swap this for an RDS Postgres query.

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "teams.json"
with open(DATA_PATH, "r", encoding="utf-8") as f:
    _DATA = json.load(f)

# Strip the _meta key — only return real teams from the API
TEAMS = {k: v for k, v in _DATA.items() if not k.startswith("_")}
META = _DATA.get("_meta", {})


# ─── Anthropic config ────────────────────────────────────────────────────────

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MAX_TOKENS = 1000
MAX_HISTORY = 30  # cap conversation length to control token spend

SYSTEM_PROMPT = """You are Hardball, an expert NBA salary cap and sports finance analyst AI. You have deep knowledge of the NBA CBA, salary cap rules, luxury tax thresholds, contract structures (max contracts, rookie scale, veteran minimums, two-way contracts, 10-day contracts), Bird Rights, trade rules (aggregation, 125%+$100K rule), draft pick restrictions, and team-building strategy implications of financial decisions.

Current 2025-26 NBA figures:
- Salary cap: $154.647M
- Luxury tax line: $187.895M
- First apron: $195.945M (hard cap when triggered by NTMLE, BAE, or sign-and-trade)
- Second apron: $207.824M (hard cap when triggered by TMLE)
- Minimum team salary: $139.182M

Mid-Level Exceptions for 25-26:
- Non-Taxpayer MLE: $14.104M (4-year contracts)
- Taxpayer MLE: $5.685M (3-year contracts) — triggers second-apron hard cap
- Cap-Room MLE: $8.781M (3-year contracts)

Key team situations as of March 2026 (sourced from Sports Business Classroom apron tracker):

Above second apron / hard-capped at second apron:
- Cleveland: $211.7M (over by $3.9M, no exception trigger needed)
- Golden State: $204.4M (TMLE trigger via Horford)
- New York: $207.5M (TMLE trigger, only $0.4M under)
- Boston: $187.3M (cash-out trigger)
- Oklahoma City: $187.2M (cash-out trigger)
- Minnesota: $195.7M (S&T-out trigger)
- Dallas: $187.5M (TMLE trigger)
- Philadelphia: $193.6M (TMLE trigger)
- Phoenix: $188.4M (cash-out trigger)
- Brooklyn: $151.3M (cash-out trigger but lowest payroll)

Hard-capped at first apron (most common):
- Lakers $195.3M (Doncic + LeBron, only $0.6M under apron 1)
- Toronto $193.4M (Barnes max + Ingram + Quickley)
- Atlanta $186.8M (post-Trae trade)
- Detroit $187.1M (Cunningham max + new pieces)
- Miami $189.5M (post-Butler era)
- Houston $194.7M (Durant arrival)
- Indiana $188.3M (Haliburton injured)
- Sacramento $192.0M (LaVine + Hunter additions)
- Orlando $188.6M (Bane trade)
- New Orleans $194.5M (Murray + Zion)
- LA Clippers $190.1M (Beal + Lopez additions)
- Plus 8 others

No hard-cap restriction:
- Denver $192.1M (under first apron, full MLE available)

Major reshape moves: Doncic→Lakers (Feb 2025), Butler→Warriors (Feb 2025), KAT→Knicks (Oct 2024), Bane→Magic (mid-2025), KD→Rockets (mid-2025), Bridges→Knicks (2024), Trae Young→Wizards (2025).

Key extensions kicking in 25-26: Tatum supermax ($54.1M), Brown ($53.1M), SGA ($38.3M), Mitchell ($50.6M), Doncic ($45M start), Mobley ($38.2M rookie max), Banchero/Wagner rookie max ($45M / $40M), Cunningham rookie max ($46.4M), Sengun rookie max ($33.8M).

Answer questions accurately, use real dollar figures, explain NBA jargon clearly, and always help the user understand the strategic implications. Keep answers concise but complete. You are not giving legal or financial advice — this is sports analysis.

When asked about a team you don't have explicit data for, reason from general CBA knowledge and acknowledge if specific figures aren't certain.

FORMATTING RULES:
- Use **bold** for key figures, team names, player names, and critical CBA terms.
- Keep paragraphs tight (2-4 sentences each).
- Use short bullet lists prefixed with "- " only when comparing items or listing 3+ parallel points.
- Always end with a single follow-up question on its own line, prefixed with "→ " — for example: "→ Want me to walk through how the second apron restricts Cleveland's flexibility this deadline?\""""


# ─── Routes ──────────────────────────────────────────────────────────────────

@bp.route("/health", methods=["GET"])
def health():
    """Elastic Beanstalk health check hits this."""
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
    """Return all teams as compact summaries (no roster bloat)."""
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
    # Sort by payroll desc — most interesting teams first
    summaries.sort(key=lambda x: x["payroll"], reverse=True)
    return jsonify({
        "teams": summaries,
        "season": META.get("season"),
        "thresholds": META.get("thresholds", {}),
    })


@bp.route("/teams/<abbr>", methods=["GET"])
def get_team(abbr):
    """Return full team detail including roster + strategic notes."""
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

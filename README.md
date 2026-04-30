# Hardball — NBA Cap Intelligence (Backend)

Hardball is an AI-powered NBA salary cap and CBA analyst. Ask natural-language questions about contracts, luxury tax, the first/second apron, hard caps, and trade math, and get answers grounded in real 2025-26 figures for all 30 teams. This repository is the Flask backend that proxies to the Anthropic API and serves team data; the React frontend lives in [qalisem/hardball-web](https://github.com/qalisem/hardball-web).

**Live demo:** https://dz3csw06yjedg.cloudfront.net

---

## Architecture

```
                    ┌────────────────────────────────────┐
  Browser (HTTPS) ─▶│  CloudFront  (E1AEOT2IV7WSET)      │
                    └────────────────────────────────────┘
                          │                    │
                 default  │                    │ /api/*
                          ▼                    ▼
                ┌──────────────────┐   ┌────────────────────────────┐
                │  S3 static site  │   │  Elastic Beanstalk         │
                │  hardball-web-   │   │  hardball-api-prod         │
                │  qali (us-east-1)│   │  Flask + Gunicorn          │
                └──────────────────┘   └────────────────────────────┘
                                                 │
                                                 ▼
                                       ┌────────────────────┐
                                       │  Anthropic API     │
                                       │  (claude-haiku-4-5)│
                                       └────────────────────┘

  ANTHROPIC_API_KEY: stored in AWS Secrets Manager,
  injected into Elastic Beanstalk environment via `eb setenv`.
```

The frontend is served from S3 through CloudFront over HTTPS. CloudFront has a second behavior on `/api/*` that points at the Elastic Beanstalk environment over HTTP/80. This makes the API same-origin from the browser's perspective — no CORS, no mixed-content blocking, no ACM cert needed on the EB load balancer.

## Stack

- **Runtime:** Python 3.11
- **Web framework:** Flask 3.0.3
- **WSGI server:** Gunicorn 22
- **HTTP client:** `requests` 2.32
- **CORS:** `Flask-CORS` (kept for local dev; production is same-origin)
- **Tests:** `pytest` (8 tests)
- **CI:** GitHub Actions (`.github/workflows/ci.yml`) runs pytest on every PR

## API

| Method | Path                  | Purpose                                              |
|--------|-----------------------|------------------------------------------------------|
| GET    | `/api/health`         | Liveness probe (Elastic Beanstalk health check)      |
| GET    | `/api/teams`          | All 30 teams as compact summaries, sorted by payroll |
| GET    | `/api/teams/<abbr>`   | Full team detail (roster, contract notes, status)    |
| POST   | `/api/chat`           | Proxy to Anthropic with the Hardball system prompt   |

`POST /api/chat` request body:

```json
{
  "messages": [
    {"role": "user", "content": "Why is Cleveland over the second apron?"}
  ]
}
```

Response body:

```json
{
  "reply": "Cleveland's payroll sits at **$211.7M** ...",
  "model": "claude-haiku-4-5-20251001",
  "usage": {"input_tokens": 1200, "output_tokens": 240}
}
```

## Local development

```bash
git clone https://github.com/qalisem/hardball-backend.git
cd hardball-backend

python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and fill in your ANTHROPIC_API_KEY

export $(grep -v '^#' .env | xargs)
python application.py
# server now on http://localhost:5000
```

Smoke test:

```bash
curl http://localhost:5000/api/health
curl http://localhost:5000/api/teams/LAL
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"What is the second apron?"}]}'
```

## Tests

```bash
pytest tests/ -v
```

8 tests covering health, team list, team detail (found / lowercase / not found), and `/api/chat` input validation (empty messages, bad shape, missing API key).

## Documentation

- [`docs/DEPLOY.md`](docs/DEPLOY.md) — full AWS deploy walkthrough (Elastic Beanstalk + S3 + CloudFront)
- [`docs/PROCESS.md`](docs/PROCESS.md) — sprint history, retros, and definition of done
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — architecture decision record

## License

MIT

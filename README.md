# Hardball — NBA Cap Intelligence (Backend)

Flask backend for Hardball, an AI-powered NBA salary cap and CBA analyst. Exposes a small JSON API: `/api/teams`, `/api/teams/<abbr>`, `/api/chat`. The chat endpoint is a thin proxy over the Anthropic API so the API key never ships to the browser.

The frontend lives in [qalisem/hardball-web](https://github.com/qalisem/hardball-web).

## Stack

Python 3.11, Flask 3, Gunicorn, `requests`, `Flask-CORS`. Tests run under `pytest`.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in ANTHROPIC_API_KEY
export $(grep -v '^#' .env | xargs)
python application.py
```

## License

MIT

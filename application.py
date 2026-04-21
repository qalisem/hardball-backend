"""WSGI entrypoint.

Elastic Beanstalk's Python platform looks for a top-level `application`
callable by default. Gunicorn and `flask run` work the same way.
"""
from app import create_app

application = create_app()

if __name__ == "__main__":
    # Local dev: `python application.py`
    application.run(host="0.0.0.0", port=5000, debug=True)

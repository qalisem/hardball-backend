"""Hardball Flask app factory."""
import os
import logging
from flask import Flask, jsonify
from flask_cors import CORS


def create_app():
    app = Flask(__name__)

    # Logging — Elastic Beanstalk pipes stdout to CloudWatch automatically
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # CORS — in production, lock this down to your S3/CloudFront origin
    allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
    CORS(app, resources={r"/api/*": {"origins": allowed_origins}})

    # Register routes
    from app.routes import bp
    app.register_blueprint(bp)

    # Global error handlers — never leak stack traces to the client
    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"error": "not_found"}), 404

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception("Unhandled server error: %s", e)
        return jsonify({"error": "server_error"}), 500

    return app

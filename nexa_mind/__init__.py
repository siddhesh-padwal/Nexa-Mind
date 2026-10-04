import os
import secrets
from pathlib import Path

from flask import Flask, jsonify, request, session
from werkzeug.exceptions import HTTPException

from . import storage
from .services.vision import VisionService
from .services.conversation import ConversationService
from .services.knowledge import KnowledgeService


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    root = Path(os.environ.get("NEXA_DATA_DIR", app.instance_path)).resolve()
    app.config.from_mapping(
        DATA_DIR=root,
        MAX_CONTENT_LENGTH=9 * 1024 * 1024,
        MAX_FORM_MEMORY_SIZE=128 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        TRUSTED_HOSTS=["127.0.0.1", "localhost", "[::1]"],
    )
    if config:
        app.config.update(config)
    root = Path(app.config["DATA_DIR"])
    root.mkdir(parents=True, exist_ok=True)
    (root / "uploads").mkdir(exist_ok=True)
    secret = root / ".secret"
    if not app.config.get("SECRET_KEY"):
        try:
            with secret.open("x", encoding="utf-8") as f:
                f.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        app.config["SECRET_KEY"] = secret.read_text(encoding="utf-8")
    storage.init_app(app)
    app.extensions["vision"] = app.config.get("VISION_SERVICE") or VisionService(root / "models")
    app.extensions["conversation"] = app.config.get("CONVERSATION_SERVICE") or ConversationService(root / "models")
    app.extensions["knowledge"] = app.config.get("KNOWLEDGE_SERVICE") or KnowledgeService()

    @app.before_request
    def csrf_guard():
        if request.method in {"POST", "DELETE", "PUT", "PATCH"}:
            expected = session.get("csrf")
            supplied = request.headers.get("X-CSRF-Token", "")
            if not expected or not secrets.compare_digest(expected, supplied):
                return jsonify(error="Your session expired. Refresh this page and try again."), 403

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(self)"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' blob: data: https://upload.wikimedia.org https://thumb.wikimedia.org; media-src 'self' blob:; "
            "connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        )
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        message = "The upload is too large. Choose an image under 8 MB." if error.code == 413 else error.description
        return jsonify(error=message), error.code

    @app.errorhandler(Exception)
    def unexpected_error(error):
        app.logger.exception("Request failed")
        return jsonify(error="The request could not be completed. Check the server log and try again."), 500

    from .routes import bp
    app.register_blueprint(bp)
    return app

"""HMAC-SHA256 signature verification for GitHub webhook payloads."""

import hashlib
import hmac
import logging
import os

from flask import Flask, jsonify, request

logger = logging.getLogger(__name__)


def verify_signature(body: bytes, secret: str, signature_header) -> bool:
    """Return True iff signature_header is a valid sha256= HMAC over body with secret.

    Uses hmac.compare_digest for constant-time comparison to prevent timing attacks.
    """
    if not signature_header or not isinstance(signature_header, str):
        return False

    if not signature_header.startswith("sha256="):
        return False

    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    provided = signature_header[len("sha256="):]
    return hmac.compare_digest(expected, provided)


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    webhook_secret = os.environ.get("WEBHOOK_SECRET")
    if not webhook_secret:
        # Warn operators at startup — all webhook requests will be rejected without a secret.
        logger.warning(
            "WEBHOOK_SECRET is not set. All webhook requests will be rejected."
        )

    @app.route("/webhook", methods=["POST"])
    def webhook():
        body = request.get_data()
        sig_header = request.headers.get("X-Hub-Signature-256")

        if not webhook_secret:
            logger.warning("Webhook request rejected: WEBHOOK_SECRET not configured")
            return jsonify({"error": "Webhook secret not configured"}), 401

        if not sig_header:
            logger.warning("Webhook request rejected: missing X-Hub-Signature-256 header")
            return jsonify({"error": "Missing X-Hub-Signature-256 header"}), 401

        if not verify_signature(body, webhook_secret, sig_header):
            logger.warning("Webhook request rejected: invalid signature")
            return jsonify({"error": "Invalid signature"}), 401

        return jsonify({"status": "ok"}), 200

    return app

"""Tiny Flask factory + one redirect route for synthesis tests."""
from flask import Flask, redirect


def create_app() -> Flask:
    app = Flask(__name__)

    @app.route("/r/<slug>")
    def redirect_slug(slug: str):
        return redirect(f"https://example.test/{slug}", code=302)

    return app

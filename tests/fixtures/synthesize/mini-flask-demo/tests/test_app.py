"""Pytest tests for miniflask — used as observation source by ground_analogue."""
import pytest

from miniflask import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_create_app_returns_flask_instance():
    app = create_app()
    assert app is not None


def test_redirect_returns_302(client):
    response = client.get("/r/abc")
    assert response.status_code == 302
    assert response.location == "https://example.test/abc"

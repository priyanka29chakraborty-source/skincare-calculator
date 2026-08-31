"""CSRF protection on state-changing admin routes.

The admin session cookie is SameSite=None, which is REQUIRED because the public
frontend lives on a different origin from this API. The consequence is that the
browser attaches the admin cookie to cross-site requests too, so a page an
admin merely visits could fire an admin action in their session.

CORS does not prevent this. CORS governs whether the attacker can READ the
response, not whether the browser SENDS the request - and by the time the read
is blocked, the deletion has already happened.

Note these tests use base_url="https://testserver": the session cookie is
Secure, so over plain http the client never sends it back and every request
looks unauthenticated.
"""

import os
import re
import sys

import pytest

os.environ.setdefault("ADMIN_PASSWORD", "testpw123")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

STATE_CHANGING = [
    "/api/admin/clear-old-logs",   # deletes log rows
    "/api/admin/reload-csv",
]


def _client():
    return TestClient(server.app, base_url="https://testserver")


def _logged_in():
    """A client with a real admin session, plus that session's CSRF token."""
    c = _client()
    r = c.post("/api/admin/login", data={"password": os.environ["ADMIN_PASSWORD"]},
               follow_redirects=False)
    assert r.status_code == 302, "login failed; check ADMIN_PASSWORD"
    page = c.get("/api/admin/dashboard", follow_redirects=False)
    assert page.status_code == 200, "dashboard did not render for a valid session"
    m = re.search(r'const CSRF = "([0-9a-f]+)"', page.text)
    assert m, "dashboard did not embed a CSRF token"
    return c, m.group(1)


def test_dashboard_embeds_a_session_bound_token():
    _, token = _logged_in()
    assert len(token) >= 32


def test_two_sessions_get_different_tokens():
    """A token must be bound to its own session, so one admin's token cannot
    authorise an action in another's."""
    _, a = _logged_in()
    _, b = _logged_in()
    assert a != b


@pytest.mark.parametrize("path", STATE_CHANGING)
def test_valid_session_without_token_is_rejected(path):
    """This is the attack: the browser supplies the cookie automatically, the
    attacker's page cannot supply the token."""
    c, _ = _logged_in()
    assert c.post(path).status_code == 403


@pytest.mark.parametrize("path", STATE_CHANGING)
def test_wrong_token_is_rejected(path):
    c, _ = _logged_in()
    assert c.post(path, headers={"X-CSRF-Token": "0" * 64}).status_code == 403


@pytest.mark.parametrize("path", STATE_CHANGING)
def test_cross_site_request_is_rejected_even_with_a_valid_token(path):
    """Defence in depth. Sec-Fetch-Site is set by the browser and cannot be
    forged by page JavaScript."""
    c, token = _logged_in()
    r = c.post(path, headers={"X-CSRF-Token": token, "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


@pytest.mark.parametrize("path", STATE_CHANGING)
def test_legitimate_dashboard_request_still_works(path):
    """The fix must not break the admin panel itself."""
    c, token = _logged_in()
    r = c.post(path, headers={"X-CSRF-Token": token, "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200


@pytest.mark.parametrize("path", STATE_CHANGING)
def test_unauthenticated_is_401_not_403(path):
    """No session is an authentication failure, not a CSRF failure - the
    distinction matters for anyone reading the logs."""
    assert _client().post(path).status_code == 401


def test_public_api_needs_no_csrf_token():
    """Public endpoints are not cookie-authenticated, so CSRF does not apply and
    they must be completely unaffected."""
    r = _client().post("/api/analyze", json={
        "ingredients": "Aqua, Niacinamide, Glycerin, Phenoxyethanol",
        "price": 500, "size_ml": 30, "category": "Serum", "skin_type": "oily"})
    assert r.status_code == 200
    assert "formulation_score" in r.json()

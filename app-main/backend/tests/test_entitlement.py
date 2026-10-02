"""Paywall integrity.

The rule: the server never sends data the user has not paid for.

Most paywalls fail by returning the full payload and hiding the paid parts in
the frontend - one press of F12 away from free. These tests assert the paid
data is genuinely ABSENT from the wire, so there is nothing to reveal by
editing client code, forging headers, or replaying the request.

They also assert the inverse, which matters just as much: safety information is
never withheld. Charging someone to learn a product may be unsafe for them in
pregnancy would make the tool actively harmful to the people with most at stake.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402
from entitlement import (  # noqa: E402
    ALWAYS_FREE_ADVISORIES,
    FREE_KEYS,
    PAID_KEYS,
    audit_no_paid_leakage,
    filter_for_entitlement,
)

PAYLOAD = {
    "ingredients": ("Aqua, Glycolic Acid, Glycerin, Retinol, Niacinamide, "
                    "Parfum, Limonene, Panthenol, Phenoxyethanol"),
    "price": 599, "size_ml": 30, "category": "Serum",
    "skin_concerns": ["Uneven Texture", "Pigmentation"],
    "skin_type": "combination", "country": "India", "currency": "INR",
}


@pytest.fixture
def client():
    return TestClient(server.app, base_url="https://testserver")


@pytest.fixture(autouse=True)
def _free_by_default(monkeypatch):
    monkeypatch.setattr(server, "_resolve_entitlement",
                        lambda request, product_data=None: False)
    # /api/analyze is rate-limited to 10/minute per IP. This file makes more
    # requests than that from one address, so without disabling the limiter the
    # later tests receive a 429 whose body has no "access" key - which looks
    # exactly like a paywall failure and is not one.
    monkeypatch.setattr(server.limiter, "enabled", False)


def _unique(**over):
    """A payload with a distinct cache key, so tests do not collide."""
    import uuid
    return {**PAYLOAD, "product_name": str(uuid.uuid4()), **over}


def _has_paid_data(response):
    """Paid DATA, not paid key names - the names legitimately appear in the
    'locked' list and the honest preview, and finding those is not a leak."""
    body = response.json()
    if set(body) & PAID_KEYS:
        return True
    return '"present_actives"' in response.text or '"fit_level"' in response.text


# --- The paid data must not be on the wire ---------------------------------


def test_free_response_omits_every_paid_key(client):
    body = client.post("/api/analyze", json=_unique()).json()
    leaked = sorted(set(body) & PAID_KEYS)
    assert not leaked, "free response carried paid keys: {}".format(leaked)
    assert body["access"]["tier"] == "free"


def test_free_response_still_contains_the_free_analysis(client):
    """Gating must not gut the free tier - it is the acquisition engine."""
    body = client.post("/api/analyze", json=_unique()).json()
    for key in ("formulation_score", "formulation_breakdown", "value_assessment",
                "identified_actives", "formulation_confidence"):
        assert key in body, "free tier lost {}".format(key)
    assert body["formulation_score"] > 0


@pytest.mark.parametrize("attack", [
    {"entitled": True},
    {"is_paid": True},
    {"tier": "full"},
    {"access": {"tier": "full"}},
    {"user_profile": {"entitled": True}},
])
def test_claiming_entitlement_in_the_request_body_does_nothing(client, attack):
    """A client-supplied entitlement flag is a request to be trusted, not proof
    of payment. If any of these worked, the paywall would be one editable
    JSON field."""
    r = client.post("/api/analyze", json=_unique(**attack))
    assert not _has_paid_data(r)
    assert r.json()["access"]["tier"] == "free"


@pytest.mark.parametrize("headers", [
    {"X-Entitled": "true"}, {"X-Tier": "full"},
    {"Authorization": "Bearer anything"}, {"X-Paid": "1"},
])
def test_forged_headers_do_nothing(client, headers):
    r = client.post("/api/analyze", json=_unique(), headers=headers)
    assert not _has_paid_data(r)


def test_forged_cookies_do_nothing(client):
    r = client.post("/api/analyze", json=_unique(),
                    cookies={"paid": "1", "tier": "full", "entitled": "yes"})
    assert not _has_paid_data(r)


def test_cache_hits_are_gated_too(client):
    """Regression guard for a real leak found during development.

    The cache stores the FULL result so one entry can serve both tiers. An
    early version returned the cached object directly, which handed a free
    caller the paid data whenever anyone had analysed the same product before
    them - a leak that only appears on the second request, so it is easy to
    miss.
    """
    payload = _unique()
    for attempt in range(3):
        r = client.post("/api/analyze", json=payload)
        assert not _has_paid_data(r), "leaked on request {}".format(attempt + 1)
        assert r.json()["access"]["tier"] == "free"


def test_entitled_caller_receives_the_full_result(client, monkeypatch):
    monkeypatch.setattr(server, "_resolve_entitlement",
                        lambda request, product_data=None: True)
    body = client.post("/api/analyze", json=_unique()).json()
    assert body["access"]["tier"] == "full"
    assert "skin_concern_fit" in body
    assert "skin_type_compatibility" in body


# --- Safety is never for sale ----------------------------------------------


def test_pregnancy_advisory_is_never_paywalled(client):
    """Retinol is the strongest case: the database marks it strictly avoid in
    pregnancy. That must reach a free user in full."""
    body = client.post("/api/analyze", json=_unique()).json()
    types = {f["type"] for f in body.get("advisory_flags", [])}
    assert "pregnancy" in types


def test_declared_allergy_warning_is_never_paywalled(client):
    """If a user tells us they react to something and it is in the product,
    withholding that behind a paywall would be indefensible."""
    body = client.post("/api/analyze", json=_unique(
        user_profile={"allergens": ["fragrance"]})).json()
    types = {f["type"] for f in body.get("advisory_flags", [])}
    assert "declared_allergen" in types


def test_formulation_safety_flags_stay_free(client):
    """Missing preservative, unstable active and weak-UVA warnings are product
    safety, not personalisation."""
    body = client.post("/api/analyze", json=_unique()).json()
    assert "formulation_flags" in body
    assert any(f["type"] == "unstabilised_active" for f in body["formulation_flags"])


def test_personal_optimisation_advisories_are_gated(client):
    """Fit-related advisories are the paid product and must not leak."""
    body = client.post("/api/analyze", json=_unique(
        user_profile={"fitzpatrick": "V", "current_routine": "retinol"})).json()
    types = {f["type"] for f in body.get("advisory_flags", [])}
    assert not (types - ALWAYS_FREE_ADVISORIES), (
        "personal advisories leaked: {}".format(types - ALWAYS_FREE_ADVISORIES))


# --- The paywall must be honest --------------------------------------------


def test_user_is_told_exactly_what_is_locked(client):
    """No dark patterns: say what is behind the wall and what was found."""
    access = client.post("/api/analyze", json=_unique()).json()["access"]
    assert access["locked"], "must state what is locked"
    assert access["message"] and access["safety_note"]
    preview = access["preview"]
    assert preview["concerns_assessed"] == 2
    assert set(preview["concern_names"]) == {"Uneven Texture", "Pigmentation"}


def test_preview_reveals_existence_not_content(client):
    """The teaser must not smuggle the answer out inside itself."""
    preview = client.post("/api/analyze", json=_unique()).json()["access"]["preview"]
    for value in preview.values():
        assert not isinstance(value, dict), "preview must not carry score objects"


# --- Unit-level guards ------------------------------------------------------


def test_free_and_paid_key_sets_do_not_overlap():
    assert not (FREE_KEYS & PAID_KEYS)


def test_audit_raises_when_a_paid_key_slips_through():
    with pytest.raises(AssertionError):
        audit_no_paid_leakage({"formulation_score": 80, "skin_concern_fit": {}})


def test_audit_raises_on_a_leaked_personal_advisory():
    with pytest.raises(AssertionError):
        audit_no_paid_leakage({"advisory_flags": [{"type": "pih_risk"}]})


def test_filter_is_a_pure_function_of_entitlement():
    full = {"formulation_score": 80, "skin_concern_fit": {"Acne": 70},
            "advisory_flags": [{"type": "pregnancy"}, {"type": "pih_risk"}]}
    assert "skin_concern_fit" in filter_for_entitlement(full, True)
    assert "skin_concern_fit" not in filter_for_entitlement(full, False)
    # The original must not be mutated - it is what goes into the cache.
    assert "skin_concern_fit" in full

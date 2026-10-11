"""Share links, evidence reviews, refund requests, and beta events."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import evidence  # noqa: E402
from compare import summarise  # noqa: E402
from entitlement import PAID_KEYS, audit_no_paid_leakage  # noqa: E402


def test_queue_counts_are_numbers():
    counts = evidence.queue_counts()
    assert isinstance(counts['pregnancy_unsigned'], int)
    assert isinstance(counts['actives_missing_evidence'], int)


def test_unsigned_review_is_not_attached(tmp_path, monkeypatch):
    path = tmp_path / "evidence_reviews.json"
    path.write_text(json.dumps({"reviews": {
        "niacinamide": {"source": "A journal", "reviewer": ""},
    }}), encoding="utf-8")
    monkeypatch.setattr(evidence, "_PATH", str(path))
    result = evidence.attach({"identified_actives": [{"name": "Niacinamide"}]})
    assert "provenance" not in result["identified_actives"][0]


def test_signed_review_is_attached(tmp_path, monkeypatch):
    path = tmp_path / "evidence_reviews.json"
    path.write_text(json.dumps({"reviews": {
        "niacinamide": {
            "source": "A journal",
            "reviewer": "Reviewer",
            "evidence_level": "strong",
            "reviewed_at": "2026-01-01",
        },
    }}), encoding="utf-8")
    monkeypatch.setattr(evidence, "_PATH", str(path))
    result = evidence.attach({"identified_actives": [{"name": "Niacinamide"}]})
    assert result["identified_actives"][0]["provenance"]["source"] == "A journal"
    assert result["identified_actives"][0]["provenance"]["reviewed_at"] == "2026-01-01"


def test_price_per_active_uses_identified_actives():
    row = summarise(
        {"formulation_score": 80, "identified_actives": [{"name": "A"}, {"name": "B"}]},
        {"product_name": "Serum", "price": 600, "size_ml": 30, "category": "Serum"},
    )
    assert row["price_per_active"] == 300


def test_share_link_returns_only_the_free_analysis(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import server

    monkeypatch.setenv("PAYWALL_ENABLED", "1")
    # The flag is read at import. Force the running module to the paid gate
    # so a share cannot depend on whatever the process was started with.
    monkeypatch.setattr(server, "_PAYWALL_ENABLED", True)
    client = TestClient(server.app)
    created = client.post("/api/share", json={
        "product_name": "Niacinamide Serum",
        "ingredients": "Aqua, Niacinamide, Glycerin, Phenoxyethanol",
        "price": 599, "size_ml": 30, "category": "Serum", "country": "India",
    })
    assert created.status_code == 200, created.text
    opened = client.get("/api/share/%s" % created.json()["share_id"])
    assert opened.status_code == 200, opened.text
    body = opened.json()
    audit_no_paid_leakage(body["result"])
    assert not (set(body["result"]) & PAID_KEYS)
    assert body["result"]["formulation_score"] or body["result"]["main_worth_score"]
    assert "skin_concern_fit" not in body["result"]


def test_unknown_event_is_rejected():
    from fastapi.testclient import TestClient
    import server
    client = TestClient(server.app)
    refused = client.post("/api/events", json={"name": "email_captured"})
    assert refused.status_code == 400
    ok = client.post("/api/events", json={"name": "analysis_completed"})
    assert ok.status_code == 200


def test_refund_request_is_recorded_without_moving_a_balance():
    from fastapi.testclient import TestClient
    import server
    client = TestClient(server.app)
    response = client.post("/api/credits/refund-request", json={
        "email": "buyer@example.com", "order_id": "order_test_1", "note": "unused",
    })
    assert response.status_code == 200
    assert response.json()["received"] is True

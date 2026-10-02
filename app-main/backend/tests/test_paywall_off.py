"""The shipped configuration: PAYWALL_ENABLED unset, everything visible.

test_paid_flow.py turns the paywall on and tests it in detail. This file tests
the state the app is actually deployed in while the product is being reviewed,
because "we switched it off" is itself a behaviour that can break - most
obviously by charging a credit anyway, which is the one failure nobody would
notice until a balance went down.
"""

import os
import sys
import tempfile
import threading
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def client(monkeypatch):
    tmp = tempfile.mkdtemp(prefix='nopaywall-')
    monkeypatch.setenv('WALLET_DB_PATH', os.path.join(tmp, 'wallet.db'))
    monkeypatch.delenv('AIVEN_PG_URL', raising=False)
    monkeypatch.delenv('DEV_UNLOCK_ALL', raising=False)
    monkeypatch.delenv('PAYWALL_ENABLED', raising=False)
    monkeypatch.setenv('SESSION_SECRET', 'off-test-secret')

    for mod in ('wallet', 'identity', 'accounts', 'server'):
        sys.modules.pop(mod, None)
    import wallet as w
    w._initialised = False
    w._local = threading.local()
    w.init_storage()

    from fastapi.testclient import TestClient
    import server
    monkeypatch.setattr(server.limiter, 'enabled', False)
    return TestClient(server.app, base_url='https://testserver')


def body():
    return {
        'ingredients': 'Aqua, Niacinamide, Glycerin, Zinc PCA, Phenoxyethanol %s'
                       % uuid.uuid4().hex[:8],
        'price': 549, 'size_ml': 30, 'category': 'Serum',
        'skin_concerns': ['Acne & Oily Skin'], 'skin_type': 'oily',
        'country': 'India', 'currency': 'INR',
    }


def test_an_anonymous_caller_gets_the_full_analysis(client):
    out = client.post('/api/analyze', json=body()).json()
    assert out['access']['tier'] == 'full'
    assert 'skin_concern_fit' in out
    assert 'skin_type_compatibility' in out


def test_no_sign_in_is_required_for_anything_on_the_result(client):
    out = client.post('/api/analyze', json=body()).json()
    for key in ('skin_concern_fit', 'skin_type_compatibility', 'skin_type_details',
                'value_assessment', 'formulation_breakdown', 'advisory_flags'):
        assert key in out, '%s is missing with the paywall off' % key


def test_nothing_is_charged(client):
    """The failure nobody would notice until a balance went down."""
    import identity
    import wallet

    code = identity.issue_code('buyer@example.com')
    client.post('/api/auth/verify-code',
                json={'email': 'buyer@example.com', 'code': code})
    account = wallet.get_or_create_account('buyer@example.com')
    wallet.grant(account, 10, reference='manual')

    for _ in range(3):
        assert client.post('/api/analyze', json=body()).json()['access']['tier'] == 'full'

    assert wallet.get_balance(account) == 10
    assert [e for e in wallet.history(account) if e['reason'] == 'spend'] == []


def test_readiness_says_so_plainly(client):
    out = client.get('/api/readiness').json()
    assert out['paywall_enabled'] is False
    assert out['currently_charging'] is False
    assert any('PAYWALL_ENABLED is off' in w for w in out['warnings'])


def test_the_ledger_still_works_while_the_gate_is_open(client):
    """Credits bought now must still be there when the gate closes."""
    import wallet
    account = wallet.get_or_create_account('buyer@example.com')
    assert wallet.grant(account, 5, reference='pay_1') == 5
    assert wallet.grant(account, 5, reference='pay_1') is None
    assert wallet.get_balance(account) == 5

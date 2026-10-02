"""The paid path end to end, through the real HTTP surface.

Each unit is tested on its own elsewhere. What this file checks is the chain:
sign in, pay, analyse, run out. The failures it is written to catch are the
ones that only appear once the parts are connected -

  * a webhook that verifies but credits the wrong account,
  * an analysis that returns the paid payload without taking a credit,
  * a page refresh charging a second credit for the same product,
  * a signed-out caller still getting the paid payload from cache.
"""

import hashlib
import hmac
import json
import os
import sys
import tempfile
import threading
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

KEY_SECRET = 'test_key_secret'
WEBHOOK_SECRET = 'test_webhook_secret'


@pytest.fixture
def env(monkeypatch):
    tmp = tempfile.mkdtemp(prefix='paidflow-')
    monkeypatch.setenv('WALLET_DB_PATH', os.path.join(tmp, 'wallet.db'))
    monkeypatch.delenv('AIVEN_PG_URL', raising=False)
    monkeypatch.delenv('DEV_UNLOCK_ALL', raising=False)
    monkeypatch.setenv('SESSION_SECRET', 'flow-test-secret')
    monkeypatch.setenv('RAZORPAY_KEY_ID', 'rzp_test_flow')
    monkeypatch.setenv('RAZORPAY_KEY_SECRET', KEY_SECRET)
    monkeypatch.setenv('RAZORPAY_WEBHOOK_SECRET', WEBHOOK_SECRET)

    for mod in ('wallet', 'identity', 'accounts', 'server'):
        sys.modules.pop(mod, None)
    import wallet as w
    w._initialised = False
    w._local = threading.local()
    w.init_storage()
    return w


@pytest.fixture
def client(env, monkeypatch):
    from fastapi.testclient import TestClient
    import server

    # Not a paywall concern: /api/analyze allows 10/minute per IP and this file
    # exceeds that from one address. A 429 body has no "access" key, which
    # looks exactly like a paywall failure and is not one.
    monkeypatch.setattr(server.limiter, 'enabled', False)
    monkeypatch.setattr(server, '_DEV_UNLOCK', False)
    return TestClient(server.app, base_url='https://testserver')


@pytest.fixture
def signed_in(client, monkeypatch):
    """Sign in without a mail server by reading the code from issue_code."""
    import identity
    code = identity.issue_code('buyer@example.com')
    monkeypatch.setattr('identity.issue_code', lambda email: code)
    monkeypatch.setattr('mailer.send_login_code', lambda email, c: 'test')

    client.post('/api/auth/request-code', json={'email': 'buyer@example.com'})
    resp = client.post('/api/auth/verify-code',
                       json={'email': 'buyer@example.com', 'code': code})
    assert resp.status_code == 200, resp.text
    import wallet
    return wallet.get_or_create_account('buyer@example.com')


def analysis_body():
    """A distinct product each call, so cache hits are deliberate not accidental."""
    return {
        'ingredients': 'Aqua, Niacinamide, Glycerin, Zinc PCA, Phenoxyethanol, '
                       'Sodium Hyaluronate %s' % uuid.uuid4().hex[:8],
        'price': 549, 'size_ml': 30, 'category': 'Serum',
        'skin_concerns': ['Acne & Oily Skin'], 'skin_type': 'oily',
        'country': 'India', 'currency': 'INR',
    }


def webhook_for(order_id, payment_id, account_id):
    body = json.dumps({
        'event': 'payment.captured',
        'payload': {'payment': {'entity': {
            'id': payment_id, 'order_id': order_id,
            'amount': 24900, 'currency': 'INR',
            'notes': {'account_id': account_id, 'pack_id': 'regular'},
        }}},
    }).encode('utf-8')
    sig = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return body, sig


def record_order(order_id, account_id, pack_id='regular'):
    """Stand in for Razorpay's side of order creation."""
    import accounts
    import wallet
    accounts._ensure_order_schema()
    wallet._execute(
        'INSERT INTO credit_order '
        '(order_id, account_id, pack_id, amount_paise, status, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (order_id, account_id, pack_id,
         wallet.CREDIT_PACKS[pack_id]['amount_paise'], 'created', 0.0),
        commit=True)


# ---------------------------------------------------------------------------
# Signed out
# ---------------------------------------------------------------------------

def test_a_signed_out_caller_is_anonymous(client):
    body = client.get('/api/auth/me').json()
    assert body == {'signed_in': False, 'balance': 0}


def test_a_signed_out_caller_gets_the_free_analysis(client):
    body = client.post('/api/analyze', json=analysis_body()).json()
    assert body['access']['tier'] == 'free'
    assert 'skin_concern_fit' not in body


def test_credit_endpoints_require_a_session(client):
    for path, payload in (('/api/credits/order', {'pack_id': 'regular'}),
                          ('/api/credits/confirm', {
                              'razorpay_order_id': 'o', 'razorpay_payment_id': 'p',
                              'razorpay_signature': 's'})):
        assert client.post(path, json=payload).status_code == 401
    assert client.get('/api/credits/history').status_code == 401


# ---------------------------------------------------------------------------
# Signed in, no credits
# ---------------------------------------------------------------------------

def test_signing_in_starts_at_zero(client, signed_in):
    body = client.get('/api/auth/me').json()
    assert body['signed_in'] is True
    assert body['balance'] == 0


def test_being_signed_in_is_not_being_paid(client, signed_in):
    """An account with no credits must still get the free tier, not an error
    and certainly not the paid payload."""
    body = client.post('/api/analyze', json=analysis_body()).json()
    assert body['access']['tier'] == 'free'
    assert 'skin_concern_fit' not in body


# ---------------------------------------------------------------------------
# Paying
# ---------------------------------------------------------------------------

def test_a_verified_webhook_delivers_the_pack(client, signed_in):
    record_order('order_1', signed_in)
    body, sig = webhook_for('order_1', 'pay_1', signed_in)
    resp = client.post('/api/credits/webhook', content=body,
                       headers={'x-razorpay-signature': sig})
    assert resp.status_code == 200 and resp.json()['handled'] is True
    assert client.get('/api/auth/me').json()['balance'] == 15


def test_an_unsigned_webhook_delivers_nothing(client, signed_in):
    """Anyone can POST to this endpoint. Only Razorpay can sign it."""
    record_order('order_2', signed_in)
    body, _sig = webhook_for('order_2', 'pay_2', signed_in)
    resp = client.post('/api/credits/webhook', content=body,
                       headers={'x-razorpay-signature': 'forged'})
    assert resp.status_code == 400
    assert client.get('/api/auth/me').json()['balance'] == 0


def test_a_webhook_with_no_signature_delivers_nothing(client, signed_in):
    record_order('order_3', signed_in)
    body, _ = webhook_for('order_3', 'pay_3', signed_in)
    assert client.post('/api/credits/webhook', content=body).status_code == 400
    assert client.get('/api/auth/me').json()['balance'] == 0


def test_a_retried_webhook_delivers_once(client, signed_in):
    """Razorpay retries until it gets a 2xx. Both deliveries must answer 2xx,
    and only the first may grant."""
    record_order('order_4', signed_in)
    body, sig = webhook_for('order_4', 'pay_4', signed_in)
    for _ in range(3):
        resp = client.post('/api/credits/webhook', content=body,
                           headers={'x-razorpay-signature': sig})
        assert resp.status_code == 200
    assert client.get('/api/auth/me').json()['balance'] == 15


def test_credits_are_delivered_to_the_order_s_account_not_the_caller(client, signed_in):
    """The webhook has no session. It must credit whoever bought the order."""
    import wallet
    other = wallet.get_or_create_account('someone-else@example.com')
    record_order('order_5', other)
    body, sig = webhook_for('order_5', 'pay_5', other)
    client.post('/api/credits/webhook', content=body,
                headers={'x-razorpay-signature': sig})
    assert client.get('/api/auth/me').json()['balance'] == 0
    assert wallet.get_balance(other) == 15


def test_the_pack_delivered_comes_from_our_order_record(client, signed_in):
    """Not from the webhook payload. A forged or stale note cannot change how
    many credits are granted."""
    record_order('order_6', signed_in, pack_id='starter')  # 5 credits
    body, sig = webhook_for('order_6', 'pay_6', signed_in)  # claims the 15 pack
    client.post('/api/credits/webhook', content=body,
                headers={'x-razorpay-signature': sig})
    assert client.get('/api/auth/me').json()['balance'] == 5


def test_a_webhook_for_an_unknown_order_grants_nothing(client, signed_in):
    body, sig = webhook_for('order_never_created', 'pay_7', signed_in)
    resp = client.post('/api/credits/webhook', content=body,
                       headers={'x-razorpay-signature': sig})
    assert resp.status_code == 200
    assert client.get('/api/auth/me').json()['balance'] == 0


def test_a_checkout_confirmation_for_someone_elses_order_is_refused(client, signed_in):
    """A valid signature is not authorisation to credit this session."""
    import wallet
    other = wallet.get_or_create_account('other@example.com')
    record_order('order_8', other)
    sig = hmac.new(KEY_SECRET.encode(), b'order_8|pay_8', hashlib.sha256).hexdigest()
    resp = client.post('/api/credits/confirm', json={
        'razorpay_order_id': 'order_8', 'razorpay_payment_id': 'pay_8',
        'razorpay_signature': sig})
    assert resp.status_code == 400
    assert client.get('/api/auth/me').json()['balance'] == 0


def test_a_genuine_checkout_confirmation_delivers(client, signed_in):
    record_order('order_9', signed_in)
    sig = hmac.new(KEY_SECRET.encode(), b'order_9|pay_9', hashlib.sha256).hexdigest()
    resp = client.post('/api/credits/confirm', json={
        'razorpay_order_id': 'order_9', 'razorpay_payment_id': 'pay_9',
        'razorpay_signature': sig})
    assert resp.status_code == 200
    assert resp.json()['balance'] == 15


def test_the_callback_and_the_webhook_together_deliver_once(client, signed_in):
    """Both routinely arrive for the same payment. Same payment id, one grant."""
    record_order('order_10', signed_in)
    sig = hmac.new(KEY_SECRET.encode(), b'order_10|pay_10', hashlib.sha256).hexdigest()
    client.post('/api/credits/confirm', json={
        'razorpay_order_id': 'order_10', 'razorpay_payment_id': 'pay_10',
        'razorpay_signature': sig})
    body, wsig = webhook_for('order_10', 'pay_10', signed_in)
    client.post('/api/credits/webhook', content=body,
                headers={'x-razorpay-signature': wsig})
    assert client.get('/api/auth/me').json()['balance'] == 15


# ---------------------------------------------------------------------------
# Spending
# ---------------------------------------------------------------------------

@pytest.fixture
def funded(client, signed_in):
    record_order('order_fund', signed_in)
    body, sig = webhook_for('order_fund', 'pay_fund', signed_in)
    client.post('/api/credits/webhook', content=body,
                headers={'x-razorpay-signature': sig})
    assert client.get('/api/auth/me').json()['balance'] == 15
    return signed_in


def test_a_paid_analysis_returns_the_full_payload(client, funded):
    body = client.post('/api/analyze', json=analysis_body()).json()
    assert body['access']['tier'] == 'full'
    assert 'skin_concern_fit' in body


def test_a_paid_analysis_costs_one_credit(client, funded):
    client.post('/api/analyze', json=analysis_body())
    assert client.get('/api/auth/me').json()['balance'] == 14


def test_re_analysing_the_same_product_is_free(client, funded):
    """A refresh, a retry after a dropped connection, or returning tomorrow.
    Charging twice for one product because the network blipped is the kind of
    thing you find out about from a complaint."""
    body = analysis_body()
    for _ in range(4):
        resp = client.post('/api/analyze', json=body).json()
        assert resp['access']['tier'] == 'full'
    assert client.get('/api/auth/me').json()['balance'] == 14


def test_each_new_product_costs_a_credit(client, funded):
    for _ in range(3):
        client.post('/api/analyze', json=analysis_body())
    assert client.get('/api/auth/me').json()['balance'] == 12


def test_running_out_falls_back_to_the_free_tier(client, signed_in):
    """Not an error page. The free analysis is a real product."""
    import wallet
    wallet.grant(signed_in, 1, reference='manual_1')
    first = client.post('/api/analyze', json=analysis_body()).json()
    assert first['access']['tier'] == 'full'
    second = client.post('/api/analyze', json=analysis_body()).json()
    assert second['access']['tier'] == 'free'
    assert 'skin_concern_fit' not in second


def test_the_balance_never_goes_negative_through_the_api(client, signed_in):
    import wallet
    wallet.grant(signed_in, 2, reference='manual_2')
    for _ in range(6):
        client.post('/api/analyze', json=analysis_body())
    assert client.get('/api/auth/me').json()['balance'] == 0


def test_a_cache_hit_still_costs_the_second_buyer_a_credit(client, funded):
    """Someone else having analysed this product first must not make it free -
    and, more importantly, must not hand the paid payload to a free caller."""
    body = analysis_body()
    client.post('/api/analyze', json=body)            # warms the cache, costs 1
    client.post('/api/auth/signout')
    free = client.post('/api/analyze', json=body).json()
    assert free['access']['tier'] == 'free'
    assert 'skin_concern_fit' not in free


def test_signing_out_ends_the_paid_tier(client, funded):
    client.post('/api/auth/signout')
    body = client.post('/api/analyze', json=analysis_body()).json()
    assert body['access']['tier'] == 'free'


def test_a_forged_session_cookie_buys_nothing(client, funded):
    """The whole paywall in one editable field, if the cookie were trusted."""
    import identity
    client.post('/api/auth/signout')
    client.cookies.set(identity.SESSION_COOKIE, 'acct_someone.9999999999.forged')
    body = client.post('/api/analyze', json=analysis_body()).json()
    assert body['access']['tier'] == 'free'


def test_history_shows_the_purchase_and_the_spend(client, funded):
    client.post('/api/analyze', json=analysis_body())
    history = client.get('/api/credits/history').json()
    reasons = [e['reason'] for e in history['entries']]
    assert 'purchase' in reasons and 'spend' in reasons
    assert history['balance'] == 14


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------

def test_readiness_refuses_to_call_sqlite_ready_to_charge(client):
    """Credits on an ephemeral disk disappear on the next restart. The deploy
    check should fail on that rather than anyone discovering it later."""
    body = client.get('/api/readiness').json()
    assert body['ledger_durable'] is False
    assert body['ready_to_charge'] is False
    assert any('AIVEN_PG_URL' in w for w in body['warnings'])


def test_readiness_reports_dev_unlock(client, monkeypatch):
    import server
    monkeypatch.setattr(server, '_DEV_UNLOCK', True)
    body = client.get('/api/readiness').json()
    assert body['dev_unlock_all'] is True
    assert any('DEV_UNLOCK_ALL' in w for w in body['warnings'])

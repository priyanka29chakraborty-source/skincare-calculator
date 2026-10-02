"""Razorpay signal verification.

One rule is under test: credits are granted only from a cryptographically
verified signal. The browser can claim anything, so every test here is a
variation on "someone is lying to our endpoint" plus the two legitimate
signals we do accept.
"""

import hashlib
import hmac
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import payments  # noqa: E402
from payments import (  # noqa: E402
    PaymentFailed,
    PaymentsNotConfigured,
    SignatureInvalid,
    is_configured,
    parse_webhook,
    public_config,
    verify_checkout_signature,
    verify_webhook,
)

KEY_ID = 'rzp_test_abc123'
KEY_SECRET = 'secret_key_value'
WEBHOOK_SECRET = 'webhook_secret_value'


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv('RAZORPAY_KEY_ID', KEY_ID)
    monkeypatch.setenv('RAZORPAY_KEY_SECRET', KEY_SECRET)
    monkeypatch.setenv('RAZORPAY_WEBHOOK_SECRET', WEBHOOK_SECRET)


def sign(secret, message):
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def webhook_body(payment_id='pay_123', order_id='order_123', amount=9900, notes=None):
    return json.dumps({
        'event': 'payment.captured',
        'payload': {'payment': {'entity': {
            'id': payment_id, 'order_id': order_id,
            'amount': amount, 'currency': 'INR',
            'notes': notes or {'account_id': 'acct_abc'},
        }}},
    }).encode('utf-8')


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def test_the_key_secret_is_never_in_the_public_config():
    """The key id identifies the merchant in the checkout widget and is public.
    The secrets are not, and there must be no path that returns them."""
    cfg = public_config()
    assert cfg['key_id'] == KEY_ID
    assert KEY_SECRET not in json.dumps(cfg)
    assert WEBHOOK_SECRET not in json.dumps(cfg)


def test_without_keys_payments_report_themselves_as_unavailable(monkeypatch):
    """Better an honest "payments are off" than a checkout that fails later."""
    monkeypatch.delenv('RAZORPAY_KEY_ID', raising=False)
    monkeypatch.delenv('RAZORPAY_KEY_SECRET', raising=False)
    assert is_configured() is False
    assert public_config()['enabled'] is False


def test_creating_an_order_without_keys_raises(monkeypatch):
    monkeypatch.delenv('RAZORPAY_KEY_ID', raising=False)
    monkeypatch.delenv('RAZORPAY_KEY_SECRET', raising=False)
    with pytest.raises(PaymentsNotConfigured):
        payments.create_order(9900, 'receipt_1')


# ---------------------------------------------------------------------------
# Checkout callback signature
# ---------------------------------------------------------------------------

def test_a_genuine_checkout_signature_verifies():
    sig = sign(KEY_SECRET, b'order_123|pay_123')
    assert verify_checkout_signature('order_123', 'pay_123', sig) is True


def test_a_forged_checkout_signature_is_rejected():
    with pytest.raises(SignatureInvalid):
        verify_checkout_signature('order_123', 'pay_123', 'deadbeef')


def test_a_signature_for_a_different_payment_is_rejected():
    """Replaying someone else's valid signature must not credit this order."""
    sig = sign(KEY_SECRET, b'order_999|pay_999')
    with pytest.raises(SignatureInvalid):
        verify_checkout_signature('order_123', 'pay_123', sig)


def test_swapping_order_and_payment_ids_is_rejected():
    sig = sign(KEY_SECRET, b'pay_123|order_123')
    with pytest.raises(SignatureInvalid):
        verify_checkout_signature('order_123', 'pay_123', sig)


@pytest.mark.parametrize('order_id,payment_id,signature', [
    ('', 'pay_123', 'abc'),
    ('order_123', '', 'abc'),
    ('order_123', 'pay_123', ''),
    (None, None, None),
])
def test_missing_checkout_fields_are_rejected(order_id, payment_id, signature):
    with pytest.raises(SignatureInvalid):
        verify_checkout_signature(order_id, payment_id, signature)


def test_a_signature_made_with_the_wrong_secret_is_rejected():
    sig = sign('not_our_secret', b'order_123|pay_123')
    with pytest.raises(SignatureInvalid):
        verify_checkout_signature('order_123', 'pay_123', sig)


# ---------------------------------------------------------------------------
# Webhook signature
# ---------------------------------------------------------------------------

def test_a_genuine_webhook_verifies():
    body = webhook_body()
    assert verify_webhook(body, sign(WEBHOOK_SECRET, body)) is True


def test_a_tampered_body_is_rejected():
    """The attack this exists to stop: a real signature on an edited amount."""
    body = webhook_body(amount=9900)
    sig = sign(WEBHOOK_SECRET, body)
    tampered = body.replace(b'9900', b'1')
    with pytest.raises(SignatureInvalid):
        verify_webhook(tampered, sig)


def test_a_webhook_signed_with_the_checkout_secret_is_rejected():
    """The two secrets are not interchangeable."""
    body = webhook_body()
    with pytest.raises(SignatureInvalid):
        verify_webhook(body, sign(KEY_SECRET, body))


def test_a_missing_signature_header_is_rejected():
    with pytest.raises(SignatureInvalid):
        verify_webhook(webhook_body(), None)


def test_verification_requires_raw_bytes():
    """Re-serialising parsed JSON gives different bytes - different key order,
    different spacing - so the HMAC fails for every legitimate delivery. That
    is how this check usually gets "fixed" by being switched off."""
    with pytest.raises(SignatureInvalid):
        verify_webhook(webhook_body().decode('utf-8'), 'anything')


def test_without_a_webhook_secret_verification_refuses_rather_than_passes(monkeypatch):
    """An unset secret must never mean "skip the check"."""
    monkeypatch.delenv('RAZORPAY_WEBHOOK_SECRET', raising=False)
    body = webhook_body()
    with pytest.raises(PaymentsNotConfigured):
        verify_webhook(body, sign(WEBHOOK_SECRET, body))


def test_byte_for_byte_equal_bodies_with_different_spacing_differ():
    """Shows why raw bytes matter: same data, different encoding, different HMAC."""
    a = b'{"event":"payment.captured"}'
    b = b'{"event": "payment.captured"}'
    assert sign(WEBHOOK_SECRET, a) != sign(WEBHOOK_SECRET, b)


# ---------------------------------------------------------------------------
# Webhook parsing
# ---------------------------------------------------------------------------

def test_a_captured_payment_is_parsed():
    out = parse_webhook(webhook_body(payment_id='pay_xyz', amount=24900))
    assert out['payment_id'] == 'pay_xyz'
    assert out['amount_paise'] == 24900
    assert out['notes']['account_id'] == 'acct_abc'


def test_other_events_are_ignored_rather_than_failing():
    """Razorpay sends many event types. Answering 2xx without acting stops the
    retries; raising would make it retry an event we will never handle."""
    body = json.dumps({'event': 'payment.failed', 'payload': {}}).encode()
    assert parse_webhook(body) is None


def test_a_capture_without_a_payment_id_is_an_error():
    body = json.dumps({
        'event': 'payment.captured',
        'payload': {'payment': {'entity': {'amount': 9900}}},
    }).encode()
    with pytest.raises(PaymentFailed):
        parse_webhook(body)


def test_a_malformed_body_is_an_error():
    with pytest.raises(PaymentFailed):
        parse_webhook(b'not json at all')


def test_a_capture_with_an_empty_payload_is_an_error():
    body = json.dumps({'event': 'payment.captured'}).encode()
    with pytest.raises(PaymentFailed):
        parse_webhook(body)


# ---------------------------------------------------------------------------
# Order creation input
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('amount', [0, -100, 99.5, '9900', None])
def test_an_order_amount_must_be_a_positive_integer_of_paise(amount):
    with pytest.raises(PaymentFailed):
        payments.create_order(amount, 'receipt_1')

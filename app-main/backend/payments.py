"""Razorpay: creating orders and accepting payment confirmations.

Why Razorpay rather than a Merchant-of-Record
---------------------------------------------
On a Rs 99 pack, Lemon Squeezy's 5% + $0.50 takes roughly 47% of the sale.
Razorpay's ~2%, and UPI's near-zero cost on small-ticket domestic payments,
is the difference between the starter pack being a product and being a loss.
The trade is that we handle Indian GST ourselves rather than having an MoR do
it - a tax question for the business, not a code one.

The one rule that matters
-------------------------
**Credits are granted only from a cryptographically verified signal.** The
browser is not a source of truth: anyone can call our endpoint claiming a
payment succeeded. Two signals are accepted, and both are verified with HMAC
against a secret the browser never sees:

* the **webhook** (``payment.captured``), signed with RAZORPAY_WEBHOOK_SECRET.
  This is authoritative - it arrives even if the customer closes the tab
  mid-redirect, which is exactly when a naive implementation loses a payment
  someone was charged for.
* the **checkout callback**, signed with RAZORPAY_KEY_SECRET. Used only so the
  balance updates immediately rather than whenever the webhook lands.

Both carry the same ``payment_id``, which wallet.grant() uses as its
idempotency reference, so whichever arrives first grants the credits and the
other is a no-op. Razorpay retries webhooks until it gets a 2xx, so duplicate
delivery is normal traffic rather than an attack - and must be free.

With no keys configured every function here raises PaymentsNotConfigured and
the API reports payments as unavailable, rather than appearing to work.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

RAZORPAY_API = 'https://api.razorpay.com/v1'
HTTP_TIMEOUT = 20


class PaymentsNotConfigured(Exception):
    """No Razorpay keys in the environment."""


class SignatureInvalid(Exception):
    """A payment signal failed verification. Never grant anything."""


class PaymentFailed(Exception):
    """Razorpay rejected or could not process the request."""


def _key_id():
    return os.environ.get('RAZORPAY_KEY_ID', '').strip()


def _key_secret():
    return os.environ.get('RAZORPAY_KEY_SECRET', '').strip()


def _webhook_secret():
    return os.environ.get('RAZORPAY_WEBHOOK_SECRET', '').strip()


def is_configured():
    return bool(_key_id() and _key_secret())


def public_config():
    """What the browser is allowed to know.

    The key id is public by design - it identifies the merchant in the checkout
    widget. The key secret and webhook secret never appear here, and there is
    no code path that puts them in a response.
    """
    return {
        'enabled': is_configured(),
        'key_id': _key_id() or None,
        'currency': 'INR',
    }


def _auth_header():
    if not is_configured():
        raise PaymentsNotConfigured('RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not set')
    token = base64.b64encode(
        ('%s:%s' % (_key_id(), _key_secret())).encode('utf-8')).decode('ascii')
    return {'Authorization': 'Basic ' + token,
            'Content-Type': 'application/json'}


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

def create_order(amount_paise, receipt, notes=None):
    """Create a Razorpay order and return the fields checkout needs.

    *amount_paise* is an integer in the smallest currency unit. Rupees as a
    float would eventually produce a 98.99999 charge, and Razorpay rejects
    non-integer amounts anyway.

    *notes* travels with the payment and comes back on the webhook. The
    account id goes there so a webhook can be attributed without trusting
    anything the browser later sends - but note that notes are visible in the
    Razorpay dashboard, so they carry an opaque account id and never an email.
    """
    if not isinstance(amount_paise, int) or amount_paise <= 0:
        raise PaymentFailed('amount must be a positive integer number of paise')

    body = {
        'amount': amount_paise,
        'currency': 'INR',
        'receipt': receipt[:40],
        'payment_capture': 1,
        'notes': notes or {},
    }
    try:
        resp = requests.post(RAZORPAY_API + '/orders', headers=_auth_header(),
                             data=json.dumps(body), timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise PaymentFailed('could not reach Razorpay: %s' % (exc,))

    if resp.status_code >= 400:
        # Razorpay's error text can quote the request, so it is logged but not
        # returned - the customer gets a generic failure.
        logger.error('razorpay order failed: %s %s', resp.status_code, resp.text[:400])
        raise PaymentFailed('payment provider rejected the order')

    data = resp.json()
    return {
        'order_id': data['id'],
        'amount': data['amount'],
        'currency': data['currency'],
        'key_id': _key_id(),
    }


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def _hmac_hex(secret, message):
    return hmac.new(secret.encode('utf-8'), message, hashlib.sha256).hexdigest()


def verify_checkout_signature(order_id, payment_id, signature):
    """Verify the signature the checkout widget hands back to the browser.

    Razorpay signs "order_id|payment_id" with the key secret. compare_digest
    rather than == so the comparison does not leak the correct prefix length
    through timing.
    """
    if not (order_id and payment_id and signature):
        raise SignatureInvalid('missing order_id, payment_id or signature')
    if not is_configured():
        raise PaymentsNotConfigured('cannot verify without RAZORPAY_KEY_SECRET')

    expected = _hmac_hex(_key_secret(), ('%s|%s' % (order_id, payment_id)).encode('utf-8'))
    if not hmac.compare_digest(expected, str(signature)):
        raise SignatureInvalid('checkout signature does not match')
    return True


def verify_webhook(raw_body, signature):
    """Verify a webhook against the raw request body.

    *raw_body* must be the exact bytes received. Re-serialising the parsed JSON
    produces different bytes - different key order, different spacing - and the
    HMAC then fails for every legitimate delivery, which is the classic way
    this check gets "fixed" by disabling it.
    """
    secret = _webhook_secret()
    if not secret:
        raise PaymentsNotConfigured('RAZORPAY_WEBHOOK_SECRET is not set')
    if not signature:
        raise SignatureInvalid('missing X-Razorpay-Signature')
    if not isinstance(raw_body, (bytes, bytearray)):
        raise SignatureInvalid('webhook body must be raw bytes')

    expected = _hmac_hex(secret, bytes(raw_body))
    if not hmac.compare_digest(expected, str(signature)):
        raise SignatureInvalid('webhook signature does not match')
    return True


def parse_webhook(raw_body):
    """Parse a verified webhook into the fields we act on.

    Only call after verify_webhook. Returns None for events we do not handle,
    so the endpoint can answer 2xx and stop the retries without acting.
    """
    try:
        event = json.loads(raw_body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as exc:
        raise PaymentFailed('webhook body is not JSON: %s' % (exc,))

    if event.get('event') != 'payment.captured':
        return None

    entity = (((event.get('payload') or {}).get('payment') or {}).get('entity') or {})
    payment_id = entity.get('id')
    if not payment_id:
        raise PaymentFailed('payment.captured without a payment id')

    return {
        'payment_id': payment_id,
        'order_id': entity.get('order_id'),
        'amount_paise': entity.get('amount'),
        'currency': entity.get('currency'),
        'notes': entity.get('notes') or {},
        'received_at': time.time(),
    }


def fetch_payment(payment_id):
    """Ask Razorpay directly what a payment is.

    The fallback when a signal is suspect: the gateway's own answer settles it,
    and it is the only check that cannot be forged by whoever is calling us.
    """
    try:
        resp = requests.get('%s/payments/%s' % (RAZORPAY_API, payment_id),
                            headers=_auth_header(), timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise PaymentFailed('could not reach Razorpay: %s' % (exc,))
    if resp.status_code >= 400:
        raise PaymentFailed('payment %s not found' % (payment_id,))
    return resp.json()

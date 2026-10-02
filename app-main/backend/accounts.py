"""HTTP surface for identity, credit packs and Razorpay.

Design notes that matter more than the routing
----------------------------------------------

* **Credits are granted from the order we recorded, never from the amount the
  caller reports.** ``credit_order`` stores pack_id and account_id at creation
  time, so a confirm or webhook can only ever deliver the pack that was paid
  for. Reading the credit count out of the webhook's ``notes`` would let a
  changed pack price, or a replayed note, hand out the wrong number.

* **Both confirmation paths share one idempotency key** - the Razorpay
  payment id. The checkout callback and the webhook routinely both arrive;
  whichever lands first grants, the other is a no-op in wallet.grant.

* **The webhook reads the raw body.** Re-serialising parsed JSON changes the
  bytes and breaks the HMAC for every legitimate delivery.

* **Errors are vague to the caller and specific in the log.** "That code is
  not right" rather than "no code was requested for that address", which would
  turn the endpoint into an account-existence oracle.
"""

import json
import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import history
import identity
import mailer
import payments
import wallet

logger = logging.getLogger(__name__)

accounts_router = APIRouter()

ORDER_SCHEMA = """
CREATE TABLE IF NOT EXISTS credit_order (
    order_id    TEXT PRIMARY KEY,
    account_id  TEXT NOT NULL,
    pack_id     TEXT NOT NULL,
    amount_paise INTEGER NOT NULL,
    status      TEXT NOT NULL,
    created_at  DOUBLE PRECISION NOT NULL
)
"""


def _ensure_order_schema():
    wallet.init_storage()
    sql = ORDER_SCHEMA if wallet.storage_is_durable() else ORDER_SCHEMA.replace(
        'DOUBLE PRECISION', 'REAL')
    wallet._execute(sql, (), commit=True)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class EmailRequest(BaseModel):
    email: str = Field(max_length=254)


class VerifyRequest(BaseModel):
    email: str = Field(max_length=254)
    code: str = Field(max_length=12)


class OrderRequest(BaseModel):
    pack_id: str = Field(max_length=32)


class ConfirmRequest(BaseModel):
    razorpay_order_id: str = Field(max_length=64)
    razorpay_payment_id: str = Field(max_length=64)
    razorpay_signature: str = Field(max_length=256)


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def current_account(request: Request):
    """The signed-in account id, or None. Never raises."""
    return identity.read_session(request.cookies.get(identity.SESSION_COOKIE))


def _require_account(request: Request):
    account_id = current_account(request)
    if not account_id:
        return None
    return account_id


def _unauthenticated():
    return JSONResponse(status_code=401, content={'error': 'Please sign in first.'})


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@accounts_router.post('/auth/request-code')
async def request_code(req: EmailRequest, request: Request):
    """Email a login code.

    The response is identical whether or not the address has an account. A
    different answer for a known address turns this into a way to test which
    of a list of emails uses the product.
    """
    try:
        email = identity.normalise_email(req.email)
    except identity.IdentityError as exc:
        return JSONResponse(status_code=400, content={'error': str(exc)})

    try:
        code = identity.issue_code(email)
        transport = mailer.send_login_code(email, code)
        logger.info('login code sent via %s', transport)
    except mailer.MailNotConfigured:
        logger.error('cannot send login codes: no SMTP configured')
        return JSONResponse(status_code=503, content={
            'error': 'Sign-in by email is not available right now.'})
    except mailer.MailFailed:
        return JSONResponse(status_code=502, content={
            'error': 'We could not send that email. Please try again.'})

    return {'sent': True, 'expires_in': identity.CODE_TTL_SECONDS}


@accounts_router.post('/auth/verify-code')
async def verify_code(req: VerifyRequest, request: Request):
    try:
        account_id = identity.verify_code(req.email, req.code)
    except identity.IdentityError as exc:
        # One message for every failure: wrong code, no code, expired, capped.
        # Distinguishing them tells an attacker which addresses are in use.
        logger.info('login rejected: %s', exc)
        return JSONResponse(status_code=400, content={
            'error': 'That code is not right, or it has expired.'})

    response = JSONResponse(content={
        'signed_in': True,
        'balance': wallet.get_balance(account_id),
    })
    response.set_cookie(identity.SESSION_COOKIE,
                        identity.make_session(account_id),
                        **identity.session_cookie_kwargs())
    return response


@accounts_router.post('/auth/signout')
async def sign_out(request: Request):
    response = JSONResponse(content={'signed_in': False})
    response.delete_cookie(identity.SESSION_COOKIE, path='/')
    return response


@accounts_router.get('/auth/me')
async def me(request: Request):
    account_id = current_account(request)
    if not account_id:
        return {'signed_in': False, 'balance': 0}
    return {
        'signed_in': True,
        'balance': wallet.get_balance(account_id),
        'cost_per_analysis': wallet.COST_PER_ANALYSIS,
    }


# ---------------------------------------------------------------------------
# Credits
# ---------------------------------------------------------------------------

@accounts_router.get('/credits/packs')
async def packs(request: Request):
    """What is for sale, and whether it can be bought right now."""
    config = payments.public_config()
    return {
        'packs': [
            dict(pack, pack_id=pack_id,
                 amount_display='%d' % (pack['amount_paise'] // 100))
            for pack_id, pack in wallet.CREDIT_PACKS.items()
        ],
        'currency': 'INR',
        'payments_enabled': config['enabled'],
        'key_id': config['key_id'],
    }


@accounts_router.post('/credits/order')
async def create_order(req: OrderRequest, request: Request):
    account_id = _require_account(request)
    if not account_id:
        return _unauthenticated()

    try:
        pack = wallet.pack_for(req.pack_id)
    except wallet.WalletError:
        return JSONResponse(status_code=400, content={'error': 'Unknown pack.'})

    if not payments.is_configured():
        return JSONResponse(status_code=503, content={
            'error': 'Payments are not available right now.'})

    try:
        # notes travel to the webhook. They carry the opaque account id only -
        # never the email, because notes are visible in the Razorpay dashboard.
        order = payments.create_order(
            pack['amount_paise'],
            receipt='pack_%s_%d' % (req.pack_id, int(time.time())),
            notes={'account_id': account_id, 'pack_id': req.pack_id})
    except payments.PaymentFailed as exc:
        logger.error('order creation failed: %s', exc)
        return JSONResponse(status_code=502, content={
            'error': 'Could not start the payment. Please try again.'})

    _ensure_order_schema()
    wallet._execute(
        'INSERT INTO credit_order '
        '(order_id, account_id, pack_id, amount_paise, status, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (order['order_id'], account_id, req.pack_id, pack['amount_paise'],
         'created', time.time()), commit=True)

    return {
        'order_id': order['order_id'],
        'amount': order['amount'],
        'currency': order['currency'],
        'key_id': order['key_id'],
        'pack': pack,
    }


def _order_record(order_id):
    _ensure_order_schema()
    cur = wallet._execute(
        'SELECT account_id, pack_id, amount_paise, status FROM credit_order '
        'WHERE order_id = ?', (order_id,))
    row = cur.fetchone()
    if not row:
        return None
    return {'account_id': row[0], 'pack_id': row[1],
            'amount_paise': int(row[2]), 'status': row[3]}


def _deliver(order_id, payment_id, source):
    """Grant the pack recorded for *order_id*. Idempotent on *payment_id*.

    The credit count comes from our own order row, never from the payment
    payload: that is what stops a changed price or an edited note delivering
    the wrong pack.
    """
    record = _order_record(order_id)
    if not record:
        logger.error('%s: no such order %s', source, order_id)
        return None

    pack = wallet.CREDIT_PACKS.get(record['pack_id'])
    if not pack:
        logger.error('%s: order %s names unknown pack %s',
                     source, order_id, record['pack_id'])
        return None

    balance = wallet.grant(
        record['account_id'], pack['credits'],
        reason=wallet.REASON_PURCHASE,
        reference=payment_id,
        metadata=json.dumps({'order_id': order_id, 'pack_id': record['pack_id'],
                             'source': source}))

    if balance is None:
        logger.info('%s: payment %s already delivered', source, payment_id)
        return wallet.get_balance(record['account_id'])

    wallet._execute('UPDATE credit_order SET status = ? WHERE order_id = ?',
                    ('paid', order_id), commit=True)
    logger.info('%s: delivered %d credits for order %s',
                source, pack['credits'], order_id)
    return balance


@accounts_router.post('/credits/confirm')
async def confirm(req: ConfirmRequest, request: Request):
    """The checkout callback. Verified, but not the authoritative signal.

    This exists so the balance updates while the customer is still looking at
    the page. The webhook is what guarantees delivery if they close the tab.
    """
    account_id = _require_account(request)
    if not account_id:
        return _unauthenticated()

    try:
        payments.verify_checkout_signature(
            req.razorpay_order_id, req.razorpay_payment_id, req.razorpay_signature)
    except (payments.SignatureInvalid, payments.PaymentsNotConfigured) as exc:
        logger.warning('checkout confirmation rejected: %s', exc)
        return JSONResponse(status_code=400, content={
            'error': 'We could not verify that payment.'})

    record = _order_record(req.razorpay_order_id)
    if not record or record['account_id'] != account_id:
        # A valid signature for someone else's order must not credit this
        # session.
        logger.warning('order %s does not belong to the calling account',
                       req.razorpay_order_id)
        return JSONResponse(status_code=400, content={
            'error': 'We could not verify that payment.'})

    balance = _deliver(req.razorpay_order_id, req.razorpay_payment_id, 'checkout')
    if balance is None:
        return JSONResponse(status_code=400, content={
            'error': 'We could not verify that payment.'})
    return {'delivered': True, 'balance': balance}


@accounts_router.post('/credits/webhook')
async def webhook(request: Request):
    """Razorpay's server-to-server confirmation. The authoritative signal.

    Always answers 2xx once the signature verifies, including for events we do
    not handle and for deliveries we have already processed - otherwise
    Razorpay retries forever. A failed signature is the one case that gets a
    4xx, because it is not Razorpay calling.
    """
    raw = await request.body()
    signature = request.headers.get('x-razorpay-signature')

    try:
        payments.verify_webhook(raw, signature)
    except payments.PaymentsNotConfigured:
        logger.error('webhook received but RAZORPAY_WEBHOOK_SECRET is not set')
        return JSONResponse(status_code=503, content={'error': 'not configured'})
    except payments.SignatureInvalid as exc:
        logger.warning('webhook signature rejected: %s', exc)
        return JSONResponse(status_code=400, content={'error': 'invalid signature'})

    try:
        event = payments.parse_webhook(raw)
    except payments.PaymentFailed as exc:
        logger.error('malformed webhook: %s', exc)
        # Signature was valid, so this is Razorpay sending something we cannot
        # read. Retrying will not help.
        return {'received': True, 'handled': False}

    if not event:
        return {'received': True, 'handled': False}

    if not event.get('order_id'):
        logger.error('payment.captured without an order id: %s', event['payment_id'])
        return {'received': True, 'handled': False}

    _deliver(event['order_id'], event['payment_id'], 'webhook')
    return {'received': True, 'handled': True}


@accounts_router.get('/history')
async def saved_analyses(request: Request):
    """What this account has analysed before."""
    account_id = _require_account(request)
    if not account_id:
        return _unauthenticated()
    return {'entries': history.recent(account_id)}


@accounts_router.get('/history/{entry_id}')
async def saved_analysis(entry_id: str, request: Request):
    """One saved analysis, with the inputs needed to re-open it.

    Scoped by account in the query itself, so an entry id copied from someone
    else's list matches nothing rather than being checked afterwards.
    """
    account_id = _require_account(request)
    if not account_id:
        return _unauthenticated()
    entry = history.get(account_id, entry_id)
    if not entry:
        return JSONResponse(status_code=404, content={'error': 'Not found.'})
    return entry


@accounts_router.post('/history/{entry_id}/forget')
async def forget_analysis(entry_id: str, request: Request):
    account_id = _require_account(request)
    if not account_id:
        return _unauthenticated()
    return {'forgotten': history.forget(account_id, entry_id)}


@accounts_router.post('/history/forget-all')
async def forget_all_analyses(request: Request):
    """Empty the history. Someone asking to be forgotten gets that."""
    account_id = _require_account(request)
    if not account_id:
        return _unauthenticated()
    return {'forgotten': history.forget_all(account_id)}


@accounts_router.get('/credits/history')
async def credit_history(request: Request):
    account_id = _require_account(request)
    if not account_id:
        return _unauthenticated()
    return {
        'balance': wallet.get_balance(account_id),
        'entries': wallet.history(account_id, limit=50),
    }

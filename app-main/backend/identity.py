"""Who the customer is: email codes in, a signed session cookie out.

Why email codes rather than passwords
-------------------------------------
Paid credits have to survive a new phone. That rules out a device-local token,
which is otherwise the lowest-friction option. It does not require passwords:
a password here would be one more secret for us to store and leak, protecting
an account whose only contents are a credit balance. An emailed code proves
control of the address we would use to restore the account anyway.

What is defended against
------------------------
* **Code guessing.** Codes are 6 digits from ``secrets``, single-use, expire in
  10 minutes, and allow 5 attempts before the code is burned. A new code does
  not reset that count: failures stay for 15 minutes, and the increment is one
  UPDATE ... WHERE attempts < 5 so parallel guesses cannot slip past the cap.
  Without the attempt cap, 6 digits is a million guesses against an endpoint.
* **Timing.** Code comparison uses ``compare_digest``.
* **Session forgery.** The cookie is ``account_id.expiry.hmac`` signed with
  SESSION_SECRET. Nothing in it is trusted before the HMAC verifies, so a
  tampered account id is rejected rather than used to read someone's balance.
* **Codes in our logs.** The code is never logged. The email is logged only as
  a hash prefix.

The session secret
------------------
SESSION_SECRET must be set in production. Without it a random one is generated
at startup, which is safe but logs everyone out on every deploy - correct for
local development, visibly wrong for production, and reported by
``secret_is_persistent()`` so the health endpoint can say so.
"""

import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import time

logger = logging.getLogger(__name__)

CODE_TTL_SECONDS = 600          # 10 minutes
SESSION_TTL_SECONDS = 60 * 60 * 24 * 90   # 90 days
MAX_CODE_ATTEMPTS = 5
CODE_LENGTH = 6
RESEND_COOLDOWN_SECONDS = 60
MAX_CODES_PER_WINDOW = 5
SEND_WINDOW_SECONDS = 15 * 60
MAX_CODES_PER_IP = 15
FAILURE_WINDOW_SECONDS = 15 * 60

COOLDOWN_MESSAGE = 'Please wait 60 seconds before requesting another code'
SEND_CAP_MESSAGE = 'Too many codes were requested. Please try again in 15 minutes.'
LOCK_MESSAGE = 'Too many attempts. Please wait 15 minutes before requesting another code.'

# Header pair stamped by the Cloudflare Pages function. The secret is what
# makes the IP trustworthy: a request that hits Render directly can set
# X-Forwarded-For to anything, so that header is never read here.
VISITOR_IP_HEADER = 'x-visitor-ip'
VISITOR_SECRET_HEADER = 'x-visitor-secret'

# Deliberately permissive: this is a deliverability check, not an attempt to
# implement RFC 5322. The real validation is that a code has to arrive.
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s.]+\.[^@\s]+$')

_GENERATED_SECRET = None


class IdentityError(Exception):
    """Something the caller did wrong, safe to report to them."""


def _session_secret():
    global _GENERATED_SECRET
    configured = os.environ.get('SESSION_SECRET', '').strip()
    if configured:
        return configured
    if _GENERATED_SECRET is None:
        _GENERATED_SECRET = secrets.token_urlsafe(32)
        logger.warning(
            'SESSION_SECRET is not set; generated an ephemeral one. Sessions '
            'will not survive a restart. Set SESSION_SECRET in production.')
    return _GENERATED_SECRET


def secret_is_persistent():
    return bool(os.environ.get('SESSION_SECRET', '').strip())


def normalise_email(email):
    email = (email or '').strip().lower()
    if not _EMAIL_RE.match(email) or len(email) > 254:
        raise IdentityError('that does not look like an email address')
    return email


def canonical_email(email):
    """One inbox, one bucket.

    Gmail ignores dots in the local part and treats ``+tag`` as the same
    mailbox. Without this, a.b+1@gmail.com and ab@gmail.com are two counters
    and the resend cap never applies to the inbox that actually receives them.
    """
    email = normalise_email(email)
    local, _, domain = email.partition('@')
    # Plus-tags are the same mailbox on Gmail and on most other providers.
    local = local.split('+', 1)[0]
    if domain in ('gmail.com', 'googlemail.com'):
        local = local.replace('.', '')
        domain = 'gmail.com'
    if not local or not domain:
        raise IdentityError('that does not look like an email address')
    return '%s@%s' % (local, domain)


def verified_client_ip(headers):
    """The visitor IP, or None when it cannot be trusted.

    The secret is optional. Unset (local development, and any caller that does
    not pass through Cloudflare, such as a Razorpay webhook or a health check)
    means "no IP", not "reject the request". A wrong or missing secret also
    means "no IP": the forwarded address is ignored rather than enforced.
    """
    secret = os.environ.get('CF_VISITOR_SECRET', '').strip()
    if not secret:
        return None
    presented = ''
    if headers is not None:
        getter = getattr(headers, 'get', None)
        presented = (getter(VISITOR_SECRET_HEADER, '') if getter else '') or ''
    presented = str(presented)
    if len(presented) != len(secret) or not hmac.compare_digest(presented, secret):
        return None
    ip = str(headers.get(VISITOR_IP_HEADER, '') or '').strip()
    if not ip or len(ip) > 64 or any(c in ip for c in ' \r\n'):
        return None
    return ip


def _email_fingerprint(email):
    """A short hash for logs. Never log the address itself."""
    return hashlib.sha256(email.encode('utf-8')).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Login codes
# ---------------------------------------------------------------------------

CODE_SCHEMA = """
CREATE TABLE IF NOT EXISTS login_code (
    email       TEXT PRIMARY KEY,
    code_hash   TEXT NOT NULL,
    expires_at  DOUBLE PRECISION NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    created_at  DOUBLE PRECISION NOT NULL,
    failed_at   DOUBLE PRECISION NOT NULL DEFAULT 0
)
"""

SEND_SCHEMA = """
CREATE TABLE IF NOT EXISTS login_send (
    bucket        TEXT PRIMARY KEY,
    window_start  DOUBLE PRECISION NOT NULL,
    hits          INTEGER NOT NULL,
    last_at       DOUBLE PRECISION NOT NULL
)
"""


def _store():
    """The wallet's connection, so identity and credits share a transaction log."""
    import wallet
    wallet.init_storage()
    return wallet


def _ensure_schema():
    wallet = _store()
    for statement in (CODE_SCHEMA, SEND_SCHEMA):
        sql = statement if wallet.storage_is_durable() else statement.replace(
            'DOUBLE PRECISION', 'REAL')
        wallet._execute(sql, (), commit=True)
    # Tables created before failed_at existed still need the column. Adding it
    # twice is an error on both drivers; that error is the "already there" case.
    alter = 'ALTER TABLE login_code ADD COLUMN failed_at DOUBLE PRECISION NOT NULL DEFAULT 0'
    if not wallet.storage_is_durable():
        alter = alter.replace('DOUBLE PRECISION', 'REAL')
    try:
        wallet._execute(alter, (), commit=True)
    except Exception:
        pass


def _hash_code(email, code):
    """Codes are stored hashed and salted with the address.

    A database read should not hand someone a working code for every pending
    login, and salting with the email stops one leaked hash being replayed
    against a different address.
    """
    return hashlib.sha256(
        ('%s:%s:%s' % (_session_secret(), email, code)).encode('utf-8')).hexdigest()


def _failure_still_counts(attempts, failed_at, now):
    if not failed_at or int(attempts or 0) <= 0:
        return False
    return (now - float(failed_at)) < FAILURE_WINDOW_SECONDS


def login_locked(email):
    """True when this inbox is inside the 15-minute failure window.

    Checked before a send is counted, so a locked address does not burn a
    resend slot or a Brevo message.
    """
    email = canonical_email(email)
    _ensure_schema()
    wallet = _store()
    cur = wallet._execute(
        'SELECT attempts, failed_at FROM login_code WHERE email = ?', (email,))
    row = cur.fetchone()
    if not row:
        return False
    return (int(row[0]) >= MAX_CODE_ATTEMPTS
            and _failure_still_counts(row[0], row[1], time.time()))


def issue_code(email):
    """Create a login code for *email* and return it.

    Returning the code rather than sending it keeps delivery out of this
    module: the caller passes it to whatever sender is configured. That also
    makes the whole flow testable without a mail server.

    A previous run of failures is kept. Replacing the row used to start the
    attempt counter at zero, so asking for a fresh code was a way past the cap.
    """
    email = canonical_email(email)
    _ensure_schema()
    wallet = _store()
    now = time.time()

    cur = wallet._execute(
        'SELECT attempts, failed_at FROM login_code WHERE email = ?', (email,))
    row = cur.fetchone()
    attempts = int(row[0]) if row else 0
    failed_at = float(row[1] or 0) if row else 0
    if attempts >= MAX_CODE_ATTEMPTS and _failure_still_counts(attempts, failed_at, now):
        raise IdentityError(LOCK_MESSAGE)
    if not _failure_still_counts(attempts, failed_at, now):
        attempts = 0
        failed_at = 0

    code = ''.join(secrets.choice('0123456789') for _ in range(CODE_LENGTH))
    code_hash = _hash_code(email, code)
    expires_at = now + CODE_TTL_SECONDS
    updated = wallet._execute(
        'UPDATE login_code SET code_hash = ?, expires_at = ?, created_at = ?, '
        'attempts = ?, failed_at = ? WHERE email = ?',
        (code_hash, expires_at, now, attempts, failed_at, email),
        commit=True)
    if updated.rowcount != 1:
        wallet._execute(
            'INSERT INTO login_code '
            '(email, code_hash, expires_at, attempts, created_at, failed_at) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (email, code_hash, expires_at, attempts, now, failed_at),
            commit=True)
    logger.info('login code issued for %s', _email_fingerprint(email))
    return code


def _claim_bucket(cur, query, bucket, limit, window, cooldown, now, cap_message):
    """Count one send, or raise. The increment itself is a single UPDATE."""
    cur.execute(query(
        'UPDATE login_send SET hits = hits + 1, last_at = ? '
        'WHERE bucket = ? AND window_start > ? AND hits < ? AND last_at <= ?'),
        (now, bucket, now - window, limit, now - cooldown))
    if cur.rowcount == 1:
        return
    cur.execute(query(
        'SELECT window_start, hits, last_at FROM login_send WHERE bucket = ?'),
        (bucket,))
    row = cur.fetchone()
    if row is None:
        wallet = _store()
        insert = (
            'INSERT INTO login_send (bucket, window_start, hits, last_at) '
            'VALUES (?, ?, 1, ?) ON CONFLICT (bucket) DO NOTHING'
            if wallet.storage_is_durable() else
            'INSERT OR IGNORE INTO login_send (bucket, window_start, hits, last_at) '
            'VALUES (?, ?, 1, ?)')
        cur.execute(query(insert), (bucket, now, now))
        if cur.rowcount == 1:
            return
        cur.execute(query(
            'UPDATE login_send SET hits = hits + 1, last_at = ? '
            'WHERE bucket = ? AND window_start > ? AND hits < ? AND last_at <= ?'),
            (now, bucket, now - window, limit, now - cooldown))
        if cur.rowcount == 1:
            return
        cur.execute(query(
            'SELECT window_start, hits, last_at FROM login_send WHERE bucket = ?'),
            (bucket,))
        row = cur.fetchone()
        if row is None:
            raise IdentityError(cap_message)
    window_start, hits, last_at = float(row[0]), int(row[1]), float(row[2])
    if now - window_start >= window:
        cur.execute(query(
            'UPDATE login_send SET window_start = ?, hits = 1, last_at = ? '
            'WHERE bucket = ?'),
            (now, now, bucket))
        return
    if cooldown and now - last_at < cooldown:
        raise IdentityError(COOLDOWN_MESSAGE)
    raise IdentityError(cap_message)


def claim_send(email, ip=None):
    """Reserve one code email. Raises before any message is sent.

    Email: 60 seconds between sends, and 5 sends per 15 minutes.
    IP: 15 sends per 15 minutes, and only when *ip* came from the verified
    Cloudflare header. ``None`` means there is no trusted IP, so the email
    cap still applies and the request is not rejected for lacking one.
    """
    email = canonical_email(email)
    _ensure_schema()
    wallet = _store()
    now = time.time()
    with wallet._transaction() as conn:
        cur = conn.cursor()
        if ip:
            _claim_bucket(
                cur, wallet._q, 'ip:%s' % ip, MAX_CODES_PER_IP,
                SEND_WINDOW_SECONDS, 0, now, SEND_CAP_MESSAGE)
        _claim_bucket(
            cur, wallet._q, 'email:%s' % email, MAX_CODES_PER_WINDOW,
            SEND_WINDOW_SECONDS, RESEND_COOLDOWN_SECONDS, now, SEND_CAP_MESSAGE)


def verify_code(email, code):
    """Return the account id on success. Raises IdentityError otherwise.

    The code is single-use: it is deleted on success. A wrong guess increments
    the counter in the same statement that checks the cap, so two requests
    cannot both be the fifth. The row is kept once the cap is reached so the
    next code request cannot start again at zero.
    """
    email = canonical_email(email)
    _ensure_schema()
    wallet = _store()

    cur = wallet._execute(
        'SELECT code_hash, expires_at, attempts, failed_at FROM login_code WHERE email = ?',
        (email,))
    row = cur.fetchone()
    if not row:
        raise IdentityError('no code was requested for that address')

    code_hash, expires_at = row[0], float(row[1])
    attempts = int(row[2])
    failed_at = float(row[3] or 0)
    now = time.time()

    if now > expires_at or not code_hash:
        if attempts <= 0:
            wallet._execute(
                'DELETE FROM login_code WHERE email = ?', (email,), commit=True)
        else:
            wallet._execute(
                'UPDATE login_code SET code_hash = ?, expires_at = ? WHERE email = ?',
                ('', now, email), commit=True)
        raise IdentityError('that code has expired, request a new one')

    supplied = _hash_code(email, str(code or '').strip())
    if hmac.compare_digest(code_hash, supplied):
        deleted = wallet._execute(
            'DELETE FROM login_code WHERE email = ? AND code_hash = ? AND attempts < ?',
            (email, code_hash, MAX_CODE_ATTEMPTS), commit=True)
        if deleted.rowcount != 1:
            raise IdentityError('too many attempts, request a new code')
        account_id = wallet.get_or_create_account(email)
        wallet.grant_trial(account_id)
        logger.info('login succeeded for %s', _email_fingerprint(email))
        return account_id

    consumed = wallet._execute(
        'UPDATE login_code SET attempts = attempts + 1, failed_at = ? '
        'WHERE email = ? AND attempts < ?',
        (now, email, MAX_CODE_ATTEMPTS), commit=True)
    if consumed.rowcount != 1:
        raise IdentityError('too many attempts, request a new code')
    raise IdentityError('that code is not right')


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

SESSION_COOKIE = 'sc_session'


def _sign(payload):
    return base64.urlsafe_b64encode(
        hmac.new(_session_secret().encode('utf-8'),
                 payload.encode('utf-8'), hashlib.sha256).digest()
    ).decode('ascii').rstrip('=')


def make_session(account_id, ttl=SESSION_TTL_SECONDS):
    """account_id.expiry.signature - nothing in it is trusted before the HMAC."""
    expiry = int(time.time() + ttl)
    payload = '%s.%d' % (account_id, expiry)
    return '%s.%s' % (payload, _sign(payload))


def read_session(token):
    """Return the account id, or None for anything that does not verify.

    Returns None rather than raising for every failure mode - expired,
    tampered, malformed, absent - because the caller's response is the same in
    all of them: treat this request as anonymous.
    """
    if not token or not isinstance(token, str):
        return None
    parts = token.rsplit('.', 2)
    if len(parts) != 3:
        return None
    account_id, expiry_raw, signature = parts

    payload = '%s.%s' % (account_id, expiry_raw)
    if not hmac.compare_digest(_sign(payload), signature):
        return None

    try:
        expiry = int(expiry_raw)
    except ValueError:
        return None
    if time.time() > expiry:
        return None
    if not account_id.startswith('acct_'):
        return None
    return account_id


def session_cookie_kwargs():
    """Cookie flags.

    SameSite=None is required because the frontend is served from a different
    origin to the API, and None demands Secure. The CSRF defence is therefore
    the existing token plus Sec-Fetch-Site checks, not the cookie's SameSite.
    """
    return {
        'httponly': True,
        'secure': True,
        'samesite': 'none',
        'max_age': SESSION_TTL_SECONDS,
        'path': '/',
    }

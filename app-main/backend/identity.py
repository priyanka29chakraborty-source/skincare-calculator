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
  10 minutes, and allow 5 attempts before the code is burned. Without the
  attempt cap, 6 digits is a million guesses against an endpoint - minutes of
  scripted traffic.
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
    created_at  DOUBLE PRECISION NOT NULL
)
"""


def _store():
    """The wallet's connection, so identity and credits share a transaction log."""
    import wallet
    wallet.init_storage()
    return wallet


def _ensure_schema():
    wallet = _store()
    sql = CODE_SCHEMA if wallet.storage_is_durable() else CODE_SCHEMA.replace(
        'DOUBLE PRECISION', 'REAL')
    wallet._execute(sql, (), commit=True)


def _hash_code(email, code):
    """Codes are stored hashed and salted with the address.

    A database read should not hand someone a working code for every pending
    login, and salting with the email stops one leaked hash being replayed
    against a different address.
    """
    return hashlib.sha256(
        ('%s:%s:%s' % (_session_secret(), email, code)).encode('utf-8')).hexdigest()


def issue_code(email):
    """Create a login code for *email* and return it.

    Returning the code rather than sending it keeps delivery out of this
    module: the caller passes it to whatever sender is configured. That also
    makes the whole flow testable without a mail server.
    """
    email = normalise_email(email)
    _ensure_schema()
    wallet = _store()

    code = ''.join(secrets.choice('0123456789') for _ in range(CODE_LENGTH))
    now = time.time()
    wallet._execute('DELETE FROM login_code WHERE email = ?', (email,))
    wallet._execute(
        'INSERT INTO login_code (email, code_hash, expires_at, attempts, created_at) '
        'VALUES (?, ?, ?, 0, ?)',
        (email, _hash_code(email, code), now + CODE_TTL_SECONDS, now),
        commit=True)
    logger.info('login code issued for %s', _email_fingerprint(email))
    return code


def verify_code(email, code):
    """Return the account id on success. Raises IdentityError otherwise.

    The code is single-use: it is deleted on success, on expiry, and when the
    attempt cap is reached. Without the cap, six digits is a million guesses
    against an HTTP endpoint.
    """
    email = normalise_email(email)
    _ensure_schema()
    wallet = _store()

    cur = wallet._execute(
        'SELECT code_hash, expires_at, attempts FROM login_code WHERE email = ?',
        (email,))
    row = cur.fetchone()
    if not row:
        raise IdentityError('no code was requested for that address')

    code_hash, expires_at, attempts = row[0], float(row[1]), int(row[2])

    if time.time() > expires_at:
        wallet._execute('DELETE FROM login_code WHERE email = ?', (email,), commit=True)
        raise IdentityError('that code has expired, request a new one')

    if attempts >= MAX_CODE_ATTEMPTS:
        wallet._execute('DELETE FROM login_code WHERE email = ?', (email,), commit=True)
        raise IdentityError('too many attempts, request a new code')

    if not hmac.compare_digest(code_hash, _hash_code(email, str(code or '').strip())):
        wallet._execute(
            'UPDATE login_code SET attempts = attempts + 1 WHERE email = ?',
            (email,), commit=True)
        raise IdentityError('that code is not right')

    wallet._execute('DELETE FROM login_code WHERE email = ?', (email,), commit=True)
    account_id = wallet.get_or_create_account(email)
    wallet.grant_trial(account_id)
    logger.info('login succeeded for %s', _email_fingerprint(email))
    return account_id


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

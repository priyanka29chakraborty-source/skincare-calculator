"""Paid analysis credits: accounts, an append-only ledger, and atomic spend.

Named wallet rather than credits because ``credits.py`` already tracks our own
third-party API quotas (Firecrawl, ScraperAPI). This module is about the
customer's money.

What this has to get right
--------------------------

Three failures here cost real money or real trust, so each is prevented by the
database rather than by careful code:

1. **Granting credits twice for one payment.** A payment gateway will retry a
   webhook until it gets a 2xx, so the same ``payment_id`` arrives repeatedly -
   that is normal operation, not an attack. A SELECT-then-INSERT check loses
   that race under concurrency. Instead ``reference`` carries a UNIQUE
   constraint and a duplicate grant is an integrity error we swallow, so the
   second delivery is a no-op no matter how it interleaves.

2. **Spending a credit twice.** Read-balance-then-write lets two concurrent
   analyses both see "1 remaining" and both proceed. Spend is therefore a
   single conditional UPDATE whose WHERE clause carries the balance check, and
   a spend is only real if that UPDATE reports a row changed.

3. **Losing the audit trail.** Balance is a cached column, but every change is
   also an immutable ledger row. If the two ever disagree, the ledger wins and
   ``recompute_balance`` repairs the cache. A customer disputing a charge, or
   us answering "where did my 15 analyses go", needs rows, not a number.

Storage follows the same pattern as admin_db: PostgreSQL when AIVEN_PG_URL is
set, SQLite otherwise.

    PRODUCTION NOTE - this must not run on SQLite on Render. Render's
    filesystem is ephemeral unless a disk is explicitly attached, so a restart
    would delete the ledger and every credit a customer paid for. Set
    AIVEN_PG_URL. ``storage_is_durable()`` reports this and the health endpoint
    surfaces it.
"""

import contextlib
import logging
import os
import secrets
import threading
import time

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------
# Prices are in paise, the smallest unit, because that is what Razorpay's API
# takes and because float rupees would eventually produce a 98.99999 charge.
CREDIT_PACKS = {
    'starter': {'credits': 5,  'amount_paise': 9900,  'label': '5 analyses'},
    'regular': {'credits': 8,  'amount_paise': 14900, 'label': '8 analyses'},
    'bulk':    {'credits': 12, 'amount_paise': 19900, 'label': '12 analyses'},
}

# One personalised analysis costs one credit. A comparison costs one credit
# per product compared, with a pair as the minimum: two products cost two,
# three cost three, and so on up to six.
COST_PER_ANALYSIS = 1
COST_PER_COMPARISON = 2


def comparison_cost(product_count):
    """Credits for comparing this many products: one each, two at the least."""
    return max(COST_PER_COMPARISON, int(product_count or 0))

# First email sign-in. Four credits covers two analyses, or one analysis
# and one comparison, or two comparisons.
TRIAL_CREDITS = 4

# Unused credits from a purchase lapse one year after that purchase.
CREDIT_LIFETIME_SECONDS = 365 * 24 * 60 * 60

# Reasons a ledger row exists. Stored as text so the history reads plainly.
REASON_PURCHASE = 'purchase'
REASON_SPEND = 'spend'
REASON_REFUND = 'refund'
REASON_GRANT = 'grant'          # manual goodwill or a promotion
REASON_REVERSAL = 'reversal'    # undoing a spend that failed downstream
REASON_EXPIRY = 'expiry'        # unused credits one year after purchase


class InsufficientCredits(Exception):
    """Raised when a spend is attempted without the balance to cover it."""


class WalletError(Exception):
    """Storage-level failure. Callers must treat this as 'do not deliver'."""


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_PG_URL = os.environ.get('AIVEN_PG_URL', '')
_USE_PG = bool(_PG_URL)
_local = threading.local()
_init_lock = threading.Lock()
_initialised = False


def storage_is_durable():
    """True when the ledger is on PostgreSQL rather than a local file.

    Exposed so the health endpoint can say so out loud: selling credits that
    live only on an ephemeral disk is the kind of failure you discover from a
    customer, not from a log.
    """
    return _USE_PG


def _sqlite_path():
    return os.environ.get(
        'WALLET_DB_PATH',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wallet.db'))


def _connect():
    if _USE_PG:
        import psycopg
        conn = getattr(_local, 'pg', None)
        if conn is None or conn.closed:
            from admin_db import AIVEN_PG_URL
            conn = psycopg.connect(conninfo=AIVEN_PG_URL)
            _local.pg = conn
        return conn
    import sqlite3
    conn = getattr(_local, 'sq', None)
    if conn is None:
        conn = sqlite3.connect(_sqlite_path(), check_same_thread=False,
                               isolation_level=None)
        conn.row_factory = sqlite3.Row
        # WAL lets a reader run while a writer holds the table, which is what
        # a web process does constantly.
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=5000')
        _local.sq = conn
    return conn


def _ph(n):
    """Placeholders for the active driver: %s for psycopg, ? for sqlite3."""
    return ', '.join(['%s' if _USE_PG else '?'] * n)


def _q(sql):
    """Translate ? placeholders to %s when running on PostgreSQL."""
    return sql.replace('?', '%s') if _USE_PG else sql


SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS wallet_account (
        account_id   TEXT PRIMARY KEY,
        email        TEXT UNIQUE,
        balance      INTEGER NOT NULL DEFAULT 0,
        created_at   DOUBLE PRECISION NOT NULL,
        updated_at   DOUBLE PRECISION NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS wallet_ledger (
        entry_id     TEXT PRIMARY KEY,
        account_id   TEXT NOT NULL,
        delta        INTEGER NOT NULL,
        reason       TEXT NOT NULL,
        reference    TEXT,
        metadata     TEXT,
        created_at   DOUBLE PRECISION NOT NULL
    )
    """,
    # The idempotency guarantee. A duplicate webhook delivery hits this
    # constraint and is swallowed, which is why grant() does not need to read
    # before it writes.
    "CREATE UNIQUE INDEX IF NOT EXISTS wallet_ledger_reference_uniq "
    "ON wallet_ledger (reference) WHERE reference IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS wallet_ledger_account_idx "
    "ON wallet_ledger (account_id, created_at)",
]

# SQLite understands partial indexes; the syntax above is portable to both.


def init_storage():
    global _initialised
    if _initialised:
        return
    with _init_lock:
        if _initialised:
            return
        conn = _connect()
        cur = conn.cursor()
        for statement in SCHEMA:
            sql = statement
            if not _USE_PG:
                sql = sql.replace('DOUBLE PRECISION', 'REAL')
            cur.execute(sql)
        if _USE_PG:
            conn.commit()
        _initialised = True
        if not _USE_PG:
            logger.warning(
                'wallet is running on SQLite at %s. This is correct for local '
                'development and WRONG for production: set AIVEN_PG_URL, or a '
                'restart will delete credits customers have paid for.',
                _sqlite_path())


def _execute(sql, params=(), commit=False):
    init_storage()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(_q(sql), params)
    if commit:
        _commit(conn)
    return cur


def _commit(conn):
    if _USE_PG:
        conn.commit()
    elif conn.in_transaction:
        conn.commit()


def _rollback(conn):
    try:
        if _USE_PG or conn.in_transaction:
            conn.rollback()
    except Exception:
        logger.exception('rollback failed')


@contextlib.contextmanager
def _transaction():
    """One unit of work on either driver.

    The SQLite connection is opened in autocommit (isolation_level=None), which
    is what lets reads run without an open transaction - but it also means a
    multi-statement change needs an explicit BEGIN or it is not atomic. A
    grant interrupted between its ledger row and its balance update would
    otherwise leave the two disagreeing.

    BEGIN IMMEDIATE rather than BEGIN: it takes the write lock up front, so two
    writers fail fast on busy_timeout instead of one discovering it cannot
    upgrade halfway through.
    """
    init_storage()
    conn = _connect()
    if not _USE_PG:
        conn.execute('BEGIN IMMEDIATE')
    try:
        yield conn
    except BaseException:
        _rollback(conn)
        raise
    else:
        _commit(conn)


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def _now():
    return time.time()


def _new_id(prefix):
    return '%s_%s' % (prefix, secrets.token_urlsafe(16))


def get_or_create_account(email):
    """Return the account id for *email*, creating it if new.

    Email is lowercased and stripped so that "A@b.com " and "a@b.com" are one
    account - otherwise a customer can pay on one and spend on the other.
    """
    email = (email or '').strip().lower()
    if not email:
        raise WalletError('an account needs an email address')

    cur = _execute('SELECT account_id FROM wallet_account WHERE email = ?', (email,))
    row = cur.fetchone()
    if row:
        return row[0]

    account_id = _new_id('acct')
    now = _now()
    try:
        _execute(
            'INSERT INTO wallet_account (account_id, email, balance, created_at, updated_at) '
            'VALUES (?, ?, 0, ?, ?)',
            (account_id, email, now, now), commit=True)
        return account_id
    except Exception:
        # Lost the race against a concurrent signup for the same address.
        # The row now exists; read it rather than failing the request.
        cur = _execute('SELECT account_id FROM wallet_account WHERE email = ?', (email,))
        row = cur.fetchone()
        if row:
            return row[0]
        raise


def _remaining_lots(rows, now):
    """Replay the ledger. A credit lasts one year from the row that added it.

    Spends consume the oldest credits that had not already lapsed at the
    moment of the spend. A later purchase moves every credit that is still
    valid at that moment onto the new purchase's expiry. Credits that had
    already lapsed stay lapsed.
    """
    lots = []
    for row in rows:
        delta = int(row[0])
        created_at = float(row[1])
        reason = row[2] if len(row) > 2 else ''
        if delta > 0:
            expires = created_at + CREDIT_LIFETIME_SECONDS
            if reason == REASON_PURCHASE:
                for lot in lots:
                    if lot[0] > 0 and lot[1] > created_at:
                        lot[1] = expires
            lots.append([delta, expires, created_at])
            continue
        need = -delta
        for lot in lots:
            if need <= 0:
                break
            if lot[1] <= created_at:
                continue
            take = min(lot[0], need)
            lot[0] -= take
            need -= take
    alive = 0
    expired = 0
    stamps = []
    soonest = None
    for remaining, expires_at, created_at in lots:
        if remaining <= 0:
            continue
        if expires_at <= now:
            expired += remaining
            stamps.append(str(int(created_at)))
        else:
            alive += remaining
            if soonest is None or expires_at < soonest:
                soonest = expires_at
    return alive, expired, stamps, soonest


def _apply_expiry_locked(conn, account_id):
    """Drop lapsed credits while this account row is locked.

    Sets the cached balance to what is still inside its year. An expiry row
    keeps the ledger equal to that number, so a later replay does not lapse
    the same credits again.
    """
    cur = conn.cursor()
    lock_sql = 'SELECT balance FROM wallet_account WHERE account_id = ?'
    if _USE_PG:
        lock_sql += ' FOR UPDATE'
    cur.execute(_q(lock_sql), (account_id,))
    row = cur.fetchone()
    if not row:
        return 0
    cur.execute(_q(
        'SELECT delta, created_at, reason FROM wallet_ledger '
        'WHERE account_id = ? ORDER BY created_at ASC'), (account_id,))
    now = _now()
    alive, expired, stamps, _soonest = _remaining_lots(cur.fetchall(), now)
    if expired > 0:
        import hashlib
        reference = 'expiry:%s:%s' % (
            account_id,
            hashlib.sha256(','.join(stamps).encode()).hexdigest()[:20])
        cur.execute(_q(
            'SELECT 1 FROM wallet_ledger WHERE reference = ?'), (reference,))
        if not cur.fetchone():
            cur.execute(_q(
                'INSERT INTO wallet_ledger '
                '(entry_id, account_id, delta, reason, reference, metadata, created_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?)'),
                (_new_id('led'), account_id, -int(expired), REASON_EXPIRY,
                 reference, None, now))
    if int(row[0]) != alive:
        cur.execute(_q(
            'UPDATE wallet_account SET balance = ?, updated_at = ? WHERE account_id = ?'),
            (int(alive), now, account_id))
    return alive


def has_purchased(account_id):
    """True once this account has bought any credit pack.

    The sign-in trial is a grant, not a purchase, so it does not unlock the
    product PDF.
    """
    if not account_id:
        return False
    cur = _execute(
        'SELECT 1 FROM wallet_ledger WHERE account_id = ? AND reason = ? '
        'AND delta > 0 LIMIT 1',
        (account_id, REASON_PURCHASE))
    return cur.fetchone() is not None


def list_accounts(limit=100):
    """Recent sign-ins: email, credits left, and when the account was created."""
    cur = _execute(
        'SELECT email, balance, created_at FROM wallet_account '
        'ORDER BY created_at DESC LIMIT ?',
        (int(limit),))
    return [
        {'email': row[0], 'balance': row[1], 'created_at': row[2]}
        for row in cur.fetchall()
    ]


def count_accounts_since(since_ts):
    cur = _execute(
        'SELECT COUNT(*) FROM wallet_account WHERE created_at >= ?',
        (float(since_ts),))
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def account_email(account_id):
    if not account_id:
        return None
    cur = _execute(
        'SELECT email FROM wallet_account WHERE account_id = ?', (account_id,))
    row = cur.fetchone()
    if not row or not row[0]:
        return None
    return str(row[0]).strip().lower()


def owner_emails():
    """Addresses in OWNER_EMAIL. One address, or several separated by commas."""
    raw = os.environ.get('OWNER_EMAIL', '')
    return [part.strip().lower() for part in raw.split(',') if part.strip()]


def is_owner(account_id):
    """True for an address listed in OWNER_EMAIL.

    This is a lifetime pass for the people who run the app. It is not a
    credit grant, so it does not expire after a year, and it is not
    DEV_UNLOCK_ALL, which would open the paid result to every visitor.
    The list is read when the request arrives, from the environment, and
    it is compared with the email on the signed-in account. A request cannot
    name itself as the owner.
    """
    owners = owner_emails()
    if not owners or not account_id:
        return False
    return account_email(account_id) in owners


def credit_expires_at(account_id):
    """When the credits still on this account lapse. None when none remain."""
    if not account_id:
        return None
    cur = _execute(
        'SELECT delta, created_at, reason FROM wallet_ledger '
        'WHERE account_id = ? ORDER BY created_at ASC',
        (account_id,))
    _alive, _expired, _stamps, soonest = _remaining_lots(cur.fetchall(), _now())
    return soonest


def get_balance(account_id):
    with _transaction() as conn:
        _apply_expiry_locked(conn, account_id)
    cur = _execute('SELECT balance FROM wallet_account WHERE account_id = ?', (account_id,))
    row = cur.fetchone()
    return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

def _write_entry(account_id, delta, reason, reference, metadata):
    entry_id = _new_id('led')
    _execute(
        'INSERT INTO wallet_ledger '
        '(entry_id, account_id, delta, reason, reference, metadata, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)',
        (entry_id, account_id, int(delta), reason, reference, metadata, _now()))
    return entry_id


def grant(account_id, credits, reason=REASON_PURCHASE, reference=None, metadata=None):
    """Add credits. Idempotent on *reference*.

    Returns the new balance, or None when *reference* has already been granted.
    None is the normal result of a retried webhook, not an error - callers
    should still answer 2xx so the gateway stops retrying.

    The ledger row is written first and its UNIQUE constraint is what makes
    this idempotent. Incrementing the balance first would double-count on the
    retry that the constraint then rejects.
    """
    if credits <= 0:
        raise WalletError('grant needs a positive number of credits')

    try:
        with _transaction() as conn:
            _write_entry(account_id, credits, reason, reference, metadata)
            cur = conn.cursor()
            cur.execute(_q(
                'UPDATE wallet_account SET balance = balance + ?, updated_at = ? '
                'WHERE account_id = ?'),
                (int(credits), _now(), account_id))
            if cur.rowcount != 1:
                raise WalletError('no such account: %s' % (account_id,))
    except Exception as exc:
        if reference and _is_duplicate(exc):
            logger.info('duplicate grant for reference %s ignored', reference)
            return None
        raise

    return get_balance(account_id)


def grant_trial(account_id):
    """Four credits, once, the first time this email signs in.

    The reference is the account, so signing in again does not add another
    four. Returns the new balance, or None when this account already received
    the trial.
    """
    return grant(
        account_id, TRIAL_CREDITS,
        reason=REASON_GRANT,
        reference='trial:%s' % account_id,
        metadata='signup_trial')


def already_spent(reference):
    """True when this exact charge has already been written to the ledger.

    Reopening a product or a comparison must stay free even after the balance
    is zero. ``spend`` checks the balance first, so a second call with the
    same reference raises InsufficientCredits before the unique index can say
    the charge already happened. Callers look here first.
    """
    if not reference:
        return False
    cur = _execute(
        'SELECT 1 FROM wallet_ledger WHERE reference = ? LIMIT 1', (reference,))
    return cur.fetchone() is not None


def spend(account_id, credits=COST_PER_ANALYSIS, reference=None, metadata=None):
    """Deduct credits atomically. Raises InsufficientCredits if unaffordable.

    The balance check lives in the WHERE clause, so two concurrent requests
    cannot both succeed against the same last credit: whichever UPDATE the
    database applies second matches no row and raises.
    """
    if credits <= 0:
        raise WalletError('spend needs a positive number of credits')

    try:
        with _transaction() as conn:
            _apply_expiry_locked(conn, account_id)
            cur = conn.cursor()
            cur.execute(_q(
                'UPDATE wallet_account SET balance = balance - ?, updated_at = ? '
                'WHERE account_id = ? AND balance >= ?'),
                (int(credits), _now(), account_id, int(credits)))
            if cur.rowcount != 1:
                raise InsufficientCredits(
                    'balance is short of %d' % (credits,))
            _write_entry(account_id, -credits, REASON_SPEND, reference, metadata)
    except InsufficientCredits:
        raise
    except Exception as exc:
        # A retried request carrying the same reference must not be charged
        # twice. The whole transaction rolled back, so the deduction is already
        # undone - just report the balance.
        if not (reference and _is_duplicate(exc)):
            raise
        logger.info('duplicate spend for reference %s ignored', reference)

    return get_balance(account_id)


def refund(account_id, credits=COST_PER_ANALYSIS, reference=None, metadata=None):
    """Return credits after a failed delivery.

    Separate from grant so the ledger distinguishes "we gave this back because
    our analysis errored" from "they bought more", which matters when reading
    an account's history during a dispute.
    """
    return grant(account_id, credits, reason=REASON_REVERSAL,
                 reference=reference, metadata=metadata)


def history(account_id, limit=50):
    cur = _execute(
        'SELECT entry_id, delta, reason, reference, metadata, created_at '
        'FROM wallet_ledger WHERE account_id = ? '
        'ORDER BY created_at DESC LIMIT ?',
        (account_id, int(limit)))
    return [
        {
            'entry_id': r[0], 'delta': int(r[1]), 'reason': r[2],
            'reference': r[3], 'metadata': r[4], 'created_at': r[5],
        }
        for r in cur.fetchall()
    ]


def recompute_balance(account_id):
    """Rebuild the cached balance from the ledger. The ledger is the truth.

    Used by the admin page and after any incident. If this ever changes a
    balance, something above is wrong and the ledger rows say what.
    """
    with _transaction() as conn:
        total = _apply_expiry_locked(conn, account_id)
    return total


def _is_duplicate(exc):
    """True when *exc* is a unique-constraint violation on either driver."""
    name = type(exc).__name__
    text = str(exc).lower()
    if name in ('UniqueViolation', 'IntegrityError'):
        return 'unique' in text or 'duplicate' in text or 'constraint' in text
    return False


def pack_for(pack_id):
    pack = CREDIT_PACKS.get(pack_id)
    if not pack:
        raise WalletError('unknown pack %r' % (pack_id,))
    return dict(pack, pack_id=pack_id)

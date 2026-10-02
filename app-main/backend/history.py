"""Saved analyses: what a signed-in customer has looked at before.

Why this stores a summary and not the whole analysis
----------------------------------------------------
A full analysis is large, and most of it is derived - re-running the engine on
the same ingredients produces it again exactly, because the score depends on
the product and the profile, not on when it was computed. So a row keeps what
is needed to show a list and to re-open the product: the identity, the score,
and the inputs. Storing the rendered payload instead would mean serving stale
results after a scoring change, which is the worse failure: a customer
comparing yesterday's saved 91 with today's recalculated 87 and concluding the
tool is unreliable.

Privacy
-------
The ingredient list is the one piece of real personal data here - it says what
someone puts on their skin, and in aggregate what they are treating. It is
stored because re-opening a saved product is the entire point of the feature,
but it is never logged, never returned for another account, and
``forget_all`` exists so an account can be emptied on request.
"""

import json
import logging
import time

logger = logging.getLogger(__name__)

MAX_ROWS_PER_ACCOUNT = 200

SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_history (
    entry_id     TEXT PRIMARY KEY,
    account_id   TEXT NOT NULL,
    analysis_key TEXT NOT NULL,
    product_name TEXT,
    brand        TEXT,
    category     TEXT,
    score        INTEGER,
    tier         TEXT,
    price        REAL,
    size_ml      REAL,
    currency     TEXT,
    skin_type    TEXT,
    concerns     TEXT,
    ingredients  TEXT,
    was_paid     INTEGER NOT NULL DEFAULT 0,
    created_at   DOUBLE PRECISION NOT NULL
)
"""

INDEXES = [
    # One row per account per product: re-analysing updates in place rather
    # than filling the list with the same product over and over.
    "CREATE UNIQUE INDEX IF NOT EXISTS analysis_history_key_uniq "
    "ON analysis_history (account_id, analysis_key)",
    "CREATE INDEX IF NOT EXISTS analysis_history_recent_idx "
    "ON analysis_history (account_id, created_at)",
]


def _wallet():
    import wallet
    wallet.init_storage()
    return wallet


def ensure_schema():
    wallet = _wallet()
    sql = SCHEMA if wallet.storage_is_durable() else SCHEMA.replace(
        'DOUBLE PRECISION', 'REAL')
    wallet._execute(sql, (), commit=True)
    for statement in INDEXES:
        wallet._execute(statement, (), commit=True)


def record(account_id, analysis_key, result, request_data, was_paid):
    """Save or update one analysis. Never raises into the request path.

    History is a convenience. A failure to save it must not turn a successful
    analysis into an error for the customer, so everything here is swallowed
    and logged.
    """
    if not account_id or not analysis_key:
        return None
    try:
        ensure_schema()
        wallet = _wallet()

        price_analysis = result.get('price_analysis') or {}
        entry_id = 'hist_%s' % abs(hash((account_id, analysis_key)))

        row = (
            entry_id, account_id, analysis_key,
            (request_data.get('product_name') or '')[:200],
            (request_data.get('brand') or '')[:120],
            (request_data.get('category') or '')[:60],
            int(result.get('formulation_score') or result.get('main_worth_score') or 0),
            # main_worth_tier is the engine's own spelling; the other is
            # accepted so a rename does not silently blank the column.
            (result.get('formulation_tier')
             or result.get('main_worth_tier') or '')[:60],
            float(request_data.get('price') or 0),
            float(request_data.get('size_ml') or 0),
            (request_data.get('currency') or 'INR')[:8],
            (request_data.get('skin_type') or '')[:40],
            json.dumps(request_data.get('skin_concerns') or [])[:500],
            (request_data.get('ingredients') or '')[:6000],
            1 if was_paid else 0,
            time.time(),
        )

        try:
            wallet._execute(
                'INSERT INTO analysis_history (entry_id, account_id, analysis_key, '
                'product_name, brand, category, score, tier, price, size_ml, '
                'currency, skin_type, concerns, ingredients, was_paid, created_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                row, commit=True)
        except Exception as exc:
            if not _is_duplicate(exc):
                raise
            # Seen this product before: refresh the score and bring it to the
            # top of the list rather than adding a second row.
            wallet._execute(
                'UPDATE analysis_history SET score = ?, tier = ?, price = ?, '
                'size_ml = ?, was_paid = ?, created_at = ? '
                'WHERE account_id = ? AND analysis_key = ?',
                (row[6], row[7], row[8], row[9],
                 1 if was_paid else 0, row[14], account_id, analysis_key),
                commit=True)

        _trim(account_id)
        return entry_id
    except Exception:
        logger.exception('could not save analysis history')
        return None


def _trim(account_id):
    """Keep the newest MAX_ROWS_PER_ACCOUNT rows.

    Unbounded growth for a feature nobody scrolls past the first page of is a
    slow storage leak, and on a paid database it is a bill.
    """
    wallet = _wallet()
    cur = wallet._execute(
        'SELECT created_at FROM analysis_history WHERE account_id = ? '
        'ORDER BY created_at DESC LIMIT 1 OFFSET ?',
        (account_id, MAX_ROWS_PER_ACCOUNT))
    row = cur.fetchone()
    if not row:
        return
    wallet._execute(
        'DELETE FROM analysis_history WHERE account_id = ? AND created_at <= ?',
        (account_id, row[0]), commit=True)


def recent(account_id, limit=30):
    ensure_schema()
    wallet = _wallet()
    cur = wallet._execute(
        'SELECT entry_id, product_name, brand, category, score, tier, price, '
        'size_ml, currency, skin_type, concerns, was_paid, created_at '
        'FROM analysis_history WHERE account_id = ? '
        'ORDER BY created_at DESC LIMIT ?',
        (account_id, int(limit)))
    out = []
    for r in cur.fetchall():
        out.append({
            'entry_id': r[0], 'product_name': r[1], 'brand': r[2],
            'category': r[3], 'score': r[4], 'tier': r[5],
            'price': r[6], 'size_ml': r[7], 'currency': r[8],
            'skin_type': r[9],
            'concerns': json.loads(r[10] or '[]'),
            'was_paid': bool(r[11]), 'created_at': r[12],
        })
    return out


def get(account_id, entry_id):
    """One saved analysis, including the ingredients needed to re-open it.

    Scoped by account_id in the WHERE clause, not checked afterwards: an entry
    id from someone else's list simply matches nothing.
    """
    ensure_schema()
    wallet = _wallet()
    cur = wallet._execute(
        'SELECT product_name, brand, category, price, size_ml, currency, '
        'skin_type, concerns, ingredients FROM analysis_history '
        'WHERE account_id = ? AND entry_id = ?',
        (account_id, entry_id))
    row = cur.fetchone()
    if not row:
        return None
    return {
        'product_name': row[0], 'brand': row[1], 'category': row[2],
        'price': row[3], 'size_ml': row[4], 'currency': row[5],
        'skin_type': row[6], 'concerns': json.loads(row[7] or '[]'),
        'ingredients': row[8],
    }


def forget(account_id, entry_id):
    ensure_schema()
    wallet = _wallet()
    cur = wallet._execute(
        'DELETE FROM analysis_history WHERE account_id = ? AND entry_id = ?',
        (account_id, entry_id), commit=True)
    return cur.rowcount > 0


def forget_all(account_id):
    """Empty an account's history. Someone asking to be forgotten gets that."""
    ensure_schema()
    wallet = _wallet()
    cur = wallet._execute(
        'DELETE FROM analysis_history WHERE account_id = ?',
        (account_id,), commit=True)
    return cur.rowcount


def _is_duplicate(exc):
    name = type(exc).__name__
    text = str(exc).lower()
    if name in ('UniqueViolation', 'IntegrityError'):
        return 'unique' in text or 'duplicate' in text or 'constraint' in text
    return False

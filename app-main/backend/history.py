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

import hashlib
import json
import logging
import re
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


PRODUCT_KEY_PREFIX = 'product:'


def fingerprint(ingredients, category):
    """The same product, whatever name, price or skin type it was run with."""
    ingredients = re.sub(r'[\s,]+', ',', (ingredients or '').strip().lower())
    category = (category or '').strip().lower()
    return hashlib.sha256(
        ('%s|%s' % (category, ingredients)).encode('utf-8')).hexdigest()[:32]


def product_key(request_data):
    return PRODUCT_KEY_PREFIX + fingerprint(
        request_data.get('ingredients'), request_data.get('category'))


def _absorb_legacy_rows(wallet, account_id, analysis_key):
    """Drop older rows of this product saved under the full cache key.

    Those keys changed with the name, skin type, concerns and price, so one
    product could fill the list several times, some rows without a name.
    Returns the name and brand worth keeping from them.
    """
    cur = wallet._execute(
        'SELECT entry_id, analysis_key, product_name, brand, category, ingredients '
        'FROM analysis_history WHERE account_id = ? ORDER BY created_at DESC',
        (account_id,))
    name, brand, stale = '', '', []
    for entry_id, key, row_name, row_brand, category, ingredients in cur.fetchall():
        if (key or '').startswith(PRODUCT_KEY_PREFIX):
            continue
        if PRODUCT_KEY_PREFIX + fingerprint(ingredients, category) != analysis_key:
            continue
        name = name or (row_name or '')
        brand = brand or (row_brand or '')
        stale.append(entry_id)
    for entry_id in stale:
        wallet._execute(
            'DELETE FROM analysis_history WHERE account_id = ? AND entry_id = ?',
            (account_id, entry_id), commit=True)
    return name, brand


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

        entry_id = 'hist_' + hashlib.sha256(
            ('%s:%s' % (account_id, analysis_key)).encode('utf-8')).hexdigest()[:24]

        name = (request_data.get('product_name') or '').strip()
        brand = (request_data.get('brand') or '').strip()
        if analysis_key.startswith(PRODUCT_KEY_PREFIX):
            old_name, old_brand = _absorb_legacy_rows(wallet, account_id, analysis_key)
            name = name or old_name
            brand = brand or old_brand

        row = (
            entry_id, account_id, analysis_key,
            name[:200],
            brand[:120],
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
            # Seen this product before: refresh it and bring it to the top of
            # the list rather than adding a second row. A blank name or brand
            # never overwrites one that was entered earlier.
            wallet._execute(
                'UPDATE analysis_history SET '
                'product_name = CASE WHEN ? <> \'\' THEN ? ELSE product_name END, '
                'brand = CASE WHEN ? <> \'\' THEN ? ELSE brand END, '
                'score = ?, tier = ?, price = ?, size_ml = ?, currency = ?, '
                'skin_type = ?, concerns = ?, was_paid = ?, created_at = ? '
                'WHERE account_id = ? AND analysis_key = ?',
                (row[3], row[3], row[4], row[4],
                 row[6], row[7], row[8], row[9], row[10], row[11], row[12],
                 1 if was_paid else 0, row[15], account_id, analysis_key),
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
    _ensure_comparisons()
    wallet = _wallet()
    cur = wallet._execute(
        'DELETE FROM analysis_history WHERE account_id = ?',
        (account_id,), commit=True)
    wallet._execute(
        'DELETE FROM comparison_history WHERE account_id = ?',
        (account_id,), commit=True)
    return cur.rowcount


COMPARISON_SCHEMA = """
CREATE TABLE IF NOT EXISTS comparison_history (
    entry_id        TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL,
    comparison_key  TEXT NOT NULL,
    products        TEXT NOT NULL,
    created_at      DOUBLE PRECISION NOT NULL
)
"""

COMPARISON_INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS comparison_history_key_uniq "
    "ON comparison_history (account_id, comparison_key)",
]


def _ensure_comparisons():
    wallet = _wallet()
    sql = COMPARISON_SCHEMA if wallet.storage_is_durable() else COMPARISON_SCHEMA.replace(
        'DOUBLE PRECISION', 'REAL')
    wallet._execute(sql, (), commit=True)
    for statement in COMPARISON_INDEXES:
        wallet._execute(statement, (), commit=True)


def record_comparison(account_id, comparison_key, products):
    """Save one comparison for this account. Never raises into the request."""
    if not account_id or not comparison_key or not products:
        return None
    try:
        _ensure_comparisons()
        wallet = _wallet()
        entry_id = 'cmp_%s' % hashlib.sha256(
            ('%s:%s' % (account_id, comparison_key)).encode('utf-8')).hexdigest()[:24]
        payload = json.dumps(products)[:20000]
        now = time.time()
        try:
            wallet._execute(
                'INSERT INTO comparison_history '
                '(entry_id, account_id, comparison_key, products, created_at) '
                'VALUES (?, ?, ?, ?, ?)',
                (entry_id, account_id, comparison_key, payload, now),
                commit=True)
        except Exception as exc:
            if not _is_duplicate(exc):
                raise
            wallet._execute(
                'UPDATE comparison_history SET products = ?, created_at = ? '
                'WHERE account_id = ? AND comparison_key = ?',
                (payload, now, account_id, comparison_key),
                commit=True)
        return entry_id
    except Exception:
        logger.exception('could not save comparison history')
        return None


def recent_comparisons(account_id, limit=30):
    _ensure_comparisons()
    wallet = _wallet()
    cur = wallet._execute(
        'SELECT entry_id, products, created_at FROM comparison_history '
        'WHERE account_id = ? ORDER BY created_at DESC LIMIT ?',
        (account_id, int(limit)))
    out = []
    for entry_id, payload, created_at in cur.fetchall():
        products = json.loads(payload or '[]')
        out.append({
            'entry_id': entry_id,
            'created_at': created_at,
            'products': [
                {
                    'product_name': p.get('product_name') or '',
                    'brand': p.get('brand') or '',
                    'category': p.get('category') or '',
                    'score': p.get('score'),
                }
                for p in products
            ],
        })
    return out


def get_comparison(account_id, entry_id):
    _ensure_comparisons()
    wallet = _wallet()
    cur = wallet._execute(
        'SELECT products FROM comparison_history '
        'WHERE account_id = ? AND entry_id = ?',
        (account_id, entry_id))
    row = cur.fetchone()
    if not row:
        return None
    return {'products': json.loads(row[0] or '[]')}


def forget_comparison(account_id, entry_id):
    _ensure_comparisons()
    wallet = _wallet()
    cur = wallet._execute(
        'DELETE FROM comparison_history WHERE account_id = ? AND entry_id = ?',
        (account_id, entry_id), commit=True)
    return cur.rowcount > 0


def _is_duplicate(exc):
    name = type(exc).__name__
    text = str(exc).lower()
    if name in ('UniqueViolation', 'IntegrityError'):
        return 'unique' in text or 'duplicate' in text or 'constraint' in text
    return False

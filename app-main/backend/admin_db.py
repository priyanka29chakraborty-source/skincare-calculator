"""
Persistent logging via Aiven PostgreSQL.
Falls back to SQLite if AIVEN_PG_URL is not set (local dev).
"""
import json
import os
import threading
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

AIVEN_PG_URL = os.environ.get('AIVEN_PG_URL', '')
_USE_PG = bool(AIVEN_PG_URL)

# ─── PostgreSQL backend ───────────────────────────────────────────────

if _USE_PG:
    try:
        import psycopg2
        from psycopg2.extras import Json
        from psycopg2.pool import ThreadedConnectionPool

        _pg_pool = None
        _pg_lock = threading.Lock()

        def _get_pg_pool():
            global _pg_pool
            if _pg_pool is None:
                with _pg_lock:
                    if _pg_pool is None:
                        _pg_pool = ThreadedConnectionPool(1, 10, AIVEN_PG_URL)
            return _pg_pool

        def _pg_exec(query, params=None, fetch=False):
            pool = _get_pg_pool()
            conn = pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    if fetch:
                        rows = cur.fetchall()
                        conn.commit()
                        return rows
                    conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"PG query error: {e}")
                raise
            finally:
                pool.putconn(conn)

        def init_db():
            _pg_exec("""
            CREATE TABLE IF NOT EXISTS fetch_logs (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ DEFAULT NOW(),
                domain TEXT, full_url TEXT, layer_attempted TEXT,
                success BOOLEAN DEFAULT FALSE, fields_fetched JSONB,
                missing_fields JSONB, response_time_ms REAL,
                error_message TEXT, api_credits_used REAL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS analysis_logs (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ DEFAULT NOW(),
                product_category TEXT, country TEXT, skin_type TEXT,
                skin_concerns JSONB, main_worth_score REAL,
                url_provided BOOLEAN DEFAULT FALSE,
                scraping_layer TEXT, analysis_time_ms REAL
            );
            CREATE TABLE IF NOT EXISTS api_credits (
                id SERIAL PRIMARY KEY,
                api_name TEXT NOT NULL, month TEXT NOT NULL,
                credits_used REAL DEFAULT 0, call_count INTEGER DEFAULT 0,
                UNIQUE(api_name, month)
            );
            CREATE INDEX IF NOT EXISTS idx_fetch_ts ON fetch_logs(timestamp);
            CREATE INDEX IF NOT EXISTS idx_fetch_domain ON fetch_logs(domain);
            CREATE INDEX IF NOT EXISTS idx_analysis_ts ON analysis_logs(timestamp);
            """)
            logger.info("Aiven PostgreSQL DB initialized")

        def log_fetch(domain, full_url, layer, success, fields_fetched,
                      missing_fields, response_time_ms, error_message=None, credits=0):
            try:
                _pg_exec("""INSERT INTO fetch_logs
                    (domain, full_url, layer_attempted, success, fields_fetched,
                     missing_fields, response_time_ms, error_message, api_credits_used)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (domain, full_url, layer, bool(success),
                     Json(fields_fetched or []), Json(missing_fields or []),
                     response_time_ms, error_message, credits))
            except Exception as e:
                logger.warning(f"log_fetch failed: {e}")

        def log_analysis(category, country, skin_type, concerns,
                         worth_score, url_provided, scraping_layer, analysis_time_ms):
            try:
                _pg_exec("""INSERT INTO analysis_logs
                    (product_category, country, skin_type, skin_concerns,
                     main_worth_score, url_provided, scraping_layer, analysis_time_ms)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (category, country, skin_type, Json(concerns or []),
                     worth_score, bool(url_provided), scraping_layer, analysis_time_ms))
            except Exception as e:
                logger.warning(f"log_analysis failed: {e}")

        def increment_credits(api_name, amount=1):
            month = datetime.now(timezone.utc).strftime('%Y-%m')
            try:
                _pg_exec("""INSERT INTO api_credits (api_name, month, credits_used, call_count)
                    VALUES (%s,%s,%s,1)
                    ON CONFLICT (api_name, month) DO UPDATE SET
                      credits_used = api_credits.credits_used + EXCLUDED.credits_used,
                      call_count = api_credits.call_count + 1""",
                    (api_name, month, amount))
            except Exception as e:
                logger.warning(f"increment_credits failed: {e}")

        def get_recent_fetches(limit=100):
            try:
                rows = _pg_exec(
                    "SELECT id,timestamp,domain,full_url,layer_attempted,success,"
                    "fields_fetched,missing_fields,response_time_ms,error_message,"
                    "api_credits_used FROM fetch_logs ORDER BY timestamp DESC LIMIT %s",
                    (limit,), fetch=True)
                keys = ['id','timestamp','domain','full_url','layer_attempted','success',
                        'fields_fetched','missing_fields','response_time_ms','error_message','api_credits_used']
                return [dict(zip(keys, r)) for r in rows]
            except Exception:
                return []

        def get_credit_summary():
            try:
                rows = _pg_exec(
                    "SELECT api_name,month,credits_used,call_count FROM api_credits ORDER BY month DESC",
                    fetch=True)
                return [{'api_name':r[0],'month':r[1],'credits_used':r[2],'call_count':r[3]} for r in rows]
            except Exception:
                return []

        def get_analysis_stats():
            try:
                rows = _pg_exec("""
                    SELECT country, AVG(main_worth_score), COUNT(*) FROM analysis_logs
                    GROUP BY country ORDER BY COUNT(*) DESC LIMIT 20""", fetch=True)
                return [{'country':r[0],'avg_score':r[1],'count':r[2]} for r in rows]
            except Exception:
                return []

    except ImportError:
        logger.warning("psycopg2 not installed, falling back to SQLite")
        _USE_PG = False

# ─── SQLite fallback ──────────────────────────────────────────────────

if not _USE_PG:
    import sqlite3

    DB_PATH = os.path.join(os.path.dirname(__file__), 'logs.db')
    _local = threading.local()

    def _get_conn():
        if not hasattr(_local, 'conn') or _local.conn is None:
            _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            _local.conn.row_factory = sqlite3.Row
            _local.conn.execute("PRAGMA journal_mode=WAL")
        return _local.conn

    def _now():
        return datetime.now(timezone.utc).isoformat()

    def _current_month():
        return datetime.now(timezone.utc).strftime('%Y-%m')

    def init_db():
        conn = _get_conn()
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS fetch_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            domain TEXT, full_url TEXT, layer_attempted TEXT,
            success INTEGER DEFAULT 0, fields_fetched TEXT, missing_fields TEXT,
            response_time_ms REAL, error_message TEXT, api_credits_used REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS analysis_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            product_category TEXT, country TEXT, skin_type TEXT, skin_concerns TEXT,
            main_worth_score REAL, url_provided INTEGER DEFAULT 0,
            scraping_layer TEXT, analysis_time_ms REAL
        );
        CREATE TABLE IF NOT EXISTS api_credits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_name TEXT NOT NULL, month TEXT NOT NULL,
            credits_used REAL DEFAULT 0, call_count INTEGER DEFAULT 0,
            UNIQUE(api_name, month)
        );
        CREATE INDEX IF NOT EXISTS idx_fetch_ts ON fetch_logs(timestamp);
        CREATE INDEX IF NOT EXISTS idx_fetch_domain ON fetch_logs(domain);
        CREATE INDEX IF NOT EXISTS idx_analysis_ts ON analysis_logs(timestamp);
        CREATE INDEX IF NOT EXISTS idx_credits_month ON api_credits(month);
        """)
        conn.commit()
        logger.info("SQLite DB initialized (set AIVEN_PG_URL for persistent PostgreSQL)")

    def log_fetch(domain, full_url, layer, success, fields_fetched,
                  missing_fields, response_time_ms, error_message=None, credits=0):
        try:
            conn = _get_conn()
            conn.execute("""INSERT INTO fetch_logs
                (timestamp, domain, full_url, layer_attempted, success,
                 fields_fetched, missing_fields, response_time_ms, error_message, api_credits_used)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (_now(), domain, full_url, layer, int(bool(success)),
                 json.dumps(fields_fetched or []), json.dumps(missing_fields or []),
                 response_time_ms, error_message, credits))
            conn.commit()
        except Exception as e:
            logger.warning(f"log_fetch failed: {e}")

    def log_analysis(category, country, skin_type, concerns,
                     worth_score, url_provided, scraping_layer, analysis_time_ms):
        try:
            conn = _get_conn()
            conn.execute("""INSERT INTO analysis_logs
                (timestamp, product_category, country, skin_type, skin_concerns,
                 main_worth_score, url_provided, scraping_layer, analysis_time_ms)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (_now(), category, country, skin_type, json.dumps(concerns or []),
                 worth_score, int(bool(url_provided)), scraping_layer, analysis_time_ms))
            conn.commit()
        except Exception as e:
            logger.warning(f"log_analysis failed: {e}")

    def increment_credits(api_name, amount=1):
        month = _current_month()
        try:
            conn = _get_conn()
            conn.execute("""INSERT INTO api_credits (api_name, month, credits_used, call_count)
                VALUES (?,?,?,1)
                ON CONFLICT(api_name, month) DO UPDATE SET
                  credits_used = credits_used + excluded.credits_used,
                  call_count = call_count + 1""", (api_name, month, amount))
            conn.commit()
        except Exception as e:
            logger.warning(f"increment_credits failed: {e}")

    def get_recent_fetches(limit=100):
        try:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT * FROM fetch_logs ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_credit_summary():
        try:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT api_name, month, credits_used, call_count FROM api_credits ORDER BY month DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_analysis_stats():
        try:
            conn = _get_conn()
            rows = conn.execute("""
                SELECT country, AVG(main_worth_score) as avg_score, COUNT(*) as count
                FROM analysis_logs GROUP BY country ORDER BY count DESC LIMIT 20
            """).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

# Auto-initialize DB on import
try:
    init_db()
except Exception as _e:
    logger.error(f'DB init failed: {_e}')

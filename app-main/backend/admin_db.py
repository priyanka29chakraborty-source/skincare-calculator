"""
Persistent logging via Aiven PostgreSQL.
Falls back to SQLite if AIVEN_PG_URL is not set (local dev).
"""
import json
import os
import csv
import io
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
                scraping_layer TEXT, analysis_time_ms REAL,
                product_name TEXT, brand TEXT, price REAL, ingredients TEXT
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
            # Add new columns to existing tables if upgrading
            for col, coltype in [('product_name','TEXT'),('brand','TEXT'),('price','REAL'),('ingredients','TEXT')]:
                try:
                    _pg_exec(f"ALTER TABLE analysis_logs ADD COLUMN IF NOT EXISTS {col} {coltype}")
                except Exception:
                    pass
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
                         worth_score, url_provided, scraping_layer, analysis_time_ms,
                         product_name=None, brand=None, price=None, ingredients=None):
            try:
                _pg_exec("""INSERT INTO analysis_logs
                    (product_category, country, skin_type, skin_concerns,
                     main_worth_score, url_provided, scraping_layer, analysis_time_ms,
                     product_name, brand, price, ingredients)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (category, country, skin_type, Json(concerns or []),
                     worth_score, bool(url_provided), scraping_layer, analysis_time_ms,
                     product_name, brand, price, ingredients))
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

        def get_fetch_logs(limit=200, status=None, domain=None):
            try:
                conditions = []
                params = []
                if status == 'success':
                    conditions.append("success = TRUE AND (missing_fields = '[]'::jsonb OR missing_fields IS NULL)")
                elif status == 'partial':
                    conditions.append("success = TRUE AND missing_fields != '[]'::jsonb")
                elif status == 'failed':
                    conditions.append("success = FALSE")
                if domain:
                    conditions.append("domain ILIKE %s")
                    params.append(f"%{domain}%")
                where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
                params.append(limit)
                rows = _pg_exec(
                    f"SELECT id,timestamp,domain,full_url,layer_attempted,success,"
                    f"fields_fetched,missing_fields,response_time_ms,error_message,"
                    f"api_credits_used FROM fetch_logs {where} ORDER BY timestamp DESC LIMIT %s",
                    params, fetch=True)
                keys = ['id','timestamp','domain','full_url','layer_attempted','success',
                        'fields_fetched','missing_fields','response_time_ms','error_message','api_credits_used']
                return [dict(zip(keys, r)) for r in rows]
            except Exception:
                return []

        def get_fetch_stats_today():
            try:
                rows = _pg_exec("""
                    SELECT
                      COUNT(*) as total,
                      SUM(CASE WHEN success THEN 1 ELSE 0 END) as success_count,
                      SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) as fail_count,
                      AVG(response_time_ms) as avg_ms
                    FROM fetch_logs WHERE timestamp >= NOW() - INTERVAL '24 hours'
                """, fetch=True)
                r = rows[0] if rows else (0,0,0,0)
                return {'total': r[0] or 0, 'success': r[1] or 0, 'failed': r[2] or 0, 'avg_ms': round(r[3] or 0)}
            except Exception:
                return {'total': 0, 'success': 0, 'failed': 0, 'avg_ms': 0}

        def get_credits_summary():
            try:
                month = datetime.now(timezone.utc).strftime('%Y-%m')
                rows = _pg_exec(
                    "SELECT api_name, credits_used, call_count FROM api_credits WHERE month=%s",
                    (month,), fetch=True)
                return {r[0]: {'used': r[1], 'calls': r[2]} for r in rows}
            except Exception:
                return {}

        def get_site_stats(days=7):
            try:
                rows = _pg_exec("""
                    SELECT domain,
                      MAX(timestamp) as last_tested,
                      AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END)*100 as success_rate,
                      AVG(response_time_ms) as avg_ms,
                      COUNT(*) as total
                    FROM fetch_logs
                    WHERE timestamp >= NOW() - INTERVAL '1 day' * %s
                    GROUP BY domain ORDER BY total DESC
                """, (days,), fetch=True)
                return [{'domain':r[0],'last_tested':str(r[1]),'success_rate':round(r[2] or 0,1),
                         'avg_ms':round(r[3] or 0),'total':r[4]} for r in rows]
            except Exception:
                return []

        def get_analysis_stats():
            try:
                now = datetime.now(timezone.utc)
                today = now.strftime('%Y-%m-%d')
                week_start = f"NOW() - INTERVAL '7 days'"
                month_start = now.strftime('%Y-%m-01')
                counts = _pg_exec(f"""
                    SELECT
                      SUM(CASE WHEN timestamp::date = '{today}' THEN 1 ELSE 0 END),
                      SUM(CASE WHEN timestamp >= NOW() - INTERVAL '7 days' THEN 1 ELSE 0 END),
                      SUM(CASE WHEN timestamp >= '{month_start}' THEN 1 ELSE 0 END),
                      COUNT(*)
                    FROM analysis_logs
                """, fetch=True)[0]
                categories = _pg_exec("""
                    SELECT product_category, COUNT(*) FROM analysis_logs
                    GROUP BY product_category ORDER BY COUNT(*) DESC LIMIT 10
                """, fetch=True)
                concerns_raw = _pg_exec("""
                    SELECT skin_concerns FROM analysis_logs WHERE skin_concerns IS NOT NULL
                """, fetch=True)
                concern_counts = {}
                for (sc,) in concerns_raw:
                    for c in (sc if isinstance(sc, list) else []):
                        concern_counts[c] = concern_counts.get(c, 0) + 1
                concerns = sorted([{'name':k,'count':v} for k,v in concern_counts.items()], key=lambda x: -x['count'])
                url_row = _pg_exec("SELECT SUM(CASE WHEN url_provided THEN 1 ELSE 0 END), SUM(CASE WHEN NOT url_provided THEN 1 ELSE 0 END) FROM analysis_logs", fetch=True)[0]
                hourly = _pg_exec("SELECT EXTRACT(HOUR FROM timestamp)::int, COUNT(*) FROM analysis_logs GROUP BY 1 ORDER BY 1", fetch=True)
                countries = _pg_exec("SELECT country, COUNT(*) FROM analysis_logs GROUP BY country ORDER BY COUNT(*) DESC LIMIT 20", fetch=True)
                return {
                    'total_today': counts[0] or 0, 'total_week': counts[1] or 0,
                    'total_month': counts[2] or 0, 'total_all': counts[3] or 0,
                    'categories': [{'name':r[0],'count':r[1]} for r in categories],
                    'concerns': concerns,
                    'url_count': url_row[0] or 0, 'manual_count': url_row[1] or 0,
                    'hourly': [{'hour':r[0],'count':r[1]} for r in hourly],
                    'countries': [{'name':r[0],'count':r[1]} for r in countries],
                }
            except Exception as e:
                logger.warning(f"get_analysis_stats failed: {e}")
                return {'total_today':0,'total_week':0,'total_month':0,'total_all':0,
                        'categories':[],'concerns':[],'url_count':0,'manual_count':0,'hourly':[],'countries':[]}

        def clear_old_logs(days=30):
            try:
                _pg_exec(f"DELETE FROM fetch_logs WHERE timestamp < NOW() - INTERVAL '1 day' * %s", (days,))
                return 1
            except Exception:
                return 0

        def export_fetch_logs_csv():
            try:
                rows = _pg_exec(
                    "SELECT timestamp,domain,full_url,layer_attempted,success,response_time_ms,error_message FROM fetch_logs ORDER BY timestamp DESC LIMIT 5000",
                    fetch=True)
                buf = io.StringIO()
                w = csv.writer(buf)
                w.writerow(['timestamp','domain','full_url','layer','success','response_ms','error'])
                w.writerows(rows)
                return buf.getvalue()
            except Exception:
                return "timestamp,domain,full_url,layer,success,response_ms,error\n"

        def export_analytics_csv():
            try:
                rows = _pg_exec(
                    "SELECT timestamp,product_category,country,skin_type,skin_concerns,main_worth_score,url_provided,product_name,brand,price FROM analysis_logs ORDER BY timestamp DESC LIMIT 5000",
                    fetch=True)
                buf = io.StringIO()
                w = csv.writer(buf)
                w.writerow(['timestamp','category','country','skin_type','concerns','score','url_provided','product_name','brand','price'])
                w.writerows(rows)
                return buf.getvalue()
            except Exception:
                return "timestamp,category,country,skin_type,concerns,score,url_provided,product_name,brand,price\n"

        # Keep old name as alias
        get_recent_fetches = get_fetch_logs
        get_credit_summary = get_credits_summary

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
            scraping_layer TEXT, analysis_time_ms REAL,
            product_name TEXT, brand TEXT, price REAL, ingredients TEXT
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
        # Migrate existing table — add new columns if they don't exist yet
        existing = [r[1] for r in conn.execute("PRAGMA table_info(analysis_logs)").fetchall()]
        for col, coltype in [('product_name','TEXT'),('brand','TEXT'),('price','REAL'),('ingredients','TEXT')]:
            if col not in existing:
                conn.execute(f"ALTER TABLE analysis_logs ADD COLUMN {col} {coltype}")
        conn.commit()
        logger.info("SQLite DB initialized")

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
                     worth_score, url_provided, scraping_layer, analysis_time_ms,
                     product_name=None, brand=None, price=None, ingredients=None):
        try:
            conn = _get_conn()
            conn.execute("""INSERT INTO analysis_logs
                (timestamp, product_category, country, skin_type, skin_concerns,
                 main_worth_score, url_provided, scraping_layer, analysis_time_ms,
                 product_name, brand, price, ingredients)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (_now(), category, country, skin_type, json.dumps(concerns or []),
                 worth_score, int(bool(url_provided)), scraping_layer, analysis_time_ms,
                 product_name, brand, price, ingredients))
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

    def get_fetch_logs(limit=200, status=None, domain=None):
        try:
            conn = _get_conn()
            conditions = ["1=1"]
            params = []
            if status == 'success':
                conditions.append("success=1 AND (missing_fields='[]' OR missing_fields IS NULL)")
            elif status == 'partial':
                conditions.append("success=1 AND missing_fields!='[]'")
            elif status == 'failed':
                conditions.append("success=0")
            if domain:
                conditions.append("domain LIKE ?")
                params.append(f"%{domain}%")
            where = " AND ".join(conditions)
            params.append(limit)
            rows = conn.execute(
                f"SELECT * FROM fetch_logs WHERE {where} ORDER BY timestamp DESC LIMIT ?",
                params).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_fetch_stats_today():
        try:
            conn = _get_conn()
            today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            r = conn.execute("""
                SELECT COUNT(*),
                  SUM(CASE WHEN success=1 THEN 1 ELSE 0 END),
                  SUM(CASE WHEN success=0 THEN 1 ELSE 0 END),
                  AVG(response_time_ms)
                FROM fetch_logs WHERE timestamp >= ?""", (today,)).fetchone()
            return {'total': r[0] or 0, 'success': r[1] or 0, 'failed': r[2] or 0, 'avg_ms': round(r[3] or 0)}
        except Exception:
            return {'total': 0, 'success': 0, 'failed': 0, 'avg_ms': 0}

    def get_credits_summary():
        """Return {api_name: {used, calls}} for current month — shape expected by credits.py."""
        month = _current_month()
        try:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT api_name, credits_used, call_count FROM api_credits WHERE month=?",
                (month,)).fetchall()
            return {r['api_name']: {'used': r['credits_used'], 'calls': r['call_count']} for r in rows}
        except Exception:
            return {}

    # Keep old name as alias
    def get_credit_summary():
        return get_credits_summary()

    def get_site_stats(days=7):
        try:
            conn = _get_conn()
            cutoff = datetime.now(timezone.utc).strftime(f'%Y-%m-%d')
            rows = conn.execute("""
                SELECT domain,
                  MAX(timestamp) as last_tested,
                  ROUND(AVG(CASE WHEN success=1 THEN 100.0 ELSE 0.0 END),1) as success_rate,
                  ROUND(AVG(response_time_ms)) as avg_ms,
                  COUNT(*) as total
                FROM fetch_logs
                WHERE timestamp >= date('now', ?)
                GROUP BY domain ORDER BY total DESC
            """, (f'-{days} days',)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_analysis_stats():
        try:
            conn = _get_conn()
            today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            month_start = datetime.now(timezone.utc).strftime('%Y-%m-01')
            counts = conn.execute("""
                SELECT
                  SUM(CASE WHEN timestamp >= ? THEN 1 ELSE 0 END),
                  SUM(CASE WHEN timestamp >= date('now','-7 days') THEN 1 ELSE 0 END),
                  SUM(CASE WHEN timestamp >= ? THEN 1 ELSE 0 END),
                  COUNT(*)
                FROM analysis_logs
            """, (today, month_start)).fetchone()
            categories = conn.execute("""
                SELECT product_category, COUNT(*) as cnt FROM analysis_logs
                GROUP BY product_category ORDER BY cnt DESC LIMIT 10
            """).fetchall()
            concerns_raw = conn.execute(
                "SELECT skin_concerns FROM analysis_logs WHERE skin_concerns IS NOT NULL"
            ).fetchall()
            concern_counts = {}
            for row in concerns_raw:
                try:
                    for c in json.loads(row[0] or '[]'):
                        concern_counts[c] = concern_counts.get(c, 0) + 1
                except Exception:
                    pass
            concerns = sorted([{'name':k,'count':v} for k,v in concern_counts.items()], key=lambda x:-x['count'])
            url_row = conn.execute("""
                SELECT SUM(CASE WHEN url_provided=1 THEN 1 ELSE 0 END),
                       SUM(CASE WHEN url_provided=0 THEN 1 ELSE 0 END)
                FROM analysis_logs""").fetchone()
            hourly = conn.execute("""
                SELECT CAST(strftime('%H', timestamp) AS INTEGER) as hr, COUNT(*) as cnt
                FROM analysis_logs GROUP BY hr ORDER BY hr
            """).fetchall()
            countries = conn.execute("""
                SELECT country, COUNT(*) as cnt FROM analysis_logs
                GROUP BY country ORDER BY cnt DESC LIMIT 20
            """).fetchall()
            return {
                'total_today': counts[0] or 0, 'total_week': counts[1] or 0,
                'total_month': counts[2] or 0, 'total_all': counts[3] or 0,
                'categories': [{'name': r[0] or 'Unknown', 'count': r[1]} for r in categories],
                'concerns': concerns,
                'url_count': url_row[0] or 0, 'manual_count': url_row[1] or 0,
                'hourly': [{'hour': r[0], 'count': r[1]} for r in hourly],
                'countries': [{'name': r[0] or 'Unknown', 'count': r[1]} for r in countries],
            }
        except Exception as e:
            logger.warning(f"get_analysis_stats failed: {e}")
            return {'total_today':0,'total_week':0,'total_month':0,'total_all':0,
                    'categories':[],'concerns':[],'url_count':0,'manual_count':0,'hourly':[],'countries':[]}

    def clear_old_logs(days=30):
        try:
            conn = _get_conn()
            conn.execute("DELETE FROM fetch_logs WHERE timestamp < date('now', ?)", (f'-{days} days',))
            conn.commit()
            return 1
        except Exception:
            return 0

    def export_fetch_logs_csv():
        try:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT timestamp,domain,full_url,layer_attempted,success,response_time_ms,error_message FROM fetch_logs ORDER BY timestamp DESC LIMIT 5000"
            ).fetchall()
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(['timestamp','domain','full_url','layer','success','response_ms','error'])
            w.writerows([tuple(r) for r in rows])
            return buf.getvalue()
        except Exception:
            return "timestamp,domain,full_url,layer,success,response_ms,error\n"

    def export_analytics_csv():
        try:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT timestamp,product_category,country,skin_type,skin_concerns,main_worth_score,url_provided,product_name,brand,price FROM analysis_logs ORDER BY timestamp DESC LIMIT 5000"
            ).fetchall()
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(['timestamp','category','country','skin_type','concerns','score','url_provided','product_name','brand','price'])
            w.writerows([tuple(r) for r in rows])
            return buf.getvalue()
        except Exception:
            return "timestamp,category,country,skin_type,concerns,score,url_provided,product_name,brand,price\n"

    # Keep old name as alias
    get_recent_fetches = get_fetch_logs

# Auto-initialize DB on import
try:
    init_db()
except Exception as _e:
    logger.error(f'DB init failed: {_e}')

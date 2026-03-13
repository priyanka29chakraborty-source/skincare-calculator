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
        import psycopg
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
                fetch_type TEXT DEFAULT 'manual',
                scraping_layer TEXT, analysis_time_ms REAL,
                product_name TEXT, brand TEXT, price REAL, ingredients TEXT,
                identified_actives JSONB,
                ingredient_count INTEGER DEFAULT 0,
                is_flagged BOOLEAN DEFAULT FALSE,
                flag_reason TEXT
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
            # Migrate existing tables — add new columns if upgrading
            for col, coltype in [
                ('product_name', 'TEXT'), ('brand', 'TEXT'), ('price', 'REAL'),
                ('ingredients', 'TEXT'), ('fetch_type', 'TEXT'), ('identified_actives', 'JSONB'),
                ('ingredient_count', 'INTEGER'), ('is_flagged', 'BOOLEAN'), ('flag_reason', 'TEXT'),
            ]:
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
                         product_name=None, brand=None, price=None, ingredients=None,
                         fetch_type='manual', identified_actives=None,
                         ingredient_count=0, is_flagged=False, flag_reason=None):
            try:
                _pg_exec("""INSERT INTO analysis_logs
                    (product_category, country, skin_type, skin_concerns,
                     main_worth_score, url_provided, fetch_type, scraping_layer,
                     analysis_time_ms, product_name, brand, price, ingredients,
                     identified_actives, ingredient_count, is_flagged, flag_reason)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (category, country, skin_type, Json(concerns or []),
                     worth_score, bool(url_provided), fetch_type, scraping_layer,
                     analysis_time_ms, product_name, brand, price, ingredients,
                     Json(identified_actives or []), int(ingredient_count),
                     bool(is_flagged), flag_reason))
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
                r = rows[0] if rows else (0, 0, 0, 0)
                total = r[0] or 0
                success_count = r[1] or 0
                fail_count = r[2] or 0
                avg_ms = round(r[3] or 0)
                success_rate = round(success_count / total * 100, 1) if total > 0 else 0
                # Most failed domain in last 24h
                fd_rows = _pg_exec("""
                    SELECT domain, COUNT(*) as cnt FROM fetch_logs
                    WHERE timestamp >= NOW() - INTERVAL '24 hours' AND success = FALSE
                    GROUP BY domain ORDER BY cnt DESC LIMIT 1
                """, fetch=True)
                failed_domain = fd_rows[0][0] if fd_rows else '-'
                return {
                    'total': total, 'success': success_count, 'failed': fail_count,
                    'avg_ms': avg_ms, 'success_rate': success_rate, 'failed_domain': failed_domain,
                }
            except Exception:
                return {'total': 0, 'success': 0, 'failed': 0, 'avg_ms': 0,
                        'success_rate': 0, 'failed_domain': '-'}

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
                result = []
                for r in rows:
                    domain = r[0]
                    success_rate = round(r[2] or 0, 1)
                    # Collect most common missing fields for this domain
                    mf_rows = _pg_exec("""
                        SELECT jsonb_array_elements_text(missing_fields) as field,
                               COUNT(*) as cnt
                        FROM fetch_logs
                        WHERE domain = %s AND missing_fields IS NOT NULL
                          AND missing_fields != '[]'::jsonb
                          AND timestamp >= NOW() - INTERVAL '1 day' * %s
                        GROUP BY field ORDER BY cnt DESC LIMIT 4
                    """, (domain, days), fetch=True)
                    missing_fields = [mf[0] for mf in mf_rows]
                    result.append({
                        'domain': domain,
                        'last_tested': str(r[1]),
                        'success_rate': success_rate,
                        'avg_ms': round(r[3] or 0),
                        'total': r[4],
                        'missing_fields': missing_fields,
                        'health_warning': success_rate < 50 and r[4] >= 3,
                    })
                return result
            except Exception:
                return []

        def get_layer_stats(days=7):
            """Return per-scraper-layer success rates for the Scraper Monitoring panel."""
            try:
                rows = _pg_exec("""
                    SELECT layer_attempted,
                      COUNT(*) as total,
                      SUM(CASE WHEN success THEN 1 ELSE 0 END) as ok
                    FROM fetch_logs
                    WHERE timestamp >= NOW() - INTERVAL '1 day' * %s
                      AND layer_attempted IS NOT NULL
                    GROUP BY layer_attempted ORDER BY total DESC
                """, (days,), fetch=True)
                result = []
                for r in rows:
                    total = r[1] or 0
                    ok = r[2] or 0
                    result.append({
                        'layer': r[0],
                        'total': total,
                        'success': ok,
                        'success_rate': round(ok / total * 100, 1) if total > 0 else 0,
                    })
                return result
            except Exception:
                return []

        def get_analysis_stats():
            try:
                now = datetime.now(timezone.utc)
                today = now.strftime('%Y-%m-%d')
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
                concerns = sorted(
                    [{'name': k, 'count': v} for k, v in concern_counts.items()],
                    key=lambda x: -x['count'])
                # fetch_type counts: url / barcode / manual
                ft_rows = _pg_exec("""
                    SELECT fetch_type, COUNT(*) FROM analysis_logs
                    GROUP BY fetch_type
                """, fetch=True)
                fetch_type_counts = {r[0] or 'manual': r[1] for r in ft_rows}
                hourly = _pg_exec(
                    "SELECT EXTRACT(HOUR FROM timestamp)::int, COUNT(*) FROM analysis_logs GROUP BY 1 ORDER BY 1",
                    fetch=True)
                countries = _pg_exec(
                    "SELECT country, COUNT(*) FROM analysis_logs GROUP BY country ORDER BY COUNT(*) DESC LIMIT 20",
                    fetch=True)
                return {
                    'total_today': counts[0] or 0, 'total_week': counts[1] or 0,
                    'total_month': counts[2] or 0, 'total_all': counts[3] or 0,
                    'categories': [{'name': r[0], 'count': r[1]} for r in categories],
                    'concerns': concerns,
                    'fetch_type_counts': fetch_type_counts,
                    'hourly': [{'hour': r[0], 'count': r[1]} for r in hourly],
                    'countries': [{'name': r[0], 'count': r[1]} for r in countries],
                }
            except Exception as e:
                logger.warning(f"get_analysis_stats failed: {e}")
                return {'total_today': 0, 'total_week': 0, 'total_month': 0, 'total_all': 0,
                        'categories': [], 'concerns': [], 'fetch_type_counts': {},
                        'hourly': [], 'countries': []}

        def get_ingredient_trends(days=7, limit=10):
            """Return most-analyzed ingredient actives over the last N days."""
            try:
                rows = _pg_exec("""
                    SELECT jsonb_array_elements(identified_actives)->>'name' as ing_name,
                           COUNT(*) as cnt
                    FROM analysis_logs
                    WHERE identified_actives IS NOT NULL
                      AND identified_actives != '[]'::jsonb
                      AND timestamp >= NOW() - INTERVAL '1 day' * %s
                    GROUP BY ing_name ORDER BY cnt DESC LIMIT %s
                """, (days, limit), fetch=True)
                return [{'name': r[0], 'count': r[1]} for r in rows if r[0]]
            except Exception:
                return []

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
                w.writerow(['timestamp', 'domain', 'full_url', 'layer', 'success', 'response_ms', 'error'])
                w.writerows(rows)
                return buf.getvalue()
            except Exception:
                return "timestamp,domain,full_url,layer,success,response_ms,error\n"

        def export_analytics_csv():
            try:
                rows = _pg_exec(
                    "SELECT timestamp,product_category,country,skin_type,skin_concerns,main_worth_score,fetch_type,product_name,brand,price FROM analysis_logs ORDER BY timestamp DESC LIMIT 5000",
                    fetch=True)
                buf = io.StringIO()
                w = csv.writer(buf)
                w.writerow(['timestamp', 'category', 'country', 'skin_type', 'concerns',
                            'score', 'fetch_type', 'product_name', 'brand', 'price'])
                w.writerows(rows)
                return buf.getvalue()
            except Exception:
                return "timestamp,category,country,skin_type,concerns,score,fetch_type,product_name,brand,price\n"

        def get_recent_analyses(limit=50):
            """Return recent analysis_logs rows for the Recent Analyses table."""
            try:
                rows = _pg_exec(
                    """SELECT id, timestamp, product_name, brand, price, product_category,
                              skin_type, main_worth_score, fetch_type, country,
                              ingredient_count, is_flagged, flag_reason
                       FROM analysis_logs ORDER BY timestamp DESC LIMIT %s""",
                    (limit,), fetch=True)
                keys = ['id','timestamp','product_name','brand','price','product_category',
                        'skin_type','main_worth_score','fetch_type','country',
                        'ingredient_count','is_flagged','flag_reason']
                return [dict(zip(keys, r)) for r in rows]
            except Exception:
                return []

        def get_flagged_analyses(limit=100, include_resolved=False):
            """Return flagged analyses for admin review."""
            try:
                where = "" if include_resolved else "WHERE is_flagged = TRUE AND flag_reason IS NOT NULL AND (resolved IS NULL OR resolved = FALSE)"
                rows = _pg_exec(f"""
                    SELECT id, timestamp, product_name, brand, price, product_category,
                           skin_type, main_worth_score, fetch_type, country,
                           ingredient_count, flag_reason, ingredients
                    FROM analysis_logs {where}
                    ORDER BY timestamp DESC LIMIT %s""",
                    (limit,), fetch=True)
                keys = ['id','timestamp','product_name','brand','price','product_category',
                        'skin_type','main_worth_score','fetch_type','country',
                        'ingredient_count','flag_reason','ingredients']
                return [dict(zip(keys, r)) for r in rows]
            except Exception:
                return []

        def get_flagged_count():
            """Count of unresolved flagged analyses."""
            try:
                rows = _pg_exec(
                    "SELECT COUNT(*) FROM analysis_logs WHERE is_flagged = TRUE AND flag_reason IS NOT NULL",
                    fetch=True)
                return rows[0][0] if rows else 0
            except Exception:
                return 0

        def resolve_flag(analysis_id):
            """Mark a flagged analysis as reviewed/resolved."""
            try:
                _pg_exec(
                    "UPDATE analysis_logs SET is_flagged = FALSE WHERE id = %s",
                    (analysis_id,))
                return True
            except Exception:
                return False

        get_recent_fetches = get_fetch_logs
        get_credit_summary = get_credits_summary

    except ImportError as e:
        logger.warning(f"psycopg2 import failed ({e}), falling back to SQLite")
        _USE_PG = False
    except Exception as e:
        logger.warning(f"PostgreSQL setup failed ({e}), falling back to SQLite")
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
            fetch_type TEXT DEFAULT 'manual',
            scraping_layer TEXT, analysis_time_ms REAL,
            product_name TEXT, brand TEXT, price REAL, ingredients TEXT,
            identified_actives TEXT,
            ingredient_count INTEGER DEFAULT 0,
            is_flagged INTEGER DEFAULT 0,
            flag_reason TEXT
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
        for col, coltype in [
            ('product_name', 'TEXT'), ('brand', 'TEXT'), ('price', 'REAL'),
            ('ingredients', 'TEXT'), ('fetch_type', 'TEXT'), ('identified_actives', 'TEXT'),
            ('ingredient_count', 'INTEGER'), ('is_flagged', 'INTEGER'), ('flag_reason', 'TEXT'),
        ]:
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
                     product_name=None, brand=None, price=None, ingredients=None,
                     fetch_type='manual', identified_actives=None,
                     ingredient_count=0, is_flagged=False, flag_reason=None):
        try:
            conn = _get_conn()
            conn.execute("""INSERT INTO analysis_logs
                (timestamp, product_category, country, skin_type, skin_concerns,
                 main_worth_score, url_provided, fetch_type, scraping_layer, analysis_time_ms,
                 product_name, brand, price, ingredients, identified_actives,
                 ingredient_count, is_flagged, flag_reason)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (_now(), category, country, skin_type, json.dumps(concerns or []),
                 worth_score, int(bool(url_provided)), fetch_type, scraping_layer,
                 analysis_time_ms, product_name, brand, price, ingredients,
                 json.dumps(identified_actives or []),
                 int(ingredient_count), int(bool(is_flagged)), flag_reason))
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
            total = r[0] or 0
            success_count = r[1] or 0
            fail_count = r[2] or 0
            avg_ms = round(r[3] or 0)
            success_rate = round(success_count / total * 100, 1) if total > 0 else 0
            # Most failed domain today
            fd = conn.execute("""
                SELECT domain, COUNT(*) as cnt FROM fetch_logs
                WHERE timestamp >= ? AND success=0
                GROUP BY domain ORDER BY cnt DESC LIMIT 1
            """, (today,)).fetchone()
            failed_domain = fd['domain'] if fd else '-'
            return {
                'total': total, 'success': success_count, 'failed': fail_count,
                'avg_ms': avg_ms, 'success_rate': success_rate, 'failed_domain': failed_domain,
            }
        except Exception:
            return {'total': 0, 'success': 0, 'failed': 0, 'avg_ms': 0,
                    'success_rate': 0, 'failed_domain': '-'}

    def get_credits_summary():
        """Return {api_name: {used, calls}} for current month."""
        month = _current_month()
        try:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT api_name, credits_used, call_count FROM api_credits WHERE month=?",
                (month,)).fetchall()
            return {r['api_name']: {'used': r['credits_used'], 'calls': r['call_count']} for r in rows}
        except Exception:
            return {}

    def get_credit_summary():
        return get_credits_summary()

    def get_site_stats(days=7):
        try:
            conn = _get_conn()
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
            result = []
            for r in rows:
                domain = r['domain']
                success_rate = r['success_rate'] or 0
                # Collect most common missing fields for this domain
                mf_rows = conn.execute("""
                    SELECT missing_fields FROM fetch_logs
                    WHERE domain=? AND missing_fields IS NOT NULL
                      AND missing_fields != '[]'
                      AND timestamp >= date('now', ?)
                """, (domain, f'-{days} days')).fetchall()
                field_counts = {}
                for mfr in mf_rows:
                    try:
                        for f in json.loads(mfr['missing_fields'] or '[]'):
                            field_counts[f] = field_counts.get(f, 0) + 1
                    except Exception:
                        pass
                missing_fields = sorted(field_counts, key=lambda k: -field_counts[k])[:4]
                result.append({
                    'domain': domain,
                    'last_tested': r['last_tested'],
                    'success_rate': success_rate,
                    'avg_ms': r['avg_ms'] or 0,
                    'total': r['total'],
                    'missing_fields': missing_fields,
                    'health_warning': success_rate < 50 and r['total'] >= 3,
                })
            return result
        except Exception:
            return []

    def get_layer_stats(days=7):
        """Return per-scraper-layer success rates."""
        try:
            conn = _get_conn()
            rows = conn.execute("""
                SELECT layer_attempted,
                  COUNT(*) as total,
                  SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as ok
                FROM fetch_logs
                WHERE timestamp >= date('now', ?)
                  AND layer_attempted IS NOT NULL
                GROUP BY layer_attempted ORDER BY total DESC
            """, (f'-{days} days',)).fetchall()
            result = []
            for r in rows:
                total = r['total'] or 0
                ok = r['ok'] or 0
                result.append({
                    'layer': r['layer_attempted'],
                    'total': total,
                    'success': ok,
                    'success_rate': round(ok / total * 100, 1) if total > 0 else 0,
                })
            return result
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
            concerns = sorted(
                [{'name': k, 'count': v} for k, v in concern_counts.items()],
                key=lambda x: -x['count'])
            # fetch_type breakdown: url / barcode / manual
            ft_rows = conn.execute("""
                SELECT fetch_type, COUNT(*) as cnt FROM analysis_logs
                GROUP BY fetch_type
            """).fetchall()
            fetch_type_counts = {r['fetch_type'] or 'manual': r['cnt'] for r in ft_rows}
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
                'fetch_type_counts': fetch_type_counts,
                'hourly': [{'hour': r[0], 'count': r[1]} for r in hourly],
                'countries': [{'name': r[0] or 'Unknown', 'count': r[1]} for r in countries],
            }
        except Exception as e:
            logger.warning(f"get_analysis_stats failed: {e}")
            return {'total_today': 0, 'total_week': 0, 'total_month': 0, 'total_all': 0,
                    'categories': [], 'concerns': [], 'fetch_type_counts': {},
                    'hourly': [], 'countries': []}

    def get_ingredient_trends(days=7, limit=10):
        """Return most-analyzed ingredient actives over the last N days."""
        try:
            conn = _get_conn()
            rows = conn.execute("""
                SELECT identified_actives FROM analysis_logs
                WHERE identified_actives IS NOT NULL
                  AND identified_actives != '[]'
                  AND timestamp >= date('now', ?)
            """, (f'-{days} days',)).fetchall()
            counts = {}
            for row in rows:
                try:
                    for item in json.loads(row['identified_actives'] or '[]'):
                        name = item.get('name', '')
                        if name:
                            counts[name] = counts.get(name, 0) + 1
                except Exception:
                    pass
            sorted_items = sorted(counts.items(), key=lambda x: -x[1])[:limit]
            return [{'name': k, 'count': v} for k, v in sorted_items]
        except Exception:
            return []

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
            w.writerow(['timestamp', 'domain', 'full_url', 'layer', 'success', 'response_ms', 'error'])
            w.writerows([tuple(r) for r in rows])
            return buf.getvalue()
        except Exception:
            return "timestamp,domain,full_url,layer,success,response_ms,error\n"

    def export_analytics_csv():
        try:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT timestamp,product_category,country,skin_type,skin_concerns,main_worth_score,fetch_type,product_name,brand,price FROM analysis_logs ORDER BY timestamp DESC LIMIT 5000"
            ).fetchall()
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(['timestamp', 'category', 'country', 'skin_type', 'concerns',
                        'score', 'fetch_type', 'product_name', 'brand', 'price'])
            w.writerows([tuple(r) for r in rows])
            return buf.getvalue()
        except Exception:
            return "timestamp,category,country,skin_type,concerns,score,fetch_type,product_name,brand,price\n"

    def get_recent_analyses(limit=50):
        """Return recent analysis_logs rows for the Recent Analyses table."""
        try:
            conn = _get_conn()
            rows = conn.execute(
                """SELECT id, timestamp, product_name, brand, price, product_category,
                          skin_type, main_worth_score, fetch_type, country,
                          ingredient_count, is_flagged, flag_reason
                   FROM analysis_logs ORDER BY timestamp DESC LIMIT ?""",
                (limit,)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_flagged_analyses(limit=100, include_resolved=False):
        """Return flagged analyses for admin review."""
        try:
            conn = _get_conn()
            where = "" if include_resolved else "WHERE is_flagged=1 AND flag_reason IS NOT NULL"
            rows = conn.execute(f"""
                SELECT id, timestamp, product_name, brand, price, product_category,
                       skin_type, main_worth_score, fetch_type, country,
                       ingredient_count, flag_reason, ingredients
                FROM analysis_logs {where}
                ORDER BY timestamp DESC LIMIT ?""",
                (limit,)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_flagged_count():
        """Count of unresolved flagged analyses."""
        try:
            conn = _get_conn()
            r = conn.execute(
                "SELECT COUNT(*) FROM analysis_logs WHERE is_flagged=1 AND flag_reason IS NOT NULL"
            ).fetchone()
            return r[0] if r else 0
        except Exception:
            return 0

    def resolve_flag(analysis_id):
        """Mark a flagged analysis as reviewed/resolved."""
        try:
            conn = _get_conn()
            conn.execute("UPDATE analysis_logs SET is_flagged=0 WHERE id=?", (analysis_id,))
            conn.commit()
            return True
        except Exception:
            return False

    get_recent_fetches = get_fetch_logs

# Auto-initialize DB on import
try:
    init_db()
except Exception as _e:
    logger.error(f'DB init failed: {_e}')

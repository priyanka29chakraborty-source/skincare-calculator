"""SQLite database for admin logging, analytics, and credit tracking."""
import sqlite3
import json
import os
import threading
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), 'logs.db')
_local = threading.local()


def _get_conn():
    if not hasattr(_local, 'conn') or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
    return _local.conn


def init_db():
    conn = _get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS fetch_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        domain TEXT,
        full_url TEXT,
        layer_attempted TEXT,
        success INTEGER DEFAULT 0,
        fields_fetched TEXT,
        missing_fields TEXT,
        response_time_ms REAL,
        error_message TEXT,
        api_credits_used REAL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS analysis_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        product_category TEXT,
        country TEXT,
        skin_type TEXT,
        skin_concerns TEXT,
        main_worth_score REAL,
        url_provided INTEGER DEFAULT 0,
        scraping_layer TEXT,
        analysis_time_ms REAL
    );

    CREATE TABLE IF NOT EXISTS api_credits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_name TEXT NOT NULL,
        month TEXT NOT NULL,
        credits_used REAL DEFAULT 0,
        call_count INTEGER DEFAULT 0,
        UNIQUE(api_name, month)
    );

    CREATE INDEX IF NOT EXISTS idx_fetch_ts ON fetch_logs(timestamp);
    CREATE INDEX IF NOT EXISTS idx_fetch_domain ON fetch_logs(domain);
    CREATE INDEX IF NOT EXISTS idx_analysis_ts ON analysis_logs(timestamp);
    CREATE INDEX IF NOT EXISTS idx_credits_month ON api_credits(month);
    """)
    conn.commit()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _current_month():
    return datetime.now(timezone.utc).strftime('%Y-%m')


def log_fetch(domain, full_url, layer, success, fields_fetched,
              missing_fields, response_time_ms, error_message=None, credits=0):
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO fetch_logs
            (timestamp, domain, full_url, layer_attempted, success,
             fields_fetched, missing_fields, response_time_ms, error_message, api_credits_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (_now(), domain, full_url, layer, 1 if success else 0,
             json.dumps(fields_fetched), json.dumps(missing_fields),
             response_time_ms, error_message, credits)
        )
        conn.commit()
    except Exception:
        pass


def log_analysis(category, country, skin_type, concerns, score,
                 url_provided, scraping_layer, time_ms):
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO analysis_logs
            (timestamp, product_category, country, skin_type, skin_concerns,
             main_worth_score, url_provided, scraping_layer, analysis_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (_now(), category, country, skin_type, json.dumps(concerns),
             score, 1 if url_provided else 0, scraping_layer, time_ms)
        )
        conn.commit()
    except Exception:
        pass


def increment_credits(api_name, credits=1):
    try:
        month = _current_month()
        conn = _get_conn()
        conn.execute(
            """INSERT INTO api_credits (api_name, month, credits_used, call_count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(api_name, month) DO UPDATE SET
            credits_used = credits_used + ?, call_count = call_count + 1""",
            (api_name, month, credits, credits)
        )
        conn.commit()
    except Exception:
        pass


def get_credits_summary():
    month = _current_month()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT api_name, credits_used, call_count FROM api_credits WHERE month = ?",
        (month,)
    ).fetchall()
    return {r['api_name']: {'used': r['credits_used'], 'calls': r['call_count']} for r in rows}


def get_fetch_logs(limit=200, status_filter=None, domain_filter=None):
    conn = _get_conn()
    q = "SELECT * FROM fetch_logs WHERE 1=1"
    params = []
    if status_filter == 'success':
        q += " AND success = 1 AND missing_fields = '[]'"
    elif status_filter == 'partial':
        q += " AND success = 1 AND missing_fields != '[]'"
    elif status_filter == 'failed':
        q += " AND success = 0"
    if domain_filter:
        q += " AND domain LIKE ?"
        params.append(f"%{domain_filter}%")
    q += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(q, params).fetchall()]


def get_fetch_stats_today():
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    conn = _get_conn()
    total = conn.execute(
        "SELECT COUNT(*) c FROM fetch_logs WHERE timestamp LIKE ?", (f"{today}%",)
    ).fetchone()['c']
    success = conn.execute(
        "SELECT COUNT(*) c FROM fetch_logs WHERE timestamp LIKE ? AND success = 1",
        (f"{today}%",)
    ).fetchone()['c']
    rate = round(success / total * 100, 1) if total > 0 else 0
    failed_domain = conn.execute(
        """SELECT domain, COUNT(*) c FROM fetch_logs
        WHERE timestamp LIKE ? AND success = 0
        GROUP BY domain ORDER BY c DESC LIMIT 1""", (f"{today}%",)
    ).fetchone()
    avg_time = conn.execute(
        "SELECT AVG(response_time_ms) a FROM fetch_logs WHERE timestamp LIKE ?",
        (f"{today}%",)
    ).fetchone()['a'] or 0
    top_layer = conn.execute(
        """SELECT layer_attempted, COUNT(*) c FROM fetch_logs
        WHERE timestamp LIKE ? AND success = 1
        GROUP BY layer_attempted ORDER BY c DESC LIMIT 1""", (f"{today}%",)
    ).fetchone()
    return {
        'total': total,
        'success_rate': rate,
        'failed_domain': failed_domain['domain'] if failed_domain else '-',
        'avg_time_ms': round(avg_time, 1),
        'top_layer': top_layer['layer_attempted'] if top_layer else '-',
    }


def get_analysis_stats():
    conn = _get_conn()
    now = datetime.now(timezone.utc)
    today = now.strftime('%Y-%m-%d')
    week_start = (now.replace(hour=0, minute=0, second=0) .__class__(
        now.year, now.month, now.day - now.weekday()
    )).strftime('%Y-%m-%d') if now.weekday() > 0 else today
    month = now.strftime('%Y-%m')

    def cnt(where="1=1", params=()):
        return conn.execute(f"SELECT COUNT(*) c FROM analysis_logs WHERE {where}", params).fetchone()['c']

    total_all = cnt()
    total_today = cnt("timestamp LIKE ?", (f"{today}%",))
    total_week = cnt("timestamp >= ?", (f"{week_start}%",))
    total_month = cnt("timestamp LIKE ?", (f"{month}%",))

    avg_score = conn.execute("SELECT AVG(main_worth_score) a FROM analysis_logs").fetchone()['a'] or 0
    avg_time = conn.execute("SELECT AVG(analysis_time_ms) a FROM analysis_logs").fetchone()['a'] or 0

    url_count = conn.execute("SELECT COUNT(*) c FROM analysis_logs WHERE url_provided = 1").fetchone()['c']
    manual_count = total_all - url_count

    categories = conn.execute(
        "SELECT product_category, COUNT(*) c FROM analysis_logs GROUP BY product_category ORDER BY c DESC"
    ).fetchall()
    countries = conn.execute(
        "SELECT country, COUNT(*) c FROM analysis_logs GROUP BY country ORDER BY c DESC LIMIT 10"
    ).fetchall()
    concerns_raw = conn.execute("SELECT skin_concerns FROM analysis_logs").fetchall()
    concern_counts = {}
    for row in concerns_raw:
        for c in json.loads(row['skin_concerns'] or '[]'):
            concern_counts[c] = concern_counts.get(c, 0) + 1
    hourly = conn.execute(
        "SELECT CAST(SUBSTR(timestamp, 12, 2) AS INTEGER) h, COUNT(*) c FROM analysis_logs GROUP BY h ORDER BY h"
    ).fetchall()

    return {
        'total_all': total_all, 'total_today': total_today,
        'total_week': total_week, 'total_month': total_month,
        'avg_score': round(avg_score, 1), 'avg_time_ms': round(avg_time, 1),
        'url_count': url_count, 'manual_count': manual_count,
        'categories': [{'name': r['product_category'] or 'Unknown', 'count': r['c']} for r in categories],
        'countries': [{'name': r['country'] or 'Unknown', 'count': r['c']} for r in countries],
        'concerns': [{'name': k, 'count': v} for k, v in sorted(concern_counts.items(), key=lambda x: -x[1])],
        'hourly': [{'hour': r['h'], 'count': r['c']} for r in hourly],
    }


def get_site_stats(days=7):
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = _get_conn()
    rows = conn.execute(
        """SELECT domain,
           COUNT(*) total,
           SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) ok,
           AVG(response_time_ms) avg_time,
           MAX(timestamp) last_tested
        FROM fetch_logs WHERE timestamp >= ? AND domain IS NOT NULL AND domain != ''
        GROUP BY domain ORDER BY total DESC""", (cutoff,)
    ).fetchall()
    results = []
    for r in rows:
        rate = round(r['ok'] / r['total'] * 100, 1) if r['total'] > 0 else 0
        missing = conn.execute(
            """SELECT missing_fields FROM fetch_logs
            WHERE domain = ? AND timestamp >= ? AND success = 1
            ORDER BY id DESC LIMIT 1""", (r['domain'], cutoff)
        ).fetchone()
        results.append({
            'domain': r['domain'], 'total': r['total'],
            'success_rate': rate, 'avg_time': round(r['avg_time'] or 0, 1),
            'last_tested': r['last_tested'],
            'missing_fields': json.loads(missing['missing_fields']) if missing else [],
        })
    return results


def clear_old_logs(days=30):
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = _get_conn()
    c1 = conn.execute("DELETE FROM fetch_logs WHERE timestamp < ?", (cutoff,)).rowcount
    c2 = conn.execute("DELETE FROM analysis_logs WHERE timestamp < ?", (cutoff,)).rowcount
    conn.commit()
    return c1 + c2


def export_fetch_logs_csv():
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM fetch_logs ORDER BY id DESC").fetchall()
    if not rows:
        return "No data"
    headers = rows[0].keys()
    lines = [','.join(headers)]
    for r in rows:
        lines.append(','.join(str(r[h]).replace(',', ';') for h in headers))
    return '\n'.join(lines)


def export_analytics_csv():
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM analysis_logs ORDER BY id DESC").fetchall()
    if not rows:
        return "No data"
    headers = rows[0].keys()
    lines = [','.join(headers)]
    for r in rows:
        lines.append(','.join(str(r[h]).replace(',', ';') for h in headers))
    return '\n'.join(lines)


# Initialize on import
init_db()

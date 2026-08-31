"""Admin dashboard routes for FastAPI."""
import os
import time
import asyncio
import aiohttp
import json
import logging
from datetime import datetime, timezone
from functools import wraps
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from jinja2 import Environment, FileSystemLoader

import admin_db
from credits import CREDIT_LIMITS, get_credit_status
from data_loader import data_loader

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/api/admin")

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=True)

ADMIN_PASSWORD = None
SESSION_SECRET = None

def _get_admin_password():
    global ADMIN_PASSWORD
    if ADMIN_PASSWORD is None:
        ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
    return ADMIN_PASSWORD

def _get_session_secret():
    global SESSION_SECRET
    if SESSION_SECRET is None:
        SESSION_SECRET = os.environ.get('SESSION_SECRET', 'default_secret_change_me')
    return SESSION_SECRET

# Rate limiting for login
_login_attempts = {}  # ip -> {'count': int, 'locked_until': float}

TEST_URLS = {
    'nykaa.com': 'https://www.nykaa.com/minimalist-10-niacinamide-5-zinc-face-serum/p/587953',
    'amazon.in': 'https://www.amazon.in/dp/B08PZYN2YY',
    'foxtale.in': 'https://foxtale.in/products/glow-sunscreen',
    'beaminimalist.com': 'https://beaminimalist.com/products/niacinamide-10-zinc-1',
    'purplle.com': 'https://www.purplle.com/product/minimalist-10-niacinamide-5-zinc-face-serum-30ml',
    'sephora.com': 'https://www.sephora.com/product/the-ordinary-niacinamide-10-zinc-1-P447866',
    'theordinary.com': 'https://theordinary.com/en-in/niacinamide-10-zinc-1-100436.html',
}

import secrets

# token -> {'exp': float, 'csrf': str}
_active_sessions = {}


def _session_entry(token):
    """Normalise the stored value.

    Older sessions stored a bare expiry float. Handling both shapes means a
    deploy does not log every admin out mid-session.
    """
    raw = _active_sessions.get(token)
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    return {'exp': raw, 'csrf': None}


def _make_session_token():
    token = secrets.token_hex(32)
    _active_sessions[token] = {
        'exp': time.time() + 28800,          # 8 hours
        'csrf': secrets.token_hex(32),
    }
    # Clean up expired sessions
    expired = [t for t, v in list(_active_sessions.items())
               if time.time() > (v['exp'] if isinstance(v, dict) else v)]
    for t in expired:
        _active_sessions.pop(t, None)
    return token


def _verify_session(request: Request):
    token = request.cookies.get('admin_session')
    if not token:
        return False
    entry = _session_entry(token)
    if not entry:
        return False
    if time.time() > entry['exp']:
        _active_sessions.pop(token, None)
        return False
    return True


def _get_csrf_token(request: Request):
    """The CSRF token bound to this session, for embedding in the dashboard."""
    entry = _session_entry(request.cookies.get('admin_session'))
    return (entry or {}).get('csrf') or ''


# Origins permitted to drive admin actions. The dashboard is served by this same
# app, so in practice this is the backend's own origin.
def _origin_is_acceptable(request: Request):
    """Reject obvious cross-site submissions.

    Defence in depth alongside the token. Sec-Fetch-Site is set by the browser
    and cannot be spoofed by page JavaScript; when it is absent (older browsers,
    non-browser clients) we fall back to the token alone rather than locking
    legitimate tools out.
    """
    site = request.headers.get('sec-fetch-site')
    if site and site not in ('same-origin', 'same-site', 'none'):
        return False
    return True


def _require_csrf(request: Request):
    """Guard every state-changing admin route.

    The session cookie is SameSite=None because the public frontend lives on a
    different origin from this API. That is necessary, but it means the browser
    attaches the admin cookie to cross-site requests too, so a page the admin
    happens to visit could fire an admin action in their session. CORS does not
    prevent this - it governs whether the attacker can READ the response, not
    whether the browser SENDS the request, and a deletion has already happened
    by then.

    The token is bound to the session, delivered only inside the dashboard HTML
    (which requires a valid session to load), and cannot be read cross-origin.
    """
    entry = _session_entry(request.cookies.get('admin_session'))
    if not entry:
        raise HTTPException(401)
    if not _origin_is_acceptable(request):
        raise HTTPException(403, detail="Cross-site request rejected.")
    expected = entry.get('csrf')
    if not expected:
        # Session predates CSRF support; require re-login rather than allowing
        # an unprotected state change.
        raise HTTPException(403, detail="Session out of date - please sign in again.")
    supplied = request.headers.get('x-csrf-token', '')
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(403, detail="Invalid or missing CSRF token.")
    return True


def _check_rate_limit(ip):
    entry = _login_attempts.get(ip, {'count': 0, 'locked_until': 0})
    if time.time() < entry.get('locked_until', 0):
        return False
    return True


def _record_attempt(ip, success):
    if success:
        _login_attempts.pop(ip, None)
        return
    entry = _login_attempts.get(ip, {'count': 0, 'locked_until': 0})
    entry['count'] = entry.get('count', 0) + 1
    if entry['count'] >= 5:
        entry['locked_until'] = time.time() + 1800  # 30 min lockout
        entry['count'] = 0
    _login_attempts[ip] = entry


# ─── Login Routes ─────────────────────────────────────────────

@admin_router.get("/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    if _verify_session(request):
        return RedirectResponse(url="/api/admin/dashboard", status_code=302)
    tmpl = jinja_env.get_template('admin_login.html')
    return HTMLResponse(tmpl.render(error=None))


@admin_router.post("/login")
async def admin_login(request: Request):
    form = await request.form()
    password = form.get('password', '')
    ip = request.client.host if request.client else '0.0.0.0'

    if not _check_rate_limit(ip):
        tmpl = jinja_env.get_template('admin_login.html')
        return HTMLResponse(tmpl.render(error="Too many attempts. Try again in 30 minutes."))

    _expected = _get_admin_password()
    # Constant-time comparison: `==` short-circuits on the first
    # mismatched byte, which leaks how much of the password was correct.
    if _expected and secrets.compare_digest(password, _expected):
        _record_attempt(ip, True)
        token = _make_session_token()
        resp = RedirectResponse(url="/api/admin/dashboard", status_code=302)
        resp.set_cookie('admin_session', token, max_age=28800, httponly=True, samesite='none', secure=True, path='/')
        return resp

    _record_attempt(ip, False)
    tmpl = jinja_env.get_template('admin_login.html')
    return HTMLResponse(tmpl.render(error="Incorrect password"))


@admin_router.get("/logout")
async def admin_logout():
    resp = RedirectResponse(url="/api/admin/login", status_code=302)
    resp.delete_cookie('admin_session')
    return resp


# ─── Dashboard ────────────────────────────────────────────────

@admin_router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    if not _verify_session(request):
        return RedirectResponse(url="/api/admin/login", status_code=302)
    tmpl = jinja_env.get_template('admin_dashboard.html')
    return HTMLResponse(tmpl.render(csrf_token=_get_csrf_token(request)))


# ─── API Endpoints for Dashboard Data ─────────────────────────

@admin_router.get("/health-check")
async def health_check(request: Request):
    if not _verify_session(request):
        raise HTTPException(401)

    results = {}

    # Backend self-check
    results['backend'] = {'status': 'green', 'time_ms': 0, 'checked': _now()}

    # CSV Database
    db_ok = len(data_loader.ingredient_lookup) > 0
    results['csv_database'] = {
        'status': 'green' if db_ok else 'red',
        'time_ms': 0,
        'checked': _now(),
        'detail': f"{len(data_loader.ingredient_lookup)} ingredients loaded" if db_ok else "Not loaded",
    }

    # External services
    checks = [
        ('firecrawl', f"https://api.firecrawl.dev/v1/scrape",
         {'Authorization': f"Bearer {os.environ.get('FIRECRAWL_API_KEY', '')}", 'Content-Type': 'application/json'}),
        ('scrapdo', f"https://api.scrape.do/?token={os.environ.get('SCRAPDO_API_KEY', '')}&url=https://httpbin.org/ip",
         {}),
        ('scraperapi', f"http://api.scraperapi.com/account?api_key={os.environ.get('SCRAPERAPI_KEY', '')}",
         {}),
        ('huggingface', 'https://api-inference.huggingface.co/models/sentence-transformers/all-MiniLM-L6-v2',
         {'Authorization': f"Bearer {os.environ.get('HUGGINGFACE_API_KEY', '')}"}),
        ('exchangerate', f"https://v6.exchangerate-api.com/v6/{os.environ.get('EXCHANGE_RATE_API_KEY', '')}/latest/USD",
         {}),
        ('openbeautyfacts', 'https://world.openbeautyfacts.org/api/v0/product/737628064502.json',
         {}),
    ]

    async with aiohttp.ClientSession() as session:
        for name, url, headers in checks:
            t0 = time.time()
            try:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    ms = round((time.time() - t0) * 1000)
                    if resp.status < 500:
                        status = 'yellow' if ms > 3000 else 'green'
                    else:
                        status = 'red'
                    results[name] = {'status': status, 'time_ms': ms, 'checked': _now(),
                                     'http_status': resp.status}
            except Exception as e:
                ms = round((time.time() - t0) * 1000)
                results[name] = {'status': 'red', 'time_ms': ms, 'checked': _now(),
                                 'error': str(e)[:100]}

    # DuckDuckGo Search test
    t0 = time.time()
    try:
        from duckduckgo_search import DDGS
        loop = asyncio.get_running_loop()
        def _ddg_test():
            with DDGS() as ddgs:
                return list(ddgs.text("skincare test", max_results=1))
        r = await asyncio.wait_for(loop.run_in_executor(None, _ddg_test), timeout=10)
        ms = round((time.time() - t0) * 1000)
        results['duckduckgo'] = {'status': 'yellow' if ms > 3000 else 'green',
                                  'time_ms': ms, 'checked': _now()}
    except Exception as e:
        ms = round((time.time() - t0) * 1000)
        results['duckduckgo'] = {'status': 'yellow', 'time_ms': ms, 'checked': _now(),
                                  'error': 'Rate limited (normal)'}

    return results


@admin_router.get("/logs")
async def get_logs(request: Request, status: str = None, domain: str = None):
    if not _verify_session(request):
        raise HTTPException(401)
    logs = admin_db.get_fetch_logs(200, status, domain)
    stats = admin_db.get_fetch_stats_today()
    return {'logs': logs, 'stats': stats}


@admin_router.get("/credits")
async def get_credits(request: Request):
    if not _verify_session(request):
        raise HTTPException(401)
    summary = admin_db.get_credits_summary()
    credit_bars, warnings = get_credit_status(summary)
    return {'credits': credit_bars, 'warnings': warnings}


@admin_router.get("/analytics")
async def get_analytics(request: Request):
    if not _verify_session(request):
        raise HTTPException(401)
    return admin_db.get_analysis_stats()


@admin_router.get("/site-stats")
async def get_site_stats(request: Request):
    if not _verify_session(request):
        raise HTTPException(401)
    stats = admin_db.get_site_stats(days=7)
    return {'sites': stats, 'test_urls': TEST_URLS}


@admin_router.get("/layer-stats")
async def get_layer_stats(request: Request):
    if not _verify_session(request):
        raise HTTPException(401)
    return {'layers': admin_db.get_layer_stats(days=7)}


@admin_router.get("/ingredient-trends")
async def get_ingredient_trends(request: Request):
    if not _verify_session(request):
        raise HTTPException(401)
    return {'trends': admin_db.get_ingredient_trends(days=7, limit=10)}


@admin_router.get("/recent-analyses")
async def get_recent_analyses(request: Request):
    if not _verify_session(request):
        raise HTTPException(401)
    return {'analyses': admin_db.get_recent_analyses(limit=50)}


@admin_router.get("/flagged-count")
async def flagged_count(request: Request):
    if not _verify_session(request):
        raise HTTPException(401)
    return {'count': admin_db.get_flagged_count()}


@admin_router.get("/flagged-analyses")
async def get_flagged_analyses(request: Request):
    if not _verify_session(request):
        raise HTTPException(401)
    resolved = request.query_params.get('resolved', 'false').lower() == 'true'
    return {'analyses': admin_db.get_flagged_analyses(limit=200, include_resolved=resolved)}


@admin_router.post("/resolve-flag/{analysis_id}")
async def resolve_flag(analysis_id: int, request: Request):
    if not _verify_session(request):
        raise HTTPException(401)
    _require_csrf(request)
    ok = admin_db.resolve_flag(analysis_id)
    return {'ok': ok}


@admin_router.post("/test-site")
async def test_site(request: Request):
    if not _verify_session(request):
        raise HTTPException(401)
    _require_csrf(request)
    body = await request.json()
    url = body.get('url', '')
    if not url:
        raise HTTPException(400, "URL required")
    from product_fetcher import fetch_product_data
    t0 = time.time()
    result = await fetch_product_data(url, timeout=30)
    elapsed = round((time.time() - t0) * 1000)
    if result:
        all_fields = ['product_name', 'brand', 'price', 'size_ml', 'ingredients', 'category', 'country']
        fetched = [f for f in all_fields if result.get(f)]
        missing = [f for f in all_fields if not result.get(f)]
        return {'success': True, 'source': result.get('source', '?'), 'time_ms': elapsed,
                'fetched': fetched, 'missing': missing}
    return {'success': False, 'source': None, 'time_ms': elapsed, 'fetched': [], 'missing': ['all']}


@admin_router.get("/db-info")
async def get_db_info(request: Request):
    if not _verify_session(request):
        raise HTTPException(401)
    import sys

    # Ingredient counts
    ing_count = len(data_loader.ingredient_lookup)
    synergy_count = sum(len(v) for v in data_loader.synergy_registry.values())
    uv_count = len(data_loader.uv_sun_db)

    # Check config keys
    keys_status = {}
    for key_name in ['FIRECRAWL_API_KEY', 'SCRAPDO_API_KEY', 'SCRAPERAPI_KEY',
                     'HUGGINGFACE_API_KEY', 'EXCHANGE_RATE_API_KEY', 'ADMIN_PASSWORD',
                     'SERPER_API_KEY', 'SESSION_SECRET']:
        keys_status[key_name] = bool(os.environ.get(key_name, ''))

    # Memory estimate
    mem_mb = round(sys.getsizeof(data_loader.ingredient_lookup) / 1024 / 1024 +
                   sys.getsizeof(data_loader.uv_sun_db) / 1024 / 1024, 2)

    return {
        'ingredient_count': ing_count,
        'synergy_count': synergy_count,
        'uv_count': uv_count,
        'keys_status': keys_status,
        'memory_mb': mem_mb,
    }


@admin_router.post("/reload-csv")
async def reload_csv(request: Request):
    if not _verify_session(request):
        raise HTTPException(401)
    _require_csrf(request)
    try:
        data_loader.load_data()
        return {'status': 'ok', 'ingredients': len(data_loader.ingredient_lookup)}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


@admin_router.post("/clear-old-logs")
async def clear_old_logs(request: Request):
    if not _verify_session(request):
        raise HTTPException(401)
    _require_csrf(request)
    deleted = admin_db.clear_old_logs(30)
    return {'deleted': deleted}


@admin_router.get("/export-logs")
async def export_logs(request: Request):
    if not _verify_session(request):
        raise HTTPException(401)
    csv = admin_db.export_fetch_logs_csv()
    return PlainTextResponse(csv, media_type='text/csv',
                             headers={'Content-Disposition': 'attachment; filename=fetch_logs.csv'})


@admin_router.get("/export-analytics")
async def export_analytics(request: Request):
    if not _verify_session(request):
        raise HTTPException(401)
    csv = admin_db.export_analytics_csv()
    return PlainTextResponse(csv, media_type='text/csv',
                             headers={'Content-Disposition': 'attachment; filename=analytics.csv'})


def _now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

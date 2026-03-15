from fastapi import FastAPI, APIRouter, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
import re
import html as html_module
import requests
import time
import hashlib
from pathlib import Path
from pydantic import BaseModel
from typing import List, Optional
from scoring import analyze_product
from data_loader import data_loader
from admin import admin_router
from admin_db import log_fetch, log_analysis, increment_credits
from bs4 import BeautifulSoup
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from product_fetcher import fetch_multiple_products, fetch_product_data

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
api_router = APIRouter(prefix="/api")
app.include_router(admin_router)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── Simple In-Memory Cache ───────────────────────────────────────────────
# Caches analysis results keyed by (url or ingredient_hash, concerns, skin_type, price, size)
_CACHE: dict = {}
_CACHE_TTL = 3600  # 1 hour

def _make_cache_key(data: dict) -> str:
    """Create a stable cache key from request fields."""
    key_str = "|".join([
        str(data.get('url', '')),
        str(data.get('ingredients', ''))[:200],
        str(data.get('product_name', '')),
        str(data.get('price', '')),
        str(data.get('size_ml', '')),
        ",".join(sorted(data.get('concerns', []))),
        str(data.get('skin_type', '')),
        str(data.get('country', '')),
    ])
    return hashlib.md5(key_str.encode()).hexdigest()

def _cache_get(key: str):
    entry = _CACHE.get(key)
    if entry and (time.time() - entry['ts']) < _CACHE_TTL:
        return entry['data']
    if entry:
        del _CACHE[key]
    return None

def _cache_set(key: str, data: dict):
    # Evict oldest if cache too large
    if len(_CACHE) > 500:
        oldest = min(_CACHE.items(), key=lambda x: x[1]['ts'])
        del _CACHE[oldest[0]]
    _CACHE[key] = {'data': data, 'ts': time.time()}


def _sanitize(text):
    """Strip HTML tags from user input."""
    if not text:
        return text
    text = str(text)
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"error": "Rate limit exceeded. Please try again later."})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": "An internal error occurred. Please try again."})


@app.middleware("http")
async def payload_limit_middleware(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 1_048_576:
        return JSONResponse(status_code=413, content={"error": "Payload too large. Maximum 1MB allowed."})
    return await call_next(request)


class AnalyzeRequest(BaseModel):
    ingredients: str
    price: float = 0
    size: float = 30  # default 30ml
    size_ml: Optional[float] = None
    category: str = "Serum"
    skin_concerns: Optional[List[str]] = []
    concerns: Optional[List[str]] = []
    skin_type: str = "normal"
    country: str = "India"
    currency: str = "INR"
    product_name: Optional[str] = None
    brand: Optional[str] = None
    url_provided: Optional[bool] = False
    fetch_type: Optional[str] = None  # "url" | "barcode" | "manual" — set by frontend
    active_concentrations: Optional[dict] = None  # scraped from product page


class FetchProductRequest(BaseModel):
    barcode: Optional[str] = None
    url: Optional[str] = None


class FindAlternativesRequest(BaseModel):
    product_category: str
    key_actives: List[str]
    country: str = "India"
    currency: str = "INR"
    upgrade_targets: Optional[List[dict]] = []
    user_score: Optional[int] = 0
    user_safety_score: Optional[float] = 0
    user_concern_fit: Optional[dict] = {}
    user_skin_type_score: Optional[int] = 0
    user_skin_type: Optional[str] = "normal"
    user_concerns: Optional[List[str]] = []
    user_price: Optional[float] = 0
    user_size_ml: Optional[float] = 30
    user_product_name: Optional[str] = None


@api_router.get("/")
async def root():
    return {"message": "Skincare Calculator API", "status": "alive", "db_loaded": data_loader.is_loaded()}


@api_router.get("/health")
async def health():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("ok")


VALID_SKIN_TYPES = {'oily', 'dry', 'combination', 'sensitive', 'normal'}
VALID_CATEGORIES = {'serum', 'moisturizer', 'cleanser', 'toner', 'sunscreen',
                    'eye cream', 'mask', 'treatment', 'facial oil', 'oil'}

@api_router.post("/analyze")
@limiter.limit("10/minute")
async def analyze(req: AnalyzeRequest, request: Request):
    ingredients = _sanitize(req.ingredients)
    if not ingredients:
        return JSONResponse(status_code=400, content={"error": "No ingredients provided"})
    if len(ingredients) > 5000:
        return JSONResponse(status_code=400, content={"error": "Ingredient list too long. Maximum 5000 characters."})

    skin_type_raw = (_sanitize(req.skin_type) or "normal").lower()
    if skin_type_raw not in VALID_SKIN_TYPES:
        skin_type_raw = "normal"

    category_raw = (_sanitize(req.category) or "Serum").lower()
    if category_raw not in VALID_CATEGORIES:
        category_raw = "serum"
    category_display = category_raw.title()

    try:
        import time as _time
        t0 = _time.time()
        size_ml = req.size_ml if req.size_ml is not None else req.size
        concerns = req.skin_concerns if req.skin_concerns else (req.concerns or [])
        product_data = {
            'ingredients': ingredients,
            'price': req.price,
            'size_ml': size_ml,
            'category': category_display,
            'concerns': [_sanitize(c) for c in concerns],
            'skin_type': skin_type_raw,
            'country': _sanitize(req.country) or "India",
            'currency': _sanitize(req.currency) or "INR",
            'product_name': _sanitize(req.product_name or ''),
            'active_concentrations': req.active_concentrations or {},
        }

        # Check cache
        cache_key = _make_cache_key(product_data)
        cached = _cache_get(cache_key)
        if cached:
            logger.info("Cache hit for analysis request")
            return cached

        result = analyze_product(product_data)
        elapsed = round((_time.time() - t0) * 1000)

        # Determine fetch_type: explicit value from request takes priority, then
        # infer from url_provided. Default is 'manual'.
        if req.fetch_type in ('url', 'barcode', 'manual'):
            fetch_type = req.fetch_type
        elif req.url_provided:
            fetch_type = 'url'
        else:
            fetch_type = 'manual'

        # Extract identified_actives names list for ingredient trend tracking
        identified_actives = result.get('identified_actives', []) or []
        ingredient_count = result.get('ingredient_count', 0) or 0
        score = result.get('main_worth_score', 0) or 0

        # ── Flagging logic ───────────────────────────────────────────────────
        # Flag if result looks like garbage data (bad scrape or empty input)
        is_flagged = False
        flag_reason = None
        if score < 15:
            is_flagged = True
            flag_reason = 'Extremely low score (<15) — manual data quality check needed'
        elif score < 25 and ingredient_count >= 5:
            is_flagged = True
            flag_reason = f'Low score ({score:.0f}) despite {ingredient_count} ingredients — possible scraped garbage'
        elif ingredient_count <= 2 and fetch_type == 'url':
            is_flagged = True
            flag_reason = f'URL fetch returned only {ingredient_count} ingredient(s) — scrape likely failed'

        log_analysis(category_display, req.country, skin_type_raw, concerns,
                     score, bool(req.url_provided), None, elapsed,
                     product_name=_sanitize(req.product_name or ''),
                     brand=_sanitize(req.brand or ''),
                     price=req.price,
                     ingredients=ingredients[:500] if ingredients else None,
                     fetch_type=fetch_type,
                     identified_actives=identified_actives,
                     ingredient_count=ingredient_count,
                     is_flagged=is_flagged,
                     flag_reason=flag_reason)

        # Store in cache
        _cache_set(cache_key, result)
        return result
    except Exception as e:
        import traceback
        logger.error(f"Analysis failed: {e}\n{traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"error": "Analysis failed. Please check your inputs."})


@api_router.post("/fetch-product")
@limiter.limit("10/minute")
async def fetch_product(req: FetchProductRequest, request: Request):
    if req.barcode:
        return await fetch_from_barcode(req.barcode)
    elif req.url:
        return await fetch_from_url(req.url)
    else:
        return JSONResponse(status_code=400, content={"error": "Provide either a barcode or URL"})


async def fetch_from_barcode(barcode: str):
    try:
        barcode = re.sub(r'[^0-9]', '', barcode)
        resp = requests.get(f"https://world.openbeautyfacts.org/product/{barcode}.json", timeout=10)
        if resp.status_code != 200:
            return JSONResponse(status_code=404, content={"error": "Product not found on Open Beauty Facts"})

        data = resp.json()
        product = data.get('product', {})
        if not product:
            return JSONResponse(status_code=404, content={"error": "Product not found"})

        ingredients_text = product.get('ingredients_text', '') or product.get('ingredients_text_en', '')
        quantity = product.get('quantity', '')
        brands = product.get('brands', '')
        product_name = product.get('product_name', '') or product.get('product_name_en', '')

        size_val = None
        size_unit = 'ml'
        if quantity:
            size_match = re.search(r'(\d+\.?\d*)\s*(ml|g|oz|fl\s*oz)', quantity, re.IGNORECASE)
            if size_match:
                size_val = float(size_match.group(1))
                size_unit = size_match.group(2).lower().replace(' ', '')

        return {
            "source": "openbeautyfacts",
            "product_name": product_name,
            "brand": brands,
            "ingredients": ingredients_text,
            "size": size_val,
            "unit": size_unit,
            "price": None,
            "country": None,
            "currency": None,
            "partial": not bool(ingredients_text),
        }
    except requests.Timeout:
        return JSONResponse(status_code=504, content={"error": "Open Beauty Facts request timed out"})
    except Exception as e:
        logger.error(f"Barcode fetch failed: {e}")
        return JSONResponse(status_code=500, content={"error": "Failed to fetch product data"})


async def fetch_from_url(url: str):
    try:
        result = await fetch_product_data(url, timeout=25)
        if result:
            has_ingredients = bool(result.get('ingredients'))
            country_uncertain = result.get('country_uncertain', False)
            return {
                "source": result.get('source', 'multi-tier-scraper'),
                "product_name": result.get('product_name'),
                "brand": result.get('brand'),
                "ingredients": result.get('ingredients'),
                "size": result.get('size_ml'),
                "unit": result.get('size_unit', 'ml'),
                "price": result.get('price'),
                "price_confidence": result.get('price_confidence', 'low'),
                "country": result.get('country'),
                "currency": result.get('currency'),
                "category": result.get('category'),
                "partial": not has_ingredients,
                "country_uncertain": country_uncertain,
                "price_note": (
                    "Price could not be determined. Please fill in manually." if not result.get('price')
                    else "Price could not be determined reliably from this page. Please double-check or edit manually." if result.get('price_confidence') == 'low'
                    else None
                ),
                "message": "Some fields could not be fetched. Please fill in the missing fields manually." if not (result.get('product_name') and has_ingredients) else None,
                "country_message": "Could not detect country automatically. Please select your country." if country_uncertain else None,
                "active_concentrations": result.get('active_concentrations', {}),
            }
        return JSONResponse(status_code=502, content={
            "error": "Data fetching failed. Please paste ingredients manually.",
            "scrape_failed": True
        })
    except Exception as e:
        logger.error(f"URL fetch failed: {e}")
        return JSONResponse(status_code=500, content={
            "error": "Data fetching failed. Please paste ingredients manually.",
            "scrape_failed": True
        })


SITE_MAP = {
    'India':       ['amazon.in', 'nykaa.com', 'flipkart.com', 'purplle.com', 'myntra.com'],
    'USA':         ['amazon.com', 'sephora.com', 'ulta.com', 'target.com', 'walmart.com'],
    'UK':          ['amazon.co.uk', 'boots.com', 'lookfantastic.com', 'cultbeauty.co.uk', 'superdrug.com'],
    'UAE':         ['amazon.ae', 'noon.com', 'namshi.com', 'facesbeauty.com', 'sephora.ae'],
    'Singapore':   ['lazada.sg', 'shopee.sg', 'sephora.com.sg', 'guardian.com.sg', 'watsons.com.sg'],
    'Australia':   ['amazon.com.au', 'adorebeauty.com.au', 'priceline.com.au', 'sephora.com.au', 'mecca.com.au'],
    'Canada':      ['amazon.ca', 'sephora.com', 'shoppersdrugmart.ca', 'well.ca', 'walmart.ca'],
    'South Korea': ['coupang.com', 'oliveyoung.co.kr', 'musinsa.com', 'ssg.com', '11st.co.kr'],
    'Japan':       ['amazon.co.jp', 'cosme.net', 'rakuten.co.jp', 'loft.co.jp', 'matsukiyo.co.jp'],
    'France':      ['amazon.fr', 'sephora.fr', 'nocibe.fr', 'marionnaud.fr', 'lookfantastic.fr'],
    'Germany':     ['amazon.de', 'douglas.de', 'notino.de', 'flaconi.de', 'dm.de'],
    'Brazil':      ['amazon.com.br', 'sephora.com.br', 'belezanaweb.com.br', 'epocacosmeticos.com.br', 'netfarma.com.br'],
}


def _ddg_search(query, max_results=8):
    """Search using DuckDuckGo with retry on rate limit."""
    import time
    try:
        from duckduckgo_search import DDGS
        from duckduckgo_search.exceptions import RatelimitException
    except ImportError:
        return []
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except RatelimitException:
        time.sleep(3)
        try:
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=min(5, max_results)))
        except Exception:
            return []
    except Exception as e:
        logger.error(f"DDG search error: {e}")
        return []


def _serp_shopping_search(query, country, serp_key, num=10):
    """Fallback to SerpAPI Google Shopping."""
    country_gl = {
        'India': 'in', 'USA': 'us', 'UK': 'uk', 'UAE': 'ae',
        'Singapore': 'sg', 'Australia': 'au', 'Canada': 'ca',
        'South Korea': 'kr', 'Japan': 'jp', 'France': 'fr',
        'Germany': 'de', 'Brazil': 'br',
    }
    gl = country_gl.get(country, 'in')
    try:
        resp = requests.get(
            'https://serpapi.com/search.json',
            params={'engine': 'google_shopping', 'q': query, 'api_key': serp_key, 'hl': 'en', 'gl': gl, 'num': num},
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            results = []
            for item in data.get('shopping_results', [])[:num]:
                link = item.get('link', '') or item.get('product_link', '') or item.get('serpapi_product_api', '')
                results.append({
                    'name': item.get('title', ''),
                    'price': item.get('extracted_price', item.get('price', '')),
                    'link': link,
                    'thumbnail': item.get('thumbnail', ''),
                    'source': item.get('source', ''),
                })
            return results
    except Exception as e:
        logger.error(f"SerpAPI search failed: {e}")
    return []


@api_router.post("/find-alternatives")
@limiter.limit("10/minute")
async def find_alternatives(req: FindAlternativesRequest, request: Request):
    # ── Gate 1: No concerns selected → never show alternatives ──────────────
    concern_scores = req.user_concern_fit or {}
    if not concern_scores or not (req.user_concerns or []):
        return {
            "scored_alternatives": [], "basic_alternatives": [],
            "user_score": req.user_score, "skip_reason": "no_concerns",
        }

    # ── Gate 2: worth score >= 75 AND all concern fits >= 75 → excellent ────
    all_concerns_great = all(
        isinstance(v, (int, float)) and v >= 75
        for v in concern_scores.values()
    )
    if all_concerns_great and (req.user_score or 0) >= 75:
        return {
            "scored_alternatives": [], "basic_alternatives": [],
            "user_score": req.user_score, "skip_reason": "excellent",
        }

    # ── Gate 3: All concern fits >= 75 (but score < 75) → still great fit ──
    weak_concerns = {k: v for k, v in concern_scores.items() if isinstance(v, (int, float)) and v < 75}
    if not weak_concerns:
        return {
            "scored_alternatives": [], "basic_alternatives": [],
            "user_score": req.user_score, "skip_reason": "great_value",
        }

    # ── Helper: detect if a result is the same product as the user's ────────
    def _is_same_as_user_product(alt_name):
        """Return True if alt_name is too similar to the user's product name."""
        user_name = (req.user_product_name or '').strip().lower()
        if not user_name or not alt_name:
            return False
        alt_lower = alt_name.strip().lower()
        # Exact match
        if user_name == alt_lower:
            return True
        # One contains the other (handles minor title differences)
        if user_name in alt_lower or alt_lower in user_name:
            return True
        # Token overlap >= 80%: strip punctuation, compare word sets
        def _tokens(s):
            return set(re.sub(r'[^\w\s]', '', s).split())
        u_tok = _tokens(user_name)
        a_tok = _tokens(alt_lower)
        if u_tok and a_tok:
            overlap = len(u_tok & a_tok) / max(len(u_tok), len(a_tok))
            if overlap >= 0.8:
                return True
        return False

    # ── Normalise category for locking ──────────────────────────────────────
    category_lock = req.product_category.lower().strip()

    # ── Normalise user's key actives for overlap check ──────────────────────
    user_actives_norm = {a.lower().strip() for a in (req.key_actives or []) if a}

    def _shares_active(alt_actives):
        """Return True if alternative shares ≥1 main active with user product."""
        if not user_actives_norm:
            return True   # no actives to compare → don't filter
        alt_norm = {a.lower().strip() for a in alt_actives}
        return bool(user_actives_norm & alt_norm)

    serp_key = os.environ.get('SERPER_API_KEY', '')

    # ── Build search queries — always include category word ──────────────────
    search_terms = []
    # Priority: key actives from user's product + category
    for active in (req.key_actives or [])[:2]:
        search_terms.append(f"{active} {category_lock}")
    # Then concern + category
    for concern in (req.user_concerns or [])[:2]:
        search_terms.append(f"{concern} {category_lock}")
    if not search_terms:
        search_terms = [category_lock]

    sites = SITE_MAP.get(req.country, SITE_MAP.get('India', []))
    site_filter = ' OR '.join(f'site:{s}' for s in sites[:3])

    # ── Helper: build rich why_better list ──────────────────────────────────
    def _build_why_better(analysis, alt_actives):
        reasons = []
        score_delta = analysis['main_worth_score'] - (req.user_score or 0)
        if score_delta > 0:
            reasons.append(f"+{score_delta} pts higher overall worth score ({analysis['main_worth_score']} vs {req.user_score})")

        alt_safety = analysis['component_scores']['D']
        safety_delta = round(alt_safety - (req.user_safety_score or 0), 1)
        if safety_delta > 0:
            reasons.append(f"Better safety profile (+{safety_delta} pts)")
        elif safety_delta == 0:
            reasons.append("Equal safety profile")

        # Concern fit comparison
        alt_concern_fit = analysis.get('skin_concern_fit', {})
        for concern, user_fit_val in concern_scores.items():
            alt_fit_raw = alt_concern_fit.get(concern, {})
            alt_fit_val = alt_fit_raw.get('score', alt_fit_raw) if isinstance(alt_fit_raw, dict) else alt_fit_raw
            if isinstance(alt_fit_val, (int, float)) and isinstance(user_fit_val, (int, float)):
                fit_delta = round(alt_fit_val - user_fit_val)
                if fit_delta > 0:
                    reasons.append(f"Better {concern} fit (+{fit_delta}% → {round(alt_fit_val)}%)")

        ac = analysis['price_analysis']['active_count']
        shared = [a for a in alt_actives if a.lower() in user_actives_norm]
        if shared:
            reasons.append(f"Contains {', '.join(shared[:2])} — same key active(s) as your product")
        elif ac > 0:
            reasons.append(f"{ac} clinically-backed active{'s' if ac != 1 else ''}")

        return reasons[:4]  # max 4 reasons

    # ── Step 1: DDG search ───────────────────────────────────────────────────
    ddg_urls = []
    for term in search_terms[:3]:
        ddg_query = f"best {term} skincare {site_filter}"
        results = _ddg_search(ddg_query, max_results=5)
        for r in results:
            url = r.get('href', '')
            if url and url not in ddg_urls:
                ddg_urls.append(url)

    # ── Step 2: Fetch + score DDG results ───────────────────────────────────
    scored_alternatives = []
    if ddg_urls:
        fetch_urls = ddg_urls[:5]
        fetched_data = await fetch_multiple_products(fetch_urls, timeout=25)
        for i, product_data in enumerate(fetched_data):
            if not (product_data and product_data.get('ingredients')):
                continue
            try:
                alt_price = product_data.get('price') or 0
                analysis = analyze_product({
                    'ingredients': product_data['ingredients'],
                    'price': alt_price,
                    'size_ml': product_data.get('size_ml') or req.user_size_ml or 30,
                    'category': category_lock,
                    'concerns': req.user_concerns or [],
                    'skin_type': req.user_skin_type or 'normal',
                    'country': req.country,
                    'currency': req.currency,
                })
                alt_score = analysis['main_worth_score']
                alt_actives = [a['name'] for a in analysis.get('identified_actives', [])[:6]]

                # ── Skip if this is the same product as the user's ───────────
                alt_name_candidate = product_data.get('product_name') or fetch_urls[i].split('/')[-1].replace('-', ' ').title()
                if _is_same_as_user_product(alt_name_candidate):
                    logger.info(f"Skipping same product as user: {alt_name_candidate}")
                    continue

                # ── Category lock: skip if product page reports a different category ──
                scraped_cat = (product_data.get('category') or '').lower().strip()
                if scraped_cat and scraped_cat != category_lock and category_lock not in scraped_cat and scraped_cat not in category_lock:
                    logger.info(f"Category mismatch skipped: scraped={scraped_cat} vs lock={category_lock}")
                    continue

                # ── Active lock: must share ≥1 main active ──────────────
                if not _shares_active(alt_actives):
                    logger.info(f"Active mismatch skipped: {alt_actives} vs {user_actives_norm}")
                    continue

                if alt_score > (req.user_score or 0):
                    score_delta = alt_score - (req.user_score or 0)
                    why_better = _build_why_better(analysis, alt_actives)
                    alt_concern_fit = analysis.get('skin_concern_fit', {})
                    concern_fit_pct = {
                        k: round((v.get('score', v) if isinstance(v, dict) else v))
                        for k, v in alt_concern_fit.items()
                        if k in concern_scores
                    }
                    scored_alternatives.append({
                        'name': alt_name_candidate,
                        'score': alt_score,
                        'score_delta': score_delta,
                        'tier': analysis['main_worth_tier'],
                        'safety_score': analysis['component_scores']['D'],
                        'skin_type_score': analysis.get('skin_type_compatibility', 0),
                        'active_count': analysis['price_analysis']['active_count'],
                        'price': alt_price if alt_price else '',
                        'link': fetch_urls[i],
                        'thumbnail': '',
                        'source': fetch_urls[i].split('/')[2] if '/' in fetch_urls[i] else '',
                        'why_better': why_better,
                        'key_actives': alt_actives,
                        'concern_fit': concern_fit_pct,
                        'has_full_analysis': True,
                    })
            except Exception as e:
                logger.error(f"Re-scoring failed for DDG result: {e}")

    # ── Step 3: SerpAPI fallback ─────────────────────────────────────────────
    basic_alternatives = []
    if not scored_alternatives and serp_key:
        for term in search_terms[:2]:
            query = f"best {term} {category_lock} skincare"
            results = _serp_shopping_search(query, req.country, serp_key, num=8)
            basic_alternatives.extend(results)

        seen = set()
        deduped = []
        for r in basic_alternatives:
            if r['name'] not in seen:
                deduped.append(r)
                seen.add(r['name'])
        basic_alternatives = deduped[:3]

        serp_urls = [r['link'] for r in basic_alternatives if r.get('link')][:3]
        if serp_urls:
            fetched = await fetch_multiple_products(serp_urls, timeout=20)
            for i, pd_item in enumerate(fetched):
                if not (pd_item and pd_item.get('ingredients')):
                    continue
                try:
                    analysis = analyze_product({
                        'ingredients': pd_item['ingredients'],
                        'price': pd_item.get('price') or 0,
                        'size_ml': pd_item.get('size_ml') or 30,
                        'category': category_lock,
                        'concerns': req.user_concerns or [],
                        'skin_type': req.user_skin_type or 'normal',
                        'country': req.country,
                        'currency': req.currency,
                    })
                    alt_score = analysis['main_worth_score']
                    alt_actives = [a['name'] for a in analysis.get('identified_actives', [])[:6]]

                    # Category + active locks apply to SerpAPI results too
                    scraped_cat = (pd_item.get('category') or '').lower().strip()
                    if scraped_cat and scraped_cat != category_lock and category_lock not in scraped_cat and scraped_cat not in category_lock:
                        continue
                    if not _shares_active(alt_actives):
                        continue
                    # Skip if this is the same product as the user's
                    if _is_same_as_user_product(basic_alternatives[i]['name']):
                        logger.info(f"Skipping same product as user (serp): {basic_alternatives[i]['name']}")
                        continue

                    if alt_score > (req.user_score or 0):
                        score_delta = alt_score - (req.user_score or 0)
                        why_better = _build_why_better(analysis, alt_actives)
                        alt_concern_fit = analysis.get('skin_concern_fit', {})
                        concern_fit_pct = {
                            k: round((v.get('score', v) if isinstance(v, dict) else v))
                            for k, v in alt_concern_fit.items()
                            if k in concern_scores
                        }
                        scored_alternatives.append({
                            'name': basic_alternatives[i]['name'],
                            'score': alt_score,
                            'score_delta': score_delta,
                            'tier': analysis['main_worth_tier'],
                            'safety_score': analysis['component_scores']['D'],
                            'skin_type_score': analysis.get('skin_type_compatibility', 0),
                            'active_count': analysis['price_analysis']['active_count'],
                            'price': basic_alternatives[i].get('price', ''),
                            'link': basic_alternatives[i].get('link', ''),
                            'thumbnail': basic_alternatives[i].get('thumbnail', ''),
                            'source': basic_alternatives[i].get('source', ''),
                            'why_better': why_better,
                            'key_actives': alt_actives,
                            'concern_fit': concern_fit_pct,
                            'has_full_analysis': True,
                        })
                except Exception as e:
                    logger.error(f"Re-scoring SerpAPI result failed: {e}")

    scored_alternatives.sort(key=lambda x: x.get('score_delta', 0), reverse=True)
    scored_names = {a['name'] for a in scored_alternatives}
    basic_alternatives = [r for r in basic_alternatives if r['name'] not in scored_names][:3]

    search_message = None
    if not scored_alternatives and not basic_alternatives:
        if not serp_key:
            search_message = (
                "Live product search requires a SerpAPI key (SERPER_API_KEY). "
                "Search the upgrade suggestions above on Nykaa, Amazon, or your preferred site."
            )
        else:
            search_message = (
                "Could not find scorable alternatives right now — search may be temporarily limited. "
                "Try searching the upgrade suggestions above directly on Nykaa or Amazon."
            )

    return {
        "scored_alternatives": scored_alternatives[:3],
        "basic_alternatives": basic_alternatives,
        "user_score": req.user_score,
        "search_message": search_message,
    }


@api_router.get("/rates")
async def get_rates():
    import json as _json
    FALLBACK_PATH = ROOT_DIR / 'fallback_rates.json'

    def _load_fallback():
        try:
            with open(FALLBACK_PATH) as f:
                return {"rates": _json.load(f).get("rates", {}), "base": "USD", "source": "fallback"}
        except Exception:
            return {"rates": {}, "base": "USD", "source": "fallback"}

    api_key = os.environ.get('EXCHANGE_RATE_API_KEY', '')
    if not api_key:
        logger.warning("No EXCHANGE_RATE_API_KEY — using fallback rates")
        return _load_fallback()
    try:
        resp = requests.get(f"https://v6.exchangerate-api.com/v6/{api_key}/latest/USD", timeout=10)
        if resp.status_code == 200:
            return {"rates": resp.json().get("conversion_rates", {}), "base": "USD", "source": "live"}
        logger.warning(f"ExchangeRate API returned {resp.status_code} — using fallback")
        return _load_fallback()
    except Exception as e:
        logger.error(f"Rate fetch failed: {e} — using fallback")
        return _load_fallback()


class BestPriceRequest(BaseModel):
    product_name: str
    brand: Optional[str] = None
    size_ml: Optional[float] = None
    country: str = "India"
    currency: str = "INR"
    user_price: Optional[float] = 0
    user_url: Optional[str] = None


def _normalize_product_key(name, brand=None, size=None):
    """Normalize product identity for comparison."""
    key = (brand or '').lower().strip() + ' ' + name.lower().strip()
    key = re.sub(r'[^\w\s]', '', key)
    key = re.sub(r'\s+', ' ', key).strip()
    return key


def _is_same_product(result_title, brand, product_name, size_ml):
    """Check if a SERP result is the same product.
    Rules:
    - Bundles/combos/multi-packs → always reject
    - Brand match ≥ 90% fuzzy (partial_ratio)
    - Product name match ≥ 85% fuzzy (token_set_ratio)
    - Size within 5ml/g tolerance (if size provided and title has a size)
    """
    from rapidfuzz import fuzz as _fuzz
    title_lower = result_title.lower()

    # Discard bundles and multi-packs
    if any(kw in title_lower for kw in ['pack of', 'combo', 'bundle', 'set of', 'kit', '2x', '3x', 'multi-pack', 'multipack']):
        return False

    # Brand match >= 90%
    if brand:
        brand_score = _fuzz.partial_ratio(brand.lower(), title_lower)
        if brand_score < 90:
            return False

    # Product name match >= 85% (token_set_ratio handles word order differences)
    if product_name:
        name_score = _fuzz.token_set_ratio(product_name.lower(), title_lower)
        if name_score < 85:
            return False

    # Size match within 5ml/g tolerance
    if size_ml:
        size_matches = re.findall(r'(\d+\.?\d*)\s*(ml|g)', title_lower)
        if size_matches:
            for val_str, unit in size_matches:
                val = float(val_str)
                if abs(val - size_ml) <= 5:
                    return True
            return False  # sizes present but none matched

    return True


@api_router.post("/best-price")
@limiter.limit("10/minute")
async def best_price(req: BestPriceRequest, request: Request):
    """Find cheapest price: DDG search → ScrapeDo/Firecrawl fetch → fallback SerpAPI.
    Returns up to 3 validated results (same brand, same size, country-specific).
    """
    sites = SITE_MAP.get(req.country, SITE_MAP.get('India', []))
    site_filter = ' OR '.join(f'site:{s}' for s in sites[:4])

    query = req.product_name
    if req.brand:
        query = f"{req.brand} {query}"
    size_query = f"{int(req.size_ml)}ml" if req.size_ml else ""

    validated = []

    # Step 1: DDG search for exact product on country-specific sites
    ddg_query = f"{query} {size_query} buy {site_filter}"
    ddg_results = _ddg_search(ddg_query, max_results=10)
    ddg_urls = [r.get('href', '') for r in ddg_results if r.get('href')]

    if ddg_urls:
        fetched = await fetch_multiple_products(ddg_urls[:6], timeout=20)
        seen_sources = set()
        for i, pd_item in enumerate(fetched):
            if not pd_item or not pd_item.get('price'):
                continue
            if i >= len(ddg_urls):
                continue
            source_domain = ddg_urls[i].split('/')[2] if '/' in ddg_urls[i] else ''
            if source_domain in seen_sources:
                continue
            name = pd_item.get('product_name') or (ddg_results[i].get('title', '') if i < len(ddg_results) else '')
            if not _is_same_product(name or '', req.brand, req.product_name, req.size_ml):
                continue
            seen_sources.add(source_domain)
            validated.append({
                'name': name,
                'price': pd_item['price'],
                'link': ddg_urls[i],
                'source': source_domain,
            })

    # Step 2: Fallback to SerpAPI if DDG didn't yield 3 results
    if len(validated) < 3:
        serp_key = os.environ.get('SERPER_API_KEY', '')
        if serp_key:
            serp_query = f"{query} {size_query}"
            serp_results = _serp_shopping_search(serp_query, req.country, serp_key, num=12)
            seen_sources = {v['source'].lower() for v in validated}
            for item in serp_results:
                if len(validated) >= 3:
                    break
                extracted_price = item.get('price')
                if not extracted_price or not isinstance(extracted_price, (int, float)):
                    continue
                source = item.get('source', '')
                if source.lower() in seen_sources:
                    continue
                title = item.get('name', '')
                if not _is_same_product(title, req.brand, req.product_name, req.size_ml):
                    continue
                seen_sources.add(source.lower())
                validated.append({
                    'name': title,
                    'price': extracted_price,
                    'link': item.get('link', ''),
                    'source': source,
                })

    # Filter eBay for India
    if req.country and req.country.lower() == 'india':
        validated = [v for v in validated if 'ebay' not in v.get('source', '').lower()]

    # Sort by price ascending
    validated.sort(key=lambda x: float(x['price']) if x['price'] else 9999999)

    # Keep max 3
    validated = validated[:3]

    user_price = float(req.user_price or 0)

    if not validated:
        # Rule 10: no results found anywhere — still show card with user URL if available
        return {
            "is_user_cheapest": False,
            "not_found": True,
            "user_url": req.user_url,
            "user_price": user_price,
            "all_prices": [],
            "savings": 0,
        }

    cheapest = validated[0]
    cheapest_price = float(cheapest['price'])

    # Annotate savings per item vs user price
    for item in validated:
        item_price = float(item['price'])
        item['savings'] = round(user_price - item_price, 2) if user_price > 0 else 0

    if user_price > 0 and user_price <= cheapest_price:
        # User's product is the cheapest
        return {
            "is_user_cheapest": True,
            "user_url": req.user_url,
            "user_price": user_price,
            "all_prices": validated,   # still show other options as reference
            "savings": 0,
        }
    else:
        return {
            "is_user_cheapest": False,
            "not_found": False,
            "best_price": cheapest,
            "user_url": req.user_url,
            "user_price": user_price,
            "all_prices": validated,
            "savings": round(user_price - cheapest_price, 2) if user_price > 0 else 0,
        }


app.include_router(api_router)

# Production: locked to urancal.com only
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[
        "https://urancal.com",
        "https://www.urancal.com",
        "https://tool.urancal.com",
        "https://skincare-calculator.pages.dev",
        "http://localhost:3000",
        "http://localhost:5001",
    ],
    # Covers Cloudflare Pages preview deployments (e.g. 023c036f.skincare-calculator.pages.dev)
    allow_origin_regex=r"https://.*\.skincare-calculator\.pages\.dev",
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

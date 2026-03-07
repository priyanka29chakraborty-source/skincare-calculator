from fastapi import FastAPI, APIRouter, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
import re
import html as html_module
import requests
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


@api_router.get("/")
async def root():
    return {"message": "Skincare Calculator API", "status": "alive", "db_loaded": data_loader.is_loaded()}


@api_router.get("/health")
async def health():
    db_loaded = data_loader.is_loaded()
    ing_count = len(data_loader.ingredient_lookup)
    if not db_loaded:
        logger.error("STARTUP WARNING: ingredient database not loaded. Check backend/database/ folder.")
    return {
        "status": "alive",
        "db_loaded": db_loaded,
        "ingredient_count": ing_count,
        "warning": "Ingredient database empty — check database/ folder" if not db_loaded else None
    }


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

    # Validate and normalise skin_type
    skin_type_raw = (_sanitize(req.skin_type) or "normal").lower()
    if skin_type_raw not in VALID_SKIN_TYPES:
        skin_type_raw = "normal"

    # Validate and normalise category
    category_raw = (_sanitize(req.category) or "Serum").lower()
    if category_raw not in VALID_CATEGORIES:
        category_raw = "serum"
    # Restore Title Case for display
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
        result = analyze_product(product_data)
        elapsed = round((_time.time() - t0) * 1000)
        log_analysis(category_display, req.country, skin_type_raw, concerns,
                     result.get('main_worth_score', 0), bool(req.url_provided), None, elapsed)
        return result
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
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
                "country": result.get('country'),
                "currency": result.get('currency'),
                "category": result.get('category'),
                "partial": not has_ingredients,
                "country_uncertain": country_uncertain,
                "price_note": "Price could not be determined. Please fill in manually." if not result.get('price') else None,
                "message": "Some fields could not be fetched. Please fill in the missing fields manually." if not (result.get('product_name') and has_ingredients) else None,
                "country_message": "Could not detect country automatically. Please select your country." if country_uncertain else None,
                "active_concentrations": result.get('active_concentrations', {}),
            }
        return JSONResponse(status_code=502, content={
            "error": "Data fetching failed. Please paste ingredients manually."
        })
    except Exception as e:
        logger.error(f"URL fetch failed: {e}")
        return JSONResponse(status_code=500, content={
            "error": "Data fetching failed. Please paste ingredients manually."
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
                # Prefer direct shopping site link over Google product page
                link = item.get('link', '') or item.get('product_link', '')
                # Skip Google product page links
                if 'google.com' in link or not link:
                    link = ''
                results.append({
                    'name': item.get('title', ''),
                    'price': item.get('extracted_price', item.get('price', '')),
                    'link': link,
                    'thumbnail': item.get('thumbnail', ''),
                    'source': item.get('source', ''),
                })
            return [r for r in results if r['link']]  # only return items with direct links
    except Exception as e:
        logger.error(f"SerpAPI search failed: {e}")
    return []


@api_router.post("/find-alternatives")
@limiter.limit("10/minute")
async def find_alternatives(req: FindAlternativesRequest, request: Request):
    # NEW: Check if ANY concern score < 75. If no concerns or all >= 75, skip.
    concern_scores = req.user_concern_fit or {}
    if not concern_scores:
        # No concerns selected — never show alternatives
        return {
            "scored_alternatives": [], "basic_alternatives": [],
            "user_score": req.user_score, "skip_reason": "no_concerns",
        }
    weak_concerns = {k: v for k, v in concern_scores.items() if isinstance(v, (int, float)) and v < 75}
    if not weak_concerns:
        # All concern scores >= 75 — great value
        return {
            "scored_alternatives": [], "basic_alternatives": [],
            "user_score": req.user_score, "skip_reason": "great_value",
        }

    serp_key = os.environ.get('SERPER_API_KEY', '')

    # Build search queries
    search_terms = []
    for target in (req.upgrade_targets or []):
        upgrade = target.get('upgrade', '')
        if upgrade:
            search_terms.append(upgrade)
    for concern in (req.user_concerns or [])[:2]:
        search_terms.append(f"{concern} {req.product_category}")
    if not search_terms:
        for active in req.key_actives[:2]:
            search_terms.append(f"{active} {req.product_category}")
    if not search_terms:
        search_terms = [req.product_category]

    sites = SITE_MAP.get(req.country, SITE_MAP.get('India', []))
    site_filter = ' OR '.join(f'site:{s}' for s in sites[:3])

    # Step 1: DDG search with country-specific sites (filter out Google links)
    ddg_urls = []
    for term in search_terms[:2]:
        ddg_query = f"{term} {req.product_category} {site_filter}"
        results = _ddg_search(ddg_query, max_results=5)
        for r in results:
            url = r.get('href', '')
            if url and url not in ddg_urls and 'google.com' not in url:
                ddg_urls.append(url)

    # Step 2: Fetch ingredients via Firecrawl → ScrapeDo waterfall
    scored_alternatives = []
    if ddg_urls:
        fetch_urls = ddg_urls[:4]
        fetched_data = await fetch_multiple_products(fetch_urls, timeout=25)
        for i, product_data in enumerate(fetched_data):
            if product_data and product_data.get('ingredients'):
                try:
                    alt_price = product_data.get('price') or 0
                    analysis = analyze_product({
                        'ingredients': product_data['ingredients'],
                        'price': alt_price,
                        'size_ml': product_data.get('size_ml') or req.user_size_ml or 30,
                        'category': req.product_category,
                        'concerns': req.user_concerns or [],
                        'skin_type': req.user_skin_type or 'normal',
                        'country': req.country,
                        'currency': req.currency,
                    })
                    alt_score = analysis['main_worth_score']
                    if alt_score > (req.user_score or 0):
                        score_delta = alt_score - (req.user_score or 0)
                        why_better = [f"+{score_delta} points higher overall ({alt_score} vs {req.user_score})"]
                        alt_safety = analysis['component_scores']['D']
                        safety_delta = alt_safety - (req.user_safety_score or 0)
                        if safety_delta > 0:
                            why_better.append(f"Better safety profile (+{safety_delta:.0f} pts)")
                        elif safety_delta >= 0:
                            why_better.append("Equal or better safety")
                        ac = analysis['price_analysis']['active_count']
                        if ac > 0:
                            why_better.append(f"{ac} clinically-backed active{'s' if ac != 1 else ''}")
                        alt_link = fetch_urls[i] if 'google.com' not in fetch_urls[i] else ''
                        alt_source = alt_link.split('/')[2].replace('www.', '') if alt_link and '/' in alt_link else ''
                        scored_alternatives.append({
                            'name': product_data.get('product_name') or fetch_urls[i].split('/')[-1].replace('-', ' ').title(),
                            'score': alt_score,
                            'score_delta': score_delta,
                            'tier': analysis['main_worth_tier'],
                            'safety_score': alt_safety,
                            'active_count': ac,
                            'price': alt_price if alt_price else '',
                            'link': alt_link,
                            'thumbnail': '',
                            'source': alt_source,
                            'why_better': why_better,
                            'key_actives': [a['name'] for a in analysis.get('identified_actives', [])[:4]],
                            'has_full_analysis': True,
                        })
                except Exception as e:
                    logger.error(f"Re-scoring failed for DDG result: {e}")

    # Step 3: Fallback to SerpAPI if DDG didn't yield scored results
    basic_alternatives = []
    if not scored_alternatives and serp_key:
        for term in search_terms[:2]:
            query = f"best {term} skincare"
            results = _serp_shopping_search(query, req.country, serp_key, num=8)
            basic_alternatives.extend(results)

        # Deduplicate
        seen = set()
        deduped = []
        for r in basic_alternatives:
            if r['name'] not in seen:
                deduped.append(r)
                seen.add(r['name'])
        basic_alternatives = deduped[:8]

        # Try to score top 3 SerpAPI results
        serp_urls = [r['link'] for r in basic_alternatives if r.get('link')][:3]
        if serp_urls:
            fetched = await fetch_multiple_products(serp_urls, timeout=20)
            for i, pd_item in enumerate(fetched):
                if pd_item and pd_item.get('ingredients'):
                    try:
                        analysis = analyze_product({
                            'ingredients': pd_item['ingredients'],
                            'price': pd_item.get('price') or 0,
                            'size_ml': pd_item.get('size_ml') or 30,
                            'category': req.product_category,
                            'concerns': req.user_concerns or [],
                            'skin_type': req.user_skin_type or 'normal',
                            'country': req.country,
                            'currency': req.currency,
                        })
                        alt_score = analysis['main_worth_score']
                        if alt_score > (req.user_score or 0):
                            score_delta = alt_score - (req.user_score or 0)
                            scored_alternatives.append({
                                'name': basic_alternatives[i]['name'],
                                'score': alt_score,
                                'score_delta': score_delta,
                                'tier': analysis['main_worth_tier'],
                                'safety_score': analysis['component_scores']['D'],
                                'active_count': analysis['price_analysis']['active_count'],
                                'price': basic_alternatives[i].get('price', ''),
                                'link': basic_alternatives[i].get('link', ''),
                                'thumbnail': basic_alternatives[i].get('thumbnail', ''),
                                'source': basic_alternatives[i].get('source', ''),
                                'why_better': [f"+{score_delta} points higher overall ({alt_score} vs {req.user_score})"],
                                'key_actives': [a['name'] for a in analysis.get('identified_actives', [])[:4]],
                                'has_full_analysis': True,
                            })
                    except Exception as e:
                        logger.error(f"Re-scoring SerpAPI result failed: {e}")

    scored_alternatives.sort(key=lambda x: x.get('score_delta', 0), reverse=True)
    scored_names = {a['name'] for a in scored_alternatives}
    basic_alternatives = [r for r in basic_alternatives if r['name'] not in scored_names][:6]

    return {
        "scored_alternatives": scored_alternatives[:3],
        "basic_alternatives": basic_alternatives,
        "user_score": req.user_score,
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
    category: Optional[str] = None
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
    """Check if a SERP result is the same product (same brand, variant, not a bundle)."""
    title_lower = result_title.lower()
    # Discard bundles and multi-packs
    if any(kw in title_lower for kw in ['pack of', 'combo', 'bundle', 'set of', 'kit', '2x', '3x']):
        return False
    # Must match brand
    if brand:
        brand_lower = brand.lower()
        if brand_lower not in title_lower:
            return False
    # Check size match if provided
    if size_ml:
        size_matches = re.findall(r'(\d+\.?\d*)\s*(ml|g)', title_lower)
        if size_matches:
            for val_str, unit in size_matches:
                val = float(val_str)
                if abs(val - size_ml) <= 5:
                    return True
            return False
    return True


@api_router.post("/best-price")
@limiter.limit("10/minute")
async def best_price(req: BestPriceRequest, request: Request):
    """Find cheapest price: DDG search → ScrapeDo/Firecrawl fetch → fallback SerpAPI."""
    sites = SITE_MAP.get(req.country, SITE_MAP.get('India', []))
    site_filter = ' OR '.join(f'site:{s}' for s in sites[:4])

    query = req.product_name or ""
    if req.brand:
        query = f"{req.brand} {query}"
    size_query = f"{int(req.size_ml)}ml" if req.size_ml else ""
    category_query = req.category or ""

    # Step 1: DDG search for exact product on country-specific sites
    ddg_query = f"{query} {size_query} {category_query} buy {site_filter}".strip()
    ddg_results = _ddg_search(ddg_query, max_results=8)
    ddg_urls = [r.get('href', '') for r in ddg_results if r.get('href')]

    validated = []

    # Step 2: Fetch prices from DDG URLs via Firecrawl/ScrapeDo
    if ddg_urls:
        fetched = await fetch_multiple_products(ddg_urls[:5], timeout=20)
        seen_sources = set()
        for i, pd_item in enumerate(fetched):
            if pd_item and pd_item.get('price'):
                source_domain = ddg_urls[i].split('/')[2] if '/' in ddg_urls[i] else ''
                # Skip Google links entirely
                if 'google.com' in source_domain:
                    continue
                if source_domain in seen_sources:
                    continue
                # Verify same product - must match brand and product name
                name = pd_item.get('product_name') or ddg_results[i].get('title', '')
                if req.brand and req.brand.lower() not in name.lower():
                    continue
                # Also check product name keyword match
                if req.product_name:
                    key_words = [w for w in req.product_name.lower().split() if len(w) > 3]
                    if key_words and not any(w in name.lower() for w in key_words[:2]):
                        continue
                # Must be on a known shopping site for the country
                if not any(s in source_domain for s in sites):
                    continue
                seen_sources.add(source_domain)
                validated.append({
                    'name': name,
                    'price': pd_item['price'],
                    'link': ddg_urls[i],
                    'source': source_domain,
                    'thumbnail': '',
                })

    # Step 3: Fallback to SerpAPI if DDG didn't yield results
    if not validated:
        serp_key = os.environ.get('SERPER_API_KEY', '')
        if serp_key:
            serp_query = f"{query} {size_query}"
            serp_results = _serp_shopping_search(serp_query, req.country, serp_key, num=10)
            seen_sources = set()
            for item in serp_results:
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
                    'thumbnail': item.get('thumbnail', ''),
                })

    validated.sort(key=lambda x: x['price'])

    # Filter out eBay for India results
    if req.country and req.country.lower() == 'india':
        validated = [v for v in validated if 'ebay' not in v.get('source', '').lower()]

    if not validated:
        return {"best_price": None, "all_prices": [], "is_user_cheapest": False, "savings": 0}

    user_price = req.user_price or 0
    cheapest = validated[0]

    if user_price > 0 and user_price <= cheapest['price']:
        return {
            "is_user_cheapest": True,
            "user_url": req.user_url,
            "user_price": user_price,
            "best_price": None,
            "all_prices": validated[:2],
            "savings": 0,
        }
    else:
        savings = round(user_price - cheapest['price'], 2) if user_price > 0 else 0
        return {
            "is_user_cheapest": False,
            "best_price": cheapest,
            "all_prices": validated[:2],
            "savings": savings,
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
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

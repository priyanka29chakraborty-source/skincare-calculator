import aiohttp
import asyncio
import re
import os
import json
import logging
import time
import random
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────

BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/html,*/*;q=0.9',
    'Accept-Language': 'en-IN,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Cache-Control': 'max-age=0',
}

CATEGORY_KEYWORDS = {
    'serum': 'Serum', 'moisturizer': 'Moisturizer', 'moisturiser': 'Moisturizer',
    'cleanser': 'Cleanser', 'face wash': 'Cleanser', 'toner': 'Toner',
    'sunscreen': 'Sunscreen', 'spf': 'Sunscreen', 'eye cream': 'Eye Cream',
    'mask': 'Mask', 'facial oil': 'Facial Oil', 'treatment': 'Treatment',
    'exfoliat': 'Treatment', 'peel': 'Treatment', 'cream': 'Moisturizer',
    'lotion': 'Moisturizer', 'gel': 'Moisturizer', 'mist': 'Toner',
    'essence': 'Toner', 'ampoule': 'Serum',
}

TLD_COUNTRY_MAP = {
    '.co.in': ('India', 'INR'), '.in': ('India', 'INR'),
    '.co.uk': ('UK', 'GBP'), '.com.au': ('Australia', 'AUD'),
    '.com.br': ('Brazil', 'BRL'), '.co.jp': ('Japan', 'JPY'),
    '.co.kr': ('South Korea', 'KRW'),
    '.ae': ('UAE', 'AED'), '.ca': ('Canada', 'CAD'),
    '.sg': ('Singapore', 'SGD'), '.fr': ('France', 'EUR'),
    '.de': ('Germany', 'EUR'),
    # NOTE: .com is NOT mapped here — it's ambiguous
}

CURRENCY_SYMBOLS = {
    'INR': r'[₹]', 'USD': r'\$', 'GBP': r'[£]', 'EUR': r'[€]',
    'AED': r'AED', 'AUD': r'A\$', 'CAD': r'C\$', 'SGD': r'S\$',
    'KRW': r'[₩]', 'JPY': r'[¥]', 'BRL': r'R\$',
}

# Layer 2: Currency symbol → country detection from page content
CURRENCY_SIGNAL_MAP = {
    '₹':  ('India', 'INR'),
    '£':  ('UK', 'GBP'),
    '€':  ('EU', 'EUR'),
    '¥':  ('Japan', 'JPY'),
    '₩':  ('South Korea', 'KRW'),
    'A$': ('Australia', 'AUD'),
    'C$': ('Canada', 'CAD'),
    'S$': ('Singapore', 'SGD'),
    'AED': ('UAE', 'AED'),
    'R$': ('Brazil', 'BRL'),
}

GARBAGE_TITLES = [
    'one moment', 'please wait', 'just a moment', 'checking your browser',
    'is blocked', 'access denied', 'captcha', 'are you a robot',
    'verify you are human', 'attention required', 'security check',
    'page not found', 'not found', '404', 'error page', 'sorry, page',
]

# Known Shopify stores (partial list - detection also uses meta tags)
KNOWN_SHOPIFY_DOMAINS = [
    # India
    'beaminimalist.com', 'foxtalecare.com', 'foxtale.in', 'dotandkey.com',
    'plumgoodness.com', 'mcaffeine.com', 'mamaearth.in', 'pilgrimbeauty.com',
    'thedermacompany.com', 'fixderma.com', 'purplle.com', 'juicychemistry.com',
    'wowskinscience.com', 'forestessentialsindia.com', 'kamaayurveda.com',
    'cosiq.in', 'reequil.com', 'minimalistskincare.com', 'consciouschemist.com',
    # International Shopify
    'cosrx.com', 'paulaschoice.com', 'adorebeauty.com.au',
]

# ─── Site-Specific Scraping Routing ──────────────────────────────────
# Maps domain → ordered list of scraper layers to try.
# 'shopify' = Shopify JSON API, 'cloud' = cloudscraper,
# 'firecrawl' = Firecrawl, 'scrapedo' = ScrapeDo, 'scraperapi' = ScraperAPI
SITE_ROUTING = {
    # India — custom (non-Shopify)
    'nykaa.com':          ['firecrawl', 'scrapedo'],
    'tirabeauty.com':     ['firecrawl', 'scrapedo'],
    'amazon.in':          ['scrapedo', 'scraperapi'],
    'purplle.com':        ['firecrawl', 'scrapedo'],
    'flipkart.com':       ['scrapedo', 'scraperapi'],
    'myntra.com':         ['firecrawl', 'scrapedo'],
    # India — Shopify
    'beaminimalist.com':  ['shopify', 'firecrawl'],
    'foxtalecare.com':    ['shopify', 'firecrawl'],
    'foxtale.in':         ['shopify', 'cloud', 'firecrawl'],
    'dotandkey.com':      ['shopify', 'firecrawl'],
    'plumgoodness.com':   ['shopify', 'firecrawl'],
    'mcaffeine.com':      ['shopify', 'firecrawl'],
    'mamaearth.in':       ['shopify', 'firecrawl'],
    'pilgrimbeauty.com':  ['shopify', 'firecrawl'],
    'thedermacompany.com':['shopify', 'firecrawl'],
    'fixderma.com':       ['shopify', 'firecrawl'],
    'juicychemistry.com': ['shopify', 'firecrawl'],
    'wowskinscience.com': ['shopify', 'firecrawl'],
    'forestessentialsindia.com': ['shopify', 'firecrawl'],
    'kamaayurveda.com':   ['shopify', 'firecrawl'],
    'cosiq.in':           ['shopify', 'firecrawl'],
    'reequil.com':        ['shopify', 'firecrawl'],
    # International — Shopify
    'cosrx.com':          ['shopify', 'firecrawl'],
    'paulaschoice.com':   ['shopify', 'firecrawl'],
    'adorebeauty.com.au': ['shopify', 'firecrawl'],
    # International — custom
    'amazon.com':         ['scrapedo', 'scraperapi'],
    'sephora.com':        ['scrapedo', 'scraperapi'],   # render=true
    'ulta.com':           ['firecrawl', 'scrapedo'],
    'theordinary.com':    ['firecrawl', 'scrapedo'],
    'boots.com':          ['scrapedo', 'scraperapi'],
    'lookfantastic.com':  ['firecrawl', 'scrapedo'],
    'cultbeauty.co.uk':   ['firecrawl', 'scrapedo'],
    'nysaa.com':          ['firecrawl', 'scrapedo'],
    'noon.com':           ['scrapedo', 'scraperapi'],   # render=true
    'oliveyoung.co.kr':   ['scrapedo', 'scraperapi'],
    'coupang.com':        ['scrapedo', 'scraperapi'],
    'lazada.sg':          ['scrapedo', 'scraperapi'],
}

# Layer 1: Known brand → country hardcoded lookup (most reliable)
KNOWN_BRAND_COUNTRIES = {
    # Indian brands on .com
    'consciouschemist.com': ('India', 'INR'), 'beaminimalist.com': ('India', 'INR'),
    'foxtalecare.com': ('India', 'INR'), 'mcaffeine.com': ('India', 'INR'),
    'mamaearth.in': ('India', 'INR'), 'plumgoodness.com': ('India', 'INR'),
    'pilgrimbeauty.com': ('India', 'INR'), 'thedermacompany.com': ('India', 'INR'),
    'dotandkey.com': ('India', 'INR'), 'fixderma.com': ('India', 'INR'),
    'juicychemistry.com': ('India', 'INR'), 'wowskinscience.com': ('India', 'INR'),
    'kamaayurveda.com': ('India', 'INR'), 'forestessentialsindia.com': ('India', 'INR'),
    'cosiq.in': ('India', 'INR'), 'reequil.com': ('India', 'INR'),
    'skinkraft.com': ('India', 'INR'), 'brillare.net': ('India', 'INR'),
    'lacto-calamine.com': ('India', 'INR'), 'biotique.com': ('India', 'INR'),
    'khadi.com': ('India', 'INR'), 'aqualogica.in': ('India', 'INR'),
    'drvclinic.com': ('India', 'INR'), 'strivertin.com': ('India', 'INR'),
    'nykaa.com': ('India', 'INR'), 'flipkart.com': ('India', 'INR'),
    'purplle.com': ('India', 'INR'), 'myntra.com': ('India', 'INR'),
    'tatacliq.com': ('India', 'INR'), '1mg.com': ('India', 'INR'),
    'tirabeauty.com': ('India', 'INR'),
    'foxtale.in': ('India', 'INR'), 'minimalistskincare.com': ('India', 'INR'),
    # Korean brands on .com
    'cosrx.com': ('South Korea', 'KRW'), 'innisfree.com': ('South Korea', 'KRW'),
    'some-by-mi.com': ('South Korea', 'KRW'), 'tonymoly.com': ('South Korea', 'KRW'),
    'missha.com': ('South Korea', 'KRW'), 'klairs.com': ('South Korea', 'KRW'),
    'isntree.com': ('South Korea', 'KRW'), 'purito.com': ('South Korea', 'KRW'),
    'anua.com': ('South Korea', 'KRW'),
    # French/EU brands on .com
    'loccitane.com': ('France', 'EUR'), 'vichy.com': ('France', 'EUR'),
    'laroche-posay.com': ('France', 'EUR'), 'loreal.com': ('France', 'EUR'),
    'garnier.com': ('France', 'EUR'),
    # UK brands on .com
    'theordinary.com': ('UK', 'GBP'), 'deciem.com': ('UK', 'GBP'),
    'revolutionbeauty.com': ('UK', 'GBP'),
    # Japanese brands on .com
    'shiseido.com': ('Japan', 'JPY'), 'skii.com': ('Japan', 'JPY'),
    # US brands (explicit)
    'cerave.com': ('USA', 'USD'), 'paulaschoice.com': ('USA', 'USD'),
    'tatcha.com': ('USA', 'USD'), 'olehenriksen.com': ('USA', 'USD'),
    'origins.com': ('USA', 'USD'), 'clinique.com': ('USA', 'USD'),
    'esteelauder.com': ('USA', 'USD'),
}


# ─── Utility Functions ───────────────────────────────────────────────

def _detect_country_from_url(url, page_content=None):
    """3-layer country detection: Brand lookup → TLD → Currency symbol on page."""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.replace('www.', '').lower() if url else ''

    # Layer 1: Known brand lookup (most reliable)
    if domain in KNOWN_BRAND_COUNTRIES:
        return KNOWN_BRAND_COUNTRIES[domain]

    # Layer 2: Unambiguous TLD (NOT .com)
    for tld, (country, currency) in TLD_COUNTRY_MAP.items():
        if domain.endswith(tld):
            return country, currency

    # Layer 3: Currency symbol detection from page content
    if page_content:
        snippet = page_content[:5000]
        for symbol, (country, currency) in CURRENCY_SIGNAL_MAP.items():
            if symbol in snippet:
                return country, currency

    # .com with no other signals — return None to flag as uncertain
    if domain.endswith('.com') or domain.endswith('.net') or domain.endswith('.org'):
        return None  # uncertain — ask user to confirm

    return 'USA', 'USD'


def _detect_category(text):
    if not text:
        return None
    text_lower = text.lower()
    for kw, cat in CATEGORY_KEYWORDS.items():
        if kw in text_lower:
            return cat
    return None


def _is_garbage(text):
    if not text:
        return True
    return any(g in text.lower() for g in GARBAGE_TITLES)


def _clean_product_name(name):
    if not name:
        return None
    for sep in [' | ', ' - ', ' – ', ' — ', ': Amazon', ' : Amazon']:
        if sep in name:
            name = name.split(sep)[0].strip()
    if len(name) > 150:
        name = name[:150].rsplit(' ', 1)[0]
    if _is_garbage(name):
        return None
    return name.strip() if name.strip() else None


def _extract_ingredients_from_body_html(body_html):
    """Extract INCI list from Shopify body_html field.
    Handles aqueous AND non-aqueous formulas (e.g. PDRN serums, oils, anhydrous products).
    """
    if not body_html:
        return None
    soup = BeautifulSoup(body_html, 'html.parser')
    plain = soup.get_text(separator=' ')

    # Strategy 1: After "Ingredients:" / "INCI:" label — any INCI content
    m = re.search(
        r'(?:all\s+)?(?:Ingredients?|INCI|Full\s+Ingredients?(?:\s*List)?)\s*[:\-]\s*'
        r'([A-Z][A-Za-z0-9\s,\(\)\-\.\/%]{40,2000})',
        plain, re.IGNORECASE
    )
    if m:
        candidate = m.group(1).strip()
        # Must look like an INCI list: has commas, not all marketing text
        if candidate.count(',') >= 3:
            return candidate

    # Strategy 2: Aqua/Water-led INCI block (aqueous formulas)
    m = re.search(
        r'((?:Aqua|Water)\s*[,/]\s*[A-Za-z][A-Za-z0-9\s,\(\)\-\.\/]{40,1500})',
        plain, re.IGNORECASE
    )
    if m:
        return m.group(1).strip()

    # Strategy 3: Non-aqueous INCI — common anhydrous first ingredients
    _ANHYDROUS_FIRST = (
        'pentylene glycol', 'glycerin', 'propanediol', 'butylene glycol',
        'caprylic', 'dimethicone', 'cyclopentasiloxane', 'squalane',
        'jojoba', 'rosehip', 'niacinamide', 'sodium hyaluronate',
    )
    for first_ing in _ANHYDROUS_FIRST:
        pat = re.compile(
            rf'(?i)({re.escape(first_ing)}[^.{{}}]{{30,1500}})',
        )
        m = pat.search(plain)
        if m and m.group(1).count(',') >= 3:
            return m.group(1).strip()

    return None


def _parse_size(text, product_name=None):
    """Extract size (value + unit) from text. Returns (float, str) or (None, 'ml')."""
    search_text = (product_name or '') + ' ' + (text or '')
    # Identify SPF token spans so we can skip size numbers that are the SPF value itself
    # e.g. "SPF50ml" or "SPF 50ml" — the 50 is the SPF value, not a product size
    # But "SPF50 60ml" or "Sunscreen SPF50 60ml" — 60ml is a separate real size
    _SPF_CONTEXT = re.compile(r'\bSPF\s*\d+', re.I)
    spf_spans = [(m.start(), m.end()) for m in _SPF_CONTEXT.finditer(search_text)]
    matches = list(re.finditer(
        r'(\d+\.?\d*)\s*(ml|g|fl\s*\.?\s*oz|oz)\b',
        search_text, re.IGNORECASE
    ))
    for m in matches:
        val = float(m.group(1))
        if not (5 <= val <= 1000):
            continue
        # Skip only if the size number's start position is strictly INSIDE an SPF token span
        # This catches "SPF50ml" and "SPF 50ml" but NOT "SPF50 60ml"
        if any(sp_start <= m.start() < sp_end for sp_start, sp_end in spf_spans):
            continue
        unit = m.group(2).lower().replace(' ', '').replace('.', '')
        if unit in ('oz', 'floz'):
            return val * 29.5735, 'ml'
        elif unit == 'g':
            return val, 'g'
        return val, 'ml'
    return None, 'ml'


def _score_result(result):
    """Score how complete a result is (0-8)."""
    s = 0
    if result.get('product_name'):
        s += 2
    if result.get('brand'):
        s += 1
    if result.get('price'):
        s += 1
    if result.get('ingredients'):
        s += 3
    if result.get('size_ml'):
        s += 1
    return s


def _merge_results(base, overlay):
    """Merge overlay into base, only filling in missing fields."""
    if not base:
        return overlay
    if not overlay:
        return base
    merged = dict(base)
    for key in ['product_name', 'brand', 'price', 'price_confidence', 'size_ml', 'size_unit',
                'ingredients', 'category', 'country', 'currency']:
        if not merged.get(key) and overlay.get(key):
            merged[key] = overlay[key]
    return merged


# ─── Layer 0: Shopify JSON API ───────────────────────────────────────

def _is_shopify_url(url):
    """Detect if URL is likely a Shopify store."""
    domain = url.lower().split('/')[2] if '//' in url else ''
    if any(d in domain for d in KNOWN_SHOPIFY_DOMAINS):
        return True
    if '/products/' in url.lower():
        return True
    return False


def _get_site_layers(url):
    """Return ordered list of scraper layers for a given URL."""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.replace('www.', '').lower()
    if domain in SITE_ROUTING:
        return SITE_ROUTING[domain]
    # Default waterfall
    if _is_shopify_url(url):
        return ['shopify', 'cloud', 'firecrawl', 'scrapedo', 'scraperapi']
    return ['cloud', 'firecrawl', 'scrapedo', 'scraperapi']



def _fetch_shopify_json(url):
    """Fetch product data from Shopify JSON API (free, no credits)."""
    try:
        clean_url = url.split('?')[0].rstrip('/')
        json_url = clean_url + '.json'

        time.sleep(random.uniform(0.3, 0.8))
        resp = __import__('requests').get(json_url, headers=BROWSER_HEADERS, timeout=12)

        if resp.status_code != 200:
            logger.info(f"Shopify JSON returned {resp.status_code} for {url}")
            return None

        product = resp.json().get('product', {})
        if not product:
            return None

        name = product.get('title', '').strip()
        brand = product.get('vendor', '').strip()

        # Price from first variant
        variants = product.get('variants', [{}])
        first_variant = variants[0] if variants else {}
        price_raw = first_variant.get('price', '0')
        price = float(price_raw) if price_raw else None

        # Size from variant title + weight
        variant_title = first_variant.get('title', '')
        size_ml, size_unit = _parse_size(variant_title, name)
        if not size_ml:
            weight = first_variant.get('weight')
            weight_unit = first_variant.get('weight_unit', 'g')
            if weight and weight_unit:
                wt = float(weight)
                if weight_unit.lower() in ('kg',):
                    size_ml, size_unit = wt * 1000, 'g'
                elif weight_unit.lower() in ('g',):
                    size_ml, size_unit = wt, 'g'
                elif weight_unit.lower() in ('oz', 'lb'):
                    size_ml, size_unit = wt * 29.5735, 'ml'

        country_result = _detect_country_from_url(url)
        if country_result:
            country, currency = country_result
        else:
            country, currency = None, None

        # Category
        product_type = product.get('product_type', '')
        tags = ' '.join(product.get('tags', []))
        category = _detect_category(f"{product_type} {name} {tags}")

        # Ingredients from body_html
        ingredients = _extract_ingredients_from_body_html(product.get('body_html', ''))

        logger.info(f"Shopify JSON: name={bool(name)}, brand={bool(brand)}, price={price}, "
                     f"size={size_ml}, ingredients={bool(ingredients)}")

        return {
            'product_name': name or None,
            'brand': brand or None,
            'price': price,
            'size_ml': size_ml,
            'size_unit': size_unit,
            'ingredients': ingredients,
            'category': category,
            'country': country,
            'currency': currency,
            'source': 'shopify_json',
        }
    except Exception as e:
        logger.info(f"Shopify JSON not available: {e}")
        return None


# ─── Layer 1: cloudscraper (free, Cloudflare bypass) ──────────────────

def _fetch_with_cloudscraper(url):
    """Use cloudscraper to bypass Cloudflare JS challenges."""
    try:
        import cloudscraper
        scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
        resp = scraper.get(url, timeout=20)
        if resp.status_code == 200 and len(resp.text) > 500:
            return resp.text
        return None
    except Exception as e:
        logger.warning(f"cloudscraper failed: {e}")
        return None


# ─── Layer 2: Firecrawl API ──────────────────────────────────────────

async def _fetch_html_firecrawl(url, timeout=25):
    api_key = os.environ.get('FIRECRAWL_API_KEY', '')
    if not api_key:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}
            async with session.post(
                'https://api.firecrawl.dev/v1/scrape',
                json={'url': url, 'formats': ['html', 'markdown'], 'waitFor': 3000},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                html = data.get('data', {}).get('html', '')
                markdown = data.get('data', {}).get('markdown', '')
                if markdown and html:
                    html = html + f'<!-- MARKDOWN_CONTENT: {markdown} -->'
                return html or markdown
    except Exception as e:
        logger.warning(f"Firecrawl failed: {e}")
        return None


# ─── Layer 3: ScrapeDo API ───────────────────────────────────────────

async def _fetch_html_scrapdo(url, timeout=25):
    api_key = os.environ.get('SCRAPDO_API_KEY', '')
    if not api_key:
        return None
    try:
        import urllib.parse
        encoded = urllib.parse.quote_plus(url)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.scrape.do/?token={api_key}&url={encoded}&render=true",
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.text()
    except Exception as e:
        logger.warning(f"Scrapdo failed: {e}")
        return None


# ─── Layer 4: ScraperAPI (premium) ────────────────────────────────────

async def _fetch_html_scraperapi(url, timeout=25):
    api_key = os.environ.get('SCRAPERAPI_KEY', '')
    if not api_key:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                'http://api.scraperapi.com',
                params={'api_key': api_key, 'url': url, 'render': 'true'},
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"ScraperAPI returned {resp.status}")
                    return None
                return await resp.text()
    except Exception as e:
        logger.warning(f"ScraperAPI failed: {e}")
        return None


# ─── HTML Metadata Extraction ─────────────────────────────────────────

def _extract_metadata(html, url):
    """Extract product metadata from raw HTML page."""
    soup = BeautifulSoup(html, 'lxml')
    text = soup.get_text(' ', strip=True)
    country_result = _detect_country_from_url(url, text)
    country_uncertain = country_result is None
    if country_result:
        country, currency = country_result
    else:
        country, currency = None, None

    # --- Product Name ---
    product_name = None
    for script_tag in soup.find_all('script', type='application/ld+json'):
        try:
            ld = json.loads(script_tag.string)
            items = ld if isinstance(ld, list) else [ld]
            for item in items:
                if item.get('@type') in ('Product', 'IndividualProduct'):
                    product_name = item.get('name', '').strip()
                    break
                for g in item.get('@graph', []):
                    if g.get('@type') in ('Product', 'IndividualProduct'):
                        product_name = g.get('name', '').strip()
                        break
        except Exception:
            pass

    if not product_name:
        og = soup.find('meta', property='og:title')
        if og and og.get('content'):
            product_name = og['content'].strip()
    if not product_name:
        pt = soup.find(id='productTitle')
        if pt:
            product_name = pt.get_text().strip()
    if not product_name:
        h1 = soup.find('h1')
        if h1:
            product_name = h1.get_text().strip()
    if not product_name:
        t = soup.find('title')
        if t:
            product_name = t.get_text().strip()

    product_name = _clean_product_name(product_name)

    # --- Brand ---
    brand = None
    for script_tag in soup.find_all('script', type='application/ld+json'):
        try:
            ld = json.loads(script_tag.string)
            items = ld if isinstance(ld, list) else [ld]
            for item in items:
                b = item.get('brand', {})
                brand = (b.get('name', '') if isinstance(b, dict) else str(b)).strip()
                if brand:
                    break
        except Exception:
            pass
    if not brand:
        og_b = soup.find('meta', property='product:brand')
        if og_b and og_b.get('content'):
            brand = og_b['content'].strip()
    if not brand:
        bl = soup.find(id='bylineInfo')
        if bl:
            brand = bl.get_text().strip().replace('Visit the ', '').replace(' Store', '').replace('Brand: ', '')
    if not brand:
        for tag in soup.find_all(['span', 'a', 'div']):
            if tag.get('itemprop') == 'brand':
                brand = tag.get_text().strip()
                break

    # --- Price ---
    price = None
    price_confidence = "low"

    # Priority 1: JSON-LD structured data (most reliable)
    # Collect ALL price candidates, then pick highest — discount/cashback amounts
    # are always smaller than the real product price.
    _jsonld_candidates = []
    for script_tag in soup.find_all('script', type='application/ld+json'):
        try:
            ld = json.loads(script_tag.string)
            items = ld if isinstance(ld, list) else [ld]
            for item in items:
                graph = item.get('@graph', [])
                candidates = [item] + graph
                for candidate in candidates:
                    # Only accept explicitly typed Product/IndividualProduct nodes
                    c_type = candidate.get('@type', '')
                    if c_type and c_type not in ('Product', 'IndividualProduct'):
                        continue
                    offers = candidate.get('offers', candidate)
                    offer_list = offers if isinstance(offers, list) else [offers]
                    for offer in offer_list:
                        if not isinstance(offer, dict):
                            continue
                        p = offer.get('price') or offer.get('highPrice')
                        if p:
                            try:
                                val = float(str(p).replace(',', ''))
                                if val > 0:
                                    _jsonld_candidates.append(val)
                            except (ValueError, TypeError):
                                pass
        except Exception:
            pass
    if _jsonld_candidates:
        # Use the highest price — real price is always > any discount/cashback amount
        price = max(_jsonld_candidates)
        price_confidence = "high"

    # Priority 2: Structured HTML price selectors (medium confidence)
    if not price:
        price_selectors = [
            # Amazon
            {'id': 'priceblock_ourprice'}, {'id': 'priceblock_dealprice'},
            {'id': 'price_inside_buybox'}, {'id': 'apex_offerDisplay_desktop'},
            {'class': 'a-price-whole'},
            # Nykaa
            {'class': 'css-1jczs19'}, {'class': 'price-box'},
            {'class': 'final-price'}, {'class': 'selling-price'},
            # Tira Beauty (Reliance React platform)
            {'data-testid': 'selling-price'}, {'data-testid': 'product-price'},
            {'class': re.compile(r'wt-text-base-max|sellingPrice|product.*price|price.*value', re.I)},
            # Generic structured selectors
            {'itemprop': 'price'},
            {'class': re.compile(r'sale.?price|selling.?price|offer.?price|current.?price|final.?price', re.I)},
            {'id': re.compile(r'sale.?price|selling.?price|offer.?price|current.?price', re.I)},
        ]
        sym = CURRENCY_SYMBOLS.get(currency, r'[\$₹£€]')
        for sel in price_selectors:
            el = soup.find(attrs=sel) if not any(isinstance(v, re.Pattern) for v in sel.values()) else soup.find(True, attrs=sel)
            if el:
                raw = el.get('content') or el.get('data-price') or el.get_text(strip=True)
                raw = re.sub(r'[^\d.,]', '', raw)
                try:
                    p = float(raw.replace(',', ''))
                    if 0 < p < 500000:
                        price = p
                        price_confidence = "medium"
                        break
                except (ValueError, TypeError):
                    pass

    # Priority 3: Regex on page text (low confidence)
    if not price:
        sym = CURRENCY_SYMBOLS.get(currency, r'[\$₹£€]')
        # Collect ALL price candidates from page — avoid picking up discounts/savings first
        price_candidates = []
        # Pattern A: Tightly anchored to price-keyword context — highest priority
        kw_pat = re.compile(
            r'(?:selling\s+price|current\s+price|offer\s+price|special\s+price|deal\s+price|you\s+pay|buy\s+(?:now\s+)?(?:at|for)?)\s*[:\-]?\s*'
            + sym + r'\s*([\d,]+\.?\d*)', re.I)
        for m in kw_pat.finditer(text[:12000]):
            try:
                p = float(m.group(1).replace(',', ''))
                if 10 < p < 200000:
                    price_candidates.append((p, 0))  # priority 0 = highest
            except ValueError:
                pass

        # Pattern B: MRP/price label
        mrp_pat = re.compile(r'(?:mrp|price|cost)\s*[:\-]?\s*' + sym + r'\s*([\d,]+\.?\d*)', re.I)
        for m in mrp_pat.finditer(text[:12000]):
            try:
                p = float(m.group(1).replace(',', ''))
                if 10 < p < 200000:
                    price_candidates.append((p, 1))
            except ValueError:
                pass

        # Pattern C: Bare currency symbol — lowest priority, skip "save/off" context
        bare_pat = re.compile(sym + r'\s*([\d,]+\.?\d*)', re.I)
        # Negative context: amounts preceded by save/off/discount
        negative_ctx = re.compile(r'(?:save|off|discount(?:ed)?|cashback|points?|earn|get)\s*' + sym + r'\s*([\d,]+)', re.I)
        negative_amounts = set()
        for m in negative_ctx.finditer(text[:12000]):
            try:
                negative_amounts.add(float(m.group(1).replace(',', '')))
            except ValueError:
                pass
        for m in bare_pat.finditer(text[:12000]):
            try:
                p = float(m.group(1).replace(',', ''))
                if 10 < p < 200000 and p not in negative_amounts:
                    price_candidates.append((p, 2))
            except ValueError:
                pass

        if price_candidates:
            # Sort: prefer lower priority number (more specific context), then higher price
            # Discount/savings/cashback amounts are always smaller than actual product price.
            price_candidates.sort(key=lambda x: (x[1], -x[0]))
            price = price_candidates[0][0]
            price_confidence = "low"
            # Extra guard: if chosen price is implausibly low and a much higher candidate exists,
            # prefer the highest priority-0 or priority-1 candidate.
            best_p0 = max((p for p, pri in price_candidates if pri == 0), default=None)
            best_p1 = max((p for p, pri in price_candidates if pri <= 1), default=None)
            if best_p0 and best_p0 > price * 3:
                price = best_p0
                price_confidence = "medium"
            elif best_p1 and best_p1 > price * 3:
                price = best_p1

    # --- Size ---
    # Build a rich search string from all possible size-bearing locations:
    # product name, og:title, meta description, JSON-LD variant titles, variant selectors
    og_title_el = soup.find('meta', property='og:title')
    og_title_str = og_title_el['content'] if og_title_el and og_title_el.get('content') else ''
    meta_desc_el = soup.find('meta', attrs={'name': 'description'})
    meta_desc_str = meta_desc_el['content'] if meta_desc_el and meta_desc_el.get('content') else ''

    # Pull variant/option text from common size-picker elements
    variant_texts = []
    for el in soup.find_all(True, attrs={
        'class': re.compile(r'variant|size|volume|option|quantity|sku', re.I)
    }):
        t = el.get_text(strip=True)
        if t and len(t) <= 30:
            variant_texts.append(t)

    size_search_text = ' '.join(filter(None, [
        product_name, og_title_str, meta_desc_str,
        ' '.join(variant_texts[:10]),
        text[:5000]
    ]))
    size_ml, size_unit = _parse_size(size_search_text, product_name)

    # --- Ingredients ---
    ingredients = None

    # Pre-clean: remove "Read more" / "Show more" / "View more" button text from soup
    _UI_TAIL_RE = re.compile(r'\b(read\s*more|show\s*more|view\s*more|see\s*more|load\s*more)\b', re.I)
    for btn in soup.find_all(['button', 'a', 'span', 'div']):
        if _UI_TAIL_RE.search(btn.get_text(strip=True)):
            btn.decompose()

    # Re-extract text after cleaning
    text_clean = soup.get_text(' ', strip=True)

    # Strategy 1: Section markers — ordered from most to least specific.
    # Negative lookbehind prevents matching "Key Ingredients:", "Hero Ingredients:" etc.
    # Those sections contain marketing text, not INCI lists.
    _MKTG_ADJECTIVE = re.compile(
        r'(?:key|hero|star|active|main|featured|highlight|top|signature|power|hero(?:ine)?|why)\s+ingredients?\s*[:\-]',
        re.I
    )
    inci_patterns = [
        # Most explicit — "All Ingredients:", "Full Ingredients:", "Complete Ingredients:"
        re.compile(r'(?:all|full|complete|total)\s+ingredients?\s*[:\-]\s*', re.I),
        # INCI label
        re.compile(r'\bINCI\s*[:\-]\s*', re.I),
        # Bare "Ingredients:" — but ONLY if not preceded by marketing adjectives
        re.compile(r'(?<!key\s)(?<!hero\s)(?<!star\s)(?<!main\s)(?<!active\s)(?<!featured\s)\bingredients?\s*[:\-]\s*', re.I),
        re.compile(r'composition\s*[:\-]\s*', re.I),
    ]

    # Helper: detect if text looks like marketing descriptions instead of INCI
    def _is_marketing_description(text):
        """Return True if text looks like 'Ingredient : does X' marketing copy, not INCI list."""
        _MARKETING_VERBS = re.compile(
            r'\b(brighten|moisturi[sz]|protect|reduce|smooth|hydrat|repair|nourish|sooth|firm|tone|revitaliz|rejuvenat|stimulat|boost|energi[sz]|defend|restore|strengthen|reviv|calm|heal)\b',
            re.I
        )
        # Check comma-separated format ("Ing1, Ing2 : does X, Ing3")
        segs = text.split(',')
        if len(segs) >= 3:
            desc_count = sum(
                1 for s in segs
                if ':' in s and re.search(r':\s*\w.{5,}', s)
            )
            if desc_count / len(segs) > 0.3:
                return True

        # Check newline/bullet format ("Vitamin C : Brightens\nYerba mate : Reduces...")
        # Each line has pattern "IngredientName : marketing sentence"
        lines = [l.strip() for l in re.split(r'[\n\r]+', text) if l.strip()]
        if len(lines) >= 2:
            desc_lines = sum(
                1 for l in lines
                if ':' in l and _MARKETING_VERBS.search(l.split(':', 1)[-1])
            )
            if desc_lines >= 2 or (len(lines) > 0 and desc_lines / len(lines) > 0.4):
                return True

        # Check if overall text has many marketing verbs relative to its length
        # (catches cases like "Vitamin C Brightens skin. Caffeine reduces puffiness.")
        word_count = len(text.split())
        verb_hits = len(_MARKETING_VERBS.findall(text))
        if word_count > 10 and verb_hits / max(1, word_count) > 0.05:
            return True

        return False

    for pat in inci_patterns:
        m = pat.search(text_clean)
        if m:
            # Extra guard: skip if the matched heading is a marketing adjective form
            match_text = text_clean[max(0, m.start()-30):m.end()]
            if _MKTG_ADJECTIVE.search(match_text):
                continue
            after = text_clean[m.end():m.end() + 3000]
            # Strip any trailing UI text
            after = _UI_TAIL_RE.sub('', after).strip()
            # Trim at the next section heading
            section_break = re.search(
                r'\n\s*(?:how to use|directions|warnings?|disclaimer|storage|about the brand|why you|key benefit)',
                after, re.I
            )
            if section_break:
                after = after[:section_break.start()]
            # Accept comma-list — does NOT require Aqua/Water (handles anhydrous products)
            cb = re.match(r'([^.]{10,}(?:,\s*[^.,]{2,}){3,})', after)
            if cb:
                candidate = cb.group(1).strip()
                # Must have enough commas to be an INCI list
                if candidate.count(',') >= 3 and not _is_marketing_description(candidate):
                    ingredients = candidate
                    break

    # Strategy 2: Aqua/Water pattern
    if not ingredients:
        wm = re.search(r'((?:Aqua|Water)(?:/[^,]*)?[^.]*(?:,\s*[\w\s\-\(\)\/]+){4,})', text_clean)
        if wm:
            ingredients = wm.group(1).strip()

    # Strategy 3: Long comma lists in HTML elements
    if not ingredients:
        for el in soup.find_all(['div', 'p', 'span', 'td', 'li']):
            el_text = el.get_text(' ', strip=True)
            # Skip elements that are clearly UI / navigation
            if _UI_TAIL_RE.search(el_text):
                continue
            if len(el_text) > 50 and el_text.count(',') >= 8:
                words = el_text.split(',')
                if any(w.strip().lower() in ('aqua', 'water', 'glycerin', 'dimethicone', 'niacinamide') for w in words[:5]):
                    # Reject marketing description blocks
                    if not _is_marketing_description(el_text):
                        ingredients = el_text.strip()
                        break

    # Strategy 4: Amazon ingredient section
    if not ingredients:
        ing_s = soup.find(attrs={'id': re.compile(r'ingredient', re.I)})
        if ing_s:
            ing_t = ing_s.get_text(' ', strip=True)
            if len(ing_t) > 20:
                ingredients = ing_t

    # Strategy 5: "All Ingredients:" label (used by Tira, COSRX, etc.)
    if not ingredients:
        all_ing_pat = re.compile(r'(?:all\s+)?ingredients?\s*(?:list)?\s*[:\-]\s*', re.I)
        m5 = all_ing_pat.search(text_clean)
        if m5:
            after5 = text_clean[m5.end():m5.end() + 3000]
            after5 = _UI_TAIL_RE.sub('', after5).strip()
            cb5 = re.match(r'([^.]{20,}(?:,\s*[^.]{2,}){4,})', after5)
            if cb5:
                candidate5 = cb5.group(1).strip()
                if not _is_marketing_description(candidate5):
                    ingredients = candidate5

    # Strategy 6: Table-based ingredient pages (e.g. Dot & Key, Foxtale style)
    # Pattern A: Proper <table> with header row containing "Ingredient"
    if not ingredients:
        for tbl in soup.find_all('table'):
            rows = tbl.find_all('tr')
            if len(rows) < 4:
                continue
            header_cells = [td.get_text(strip=True).lower() for td in rows[0].find_all(['th', 'td'])]
            if not any('ingredient' in h for h in header_cells):
                continue
            # Find the column that holds the INCI name (first column matching "ingredient")
            ing_col = next((i for i, h in enumerate(header_cells) if 'ingredient' in h), 0)
            names = []
            for row in rows[1:]:
                cells = row.find_all(['td', 'th'])
                if len(cells) > ing_col:
                    name = cells[ing_col].get_text(strip=True)
                    if name and 2 < len(name) <= 80 and name.lower() not in ('ingredient', 'ingredients', 'inci'):
                        names.append(name)
            if len(names) >= 4:
                ingredients = ', '.join(names)
                break

    # Strategy 7: Div/span grid layout — detect "Synthetic/Natural/Lab Synthesized" noise
    # pattern in direct children of a container, extract only the ingredient name children.
    if not ingredients:
        _GRID_NOISE_FULL = re.compile(
            r'^(synthetic|natural|lab\s+synthesized|plant|mineral|animal|marine|water'
            r'|ingredient\s+type|source|benefit|ingredient)$',
            re.I
        )
        _GRID_BENEFIT = re.compile(
            r'\b(brightens?|moisturi[sz]|moisturizer|reduces?|exfoliat|repairs?|nourish'
            r'|soothes?|hydrat|antioxidant|anti[\-\s]aging|anti[\-\s]inflammatory'
            r'|humectant|emollient|preservative|thickener|stabilizer|chelating'
            r'|conditioning|antimicrobial|brightening|diluent|solvent|emulsifier'
            r'|pH\s+adjuster|penetration)\b',
            re.I
        )
        for container in soup.find_all(['div', 'ul', 'section'], recursive=True):
            children = [c for c in container.children
                        if hasattr(c, 'get_text') and c.get_text(strip=True)]
            if len(children) < 8:
                continue
            child_texts = [c.get_text(strip=True) for c in children]
            noise_count = sum(1 for t in child_texts if _GRID_NOISE_FULL.match(t))
            if noise_count < 4:
                continue
            names = []
            for t in child_texts:
                if _GRID_NOISE_FULL.match(t):
                    continue
                if _GRID_BENEFIT.search(t):
                    continue
                if len(t) > 80 or len(t) < 2:
                    continue
                if re.match(r'^[A-Za-z0-9]', t):
                    names.append(t)
            if len(names) >= 6:
                ingredients = ', '.join(names)
                break

    # --- Brand (additional fallbacks for sites missing JSON-LD/meta) ---
    if not brand:
        og_site = soup.find('meta', property='og:site_name')
        if og_site and og_site.get('content'):
            candidate = og_site['content'].strip()
            if candidate and len(candidate) <= 40 and 'skincare' not in candidate.lower():
                brand = candidate
    if not brand:
        for sel in [{'class': re.compile(r'brand[-_]?name|product[-_]?brand|vendor', re.I)},
                    {'id': re.compile(r'brand[-_]?name|product[-_]?brand', re.I)}]:
            el = soup.find(True, attrs=sel)
            if el:
                candidate = el.get_text(strip=True)
                if candidate and len(candidate) <= 50:
                    brand = candidate
                    break
    if not brand and product_name:
        _GENERIC_STARTS = {'the', 'a', 'an', 'new', 'best', 'pure', 'natural', 'organic', 'advanced'}
        first_word = product_name.split()[0] if product_name.split() else ''
        if first_word and first_word[0].isupper() and first_word.lower() not in _GENERIC_STARTS and len(first_word) >= 3:
            brand = first_word

    # Clean ingredients
    if ingredients:
        ingredients = re.sub(r'^(?:Ingredients|INCI|Composition)\s*[:\-]\s*', '', ingredients, flags=re.I)
        ingredients = re.sub(r'\s*(?:How to use|Directions|Warning|Disclaimer|Storage).*$', '', ingredients, flags=re.I)
        ingredients = _UI_TAIL_RE.sub('', ingredients).strip().rstrip(',').strip()

        # ── Post-processor: two-step table-dump cleaner ────────────────────────
        # Fires when the extracted text still contains table metadata words mixed
        # in with ingredient names (happens when HTML structure is already lost
        # and the text_clean path was used instead of the soup-based strategies).
        #
        # Format: "Aqua Natural Water Diluent & Solvent Niacinamide Synthetic Lab Synthesized ..."
        # Each entry is: [NAME] [Synthetic|Natural] [Lab Synthesized|Plant|Water] [benefit text]
        #
        # Algorithm:
        #   Step 1: Remove header row junk.
        #   Step 2: Replace the TYPE+SOURCE columns ("Synthetic Lab Synthesized" etc.) with "|".
        #   Step 3: Each fragment between "|" has the ingredient name at its TAIL and
        #           benefit text at its HEAD. Walk backwards past benefit words to get the name.
        _TABLE_MARKER_RE = re.compile(r'\b(synthetic|lab\s+synthesized|natural|plant)\b', re.I)
        if len(_TABLE_MARKER_RE.findall(ingredients)) >= 4:
            # Step 1: strip header row
            cleaned = re.sub(
                r'^.*?(?:Ingredient\s+Type\s+Source\s+Benefit|Key\s+Ingredients.*?Benefit)\s*',
                '', ingredients, flags=re.I | re.DOTALL
            ).strip()
            # Step 2: replace TYPE+SOURCE with separator
            cleaned = re.sub(
                r'\b(Synthetic|Natural)\s+(Lab\s+Synthesized|Plant|Water|Mineral|Animal|Marine)\b',
                ' | ', cleaned, flags=re.I
            )
            # Step 3: extract name from tail of each fragment
            _BENEFIT_STOP = re.compile(
                r'^(Brightens?|Moisturi[sz]|Moisturizer|Reduces?|Exfoliat|Repairs?'
                r'|Nourish|Soothes?|Hydrat|Antioxidant|Improves?|Retains?|Conditions?'
                r'|Helps|Anti|Humectant|Emollient|Emulsifier|Preservative|Thickener'
                r'|Diluent|Solvent|Stabilizer|Chelating|Antimicrobial|pH|Adjuster'
                r'|Penetration|Brightening|Hydrator|Enhances?|Rich|Fungal|Microbial'
                r'|Aging|Conditioning)\b',
                re.I
            )
            _STOP_SINGLE = {
                '&', 'Clear', 'Pores', 'Tone', 'Skin', 'Moisture', 'Barrier',
                'Aging', 'Repair', 'Irritation', 'Pigmentation', 'Puffiness',
            }
            parts = cleaned.split(' | ')
            extracted = []
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                words = part.split()
                name_words = []
                for w in reversed(words):
                    if _BENEFIT_STOP.match(w) or w in _STOP_SINGLE:
                        break
                    name_words.insert(0, w)
                name = ' '.join(name_words).strip().strip('&.,; ')
                if (name and 2 <= len(name) <= 80
                        and re.match(r'^[A-Za-z0-9]', name)
                        and not _BENEFIT_STOP.match(name.split()[0])):
                    extracted.append(name)
            if len(extracted) >= 4:
                seen = set()
                deduped = []
                for n in extracted:
                    if n.lower() not in seen:
                        seen.add(n.lower())
                        deduped.append(n)
                ingredients = ', '.join(deduped)

        if len(ingredients) > 3000:
            ingredients = ingredients[:3000]

    # --- Active Concentrations ---
    # Search for "X% ingredient" patterns, preferring the ingredients/description region.
    # Stop-word filtering prevents promo language like "30% off" from being captured.
    active_concentrations = {}

    _CONC_STOP_WORDS = {
        'off', 'discount', 'cashback', 'save', 'savings', 'offer', 'deal', 'mrp',
        'price', 'ml', 'g', 'spf', 'pa', 'uv', 'sale', 'flat', 'extra', 'more',
        'free', 'buy', 'get', 'earn', 'points', 'reward', 'tax', 'gst', 'vat',
    }

    def _normalize_conc_name(raw_name):
        """Normalize a scraped concentration name to match parsed ingredient tokens.
        Strips parenthetical descriptors and lowercases — same logic as parse_ingredients().
        """
        name = raw_name.strip()
        # Strip parenthetical descriptors: "(Vitamin B3)", "(Provitamin B5)", etc.
        name = re.sub(r'\([^)]*\)', '', name).strip()
        # Strip trailing/leading punctuation
        name = name.strip('.-/ ')
        # Lowercase
        return name.lower()

    def _is_valid_conc_name(name_clean):
        """Return True only if the name looks like a real cosmetic ingredient."""
        if not name_clean or len(name_clean) <= 2:
            return False
        if name_clean[0].isdigit():
            return False
        # Reject pure numbers
        if re.match(r'^[\d\.\s]+$', name_clean):
            return False
        # Reject single-word stop words
        parts = name_clean.split()
        if all(p in _CONC_STOP_WORDS for p in parts):
            return False
        # Reject if first word is a stop word (catches "off season", "discount code", etc.)
        if parts and parts[0] in _CONC_STOP_WORDS:
            return False
        return True

    _conc_patterns = [
        # "10% Niacinamide" or "10 % niacinamide"
        re.compile(r'([\d]+\.?\d*)\s*%\s+([a-zA-Z][a-zA-Z0-9 \-\/\(\)]{2,40}?)(?=\s*[,\.\|+&\n<]|$)', re.I),
        # "Niacinamide 10%" or "Niacinamide (10%)"
        re.compile(r'([a-zA-Z][a-zA-Z0-9 \-\/\(\)]{2,40}?)\s+\(?(\d+\.?\d*)\s*%\)?', re.I),
    ]

    # Priority regions: prefer ingredients/description section text; fall back to full text.
    # Concentrations in the ingredient/description region are more trustworthy than promo banners.
    _PRIO_REGION_RE = re.compile(
        r'(?:ingredients?|inci|composition|key\s+ingredients?|active\s+ingredients?'
        r'|hero\s+ingredient|description|why\s+you|product\s+detail|about\s+(?:the\s+)?product)'
        r'\s*[:\-]?\s*(.{20,2000})',
        re.I | re.DOTALL
    )
    priority_text = ''
    pm = _PRIO_REGION_RE.search(text)
    if pm:
        priority_text = pm.group(1)[:2000]

    def _extract_concs_from_region(region_text, priority):
        """Extract concentration matches from a text region.
        priority=0 means high-trust (ingredient section), priority=1 means low-trust (full text).
        Lower priority number wins when merging.
        """
        results = {}
        for pat in _conc_patterns:
            for m in pat.finditer(region_text):
                g = m.groups()
                try:
                    if g[0][0].isdigit():
                        pct, raw_name = float(g[0]), g[1]
                    else:
                        raw_name, pct = g[0], float(g[1])
                    if not (0 < pct <= 60):
                        continue
                    norm = _normalize_conc_name(raw_name)
                    if not _is_valid_conc_name(norm):
                        continue
                    # Handle "Alpha Arbutin + Kojic Acid" combined names — split on +
                    sub_names = [s.strip() for s in re.split(r'\s*\+\s*', norm)]
                    for sub in sub_names:
                        sub_clean = _normalize_conc_name(sub)
                        if _is_valid_conc_name(sub_clean):
                            existing_priority, _ = results.get(sub_clean, (99, 0))
                            if priority < existing_priority:
                                results[sub_clean] = (priority, pct)
                except (ValueError, IndexError):
                    pass
        return results

    # Merge: priority region first (trust=0), then full page text (trust=1)
    conc_with_priority = {}
    if priority_text:
        for k, v in _extract_concs_from_region(priority_text, 0).items():
            conc_with_priority[k] = v
    for k, v in _extract_concs_from_region(text, 1).items():
        existing_priority = conc_with_priority.get(k, (99, 0))[0]
        if v[0] < existing_priority:
            conc_with_priority[k] = v

    active_concentrations = {k: v[1] for k, v in conc_with_priority.items()}

    # --- Category ---
    category = _detect_category(product_name or '') or _detect_category(text[:500])

    return {
        'product_name': product_name,
        'brand': brand,
        'price': price,
        'price_confidence': price_confidence,
        'size_ml': size_ml,
        'size_unit': size_unit,
        'ingredients': ingredients,
        'category': category,
        'country': country,
        'currency': currency,
        'country_uncertain': country_uncertain,
        'active_concentrations': active_concentrations,  # e.g. {'niacinamide': 10.0, 'retinol': 0.3}
    }


# ─── Main Fetch Orchestrator ─────────────────────────────────────────

async def fetch_product_data(url, timeout=25):
    """
    Site-specific routing waterfall with smart merging.
    Each domain has a pre-defined ordered list of scrapers from SITE_ROUTING.
    Layers: shopify, cloud, firecrawl, scrapedo, scraperapi
    """
    import time as _time
    from urllib.parse import urlparse
    try:
        from admin_db import log_fetch, increment_credits
    except Exception:
        log_fetch = lambda *a, **k: None
        increment_credits = lambda *a, **k: None

    domain = urlparse(url).netloc.replace('www.', '') if url else ''
    ALL_FIELDS = ['product_name', 'brand', 'price', 'size_ml', 'ingredients', 'category', 'country']
    partial_data = None
    loop = asyncio.get_event_loop()

    def _log(layer, result, t0, error=None):
        elapsed = round((_time.time() - t0) * 1000)
        if result:
            fetched = [f for f in ALL_FIELDS if result.get(f)]
            missing = [f for f in ALL_FIELDS if not result.get(f)]
            log_fetch(domain, url, layer, True, fetched, missing, elapsed)
        else:
            log_fetch(domain, url, layer, False, [], ALL_FIELDS, elapsed, error)

    def _is_full(r):
        return r and r.get('ingredients') and r.get('product_name')

    def _try_merge(base, overlay, layer_name):
        merged = _merge_results(base, overlay)
        src = f"{base.get('source', '')}+{layer_name}" if base and base.get('source') else layer_name
        merged['source'] = src
        return merged

    layers = _get_site_layers(url)
    credit_map = {'firecrawl': ('firecrawl', 1), 'scrapedo': ('scrapdo', 5), 'scraperapi': ('scraperapi', 10)}
    api_fetchers = {
        'firecrawl': _fetch_html_firecrawl,
        'scrapedo': _fetch_html_scrapdo,
        'scraperapi': _fetch_html_scraperapi,
    }

    for layer in layers:
        t0 = _time.time()

        # ── Shopify JSON ──
        if layer == 'shopify':
            shopify = _fetch_shopify_json(url)
            if shopify:
                _log('Shopify JSON', shopify, t0)
                if _is_full(shopify):
                    shopify['source'] = 'shopify_json'
                    logger.info(f"Shopify JSON fully resolved: {url}")
                    return shopify
                partial_data = _merge_results(partial_data, shopify)
                logger.info(f"Shopify JSON partial: {url}")
            else:
                _log('Shopify JSON', None, t0, 'Blocked or not Shopify')
            continue

        # ── cloudscraper ──
        if layer == 'cloud':
            try:
                cs_html = await asyncio.wait_for(
                    loop.run_in_executor(None, _fetch_with_cloudscraper, url), timeout=22)
                if cs_html and len(cs_html) > 500:
                    result = _extract_metadata(cs_html, url)
                    if not _is_garbage(result.get('product_name', '')):
                        _log('cloudscraper', result, t0)
                        if _is_full(result):
                            merged = _try_merge(partial_data, result, 'cloudscraper')
                            logger.info(f"cloudscraper fully resolved: {url}")
                            return merged
                        if _score_result(result) >= 2:
                            partial_data = _merge_results(partial_data, result)
                    else:
                        _log('cloudscraper', None, t0, 'Garbage/bot-blocked')
                else:
                    _log('cloudscraper', None, t0, 'Empty response')
            except Exception as e:
                _log('cloudscraper', None, t0, str(e)[:200])
            continue

        # ── API scrapers (firecrawl, scrapedo, scraperapi) ──
        if layer in api_fetchers:
            t_limit = 30 if layer == 'scraperapi' else timeout
            try:
                html = await api_fetchers[layer](url, t_limit)
                api_name, credits = credit_map[layer]
                increment_credits(api_name, credits)
                if html and len(html) > 500:
                    result = _extract_metadata(html, url)
                    if _is_garbage(result.get('product_name', '')):
                        _log(layer, None, t0, 'Garbage page')
                        continue
                    _log(layer, result, t0)
                    if _is_full(result):
                        merged = _try_merge(partial_data, result, layer)
                        logger.info(f"{layer} fully resolved: {url}")
                        return merged
                    if _score_result(result) >= 2:
                        partial_data = _merge_results(partial_data, result)
                        logger.info(f"{layer} partial (score {_score_result(partial_data)}/8): {url}")
                else:
                    _log(layer, None, t0, 'Empty response')
            except Exception as e:
                _log(layer, None, t0, str(e)[:200])
                logger.info(f"{layer} failed: {e}")

    # Return best partial or None
    if partial_data and _score_result(partial_data) >= 2:
        logger.info(f"Returning best partial result (score {_score_result(partial_data)}/8): {url}")
        return partial_data

    logger.warning(f"All scrapers failed for {url}")
    return None


async def fetch_multiple_products(urls, timeout=25):
    tasks = [fetch_product_data(url, timeout) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r if not isinstance(r, Exception) else None for r in results]

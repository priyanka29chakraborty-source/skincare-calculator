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
    'amazon.in':          ['scrapedo', 'scraperapi'],
    'purplle.com':        ['firecrawl', 'scrapedo'],
    'flipkart.com':       ['scrapedo', 'scraperapi'],
    'myntra.com':         ['firecrawl', 'scrapedo'],
    # India — Shopify
    'beaminimalist.com':  ['shopify', 'firecrawl'],
    'foxtalecare.com':    ['shopify', 'firecrawl'],
    'foxtale.in':         ['shopify', 'firecrawl'],
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
    """Extract INCI list from Shopify body_html field."""
    if not body_html:
        return None
    soup = BeautifulSoup(body_html, 'html.parser')
    plain = soup.get_text(separator=' ')

    # Strategy 1: After "Ingredients:" label
    m = re.search(
        r'(?:Ingredients|INCI|Full Ingredients?\s*(?:List)?)\s*[:\-]?\s*'
        r'((?:Aqua|Water)[^.]{30,1500})',
        plain, re.IGNORECASE
    )
    if m:
        return m.group(1).strip()

    # Strategy 2: Standalone INCI block starting with Aqua/Water
    m = re.search(
        r'((?:Aqua|Water)\s*,\s*[A-Za-z][A-Za-z0-9\s,\(\)\-\.\/]{40,1500})',
        plain, re.IGNORECASE
    )
    if m:
        return m.group(1).strip()

    return None


def _parse_size(text, product_name=None):
    """Extract size (value + unit) from text. Returns (float, str) or (None, 'ml')."""
    search_text = (product_name or '') + ' ' + (text or '')
    matches = re.findall(
        r'(?<!SPF\s)(?<!spf\s)(\d+\.?\d*)\s*(ml|g|fl\s*\.?\s*oz|oz)\b',
        search_text, re.IGNORECASE
    )
    for val_str, unit_str in matches:
        val = float(val_str)
        if 5 <= val <= 1000:
            unit = unit_str.lower().replace(' ', '').replace('.', '')
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
    for key in ['product_name', 'brand', 'price', 'size_ml', 'size_unit',
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
    for script_tag in soup.find_all('script', type='application/ld+json'):
        try:
            ld = json.loads(script_tag.string)
            items = ld if isinstance(ld, list) else [ld]
            for item in items:
                offers = item.get('offers', item)
                if isinstance(offers, list):
                    offers = offers[0]
                if isinstance(offers, dict):
                    p = offers.get('price') or offers.get('lowPrice')
                    if p:
                        price = float(str(p).replace(',', ''))
                        break
        except Exception:
            pass

    if not price:
        sym = CURRENCY_SYMBOLS.get(currency, r'[\$₹£€]')
        patterns = [
            re.compile(r'(?:sale|offer|special|discounted?|selling)\s*(?:price)?[:\s]*' + sym + r'\s*(\d[\d,]*\.?\d*)', re.I),
            re.compile(sym + r'\s*(\d[\d,]*\.?\d*)', re.I),
        ]
        for pat in patterns:
            m = pat.search(text[:8000])
            if m:
                try:
                    p = float(m.group(1).replace(',', ''))
                    if 0 < p < 100000:
                        price = p
                        break
                except ValueError:
                    pass

    # --- Size ---
    size_ml, size_unit = _parse_size(text[:3000], product_name)

    # --- Ingredients ---
    ingredients = None

    # Strategy 1: Section markers
    inci_patterns = [
        re.compile(r'(?:full\s+)?ingredients?\s*[:\-]\s*', re.I),
        re.compile(r'INCI\s*[:\-]\s*', re.I),
        re.compile(r'composition\s*[:\-]\s*', re.I),
    ]
    for pat in inci_patterns:
        m = pat.search(text)
        if m:
            after = text[m.end():m.end() + 3000]
            cb = re.match(r'([^.]{20,}(?:,\s*[^.]{2,}){4,})', after)
            if cb:
                ingredients = cb.group(1).strip()
                break

    # Strategy 2: Aqua/Water pattern
    if not ingredients:
        wm = re.search(r'((?:Aqua|Water)(?:/[^,]*)?[^.]*(?:,\s*[\w\s\-\(\)\/]+){4,})', text)
        if wm:
            ingredients = wm.group(1).strip()

    # Strategy 3: Long comma lists in HTML elements
    if not ingredients:
        for el in soup.find_all(['div', 'p', 'span', 'td', 'li']):
            el_text = el.get_text(' ', strip=True)
            if len(el_text) > 50 and el_text.count(',') >= 8:
                words = el_text.split(',')
                if any(w.strip().lower() in ('aqua', 'water', 'glycerin', 'dimethicone', 'niacinamide') for w in words[:5]):
                    ingredients = el_text.strip()
                    break

    # Strategy 4: Amazon ingredient section
    if not ingredients:
        ing_s = soup.find(attrs={'id': re.compile(r'ingredient', re.I)})
        if ing_s:
            ing_t = ing_s.get_text(' ', strip=True)
            if len(ing_t) > 20:
                ingredients = ing_t

    # Clean ingredients
    if ingredients:
        ingredients = re.sub(r'^(?:Ingredients|INCI|Composition)\s*[:\-]\s*', '', ingredients, flags=re.I)
        ingredients = re.sub(r'\s*(?:How to use|Directions|Warning|Disclaimer|Storage).*$', '', ingredients, flags=re.I)
        if len(ingredients) > 3000:
            ingredients = ingredients[:3000]

    # --- Active Concentrations ---
    # Scan the ENTIRE page text for "X% ingredient" patterns regardless of section heading.
    # This catches concentrations listed under "Why You'll Love It", "Hero Ingredient",
    # "Product Description", "Key Ingredients", etc.
    active_concentrations = {}
    _conc_patterns = [
        # "10% Niacinamide" or "10 % niacinamide"
        re.compile(r'([\d]+\.?\d*)\s*%\s+([a-zA-Z][a-zA-Z0-9 \-\/\(\)]{2,40}?)(?=\s*[,\.\|+&\n<]|$)', re.I),
        # "Niacinamide 10%" or "Niacinamide (10%)"
        re.compile(r'([a-zA-Z][a-zA-Z0-9 \-\/\(\)]{2,40}?)\s+\(?(\d+\.?\d*)\s*%\)?', re.I),
    ]
    # Search full text (not just 3000 chars — concentrations can appear anywhere)
    for pat in _conc_patterns:
        for m in pat.finditer(text):
            g = m.groups()
            try:
                if g[0][0].isdigit():
                    pct, name = float(g[0]), g[1].strip().lower()
                else:
                    name, pct = g[0].strip().lower(), float(g[1])
                # Sanity check: valid % range, name not a number, not too short
                if 0 < pct <= 100 and len(name) > 2 and not name[0].isdigit():
                    # Don't overwrite with less specific match
                    if name not in active_concentrations:
                        active_concentrations[name] = pct
            except (ValueError, IndexError):
                pass

    # --- Category ---
    category = _detect_category(product_name or '') or _detect_category(text[:500])

    return {
        'product_name': product_name,
        'brand': brand,
        'price': price,
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

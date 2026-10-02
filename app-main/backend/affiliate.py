"""Affiliate tagging for outbound retailer links.

Scope and design rules
----------------------

1. **A tag is only ever applied to the store it was issued for.** Amazon
   Associates IDs are per-locale: ``pc2920-21`` is an amazon.in tag. Putting it
   on an amazon.com link earns nothing, and the Associates Operating Agreement
   requires separate enrolment per locale. So each store maps to its own tag and
   an unmapped store gets no tag at all - never a "close enough" one.

2. **Tagging never changes which product we show or where it ranks.** This
   module runs at the very end, on links that have already been chosen on price
   and product-match grounds. There is no code path in which carrying a tag can
   promote a retailer. That separation is the whole reason this lives in its own
   module rather than inside the best-price search: an affiliate link that could
   influence the recommendation would make the recommendation worthless.

3. **Disclosure is mandatory, not a nicety.** The Associates Operating Agreement
   requires a clear statement wherever affiliate links appear, and the US FTC
   endorsement guides require it independently. ``disclosure_for()`` returns the
   required text and the API attaches it to any response that carries a tagged
   link, so the UI cannot ship tagged links without it.

4. **Links are not rewritten to a different destination.** Only the tracking
   parameter is set. The user lands on exactly the page we found, at the price
   we quoted.

Enable a store by setting its environment variable. With no variables set,
every function here is a no-op that returns its input unchanged, which is the
correct behaviour before the Associates account is approved.
"""

import os
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# ---------------------------------------------------------------------------
# Store registry
# ---------------------------------------------------------------------------
# host suffix -> (environment variable, query parameter)
#
# Host matching is on a registrable-suffix basis so that regional subdomains
# (www.amazon.in, smile.amazon.in) match while a lookalike (amazon.in.evil.com)
# does not. See _host_matches.
_AMAZON_PARAM = 'tag'

AFFILIATE_STORES = {
    'amazon.in':      ('AMAZON_TAG_IN', _AMAZON_PARAM),
    'amazon.com':     ('AMAZON_TAG_COM', _AMAZON_PARAM),
    'amazon.co.uk':   ('AMAZON_TAG_UK', _AMAZON_PARAM),
    'amazon.ae':      ('AMAZON_TAG_AE', _AMAZON_PARAM),
    'amazon.com.au':  ('AMAZON_TAG_AU', _AMAZON_PARAM),
    'amazon.ca':      ('AMAZON_TAG_CA', _AMAZON_PARAM),
    'amazon.sg':      ('AMAZON_TAG_SG', _AMAZON_PARAM),
    'amazon.co.jp':   ('AMAZON_TAG_JP', _AMAZON_PARAM),
    'amazon.fr':      ('AMAZON_TAG_FR', _AMAZON_PARAM),
    'amazon.de':      ('AMAZON_TAG_DE', _AMAZON_PARAM),
    'amazon.com.br':  ('AMAZON_TAG_BR', _AMAZON_PARAM),
}

# The one tag that exists today. Kept as a default for its own store only, so
# that a deployment without environment variables still tags amazon.in and
# still leaves every other store untagged.
_DEFAULT_TAGS = {
    'AMAZON_TAG_IN': 'pc2920-21',
}

DISCLOSURE_TEXT = (
    "As an Amazon Associate we earn from qualifying purchases. "
    "Buying through these links costs you nothing extra and never affects "
    "a product's score or where it ranks here."
)

DISCLOSURE_SHORT = "Paid link"


def _tag_for_env(env_var):
    """The configured tag for a store, or None if that store is not enabled."""
    value = os.environ.get(env_var, _DEFAULT_TAGS.get(env_var, ''))
    value = (value or '').strip()
    return value or None


def _host_matches(host, suffix):
    """True when *host* is *suffix* or a subdomain of it.

    Exact-or-dotted-suffix, never a substring: "amazon.in.phishing.example"
    does not match "amazon.in", and neither does "notamazon.in".
    """
    host = host.lower().rstrip('.')
    if host.startswith('www.'):
        host = host[4:]
    return host == suffix or host.endswith('.' + suffix)


def _store_for(host):
    """Return (env_var, param) for the longest matching store suffix, or None.

    Longest-first matters: amazon.com.au and amazon.com.br would both also
    match amazon.com if the shortest suffix were allowed to win, which would
    put a US tag on an Australian link.
    """
    best = None
    for suffix, cfg in AFFILIATE_STORES.items():
        if _host_matches(host, suffix):
            if best is None or len(suffix) > len(best[0]):
                best = (suffix, cfg)
    return best[1] if best else None


def tag_url(url):
    """Return *url* with our tracking parameter set, or *url* unchanged.

    Unchanged when: the input is not a string, the scheme is not http(s), the
    host is not a store we are enrolled in, or that store has no tag
    configured. Any existing value of the tracking parameter is replaced -
    whoever referred the link before us did not refer this visit.
    """
    if not url or not isinstance(url, str):
        return url
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        return url

    host = parts.hostname or ''
    store = _store_for(host)
    if not store:
        return url
    env_var, param = store
    tag = _tag_for_env(env_var)
    if not tag:
        return url

    query = [(k, v) for (k, v) in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() != param.lower()]
    query.append((param, tag))
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(query), parts.fragment))


def is_tagged(url):
    """True when tag_url would actually change this URL."""
    return isinstance(url, str) and bool(url) and tag_url(url) != url


def tag_links(payload, fields=('link', 'url', 'user_url', 'buy_url', 'product_url')):
    """Tag every known link field in a nested dict/list, in place.

    Returns ``(payload, tagged_any)``. ``tagged_any`` is what decides whether
    the response needs to carry the disclosure, so the two can never drift
    apart: a tagged link and its disclosure are produced by the same walk.
    """
    tagged_any = [False]

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in fields and isinstance(value, str):
                    new = tag_url(value)
                    if new != value:
                        node[key] = new
                        tagged_any[0] = True
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return payload, tagged_any[0]


def disclosure_for(payload):
    """Tag a payload's links and attach the disclosure if any were tagged.

    This is the function the API should call, rather than tag_links directly,
    because it is the one that cannot produce a tagged link without its
    required disclosure.
    """
    payload, tagged_any = tag_links(payload)
    if tagged_any and isinstance(payload, dict):
        payload['affiliate_disclosure'] = DISCLOSURE_TEXT
        payload['affiliate_label'] = DISCLOSURE_SHORT
    return payload


def enabled_stores():
    """Stores with a tag configured. For the admin page and for tests."""
    return sorted(
        suffix for suffix, (env_var, _param) in AFFILIATE_STORES.items()
        if _tag_for_env(env_var)
    )

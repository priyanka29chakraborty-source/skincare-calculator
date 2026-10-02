"""Affiliate tagging.

Three things have to hold, and the money is the least important of them:

1. A tag only ever reaches the store it was issued for. Amazon Associates IDs
   are per-locale, so an India tag on amazon.com earns nothing and breaches the
   Operating Agreement's per-locale enrolment requirement.
2. A tagged link never ships without its disclosure. The Associates agreement
   and the FTC endorsement guides both require one.
3. Tagging cannot influence what we recommend. These tests assert the module
   has no inputs that would let it - it sees a finished payload and only ever
   edits a query string.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import affiliate  # noqa: E402
from affiliate import (  # noqa: E402
    DISCLOSURE_TEXT,
    disclosure_for,
    enabled_stores,
    is_tagged,
    tag_links,
    tag_url,
)


@pytest.fixture(autouse=True)
def only_india_enabled(monkeypatch):
    """The real configuration: one approved locale, every other store off.

    Tests that need a second store enable it explicitly, so an accidental
    environment variable in CI cannot make a locale-isolation test pass.
    """
    for env_var, _param in affiliate.AFFILIATE_STORES.values():
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setenv('AMAZON_TAG_IN', 'pc2920-21')
    yield


# ---------------------------------------------------------------------------
# Locale isolation - the rule that actually costs money to get wrong
# ---------------------------------------------------------------------------

def test_the_india_tag_is_applied_to_amazon_in():
    out = tag_url('https://www.amazon.in/dp/B08XYZ')
    assert 'tag=pc2920-21' in out


@pytest.mark.parametrize('url', [
    'https://www.amazon.com/dp/B08XYZ',
    'https://www.amazon.co.uk/dp/B08XYZ',
    'https://www.amazon.ae/dp/B08XYZ',
    'https://www.amazon.com.au/dp/B08XYZ',
    'https://www.amazon.de/dp/B08XYZ',
])
def test_the_india_tag_never_leaks_to_another_amazon_locale(url):
    """An amazon.in tag on amazon.com earns nothing and is a policy breach."""
    assert tag_url(url) == url


def test_amazon_com_au_does_not_match_amazon_com():
    """Longest-suffix matching.

    amazon.com.au ends with neither "amazon.com" nor ".amazon.com", but the
    guard matters the moment a US tag is configured, so assert it directly.
    """
    os.environ['AMAZON_TAG_COM'] = 'ustag-20'
    try:
        assert tag_url('https://www.amazon.com.au/dp/B1') == 'https://www.amazon.com.au/dp/B1'
        assert 'tag=ustag-20' in tag_url('https://www.amazon.com/dp/B1')
    finally:
        del os.environ['AMAZON_TAG_COM']


def test_an_unknown_retailer_is_never_tagged():
    for url in ('https://www.nykaa.com/p/123',
                'https://www.flipkart.com/item',
                'https://minimalist.co/products/niacinamide'):
        assert tag_url(url) == url


# ---------------------------------------------------------------------------
# Host matching - a lookalike domain must not collect our tag
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('url', [
    'https://amazon.in.phishing.example/dp/B1',
    'https://notamazon.in/dp/B1',
    'https://evil.com/?next=amazon.in',
    'https://amazon.invalid/dp/B1',
])
def test_lookalike_hosts_are_not_tagged(url):
    assert tag_url(url) == url


def test_subdomains_of_a_real_store_are_tagged():
    assert 'tag=pc2920-21' in tag_url('https://smile.amazon.in/dp/B1')
    assert 'tag=pc2920-21' in tag_url('https://amazon.in/dp/B1')


@pytest.mark.parametrize('url', [
    'javascript:alert(1)',
    'data:text/html,<script>',
    'ftp://amazon.in/file',
    'file:///etc/passwd',
])
def test_non_http_schemes_are_left_alone(url):
    assert tag_url(url) == url


@pytest.mark.parametrize('value', [None, '', 123, {}, []])
def test_non_string_input_is_returned_unchanged(value):
    assert tag_url(value) == value


# ---------------------------------------------------------------------------
# The link still points where we said it did
# ---------------------------------------------------------------------------

def test_the_destination_is_never_rewritten():
    out = tag_url('https://www.amazon.in/dp/B08XYZ/ref=sr_1_3?keywords=serum#reviews')
    assert out.startswith('https://www.amazon.in/dp/B08XYZ/ref=sr_1_3')
    assert out.endswith('#reviews')
    assert 'keywords=serum' in out


def test_an_existing_foreign_tag_is_replaced_not_appended():
    out = tag_url('https://www.amazon.in/dp/B1?tag=someoneelse-21')
    assert 'someoneelse-21' not in out
    assert out.count('tag=') == 1
    assert 'tag=pc2920-21' in out


def test_tagging_is_idempotent():
    once = tag_url('https://www.amazon.in/dp/B1')
    assert tag_url(once) == once


# ---------------------------------------------------------------------------
# Disclosure is attached by the same pass that tags
# ---------------------------------------------------------------------------

def test_a_tagged_payload_always_carries_the_disclosure():
    payload = disclosure_for({
        'best_price': {'link': 'https://www.amazon.in/dp/B1', 'price': 499},
        'all_prices': [{'link': 'https://www.amazon.in/dp/B2', 'price': 549}],
    })
    assert payload['affiliate_disclosure'] == DISCLOSURE_TEXT
    assert 'tag=pc2920-21' in payload['best_price']['link']


def test_an_untagged_payload_carries_no_disclosure():
    """Claiming a commercial relationship we do not have is its own problem."""
    payload = disclosure_for({
        'best_price': {'link': 'https://www.nykaa.com/p/1', 'price': 499},
    })
    assert 'affiliate_disclosure' not in payload


def test_disclosure_names_amazon_and_says_the_price_is_unchanged():
    assert 'Amazon Associate' in DISCLOSURE_TEXT
    assert 'nothing extra' in DISCLOSURE_TEXT
    assert 'score' in DISCLOSURE_TEXT


def test_nested_links_at_any_depth_are_tagged():
    payload = {'a': {'b': [{'c': {'link': 'https://www.amazon.in/dp/B9'}}]}}
    out, tagged = tag_links(payload)
    assert tagged is True
    assert 'tag=pc2920-21' in out['a']['b'][0]['c']['link']


def test_user_url_is_tagged_too():
    payload, tagged = tag_links({'user_url': 'https://www.amazon.in/dp/B1'})
    assert tagged is True
    assert 'tag=pc2920-21' in payload['user_url']


def test_fields_that_are_not_links_are_untouched():
    payload = {'name': 'https://www.amazon.in/dp/B1', 'source': 'amazon.in'}
    out, tagged = tag_links(payload)
    assert tagged is False
    assert out['name'] == 'https://www.amazon.in/dp/B1'


# ---------------------------------------------------------------------------
# Off by default
# ---------------------------------------------------------------------------

def test_with_no_store_configured_nothing_is_tagged(monkeypatch):
    """The correct state before the Associates account is approved."""
    monkeypatch.setattr(affiliate, '_DEFAULT_TAGS', {})
    for env_var, _param in affiliate.AFFILIATE_STORES.values():
        monkeypatch.delenv(env_var, raising=False)
    assert enabled_stores() == []
    url = 'https://www.amazon.in/dp/B1'
    assert tag_url(url) == url
    assert 'affiliate_disclosure' not in disclosure_for({'link': url})


def test_a_blank_env_var_disables_a_store(monkeypatch):
    monkeypatch.setenv('AMAZON_TAG_IN', '   ')
    url = 'https://www.amazon.in/dp/B1'
    assert tag_url(url) == url


def test_only_india_is_enabled_today():
    assert enabled_stores() == ['amazon.in']


# ---------------------------------------------------------------------------
# Tagging cannot influence ranking
# ---------------------------------------------------------------------------

def test_is_tagged_does_not_mutate_its_argument():
    """Used for UI labelling; it must stay a pure query."""
    url = 'https://www.amazon.in/dp/B1'
    assert is_tagged(url) is True
    assert url == 'https://www.amazon.in/dp/B1'


def test_tagging_preserves_list_order_and_every_price():
    """The ranking is decided upstream; this pass may not reorder or reprice.

    An affiliate link that could promote a retailer would make the whole
    recommendation worthless, so assert the shape survives untouched.
    """
    before = [
        {'link': 'https://www.nykaa.com/p/1', 'price': 399, 'source': 'nykaa.com'},
        {'link': 'https://www.amazon.in/dp/B1', 'price': 449, 'source': 'amazon.in'},
        {'link': 'https://www.flipkart.com/x', 'price': 480, 'source': 'flipkart.com'},
    ]
    payload = disclosure_for({'all_prices': [dict(x) for x in before]})
    after = payload['all_prices']

    assert [x['price'] for x in after] == [399, 449, 480]
    assert [x['source'] for x in after] == [b['source'] for b in before]
    # The cheapest is still the untagged retailer - tagging did not promote
    # the one we earn from.
    assert after[0]['source'] == 'nykaa.com'
    assert after[0]['link'] == before[0]['link']

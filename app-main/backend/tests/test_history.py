"""Saved analyses.

Two things matter beyond "it stores rows": one account can never read
another's, and a storage failure can never break an analysis - history is a
convenience bolted onto the request path, and the request has already
succeeded by the time it runs.
"""

import os
import sys
import tempfile
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def hist(monkeypatch):
    tmp = tempfile.mkdtemp(prefix='history-test-')
    monkeypatch.setenv('WALLET_DB_PATH', os.path.join(tmp, 'wallet.db'))
    monkeypatch.delenv('AIVEN_PG_URL', raising=False)
    for mod in ('wallet', 'history'):
        sys.modules.pop(mod, None)
    import wallet as w
    import history as h
    w._initialised = False
    w._local = threading.local()
    w.init_storage()
    h.ensure_schema()
    return h


@pytest.fixture
def account(hist):
    import wallet
    return wallet.get_or_create_account('buyer@example.com')


def request_data(name='Niacinamide 10%', category='Serum'):
    return {
        'product_name': name, 'brand': 'Minimalist', 'category': category,
        'price': 549, 'size_ml': 30, 'currency': 'INR', 'skin_type': 'oily',
        'skin_concerns': ['Acne & Oily Skin'],
        'ingredients': 'Aqua, Niacinamide, Zinc PCA',
    }


def result(score=91):
    return {'formulation_score': score, 'formulation_tier': 'Excellent formulation'}


# ---------------------------------------------------------------------------
# Storing
# ---------------------------------------------------------------------------

def test_an_analysis_is_saved(hist, account):
    hist.record(account, 'key1', result(), request_data(), was_paid=True)
    rows = hist.recent(account)
    assert len(rows) == 1
    assert rows[0]['product_name'] == 'Niacinamide 10%'
    assert rows[0]['score'] == 91
    assert rows[0]['was_paid'] is True


def test_re_analysing_updates_in_place(hist, account):
    """Otherwise the list fills with the same product over and over."""
    hist.record(account, 'key1', result(91), request_data(), was_paid=False)
    hist.record(account, 'key1', result(88), request_data(), was_paid=True)
    rows = hist.recent(account)
    assert len(rows) == 1
    assert rows[0]['score'] == 88
    assert rows[0]['was_paid'] is True


def test_different_products_are_separate_rows(hist, account):
    hist.record(account, 'key1', result(), request_data('A'), was_paid=False)
    hist.record(account, 'key2', result(), request_data('B'), was_paid=False)
    assert len(hist.recent(account)) == 2


def test_newest_first(hist, account):
    hist.record(account, 'key1', result(), request_data('Older'), was_paid=False)
    hist.record(account, 'key2', result(), request_data('Newer'), was_paid=False)
    assert hist.recent(account)[0]['product_name'] == 'Newer'


def test_recording_without_an_account_does_nothing(hist):
    assert hist.record(None, 'key1', result(), request_data(), was_paid=False) is None


def test_a_storage_failure_never_breaks_the_analysis(hist, account, monkeypatch):
    """The analysis has already succeeded by the time this runs. Turning that
    into an error because a convenience feature failed would be the wrong
    trade."""
    def explode(*args, **kwargs):
        raise RuntimeError('disk is on fire')
    monkeypatch.setattr(hist, 'ensure_schema', explode)
    assert hist.record(account, 'key1', result(), request_data(), was_paid=False) is None


def test_an_oversized_ingredient_list_is_truncated_not_rejected(hist, account):
    data = request_data()
    data['ingredients'] = 'Aqua, ' * 5000
    assert hist.record(account, 'key1', result(), data, was_paid=False)
    entry = hist.get(account, hist.recent(account)[0]['entry_id'])
    assert len(entry['ingredients']) <= 6000


def test_the_list_is_capped(hist, account):
    """Unbounded growth for a list nobody scrolls past the first page of is a
    slow storage leak, and on a paid database it is a bill."""
    for i in range(hist.MAX_ROWS_PER_ACCOUNT + 25):
        hist.record(account, 'key%d' % i, result(), request_data('P%d' % i),
                    was_paid=False)
    import wallet
    cur = wallet._execute(
        'SELECT COUNT(*) FROM analysis_history WHERE account_id = ?', (account,))
    assert cur.fetchone()[0] <= hist.MAX_ROWS_PER_ACCOUNT


# ---------------------------------------------------------------------------
# Isolation between accounts
# ---------------------------------------------------------------------------

def test_one_account_never_sees_anothers_history(hist, account):
    import wallet
    other = wallet.get_or_create_account('other@example.com')
    hist.record(account, 'k', result(), request_data('Mine'), was_paid=False)
    hist.record(other, 'k', result(), request_data('Theirs'), was_paid=False)

    assert [r['product_name'] for r in hist.recent(account)] == ['Mine']
    assert [r['product_name'] for r in hist.recent(other)] == ['Theirs']


def test_an_entry_id_from_another_account_fetches_nothing(hist, account):
    """Scoped in the WHERE clause, so a copied id matches no row rather than
    being checked after it has already been read."""
    import wallet
    other = wallet.get_or_create_account('other@example.com')
    hist.record(other, 'k', result(), request_data('Theirs'), was_paid=False)
    their_id = hist.recent(other)[0]['entry_id']
    assert hist.get(account, their_id) is None


def test_forgetting_another_accounts_entry_does_nothing(hist, account):
    import wallet
    other = wallet.get_or_create_account('other@example.com')
    hist.record(other, 'k', result(), request_data('Theirs'), was_paid=False)
    their_id = hist.recent(other)[0]['entry_id']
    assert hist.forget(account, their_id) is False
    assert len(hist.recent(other)) == 1


# ---------------------------------------------------------------------------
# Reading back and deleting
# ---------------------------------------------------------------------------

def test_a_saved_entry_can_be_re_opened(hist, account):
    hist.record(account, 'key1', result(), request_data(), was_paid=True)
    entry_id = hist.recent(account)[0]['entry_id']
    entry = hist.get(account, entry_id)
    assert entry['ingredients'] == 'Aqua, Niacinamide, Zinc PCA'
    assert entry['concerns'] == ['Acne & Oily Skin']
    assert entry['skin_type'] == 'oily'


def test_forgetting_one_entry(hist, account):
    hist.record(account, 'key1', result(), request_data('A'), was_paid=False)
    hist.record(account, 'key2', result(), request_data('B'), was_paid=False)
    entry_id = hist.recent(account)[0]['entry_id']
    assert hist.forget(account, entry_id) is True
    assert len(hist.recent(account)) == 1


def test_forgetting_everything(hist, account):
    for i in range(4):
        hist.record(account, 'k%d' % i, result(), request_data('P%d' % i),
                    was_paid=False)
    assert hist.forget_all(account) == 4
    assert hist.recent(account) == []


def test_forget_all_leaves_other_accounts_alone(hist, account):
    import wallet
    other = wallet.get_or_create_account('other@example.com')
    hist.record(account, 'k', result(), request_data('Mine'), was_paid=False)
    hist.record(other, 'k', result(), request_data('Theirs'), was_paid=False)
    hist.forget_all(account)
    assert len(hist.recent(other)) == 1


def test_a_real_analysis_fills_the_score_and_tier(hist, account):
    """Guards the same bug test_compare documents: the engine names the tier
    main_worth_tier, so reading result['formulation_tier'] alone saved an
    empty column while every synthetic test stayed green."""
    from scoring import analyze_product

    data = {
        'ingredients': 'Aqua, Niacinamide, Zinc PCA, Glycerin, Phenoxyethanol',
        'price': 549, 'size_ml': 30, 'category': 'Serum', 'country': 'India',
        'currency': 'INR', 'skin_type': 'oily', 'skin_concerns': [],
        'product_name': 'Niacinamide 10%', 'brand': 'Minimalist',
    }
    hist.record(account, 'real-key', analyze_product(data), data, was_paid=True)

    row = hist.recent(account)[0]
    assert row['score'] > 0
    assert row['tier'], 'tier column is empty'
    assert row['product_name'] == 'Niacinamide 10%'

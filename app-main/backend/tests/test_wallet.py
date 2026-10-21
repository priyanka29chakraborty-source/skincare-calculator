"""The credit ledger.

This is the only part of the app where a bug costs a customer money, so the
tests are about the three failures that actually happen in production:

  * a retried webhook granting the same purchase twice,
  * two concurrent analyses both spending the last credit,
  * the cached balance drifting from the ledger.

Each is prevented by the database rather than by careful code, and each test
here exercises the mechanism rather than the happy path.
"""

import os
import sys
import tempfile
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def wallet(monkeypatch):
    """A fresh SQLite ledger per test, in a temp directory."""
    tmp = tempfile.mkdtemp(prefix='wallet-test-')
    monkeypatch.setenv('WALLET_DB_PATH', os.path.join(tmp, 'wallet.db'))
    monkeypatch.delenv('AIVEN_PG_URL', raising=False)

    for mod in list(sys.modules):
        if mod == 'wallet':
            del sys.modules[mod]
    import wallet as w
    w._initialised = False
    w._local = threading.local()
    w.init_storage()
    return w


@pytest.fixture
def account(wallet):
    return wallet.get_or_create_account('buyer@example.com')


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def test_a_new_account_starts_empty(wallet, account):
    assert wallet.get_balance(account) == 0


def test_the_same_email_is_always_the_same_account(wallet):
    """Case and whitespace must not split an account.

    Otherwise someone pays on "A@b.com " and spends on "a@b.com", and their
    credits are simply gone from their point of view.
    """
    a = wallet.get_or_create_account('Buyer@Example.com')
    b = wallet.get_or_create_account('  buyer@example.com ')
    assert a == b


def test_an_account_needs_an_email(wallet):
    with pytest.raises(wallet.WalletError):
        wallet.get_or_create_account('')


def test_balance_of_an_unknown_account_is_zero(wallet):
    assert wallet.get_balance('acct_does_not_exist') == 0


def test_failed_statement_rolls_back_postgres_connection(wallet, monkeypatch):
    """A rejected statement must not poison later work on the same PG thread."""
    class FailingCursor:
        def execute(self, _sql, _params):
            raise RuntimeError('duplicate key')

    class FakeConnection:
        def __init__(self):
            self.rollbacks = 0

        def cursor(self):
            return FailingCursor()

        def rollback(self):
            self.rollbacks += 1

    conn = FakeConnection()
    monkeypatch.setattr(wallet, '_USE_PG', True)
    monkeypatch.setattr(wallet, 'init_storage', lambda: None)
    monkeypatch.setattr(wallet, '_connect', lambda: conn)

    with pytest.raises(RuntimeError, match='duplicate key'):
        wallet._execute('INSERT INTO example VALUES (?)', ('value',), commit=True)
    assert conn.rollbacks == 1


def test_account_list_shows_the_balance_after_a_spend(wallet, account):
    wallet.grant(account, 4, reference='trial_list')
    wallet.spend(account, reference='analysis_1')
    listed = wallet.list_accounts()
    assert listed[0]['email'] == 'buyer@example.com'
    assert listed[0]['balance'] == 3


# ---------------------------------------------------------------------------
# Granting - idempotency is the whole point
# ---------------------------------------------------------------------------

def test_a_purchase_adds_credits(wallet, account):
    assert wallet.grant(account, 15, reference='pay_abc') == 15


def test_the_same_payment_delivered_twice_grants_once(wallet, account):
    """Razorpay retries until it gets a 2xx. Duplicate delivery is normal."""
    assert wallet.grant(account, 5, reference='pay_retry') == 5
    assert wallet.grant(account, 5, reference='pay_retry') is None
    assert wallet.get_balance(account) == 5


def test_a_duplicate_grant_writes_no_second_ledger_row(wallet, account):
    wallet.grant(account, 5, reference='pay_once')
    wallet.grant(account, 5, reference='pay_once')
    rows = wallet.history(account)
    assert len([r for r in rows if r['reference'] == 'pay_once']) == 1


def test_concurrent_deliveries_of_one_payment_grant_once(wallet, account):
    """The race a SELECT-then-INSERT check loses."""
    errors = []

    def deliver():
        try:
            wallet.grant(account, 10, reference='pay_race')
        except Exception as exc:  # noqa: BLE001 - recorded, asserted below
            errors.append(exc)

    threads = [threading.Thread(target=deliver) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert wallet.get_balance(account) == 10


def test_different_payments_both_grant(wallet, account):
    wallet.grant(account, 5, reference='pay_1')
    wallet.grant(account, 15, reference='pay_2')
    assert wallet.get_balance(account) == 20


def test_a_grant_without_a_reference_is_not_deduplicated(wallet, account):
    """Manual goodwill grants are deliberately repeatable."""
    wallet.grant(account, 1, reason=wallet.REASON_GRANT)
    wallet.grant(account, 1, reason=wallet.REASON_GRANT)
    assert wallet.get_balance(account) == 2


def test_granting_to_a_missing_account_fails_loudly(wallet):
    with pytest.raises(wallet.WalletError):
        wallet.grant('acct_nope', 5, reference='pay_x')


def test_a_grant_must_be_positive(wallet, account):
    for bad in (0, -5):
        with pytest.raises(wallet.WalletError):
            wallet.grant(account, bad)


# ---------------------------------------------------------------------------
# Spending - never oversell
# ---------------------------------------------------------------------------

def test_spending_deducts_one_credit(wallet, account):
    wallet.grant(account, 3, reference='p1')
    assert wallet.spend(account) == 2


def test_spending_without_credits_raises_and_changes_nothing(wallet, account):
    with pytest.raises(wallet.InsufficientCredits):
        wallet.spend(account)
    assert wallet.get_balance(account) == 0
    assert wallet.history(account) == []


def test_spending_more_than_the_balance_is_all_or_nothing(wallet, account):
    wallet.grant(account, 2, reference='p1')
    with pytest.raises(wallet.InsufficientCredits):
        wallet.spend(account, credits=3)
    assert wallet.get_balance(account) == 2


def test_the_last_credit_cannot_be_spent_twice_concurrently(wallet, account):
    """The failure a read-then-write balance check allows.

    Ten threads race for one credit. Exactly one may win; the balance must
    never go negative.
    """
    wallet.grant(account, 1, reference='p1')
    wins, losses = [], []
    lock = threading.Lock()

    def attempt(i):
        try:
            wallet.spend(account, reference='analysis_%d' % i)
            with lock:
                wins.append(i)
        except wallet.InsufficientCredits:
            with lock:
                losses.append(i)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(wins) == 1, 'oversold: %d spends succeeded against 1 credit' % len(wins)
    assert len(losses) == 9
    assert wallet.get_balance(account) == 0


def test_the_balance_never_goes_negative_under_load(wallet, account):
    wallet.grant(account, 5, reference='p1')

    def attempt(i):
        try:
            wallet.spend(account, reference='a_%d' % i)
        except wallet.InsufficientCredits:
            pass

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(25)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert wallet.get_balance(account) == 0


def test_a_retried_analysis_is_charged_once(wallet, account):
    """Same reference, so a client retry does not cost a second credit."""
    wallet.grant(account, 5, reference='p1')
    wallet.spend(account, reference='analysis_42')
    wallet.spend(account, reference='analysis_42')
    assert wallet.get_balance(account) == 4


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------

def test_a_refund_returns_the_credit(wallet, account):
    wallet.grant(account, 2, reference='p1')
    wallet.spend(account, reference='analysis_1')
    wallet.refund(account, reference='refund_analysis_1')
    assert wallet.get_balance(account) == 2


def test_a_refund_is_recorded_separately_from_a_purchase(wallet, account):
    """During a dispute, "we gave this back" must not read as "they bought more"."""
    wallet.grant(account, 2, reference='p1')
    wallet.spend(account, reference='a1')
    wallet.refund(account, reference='r1')
    reasons = [r['reason'] for r in wallet.history(account)]
    assert wallet.REASON_REVERSAL in reasons
    assert reasons.count(wallet.REASON_PURCHASE) == 1


# ---------------------------------------------------------------------------
# The ledger is the truth
# ---------------------------------------------------------------------------

def test_the_ledger_sums_to_the_balance(wallet, account):
    wallet.grant(account, 15, reference='p1')
    wallet.spend(account, reference='a1')
    wallet.spend(account, reference='a2')
    wallet.refund(account, reference='r1')
    assert sum(r['delta'] for r in wallet.history(account)) == wallet.get_balance(account)


def test_recompute_repairs_a_drifted_balance(wallet, account):
    """If the cache and the ledger ever disagree, the ledger wins."""
    wallet.grant(account, 10, reference='p1')
    wallet._execute(
        'UPDATE wallet_account SET balance = 9999 WHERE account_id = ?',
        (account,), commit=True)
    raw = wallet._execute(
        'SELECT balance FROM wallet_account WHERE account_id = ?', (account,))
    assert int(raw.fetchone()[0]) == 9999
    assert wallet.recompute_balance(account) == 10
    assert wallet.get_balance(account) == 10


def test_unused_credits_expire_one_year_after_purchase(wallet, account, monkeypatch):
    bought = 1_700_000_000.0
    monkeypatch.setattr(wallet, '_now', lambda: bought)
    wallet.grant(account, 5, reference='pay_old')
    wallet.spend(account, reference='used_one')
    monkeypatch.setattr(wallet, '_now', lambda: bought + wallet.CREDIT_LIFETIME_SECONDS + 5)
    assert wallet.get_balance(account) == 0
    try:
        wallet.spend(account, reference='too_late')
        raised = False
    except wallet.InsufficientCredits:
        raised = True
    assert raised


def test_a_later_purchase_survives_an_older_pack_expiring(wallet, account, monkeypatch):
    bought = 1_700_000_000.0
    monkeypatch.setattr(wallet, '_now', lambda: bought)
    wallet.grant(account, 5, reference='pay_old')
    later = bought + 200 * 24 * 60 * 60
    monkeypatch.setattr(wallet, '_now', lambda: later)
    wallet.grant(account, 2, reference='pay_new')
    monkeypatch.setattr(wallet, '_now', lambda: bought + wallet.CREDIT_LIFETIME_SECONDS + 5)
    # The first pack was still valid when the second was bought, so those
    # remaining credits take the new expiry. Both packs are still live here.
    assert wallet.get_balance(account) == 7
    monkeypatch.setattr(wallet, '_now', lambda: later + wallet.CREDIT_LIFETIME_SECONDS + 5)
    assert wallet.get_balance(account) == 0


def test_a_purchase_does_not_restore_credits_that_already_expired(wallet, account, monkeypatch):
    bought = 1_700_000_000.0
    monkeypatch.setattr(wallet, '_now', lambda: bought)
    wallet.grant(account, 5, reference='pay_old')
    later = bought + wallet.CREDIT_LIFETIME_SECONDS + 5
    monkeypatch.setattr(wallet, '_now', lambda: later)
    assert wallet.get_balance(account) == 0
    wallet.grant(account, 2, reference='pay_new')
    assert wallet.get_balance(account) == 2


def test_history_is_newest_first(wallet, account):
    wallet.grant(account, 5, reference='p1')
    wallet.spend(account, reference='a1')
    rows = wallet.history(account)
    assert rows[0]['reason'] == wallet.REASON_SPEND
    assert rows[-1]['reason'] == wallet.REASON_PURCHASE


def test_one_accounts_history_never_shows_another(wallet):
    a = wallet.get_or_create_account('a@example.com')
    b = wallet.get_or_create_account('b@example.com')
    wallet.grant(a, 5, reference='pa')
    wallet.grant(b, 9, reference='pb')
    assert all(r['delta'] == 5 for r in wallet.history(a))
    assert wallet.get_balance(b) == 9


# ---------------------------------------------------------------------------
# Packs and durability
# ---------------------------------------------------------------------------

def test_the_three_packs_are_priced_as_agreed(wallet):
    assert wallet.CREDIT_PACKS['starter'] == {
        'credits': 5, 'amount_paise': 9900, 'label': '5 credits'}
    assert wallet.CREDIT_PACKS['regular'] == {
        'credits': 8, 'amount_paise': 14900, 'label': '8 credits'}
    assert wallet.CREDIT_PACKS['bulk'] == {
        'credits': 12, 'amount_paise': 19900, 'label': '12 credits'}


def test_prices_are_whole_paise(wallet):
    """Razorpay rejects non-integer amounts, and float rupees eventually
    produce a 98.99999 charge."""
    for pack in wallet.CREDIT_PACKS.values():
        assert isinstance(pack['amount_paise'], int)


def test_an_unknown_pack_is_rejected(wallet):
    with pytest.raises(wallet.WalletError):
        wallet.pack_for('enterprise')


def test_sqlite_storage_reports_itself_as_not_durable(wallet):
    """Render's disk is ephemeral unless one is attached, so selling credits
    on SQLite there would delete them on the next restart. The health endpoint
    reads this."""
    assert wallet.storage_is_durable() is False

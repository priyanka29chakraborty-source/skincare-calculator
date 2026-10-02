"""Login codes and session cookies.

The account holds a credit balance someone paid for, so the tests here are
about the two ways in: guessing a code, and forging a session.
"""

import os
import sys
import tempfile
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def ident(monkeypatch):
    tmp = tempfile.mkdtemp(prefix='identity-test-')
    monkeypatch.setenv('WALLET_DB_PATH', os.path.join(tmp, 'wallet.db'))
    monkeypatch.delenv('AIVEN_PG_URL', raising=False)
    monkeypatch.setenv('SESSION_SECRET', 'test-secret-value')

    for mod in ('wallet', 'identity'):
        sys.modules.pop(mod, None)
    import wallet as w
    import identity as i
    w._initialised = False
    w._local = threading.local()
    w.init_storage()
    return i


# ---------------------------------------------------------------------------
# Email normalisation
# ---------------------------------------------------------------------------

def test_an_address_is_lowercased_and_stripped(ident):
    assert ident.normalise_email('  Buyer@Example.COM ') == 'buyer@example.com'


@pytest.mark.parametrize('bad', ['', 'not-an-email', 'a@b', '@b.com', 'a b@c.com', None])
def test_a_malformed_address_is_rejected(ident, bad):
    with pytest.raises(ident.IdentityError):
        ident.normalise_email(bad)


def test_an_absurdly_long_address_is_rejected(ident):
    with pytest.raises(ident.IdentityError):
        ident.normalise_email('a' * 250 + '@example.com')


# ---------------------------------------------------------------------------
# Login codes
# ---------------------------------------------------------------------------

def test_a_correct_code_returns_an_account(ident):
    code = ident.issue_code('buyer@example.com')
    account_id = ident.verify_code('buyer@example.com', code)
    assert account_id.startswith('acct_')


def test_the_code_is_six_digits(ident):
    code = ident.issue_code('buyer@example.com')
    assert len(code) == 6 and code.isdigit()


def test_a_wrong_code_is_rejected(ident):
    ident.issue_code('buyer@example.com')
    with pytest.raises(ident.IdentityError):
        ident.verify_code('buyer@example.com', '000000')


def test_a_code_is_single_use(ident):
    """A code left valid after use is a credential sitting in an inbox."""
    code = ident.issue_code('buyer@example.com')
    ident.verify_code('buyer@example.com', code)
    with pytest.raises(ident.IdentityError):
        ident.verify_code('buyer@example.com', code)


def test_a_code_for_one_address_does_not_work_for_another(ident):
    code = ident.issue_code('a@example.com')
    ident.issue_code('b@example.com')
    with pytest.raises(ident.IdentityError):
        ident.verify_code('b@example.com', code)


def test_guessing_is_capped(ident):
    """Six digits is a million guesses without a cap - minutes of scripted
    traffic. After five wrong attempts the code is burned, not just refused."""
    code = ident.issue_code('buyer@example.com')
    for _ in range(ident.MAX_CODE_ATTEMPTS):
        with pytest.raises(ident.IdentityError):
            ident.verify_code('buyer@example.com', '000000')
    with pytest.raises(ident.IdentityError):
        ident.verify_code('buyer@example.com', code)


def test_an_expired_code_is_rejected(ident, monkeypatch):
    code = ident.issue_code('buyer@example.com')
    # Jump past the TTL rather than sleeping through it. ident.time is this
    # module's time, so capture the real clock before patching it.
    real_time = time.time
    monkeypatch.setattr(ident.time, 'time',
                        lambda: real_time() + ident.CODE_TTL_SECONDS + 1)
    with pytest.raises(ident.IdentityError):
        ident.verify_code('buyer@example.com', code)


def test_an_expired_code_is_deleted_not_merely_refused(ident, monkeypatch):
    """So a later clock skew or retry cannot resurrect it."""
    import wallet
    code = ident.issue_code('buyer@example.com')
    real_time = time.time
    monkeypatch.setattr(ident.time, 'time',
                        lambda: real_time() + ident.CODE_TTL_SECONDS + 1)
    with pytest.raises(ident.IdentityError):
        ident.verify_code('buyer@example.com', code)
    monkeypatch.undo()
    cur = wallet._execute('SELECT COUNT(*) FROM login_code WHERE email = ?',
                          ('buyer@example.com',))
    assert cur.fetchone()[0] == 0


def test_verifying_without_requesting_is_rejected(ident):
    with pytest.raises(ident.IdentityError):
        ident.verify_code('nobody@example.com', '123456')


def test_requesting_a_second_code_invalidates_the_first(ident):
    first = ident.issue_code('buyer@example.com')
    second = ident.issue_code('buyer@example.com')
    with pytest.raises(ident.IdentityError):
        ident.verify_code('buyer@example.com', first)
    assert ident.verify_code('buyer@example.com', second).startswith('acct_')


def test_the_same_address_always_reaches_the_same_account(ident):
    a = ident.verify_code('buyer@example.com', ident.issue_code('buyer@example.com'))
    b = ident.verify_code('BUYER@example.com', ident.issue_code('BUYER@example.com'))
    assert a == b


def test_codes_are_not_stored_in_plain_text(ident):
    """A database read should not hand over a working code for every pending
    login."""
    import wallet
    code = ident.issue_code('buyer@example.com')
    cur = wallet._execute('SELECT code_hash FROM login_code WHERE email = ?',
                          ('buyer@example.com',))
    stored = cur.fetchone()[0]
    assert code not in stored
    assert len(stored) == 64


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def test_a_session_round_trips(ident):
    token = ident.make_session('acct_abc123')
    assert ident.read_session(token) == 'acct_abc123'


def test_a_tampered_account_id_is_rejected(ident):
    """The attack: edit the cookie to someone else's account and read their
    balance."""
    token = ident.make_session('acct_abc123')
    forged = token.replace('acct_abc123', 'acct_victim')
    assert ident.read_session(forged) is None


def test_a_tampered_expiry_is_rejected(ident):
    token = ident.make_session('acct_abc123', ttl=1)
    account_id, expiry, sig = token.rsplit('.', 2)
    forged = '%s.%d.%s' % (account_id, int(expiry) + 10 ** 6, sig)
    assert ident.read_session(forged) is None


def test_an_expired_session_is_rejected(ident):
    token = ident.make_session('acct_abc123', ttl=-1)
    assert ident.read_session(token) is None


@pytest.mark.parametrize('token', [
    None, '', 'garbage', 'a.b', 'a.b.c.d.e', 123, 'acct_x.notanumber.sig',
])
def test_malformed_sessions_are_anonymous_not_errors(ident, token):
    """Every failure mode has the same correct response: treat as anonymous."""
    assert ident.read_session(token) is None


def test_a_session_signed_with_another_secret_is_rejected(ident, monkeypatch):
    token = ident.make_session('acct_abc123')
    monkeypatch.setenv('SESSION_SECRET', 'a-different-secret')
    assert ident.read_session(token) is None


def test_a_payload_that_is_not_an_account_id_is_rejected(ident):
    """Defence in depth: even correctly signed, the subject must be an account."""
    payload = 'admin.%d' % (int(time.time()) + 1000)
    token = '%s.%s' % (payload, ident._sign(payload))
    assert ident.read_session(token) is None


def test_the_cookie_is_httponly_and_secure(ident):
    flags = ident.session_cookie_kwargs()
    assert flags['httponly'] is True
    assert flags['secure'] is True
    assert flags['samesite'] == 'none'


def test_a_missing_session_secret_is_reported(ident, monkeypatch):
    """Safe, but it logs everyone out on every deploy - the health endpoint
    should say so rather than letting it pass unnoticed."""
    monkeypatch.delenv('SESSION_SECRET', raising=False)
    assert ident.secret_is_persistent() is False
    monkeypatch.setenv('SESSION_SECRET', 'x')
    assert ident.secret_is_persistent() is True

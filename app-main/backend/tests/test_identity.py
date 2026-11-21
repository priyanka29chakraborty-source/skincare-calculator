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
    traffic. After five wrong attempts the real code is refused too."""
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


def test_the_first_sign_in_includes_four_credits_once(ident):
    import wallet
    account = ident.verify_code('buyer@example.com', ident.issue_code('buyer@example.com'))
    assert wallet.get_balance(account) == 4
    ident.verify_code('buyer@example.com', ident.issue_code('buyer@example.com'))
    assert wallet.get_balance(account) == 4


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
# Resend throttle, lockout, and the verified visitor IP
# ---------------------------------------------------------------------------

class _Headers:
    def __init__(self, data):
        self._data = {k.lower(): v for k, v in data.items()}

    def get(self, key, default=''):
        return self._data.get(str(key).lower(), default)


class _Request:
    def __init__(self, headers):
        self.headers = _Headers(headers)


def test_gmail_aliases_are_one_inbox(ident):
    assert ident.canonical_email('A.B+promo@GoogleMail.com') == 'ab@gmail.com'
    assert ident.canonical_email('first.last+tag@example.com') == 'first.last@example.com'
    # Dots outside Gmail are a different address.
    assert ident.canonical_email('first.last@example.com') == 'first.last@example.com'
    with pytest.raises(ident.IdentityError):
        ident.canonical_email('+tag@gmail.com')


def test_gmail_aliases_share_one_code_and_one_attempt_count(ident):
    code = ident.issue_code('a.b+tag@gmail.com')
    with pytest.raises(ident.IdentityError):
        ident.verify_code('ab@gmail.com', '000000')
    assert ident.verify_code('ab@googlemail.com', code).startswith('acct_')


def test_a_fresh_code_does_not_reset_the_attempt_count(ident):
    """Requesting another code used to DELETE the row and start attempts at 0."""
    import wallet
    ident.issue_code('buyer@example.com')
    for _ in range(4):
        with pytest.raises(ident.IdentityError):
            ident.verify_code('buyer@example.com', '000000')
    fresh = ident.issue_code('buyer@example.com')
    with pytest.raises(ident.IdentityError):
        ident.verify_code('buyer@example.com', '000000')
    with pytest.raises(ident.IdentityError):
        ident.verify_code('buyer@example.com', fresh)
    cur = wallet._execute(
        'SELECT attempts FROM login_code WHERE email = ?', ('buyer@example.com',))
    assert cur.fetchone()[0] == 5
    with pytest.raises(ident.IdentityError, match='15 minutes'):
        ident.issue_code('buyer@example.com')


def test_the_lockout_ends_after_fifteen_minutes(ident, monkeypatch):
    ident.issue_code('buyer@example.com')
    for _ in range(5):
        with pytest.raises(ident.IdentityError):
            ident.verify_code('buyer@example.com', '000000')
    with pytest.raises(ident.IdentityError):
        ident.issue_code('buyer@example.com')
    real = time.time
    monkeypatch.setattr(
        ident.time, 'time', lambda: real() + ident.FAILURE_WINDOW_SECONDS + 1)
    code = ident.issue_code('buyer@example.com')
    assert ident.verify_code('buyer@example.com', code).startswith('acct_')


def test_a_guess_past_the_cap_does_not_increment(ident):
    """The cap is in the UPDATE, so a sixth guess changes nothing."""
    import wallet
    ident.issue_code('buyer@example.com')
    for _ in range(5):
        with pytest.raises(ident.IdentityError):
            ident.verify_code('buyer@example.com', '000000')
    with pytest.raises(ident.IdentityError, match='too many attempts'):
        ident.verify_code('buyer@example.com', '000000')
    cur = wallet._execute(
        'SELECT attempts FROM login_code WHERE email = ?', ('buyer@example.com',))
    assert cur.fetchone()[0] == 5


def test_parallel_guesses_stop_at_five(ident):
    import wallet
    ident.issue_code('buyer@example.com')
    for _ in range(4):
        with pytest.raises(ident.IdentityError):
            ident.verify_code('buyer@example.com', '000000')
    errors = []

    def guess():
        try:
            ident.verify_code('buyer@example.com', '000000')
        except ident.IdentityError as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=guess) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    cur = wallet._execute(
        'SELECT attempts FROM login_code WHERE email = ?', ('buyer@example.com',))
    assert cur.fetchone()[0] == 5
    assert len(errors) == 8


def test_resend_is_limited_per_inbox(ident, monkeypatch):
    clock = {'t': time.time()}
    monkeypatch.setattr(ident.time, 'time', lambda: clock['t'])
    for _ in range(ident.MAX_CODES_PER_WINDOW):
        ident.claim_send('a.b+x@gmail.com')
        clock['t'] += ident.RESEND_COOLDOWN_SECONDS
    # The dotted alias is the same Gmail inbox, so it shares the cap.
    with pytest.raises(ident.IdentityError, match='15 minutes'):
        ident.claim_send('ab@gmail.com')
    clock['t'] += ident.SEND_WINDOW_SECONDS
    ident.claim_send('ab@gmail.com')


def test_a_second_request_inside_a_minute_does_not_send_mail(ident, monkeypatch):
    import json
    import accounts
    monkeypatch.setattr(accounts, 'identity', ident)
    sent = []
    monkeypatch.setattr(
        accounts.mailer, 'send_login_code', lambda email, code: sent.append(email) or 'test')

    import asyncio
    first = asyncio.run(accounts.request_code(
        accounts.EmailRequest(email='flood@example.com'), _Request({})))
    second = asyncio.run(accounts.request_code(
        accounts.EmailRequest(email='flood@example.com'), _Request({})))
    assert first == {'sent': True, 'expires_in': ident.CODE_TTL_SECONDS}
    assert second.status_code == 429
    assert json.loads(second.body)['error'] == ident.COOLDOWN_MESSAGE
    assert sent == ['flood@example.com']


def test_a_locked_inbox_is_not_emailed(ident, monkeypatch):
    import json
    import accounts
    monkeypatch.setattr(accounts, 'identity', ident)
    sent = []
    monkeypatch.setattr(
        accounts.mailer, 'send_login_code', lambda email, code: sent.append(email) or 'test')
    ident.issue_code('buyer@example.com')
    for _ in range(5):
        with pytest.raises(ident.IdentityError):
            ident.verify_code('buyer@example.com', '000000')

    import asyncio
    resp = asyncio.run(accounts.request_code(
        accounts.EmailRequest(email='buyer@example.com'), _Request({})))
    assert resp.status_code == 429
    assert '15 minutes' in json.loads(resp.body)['error']
    assert sent == []


def test_an_unverified_ip_is_ignored(ident, monkeypatch):
    """X-Forwarded-For on the raw Render URL is not a visitor IP."""
    monkeypatch.setenv('CF_VISITOR_SECRET', 'shared-secret')
    spoofed = _Headers({
        'X-Forwarded-For': '203.0.113.8',
        'X-Visitor-IP': '203.0.113.8',
        'X-Visitor-Secret': 'not-the-secret',
    })
    assert ident.verified_client_ip(spoofed) is None
    monkeypatch.delenv('CF_VISITOR_SECRET', raising=False)
    matching = _Headers({
        'X-Visitor-IP': '203.0.113.8',
        'X-Visitor-Secret': 'shared-secret',
        'X-Forwarded-For': '198.51.100.4',
    })
    # Secret not configured: do not block, and do not trust the header.
    assert ident.verified_client_ip(matching) is None
    ident.claim_send('direct@example.com', ident.verified_client_ip(matching))


def test_a_verified_ip_is_capped_across_inboxes(ident, monkeypatch):
    import json
    import accounts
    monkeypatch.setenv('CF_VISITOR_SECRET', 'shared-secret')
    monkeypatch.setattr(accounts, 'identity', ident)
    sent = []
    monkeypatch.setattr(
        accounts.mailer, 'send_login_code', lambda email, code: sent.append(email) or 'test')
    headers = {
        'X-Visitor-IP': '203.0.113.8',
        'X-Visitor-Secret': 'shared-secret',
    }
    import asyncio
    last = None
    for n in range(ident.MAX_CODES_PER_IP + 1):
        last = asyncio.run(accounts.request_code(
            accounts.EmailRequest(email='person%d@example.com' % n),
            _Request(headers)))
    assert last.status_code == 429
    assert json.loads(last.body)['error'] == ident.SEND_CAP_MESSAGE
    assert len(sent) == ident.MAX_CODES_PER_IP


def test_a_spoofed_forwarded_for_does_not_share_the_ip_cap(ident, monkeypatch):
    """Same claimed IP, but the secret does not match, so each inbox is its own cap."""
    monkeypatch.setenv('CF_VISITOR_SECRET', 'shared-secret')
    for n in range(ident.MAX_CODES_PER_IP + 1):
        ident.claim_send(
            'other%d@example.com' % n,
            ident.verified_client_ip(_Headers({
                'X-Forwarded-For': '203.0.113.8',
                'X-Visitor-IP': '203.0.113.8',
                'X-Visitor-Secret': 'wrong',
            })))


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

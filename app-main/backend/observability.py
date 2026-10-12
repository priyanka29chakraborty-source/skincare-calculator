"""Error monitoring.

Without this, a 500 in production is invisible: the user sees a generic error,
the traceback goes to stdout, and nobody is told. You find out when someone
complains, or you never find out.

Deliberately optional. If SENTRY_DSN is unset - local development, or a
deployment that has not configured it - every function here is a no-op and the
app behaves exactly as before. Monitoring must never be the reason the app
fails to start.

PRIVACY: send_default_pii is off, and before_send strips the fields users
actually type. Ingredient lists and product names are user-submitted content;
they belong in your own logs, not in a third-party error tracker.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

_ENABLED = False

# Request fields that carry user-submitted content. Scrubbed before anything
# leaves the process.
_SENSITIVE_FIELDS = (
    'ingredients', 'product_name', 'brand', 'url', 'barcode',
    'password', 'admin_session', 'x-csrf-token', 'cookie', 'authorization',
    'active_concentrations', 'email', 'current_routine', 'note', 'code',
    'dsn', 'smtp_password', 'aiven_pg_url',
)
_SECRET_TEXT = re.compile(
    r'(?i)(?:postgres|postgresql|mysql|mongodb|redis|amqp)://\S+'
    r'|https?://[^\s/@]+:[^\s/@]+@[^\s]+'
    r'|(?:password|secret|dsn)\s*[=:]\s*\S+'
)


def _redact_text(value):
    if not isinstance(value, str):
        return value
    return _SECRET_TEXT.sub('[scrubbed]', value)


def _scrub(event, _hint):
    """Remove user content and secrets from an event before it is sent."""
    try:
        req = event.get('request') or {}

        # Request body
        data = req.get('data')
        if isinstance(data, dict):
            for k in list(data):
                if k.lower() in _SENSITIVE_FIELDS:
                    data[k] = '[scrubbed]'

        # Headers and cookies
        headers = req.get('headers')
        if isinstance(headers, dict):
            for k in list(headers):
                if k.lower() in _SENSITIVE_FIELDS:
                    headers[k] = '[scrubbed]'
        req.pop('cookies', None)

        # Query string can carry a barcode or url
        if req.get('query_string'):
            for f in ('url', 'barcode'):
                if f in str(req['query_string']).lower():
                    req['query_string'] = '[scrubbed]'
                    break

        # Local variables and the exception text. A database error often
        # quotes the connection address, which is not a field name.
        for exc in (event.get('exception') or {}).get('values') or []:
            if isinstance(exc.get('value'), str):
                exc['value'] = _redact_text(exc['value'])
            for frame in (exc.get('stacktrace') or {}).get('frames') or []:
                vars_ = frame.get('vars')
                if isinstance(vars_, dict):
                    for k in list(vars_):
                        if k.lower() in _SENSITIVE_FIELDS:
                            vars_[k] = '[scrubbed]'
                        elif isinstance(vars_[k], str):
                            vars_[k] = _redact_text(vars_[k])
    except Exception:
        # Never let scrubbing raise - a broken scrubber must not suppress the
        # error report, but it must also not send unscrubbed data. Dropping the
        # event is the safe failure.
        return None
    return event


def init_error_monitoring(app=None):
    """Wire up Sentry if configured. Safe to call unconditionally."""
    global _ENABLED
    dsn = os.environ.get('SENTRY_DSN', '').strip()
    if not dsn:
        logger.info("SENTRY_DSN not set - error monitoring disabled")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed")
        return False

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get('ENVIRONMENT', 'production'),
            release=os.environ.get('RENDER_GIT_COMMIT', '')[:12] or None,
            integrations=[StarletteIntegration(), FastApiIntegration()],
            # Tracing at 10% of requests. The Sentry SDK treats tracing as part
            # of its recommended default init, and on this app it answers a
            # question errors cannot: which analysis is slow, and whether it is
            # our scoring or a third-party scrape. Sampled rather than full
            # because traces are billed by volume and 10% is plenty to see a
            # pattern. SENTRY_TRACES_SAMPLE_RATE overrides it; 0 turns it off.
            traces_sample_rate=float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '0.1')),
            send_default_pii=False,
            before_send=_scrub,
            max_breadcrumbs=25,
        )
        _ENABLED = True
        logger.info("Error monitoring enabled")
        return True
    except Exception as exc:
        # A misconfigured DSN must not prevent the app from starting.
        logger.warning("Could not initialise error monitoring: %s", exc)
        return False


def capture(exc, **context):
    """Report a handled exception that would otherwise be swallowed.

    Use at points where the app deliberately degrades - a failed scrape, a
    third-party timeout - so that silent fallbacks are still visible.
    """
    if not _ENABLED:
        return
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for k, v in context.items():
                scope.set_tag(k, str(v)[:200])
            sentry_sdk.capture_exception(exc)
    except Exception:
        pass


def is_enabled():
    return _ENABLED

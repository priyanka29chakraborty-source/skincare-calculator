"""Sending login codes.

Deliberately small. SMTP when configured, and in development the code goes to
the log instead so the whole flow can be exercised without a mail account.

The development fallback is gated on an explicit environment variable rather
than on "SMTP is not configured", because the failure mode of getting that
wrong is login codes printed into production logs. If SMTP is missing and
MAIL_DEV_ECHO is not set, sending fails loudly.
"""

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

logger = logging.getLogger(__name__)


class MailNotConfigured(Exception):
    pass


class MailFailed(Exception):
    pass


def _cfg(name, default=''):
    return os.environ.get(name, default).strip()


def is_configured():
    return bool(_cfg('SMTP_HOST') and _cfg('SMTP_FROM'))


def dev_echo_enabled():
    return _cfg('MAIL_DEV_ECHO').lower() in ('1', 'true', 'yes')


def send_login_code(email, code):
    """Deliver a login code. Returns the transport used, for the caller's log."""
    subject = 'Your Urancal sign-in code'
    body = (
        'Your sign-in code is {code}\n\n'
        'It expires in 10 minutes and can be used once.\n\n'
        'If you did not ask to sign in, you can ignore this email - someone '
        'typed your address by mistake, and nothing has happened to your '
        'account.\n'
    ).format(code=code)

    if is_configured():
        _send_smtp(email, subject, body)
        return 'smtp'

    if dev_echo_enabled():
        # Never reached in production unless MAIL_DEV_ECHO is deliberately set.
        logger.warning('MAIL_DEV_ECHO: login code for %s is %s', email, code)
        return 'dev-echo'

    raise MailNotConfigured(
        'SMTP_HOST and SMTP_FROM are not set, and MAIL_DEV_ECHO is off')


def _send_smtp(to_address, subject, body):
    message = EmailMessage()
    message['From'] = _cfg('SMTP_FROM')
    message['To'] = to_address
    message['Subject'] = subject
    message.set_content(body)

    host = _cfg('SMTP_HOST')
    port = int(_cfg('SMTP_PORT', '587') or 587)
    user = _cfg('SMTP_USER')
    password = _cfg('SMTP_PASSWORD')

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=20,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            server.starttls(context=ssl.create_default_context())
        with server:
            if user:
                server.login(user, password)
            server.send_message(message)
    except Exception as exc:
        # The address is in the exception text on some servers, so log the
        # failure without the message body or the code.
        logger.error('SMTP send failed: %s: %s', type(exc).__name__, exc)
        raise MailFailed('could not send the email')

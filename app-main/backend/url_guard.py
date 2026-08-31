"""SSRF guard for the product-fetch pipeline.

/api/fetch-product takes a URL from an unauthenticated caller and fetches it
server-side. Without validation that is a server-side request forgery primitive:
an attacker can point it at cloud metadata (169.254.169.254), at loopback, or at
any host on the private network the backend runs in, and read back whatever the
HTML parser can extract from the response.

This module is the single choke point. Call `validate_public_url()` before any
outbound request, and re-check every redirect hop, since a permitted host can
redirect to a forbidden one.
"""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = ('http', 'https')

# Hostnames that must never be resolved or fetched, regardless of what they
# resolve to today.
_BLOCKED_HOSTNAMES = {
    'localhost', 'localhost.localdomain', 'ip6-localhost', 'ip6-loopback',
    'metadata', 'metadata.google.internal', 'metadata.goog',
    'instance-data', 'instance-data.ec2.internal',
}

# Cloud instance-metadata endpoints. These are link-local and therefore already
# covered by the range check, but are named explicitly so the intent is obvious
# to anyone reading or auditing this.
_METADATA_IPS = {
    '169.254.169.254',   # AWS / GCP / Azure / DigitalOcean / Oracle
    '169.254.170.2',     # AWS ECS task metadata
    '100.100.100.200',   # Alibaba Cloud
    'fd00:ec2::254',     # AWS IMDSv2 over IPv6
}


class UnsafeURLError(ValueError):
    """Raised when a URL must not be fetched server-side."""


def _ip_is_forbidden(ip):
    """True for any address that is not a normal, routable public host."""
    return (
        ip.is_private          # RFC1918 / RFC4193 unique-local
        or ip.is_loopback      # 127.0.0.0/8, ::1
        or ip.is_link_local    # 169.254.0.0/16, fe80::/10 - cloud metadata
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified   # 0.0.0.0, ::
        or (getattr(ip, 'is_site_local', False))  # deprecated IPv6 site-local
    )


def _resolve(hostname):
    """Resolve a hostname to every address it maps to.

    All of them are checked, not just the first: a hostname with one public and
    one private A record must be rejected outright.
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UnsafeURLError("Could not resolve host: {}".format(hostname)) from exc
    addresses = set()
    for family, _type, _proto, _canon, sockaddr in infos:
        addresses.add(sockaddr[0])
    return addresses


def validate_public_url(url, _redirect_depth=0):
    """Return the URL if it is safe to fetch server-side, else raise.

    Rejects non-http(s) schemes (file://, gopher://, ftp://), credentials
    embedded in the URL, blocked hostnames, and any host resolving to a
    loopback, link-local, private, reserved or multicast address.
    """
    if not url or not isinstance(url, str):
        raise UnsafeURLError("No URL provided.")

    url = url.strip()
    if len(url) > 2048:
        raise UnsafeURLError("URL is too long.")

    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise UnsafeURLError("Malformed URL.") from exc

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeURLError(
            "Only http and https URLs can be fetched (got {!r}).".format(
                parsed.scheme or 'none'))

    # Credentials in the URL are a common way to confuse host parsing.
    if parsed.username or parsed.password:
        raise UnsafeURLError("URLs containing credentials are not accepted.")

    hostname = (parsed.hostname or '').strip().lower().rstrip('.')
    if not hostname:
        raise UnsafeURLError("URL has no host.")

    if hostname in _BLOCKED_HOSTNAMES:
        raise UnsafeURLError("This host is not permitted.")

    # A literal IP in the URL is checked directly, without a DNS round trip.
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None

    if literal is not None:
        if str(literal) in _METADATA_IPS or _ip_is_forbidden(literal):
            raise UnsafeURLError("This address is not permitted.")
        return url

    for addr in _resolve(hostname):
        if addr in _METADATA_IPS:
            raise UnsafeURLError("This address is not permitted.")
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            raise UnsafeURLError("Host resolved to an unreadable address.")
        if _ip_is_forbidden(ip):
            # Deliberately vague to the caller; specific in the log.
            logger.warning(
                "Blocked SSRF attempt: %s resolved to %s", hostname, addr)
            raise UnsafeURLError("This address is not permitted.")

    return url


def is_safe_public_url(url):
    """Boolean form, for call sites that filter lists of URLs."""
    try:
        validate_public_url(url)
        return True
    except UnsafeURLError:
        return False
    except Exception:
        return False

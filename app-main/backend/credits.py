"""API credit tracking with monthly limits and per-API renewal dates."""

# renewal_day: the day of month each plan resets (1-based).
# limit/per_call values remain unchanged.
CREDIT_LIMITS = {
    'firecrawl':       {'limit': 500,  'per_call': 1,  'free': True,  'renewal_day': 5},
    'scrapdo':         {'limit': 1000, 'per_call': 5,  'free': False, 'renewal_day': 5},
    'scraperapi':      {'limit': 1000, 'per_call': 10, 'free': True,  'renewal_day': 7},
    'huggingface':     {'limit': 500,  'per_call': 1,  'free': True,  'renewal_day': 1},
    'exchangerate':    {'limit': 1500, 'per_call': 1,  'free': True,  'renewal_day': 1},
    'duckduckgo':      {'limit': None, 'per_call': 0,  'free': True,  'renewal_day': 1},
    'openbeautyfacts': {'limit': None, 'per_call': 0,  'free': True,  'renewal_day': 1},
    'serpapi':         {'limit': 100,  'per_call': 1,  'free': True,  'renewal_day': 7},
}


def _next_renewal_date(renewal_day, now, calendar):
    """Compute the next renewal date given a renewal_day (1-based day of month)."""
    import datetime
    try:
        candidate = now.replace(day=renewal_day, hour=0, minute=0, second=0, microsecond=0)
    except ValueError:
        # renewal_day doesn't exist in this month (e.g. day 31 in April) — use last day
        last_day = calendar.monthrange(now.year, now.month)[1]
        candidate = now.replace(day=last_day, hour=0, minute=0, second=0, microsecond=0)
    if candidate.date() <= now.date():
        # Already passed — next occurrence is next month
        year = now.year + (now.month // 12)
        month = (now.month % 12) + 1
        try:
            candidate = candidate.replace(year=year, month=month)
        except ValueError:
            last_day = calendar.monthrange(year, month)[1]
            candidate = candidate.replace(year=year, month=month, day=last_day)
    return candidate


def get_credit_status(credits_summary):
    """Build credit status with usage bars, warnings and per-API renewal dates."""
    from datetime import datetime, timezone
    import calendar

    now = datetime.now(timezone.utc)
    # Generic fallback: days remaining in month
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    generic_days_remaining = days_in_month - now.day + 1

    result = []
    warnings = []

    for api_name, config in CREDIT_LIMITS.items():
        usage = credits_summary.get(api_name, {'used': 0, 'calls': 0})
        used = usage['used']
        calls = usage['calls']
        limit = config['limit']
        renewal_day = config.get('renewal_day', 1)

        # Compute next renewal date for this specific API
        next_renewal = _next_renewal_date(renewal_day, now, calendar)
        days_remaining = max(0, (next_renewal.date() - now.date()).days)
        next_renewal_str = next_renewal.strftime('%-d %b')  # e.g. "7 Apr"

        if limit is not None:
            pct = round(used / limit * 100, 1) if limit > 0 else 0
            remaining = max(0, limit - used)
            if pct >= 80:
                warnings.append(
                    f"{api_name.title()} is at {pct}% — consider reducing usage or upgrading plan"
                )
        else:
            pct = 0
            remaining = None

        result.append({
            'name': api_name,
            'display_name': api_name.replace('_', ' ').title(),
            'used': used,
            'calls': calls,
            'limit': limit,
            'remaining': remaining,
            'pct': pct,
            'per_call': config['per_call'],
            'days_remaining': days_remaining,
            'next_renewal': next_renewal_str,
            'unlimited': limit is None,
        })

    return result, warnings

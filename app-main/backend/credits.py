"""API credit tracking with monthly limits."""

CREDIT_LIMITS = {
    'firecrawl':       {'limit': 500,  'per_call': 1,  'free': True},
    'scrapdo':         {'limit': 1000, 'per_call': 5,  'free': False},
    'scraperapi':      {'limit': 1000, 'per_call': 10, 'free': True},
    'huggingface':     {'limit': 500,  'per_call': 1,  'free': True},
    'exchangerate':    {'limit': 1500, 'per_call': 1,  'free': True},
    'duckduckgo':      {'limit': None, 'per_call': 0,  'free': True},
    'openbeautyfacts': {'limit': None, 'per_call': 0,  'free': True},
    'serpapi':         {'limit': 100,  'per_call': 1,  'free': True},
}


def get_credit_status(credits_summary):
    """Build credit status with usage bars and warnings."""
    from datetime import datetime, timezone
    import calendar

    now = datetime.now(timezone.utc)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    days_remaining = days_in_month - now.day + 1

    result = []
    warnings = []

    for api_name, config in CREDIT_LIMITS.items():
        usage = credits_summary.get(api_name, {'used': 0, 'calls': 0})
        used = usage['used']
        calls = usage['calls']
        limit = config['limit']

        if limit is not None:
            pct = round(used / limit * 100, 1) if limit > 0 else 0
            remaining = max(0, limit - used)
            if pct >= 80:
                warnings.append(f"{api_name.title()} is at {pct}% — consider reducing usage or upgrading plan")
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
            'unlimited': limit is None,
        })

    return result, warnings

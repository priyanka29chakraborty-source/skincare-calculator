"""Reviewed evidence for score-driving ingredients.

Reviews are written by a person into evidence_reviews.json. This module
attaches a review when one exists and reports what is still unsigned.
It does not invent a source, a reviewer, or a date.
"""

import json
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'evidence_reviews.json')

_ACTIVE_CLASSES = ('active', 'retinoid', 'brightening active', 'peptide')


def _load():
    try:
        with open(_PATH, encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    reviews = data.get('reviews') if isinstance(data, dict) else None
    return reviews if isinstance(reviews, dict) else {}


def review_for(name):
    """A signed review, or None. A blank reviewer is not a review."""
    row = _load().get((name or '').strip().lower())
    if not isinstance(row, dict):
        return None
    if not str(row.get('reviewer') or '').strip():
        return None
    if not str(row.get('source') or '').strip():
        return None
    return {
        'source': str(row['source']).strip(),
        'evidence_level': str(row.get('evidence_level') or '').strip(),
        'reviewed_at': str(row.get('reviewed_at') or '').strip(),
        'reviewer': str(row['reviewer']).strip(),
    }


def attach(result):
    """Add provenance to actives that have a signed review. Leave the rest alone."""
    if not isinstance(result, dict):
        return result
    for active in result.get('identified_actives') or []:
        if not isinstance(active, dict):
            continue
        found = review_for(active.get('name'))
        if found:
            active['provenance'] = found
    return result


def _unsigned_names():
    import data_loader
    seen = set()
    pregnancy = []
    actives = []
    for entry in data_loader.data_loader.ingredient_lookup.values():
        if not isinstance(entry, dict):
            continue
        key = id(entry)
        if key in seen:
            continue
        seen.add(key)
        name = str(entry.get('INCI_Name') or '').strip()
        if not name or review_for(name):
            continue
        if str(entry.get('Pregnancy_Safety') or '').strip():
            pregnancy.append(name)
        klass = str(entry.get('Ingredient_Class') or '').lower()
        if klass in _ACTIVE_CLASSES and not str(entry.get('Evidence_Strength') or '').strip():
            actives.append(name)
    return pregnancy, actives


def queue_counts():
    """How many score-driving records still have no signed review.

    Pregnancy lines and actives are counted separately. A record is signed
    only when evidence_reviews.json names both a reviewer and a source.
    """
    pregnancy, actives = _unsigned_names()
    return {'pregnancy_unsigned': len(pregnancy), 'actives_missing_evidence': len(actives)}

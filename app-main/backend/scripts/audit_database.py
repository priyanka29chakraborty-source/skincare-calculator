# -*- coding: utf-8 -*-
"""Data-quality audit of the ingredient database.

Written after a card showed "Add-On: Adapalene / Key active ingredient:
Niacinamide". That one turned out to be a mislabelled field rather than bad
data, but the question it raised - how many more are there - deserved an
answer rather than an assurance.

Each check looks for a claim the data makes that contradicts another claim it
makes. Internal contradictions are findable; being wrong about the world is
not, and this script does not pretend otherwise.

    python scripts/audit_database.py
"""
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(HERE, 'database')


def _db_path():
    for name in (
        'Urancal Ingredient Database.json',
        'urancal_ingredient_database.json',
        'ingredients.json',
    ):
        path = os.path.join(DB_DIR, name)
        if os.path.exists(path):
            return path
    raise FileNotFoundError('Urancal Ingredient Database.json not found in %s' % DB_DIR)


def _num(value):
    try:
        text = str(value).strip().replace('%', '')
        return float(text) if text and text.lower() != 'nan' else None
    except (TypeError, ValueError):
        return None


def load():
    with open(_db_path(), encoding='utf-8') as handle:
        return json.load(handle)['ingredients']


def audit(records):
    findings = defaultdict(list)

    for key, entry in records.items():
        name = entry.get('INCI_Name') or key
        lo, opt, hi = (_num(entry.get('Min_Effective_%')),
                       _num(entry.get('Optimal_%')),
                       _num(entry.get('Max_Safe_%')))

        # 1. Dose ranges that cannot be satisfied. These drive the "within its
        #    evidenced range" sentence, so an inverted range makes the app
        #    state something impossible.
        if lo is not None and hi is not None and lo > hi:
            findings['dose range: minimum above maximum'].append(
                '%s: min %s > max %s' % (name, lo, hi))
        if opt is not None and lo is not None and opt < lo:
            findings['dose range: optimal below minimum'].append(
                '%s: optimal %s < min %s' % (name, opt, lo))
        if opt is not None and hi is not None and opt > hi:
            findings['dose range: optimal above maximum'].append(
                '%s: optimal %s > max %s' % (name, opt, hi))

        # 1b. A legal cap above the toxicological ceiling makes no sense: the
        #     law does not permit more than is safe. The reverse is ordinary -
        #     D5 is safe at 5% and capped at 0.1% for persistence, not toxicity.
        eu = _num(entry.get('Max_Allowed_EU_%'))
        if eu is not None and hi is not None and eu > hi:
            findings['EU cap above the safety ceiling'].append(
                '%s: EU %s > safe %s' % (name, eu, hi))

        # 2. An ingredient listed as working synergistically with itself.
        partners = [p.strip().lower() for p in
                    str(entry.get('Synergistic_Ingredients') or '').split(';') if p.strip()]
        if str(name).strip().lower() in partners:
            findings['synergy: paired with itself'].append(str(name))

        # 3. Contradictory pregnancy guidance in one record.
        #
        # Narrower than it first was. Matching "safe" and "avoid" anywhere in
        # the field flagged three entries that are perfectly coherent:
        #   "Safe; avoid sun exposure after use"        - avoids the sun
        #   "Strictly Avoid - insufficient safety data" - the word inside
        #                                                 "safety"
        #   "Safe for most; avoid if lactose sensitive" - a named exception
        # A real contradiction is a verdict of safe and a verdict of avoid
        # about the ingredient itself, so only the opening verdict counts.
        preg = str(entry.get('Pregnancy_Safety') or '').strip().lower()
        verdict = re.split(r'[;,.—-]', preg)[0] if preg else ''
        if 'avoid' in verdict and re.search(r'\bsafe\b', verdict):
            findings['pregnancy: says both safe and avoid'].append(
                '%s: %s' % (name, preg[:80]))

        # 4. Comedogenicity outside the 0-5 scale the field is named for.
        com = _num(entry.get('Comedogenicity_0_5'))
        if com is not None and not (0 <= com <= 5):
            findings['comedogenic rating outside 0-5'].append('%s: %s' % (name, com))

        # 5. Classed as an active with no benefit recorded - these reach the
        #    "adds ..." line in the pairings card.
        klass = str(entry.get('Ingredient_Class') or '').lower()
        if klass in ('active', 'retinoid', 'brightening active'):
            if not str(entry.get('Primary_Benefits') or '').strip():
                findings['active with no Primary_Benefits'].append(str(name))

        # 6. Evidence strength missing on an active, which the scoring engine
        #    reads directly.
        if klass in ('active', 'retinoid', 'brightening active'):
            if not str(entry.get('Evidence_Strength') or '').strip():
                findings['active with no Evidence_Strength'].append(str(name))

    # 7. Two records claiming the same INCI name.
    by_inci = defaultdict(list)
    for key, entry in records.items():
        inci = str(entry.get('INCI_Name') or '').strip().lower()
        if inci:
            by_inci[inci].append(key)
    for inci, keys in by_inci.items():
        if len(keys) > 1:
            findings['duplicate INCI name'].append('%s: %s' % (inci, ', '.join(keys)))

    return findings


def main():
    records = load()
    findings = audit(records)

    print('Audited %d ingredient records.\n' % len(records))
    if not findings:
        print('No internal contradictions found.')
        return 0

    total = 0
    for check in sorted(findings):
        rows = findings[check]
        total += len(rows)
        print('%-42s %d' % (check, len(rows)))
        for row in rows[:6]:
            print('    - %s' % row)
        if len(rows) > 6:
            print('    ... and %d more' % (len(rows) - 6))
        print()

    print('%d findings across %d checks.' % (total, len(findings)))
    return 0


if __name__ == '__main__':
    sys.exit(main())

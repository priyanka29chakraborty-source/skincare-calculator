# -*- coding: utf-8 -*-
"""Separate "how much is toxicologically safe" from "how much the law allows".

Max_Safe_% was carrying both meanings, which is why Cyclopentasiloxane read
min 1.0 / max 0.1: the floor was a formulator's use level for slip and the
ceiling was the EU 2024/1328 restriction. Those are not the same kind of
number and cannot be compared. D5 is not toxic at 5%; it is simply no longer
permitted above 0.1%.

Three fields now:

    Min_Effective_%    the level at which it does its job
    Max_Safe_%         toxicological ceiling (100.0 where nothing limits it)
    Max_Allowed_EU_%   what EU cosmetics regulation permits

Only the two silicones are given values here. The survey found 24 other
records whose Regional_Restrictions text mentions a percentage, and several
look as though Max_Safe_% holds a legal cap rather than a safety ceiling -
Phenoxyethanol at 1.0 is the Annex V limit, Limonene at 0.1 is not obviously
either. Those are judgements about regulation that want a person who can cite
the instrument, so this script lists them and changes nothing about them.

    python scripts/add_eu_limit_field.py          # report only
    python scripts/add_eu_limit_field.py --write  # apply
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_DIR = os.path.join(HERE, 'database')


def _resolve_db_path():
    for name in (
        'Urancal Ingredient Database.json',
        'urancal_ingredient_database.json',
        'ingredients.json',
    ):
        path = os.path.join(_DB_DIR, name)
        if os.path.exists(path):
            return path
    return os.path.join(_DB_DIR, 'Urancal Ingredient Database.json')


JSON_PATH = _resolve_db_path()

# INCI key -> (Min_Effective_%, Optimal_%, Max_Safe_%, Max_Allowed_EU_%, note)
#
# D5/D6: restricted to 0.1% in all cosmetics from 6 June 2026 under EU
# 2024/1328, classified vPvB. Not a toxicity limit - an environmental
# persistence one - so Max_Safe_% is the toxicological answer and the cap sits
# in its own field.
CORRECTIONS = {
    'cyclopentasiloxane': ('1.0', '5.0', '100.0', '0.1',
                           'EU 2024/1328: 0.1% in all cosmetics from 2026-06-06 (vPvB)'),
    'cyclohexasiloxane': ('1.0', '10.0', '100.0', '0.1',
                          'EU 2024/1328: 0.1% in all cosmetics from 2026-06-06 (vPvB)'),
}


def main():
    write = '--write' in sys.argv
    with open(JSON_PATH, encoding='utf-8') as handle:
        doc = json.load(handle)
    records = doc['ingredients']

    # Every record gains the field so its absence never has to be guessed at.
    added = 0
    for entry in records.values():
        if 'Max_Allowed_EU_%' not in entry:
            entry['Max_Allowed_EU_%'] = ''
            added += 1

    applied = []
    for key, (lo, opt, safe, eu, note) in CORRECTIONS.items():
        entry = records.get(key)
        if entry is None:
            print('MISSING: %s' % key)
            continue
        entry['Min_Effective_%'] = lo
        entry['Optimal_%'] = opt
        entry['Max_Safe_%'] = safe
        entry['Max_Allowed_EU_%'] = eu
        entry['Data_Source'] = note
        applied.append('%s: effective %s-%s, safe to %s, EU cap %s'
                       % (entry.get('INCI_Name'), lo, opt, safe, eu))

    print('Added Max_Allowed_EU_%% to %d records.' % added)
    for line in applied:
        print('  set  ' + line)

    # Everything else that mentions a percentage in its restrictions text.
    pattern = re.compile(r'\d+(?:\.\d+)?\s*%')
    review = []
    for key, entry in records.items():
        if key in CORRECTIONS:
            continue
        restrictions = str(entry.get('Regional_Restrictions') or '')
        if restrictions.strip() and pattern.search(restrictions):
            review.append('%-28s Max_Safe_%%=%-8s %s'
                          % (str(entry.get('INCI_Name'))[:28],
                             entry.get('Max_Safe_%'), restrictions[:76]))

    print('\n%d records mention a regulatory percentage and were NOT changed.' % len(review))
    print('Each needs someone who can cite the instrument to say whether '
          'Max_Safe_%% is a safety ceiling or a legal cap:\n')
    for line in sorted(review):
        print('  ' + line)

    if write:
        with open(JSON_PATH, 'w', encoding='utf-8') as handle:
            json.dump(doc, handle, ensure_ascii=False, separators=(',', ':'))
        print('\nWritten.')
    else:
        print('\nDry run. Pass --write to apply.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

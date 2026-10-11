"""The audit's own checks work.

"No contradictions found" is the same output whether the checks are working or
matching nothing, and this file exists because that is not hypothetical: a
patch script wrote the word boundaries in audit_database.py as literal
backspace characters twice, and the audit went on reporting a clean database
while matching nothing at all. A green check that cannot fail is worse than no
check, because it is believed.

Every check is fed a record that must trip it and one that must not.
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'scripts'))

from scripts.audit_database import audit  # noqa: E402


def flagged(check, record):
    findings = audit({'key': record})
    return bool(findings.get(check))


@pytest.mark.parametrize('record', [
    {'INCI_Name': 'Bad', 'Min_Effective_%': '5', 'Max_Safe_%': '1'},
])
def test_catches_a_minimum_above_the_maximum(record):
    assert flagged('dose range: minimum above maximum', record)


def test_allows_an_ordinary_dose_range():
    assert not flagged('dose range: minimum above maximum',
                       {'INCI_Name': 'Good', 'Min_Effective_%': '1', 'Max_Safe_%': '5'})


def test_catches_an_optimal_above_the_maximum():
    assert flagged('dose range: optimal above maximum',
                   {'INCI_Name': 'Bad', 'Optimal_%': '9', 'Max_Safe_%': '2'})


def test_catches_a_legal_cap_above_the_safety_ceiling():
    assert flagged('EU cap above the safety ceiling',
                   {'INCI_Name': 'Bad', 'Max_Allowed_EU_%': '10', 'Max_Safe_%': '2'})


def test_allows_a_legal_cap_below_the_safety_ceiling():
    """D5's actual shape: safe at 100, capped at 0.1 for persistence."""
    assert not flagged('EU cap above the safety ceiling',
                       {'INCI_Name': 'D5', 'Max_Allowed_EU_%': '0.1', 'Max_Safe_%': '100'})


def test_catches_an_ingredient_paired_with_itself():
    assert flagged('synergy: paired with itself',
                   {'INCI_Name': 'Niacinamide',
                    'Synergistic_Ingredients': 'Niacinamide;Zinc PCA'})


def test_allows_a_normal_synergy_pair():
    assert not flagged('synergy: paired with itself',
                       {'INCI_Name': 'Niacinamide', 'Synergistic_Ingredients': 'Zinc PCA'})


def test_catches_a_genuine_pregnancy_contradiction():
    assert flagged('pregnancy: says both safe and avoid',
                   {'INCI_Name': 'Bad', 'Pregnancy_Safety': 'Safe but avoid entirely'})


@pytest.mark.parametrize('text', [
    'Safe; avoid sun exposure after use',          # avoids the sun, not itself
    'Strictly Avoid - insufficient safety data',   # "safe" inside "safety"
    'Safe for most; avoid if lactose sensitive',   # a named exception
])
def test_does_not_flag_coherent_pregnancy_guidance(text):
    """The three real records this check flagged before it was narrowed. Each
    is coherent, so the check was wrong rather than the data."""
    assert not flagged('pregnancy: says both safe and avoid',
                       {'INCI_Name': 'Real', 'Pregnancy_Safety': text})


def test_catches_a_comedogenic_rating_off_the_scale():
    assert flagged('comedogenic rating outside 0-5',
                   {'INCI_Name': 'Bad', 'Comedogenicity_0_5': '9'})


def test_catches_an_active_missing_the_fields_the_engine_reads():
    assert flagged('active with no Primary_Benefits',
                   {'INCI_Name': 'Bad', 'Ingredient_Class': 'Active',
                    'Evidence_Strength': 'Strong'})
    assert flagged('active with no Evidence_Strength',
                   {'INCI_Name': 'Bad', 'Ingredient_Class': 'Active',
                    'Primary_Benefits': 'Brightening'})


def test_catches_two_records_claiming_one_name():
    findings = audit({'a': {'INCI_Name': 'Same'}, 'b': {'INCI_Name': 'Same'}})
    assert findings.get('duplicate INCI name')


def test_the_audit_source_has_no_mangled_escapes():
    """Guards the bug directly. A regex written through nested shell and Python
    escaping became chr(8) rather than a word boundary, so it matched nothing
    and the audit reported a clean database while checking nothing."""
    path = os.path.join(os.path.dirname(HERE), 'scripts', 'audit_database.py')
    with open(path, encoding='utf-8') as handle:
        source = handle.read()
    stray = sorted({hex(ord(c)) for c in source if ord(c) < 32 and c not in '\n\t'})
    assert not stray, 'control characters in audit source: %s' % stray

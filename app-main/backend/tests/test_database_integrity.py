"""The ingredient database does not contradict itself.

Added after a card read "Add-On: Adapalene / Key active ingredient:
Niacinamide". That one was a mislabelled field rather than bad data, but it
raised a fair question - how many more are there - and an assurance is not an
answer. These checks are the answer, and they run on every test pass so the
answer stays current.

They only catch claims the data makes that contradict other claims it makes.
Being wrong about the world is not detectable from inside the file, and
nothing here pretends otherwise: the open problem remains that roughly 96% of
records carry no citation.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.audit_database import audit, load  # noqa: E402


@pytest.fixture(scope='module')
def findings():
    return audit(load())


@pytest.fixture(scope='module')
def records():
    return load()


def test_the_database_has_no_internal_contradictions(findings):
    if findings:
        report = '\n'.join(
            '%s (%d): %s' % (check, len(rows), '; '.join(rows[:3]))
            for check, rows in sorted(findings.items()))
        pytest.fail('database audit found contradictions:\n' + report)


def test_dose_ranges_are_satisfiable(records):
    """min <= optimal <= max, or the engine can state an impossible dose.

    Cyclopentasiloxane and Cyclohexasiloxane held min 1.0 against max 0.1,
    because Max_Safe_% was carrying two meanings at once: a toxicological
    ceiling for most records and a legal cap for these. D5 is not toxic at 5%;
    it is simply not permitted above 0.1% under EU 2024/1328, for persistence
    rather than toxicity. The cap moved to Max_Allowed_EU_% and the efficacy
    figures went back to describing efficacy.
    """
    from scripts.audit_database import _num

    broken = []
    for key, entry in records.items():
        lo, opt, hi = (_num(entry.get('Min_Effective_%')),
                       _num(entry.get('Optimal_%')),
                       _num(entry.get('Max_Safe_%')))
        name = entry.get('INCI_Name') or key
        if lo is not None and hi is not None and lo > hi:
            broken.append('%s: min %s > max %s' % (name, lo, hi))
        if opt is not None and hi is not None and opt > hi:
            broken.append('%s: optimal %s > max %s' % (name, opt, hi))
    assert not broken, broken


def test_every_active_has_the_fields_the_engine_reads(records):
    """Evidence strength and benefits reach the score and the pairings card."""
    missing = []
    for key, entry in records.items():
        klass = str(entry.get('Ingredient_Class') or '').lower()
        if klass not in ('active', 'retinoid', 'brightening active'):
            continue
        name = entry.get('INCI_Name') or key
        if not str(entry.get('Evidence_Strength') or '').strip():
            missing.append('%s: no Evidence_Strength' % name)
        if not str(entry.get('Primary_Benefits') or '').strip():
            missing.append('%s: no Primary_Benefits' % name)
    assert not missing, missing


def test_no_ingredient_is_its_own_synergy_partner(records):
    bad = []
    for key, entry in records.items():
        name = str(entry.get('INCI_Name') or key).strip().lower()
        partners = [p.strip().lower() for p in
                    str(entry.get('Synergistic_Ingredients') or '').split(';') if p.strip()]
        if name in partners:
            bad.append(name)
    assert not bad, bad


# ---------------------------------------------------------------------------
# The upgrade map
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def upgrade_map():
    import pandas as pd
    from data_loader import data_loader
    if data_loader.active_upgrade_map is not None:
        return data_loader.active_upgrade_map
    return pd.DataFrame()


def test_upgrade_rows_name_two_different_actives(upgrade_map):
    """Primary_Active is what you already have, Upgrade_Active is what to step
    up to. A row where they match is not an upgrade."""
    rows = upgrade_map[upgrade_map['Upgrade_Active'].notna()]
    same = rows[rows['Primary_Active'].astype(str).str.strip().str.lower()
                == rows['Upgrade_Active'].astype(str).str.strip().str.lower()]
    assert same.empty, same[['Skin_Concern', 'Primary_Active', 'Upgrade_Active']].to_dict('records')


def test_rows_without_an_upgrade_say_why(upgrade_map):
    """843 of 859 rows have no upgrade. That is deliberate - they record that
    no pathway is established - and each one has to say so rather than simply
    being blank."""
    blank = upgrade_map[upgrade_map['Upgrade_Active'].isna()
                        | (upgrade_map['Upgrade_Active'].astype(str).str.strip() == '')]
    silent = blank[blank['Upgrade_Reason'].isna()
                   | (blank['Upgrade_Reason'].astype(str).str.strip() == '')]
    assert silent.empty, 'rows with no upgrade and no reason: %d' % len(silent)


def test_the_engine_reports_both_actives_separately():
    """The reported bug. The card printed Primary_Active under "Key active
    ingredient" while the heading named Upgrade_Active, so an Adapalene
    suggestion was captioned Niacinamide. One key, two meanings.

    Adapalene is only offered when acne still needs help. A formula that
    already scores 70+ for acne must not keep pushing a treatment upgrade.
    """
    from scoring import analyze_product, get_upgrade_suggestions

    result = analyze_product({
        'ingredients': 'Aqua, Glycerin, Phenoxyethanol, Niacinamide',
        'price': 500, 'size_ml': 30, 'category': 'Serum', 'country': 'India',
        'currency': 'INR', 'skin_type': 'oily',
        'concerns': ['Acne & Oily Skin'],
    })
    suggestions = result['upgrade_suggestions']
    acne_fit = (result.get('skin_concern_fit') or {}).get('Acne & Oily Skin') or {}
    acne_score = acne_fit.get('score') if isinstance(acne_fit, dict) else acne_fit
    if acne_score is not None and acne_score >= 70:
        assert not any(
            str(s.get('concern') or '').lower().startswith('acne') for s in suggestions)
    else:
        assert suggestions, 'expected upgrade suggestions for a weak niacinamide serum'
        acne = next(s for s in suggestions if 'acne' in str(s.get('concern') or '').lower())
        assert acne['suggested_active'] == 'Adapalene'
        assert acne['builds_on'] == 'Niacinamide'

    forced = get_upgrade_suggestions(
        ['Aqua', 'Niacinamide', 'Glycerin', 'Phenoxyethanol'],
        ['Acne & Oily Skin'],
        skin_type='oily',
        category='Serum',
        concern_fit={'concerns': {
            'Acne & Oily Skin': {
                'score': 40,
                'present_actives': ['Niacinamide'],
                'explanation': ['Contains Niacinamide, but the dose is too low.'],
            }
        }},
    )
    assert forced
    acne = next(s for s in forced if 'acne' in str(s.get('concern') or '').lower())
    assert acne['suggested_active'] == 'Adapalene'
    assert acne['builds_on'] == 'Niacinamide'
    assert acne['suggested_active'] != acne.get('builds_on')


def test_a_legal_cap_never_exceeds_the_safety_ceiling(records):
    """The law does not permit more of something than is safe.

    The reverse is ordinary and expected: D5 is safe at 5% and capped at 0.1%
    for environmental persistence, so Max_Allowed_EU_% below Max_Safe_% is the
    normal shape.
    """
    from scripts.audit_database import _num

    bad = []
    for key, entry in records.items():
        eu, safe = _num(entry.get('Max_Allowed_EU_%')), _num(entry.get('Max_Safe_%'))
        if eu is not None and safe is not None and eu > safe:
            bad.append('%s: EU %s > safe %s' % (entry.get('INCI_Name') or key, eu, safe))
    assert not bad, bad


def test_every_record_carries_the_eu_field(records):
    """Present everywhere, so an empty value means "not restricted" rather
    than "nobody has looked"."""
    missing = [k for k, v in records.items() if 'Max_Allowed_EU_%' not in v]
    assert not missing, '%d records without the field' % len(missing)


def test_the_restricted_silicones_keep_their_effective_dose(records):
    """Regression on the first attempt at this, which cleared Min_Effective_%
    and Optimal_% to make the ranges satisfiable. That removed real
    information - these silicones do have a working level - instead of
    separating the two kinds of limit."""
    for key in ('cyclopentasiloxane', 'cyclohexasiloxane'):
        entry = records[key]
        assert entry['Min_Effective_%'], '%s lost its effective dose' % key
        assert entry['Optimal_%'], '%s lost its optimal dose' % key
        assert float(entry['Max_Allowed_EU_%']) == 0.1
        assert float(entry['Max_Safe_%']) == 100.0

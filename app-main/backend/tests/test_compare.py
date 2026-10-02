"""Side-by-side comparison.

The tests here are mostly about what a comparison refuses to say. It is easy
to produce a table that ranks everything; the work is in not claiming a
difference the method cannot support, and in never letting price leak into a
judgement about how well something is made.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compare import (  # noqa: E402
    MEANINGFUL_GAP,
    CompareError,
    compare,
)


def product(name, category='Serum', price=500, size=30, ingredients='Aqua, Niacinamide'):
    return {'product_name': name, 'category': category, 'price': price,
            'size_ml': size, 'ingredients': ingredients, 'currency': 'INR'}


def fake_engine(scores):
    """An analyse() that returns a chosen score per product name."""
    def analyse(data):
        name = data['product_name']
        return {
            'formulation_score': scores[name],
            'formulation_tier': 'Well formulated',
            'formulation_summary': '%s summary' % name,
            'formulation_breakdown': [
                {'key': 'actives', 'label': 'Active ingredients',
                 'score': scores[name] * 0.4, 'max': 40},
                {'key': 'evidence', 'label': 'Evidence quality',
                 'score': scores[name] * 0.3, 'max': 30},
            ],
        }
    return analyse


# ---------------------------------------------------------------------------
# Input limits
# ---------------------------------------------------------------------------

def test_one_product_is_not_a_comparison():
    with pytest.raises(CompareError):
        compare([product('A')], fake_engine({'A': 90}))


def test_more_than_four_is_refused():
    names = list('ABCDE')
    with pytest.raises(CompareError):
        compare([product(n) for n in names],
                fake_engine({n: 80 for n in names}))


def test_a_product_without_ingredients_is_refused():
    """Scoring an empty INCI list would produce a number with nothing behind it."""
    with pytest.raises(CompareError):
        compare([product('A'), product('B', ingredients='   ')],
                fake_engine({'A': 90, 'B': 80}))


def test_not_a_list_is_refused():
    with pytest.raises(CompareError):
        compare('two products', fake_engine({}))


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------

def test_a_clear_gap_names_the_better_formulation():
    out = compare([product('A'), product('B')], fake_engine({'A': 92, 'B': 71}))
    assert out['verdict']['best_formulation'] == 'A'
    assert '21 points' in out['verdict']['note']


def test_a_gap_inside_the_confidence_limit_names_no_winner():
    """Sub-1% ingredients are unordered by law, so a few points is noise.

    Declaring a winner there would be the tool asserting precision it does not
    have - the single easiest way to lose a reader who knows the subject.
    """
    out = compare([product('A'), product('B')],
                  fake_engine({'A': 88, 'B': 88 - (MEANINGFUL_GAP - 1)}))
    assert out['verdict']['best_formulation'] is None
    assert 'too close to separate' in out['verdict']['note']
    assert 'below 1%' in out['verdict']['note']


def test_the_boundary_gap_does_count():
    out = compare([product('A'), product('B')],
                  fake_engine({'A': 88, 'B': 88 - MEANINGFUL_GAP}))
    assert out['verdict']['best_formulation'] == 'A'


# ---------------------------------------------------------------------------
# Price is kept out of the quality judgement
# ---------------------------------------------------------------------------

def test_the_cheaper_product_does_not_win_on_formulation():
    """The rule the whole app rests on. A table that silently rewarded the
    cheaper product would be a price guide pretending to be a quality
    assessment."""
    out = compare([product('Expensive', price=3000), product('Cheap', price=200)],
                  fake_engine({'Expensive': 94, 'Cheap': 61}))
    assert out['verdict']['best_formulation'] == 'Expensive'
    assert out['verdict']['best_value'] == 'Cheap'


def test_best_value_is_price_per_ml_not_price():
    """A 100ml bottle at 900 beats a 30ml at 500."""
    out = compare([product('Big', price=900, size=100),
                   product('Small', price=500, size=30)],
                  fake_engine({'Big': 80, 'Small': 80}))
    assert out['verdict']['best_value'] == 'Big'


def test_value_and_formulation_are_reported_separately():
    out = compare([product('A', price=100), product('B', price=2000)],
                  fake_engine({'A': 60, 'B': 95}))
    verdict = out['verdict']
    assert verdict['best_formulation'] == 'B'
    assert verdict['best_value'] == 'A'
    assert 'does not consider price' in out['method_note']


def test_products_without_a_price_still_compare_on_formulation():
    out = compare([product('A', price=0, size=0), product('B', price=0, size=0)],
                  fake_engine({'A': 90, 'B': 70}))
    assert out['verdict']['best_formulation'] == 'A'
    assert out['verdict']['best_value'] is None


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

def test_mixed_categories_are_shown_but_not_ranked():
    """A cleanser's 88 and a serum's 88 were produced by different rubrics.
    Ordering them implies a comparison that was never made."""
    out = compare([product('Serum A', category='Serum'),
                   product('Cleanser B', category='Cleanser')],
                  fake_engine({'Serum A': 91, 'Cleanser B': 88}))
    assert out['same_category'] is False
    assert out['verdict']['comparable'] is False
    assert out['verdict']['best_formulation'] is None
    assert 'different rubrics' in out['verdict']['note']
    # The scores are still shown - withholding them would be unhelpful.
    assert [p['formulation_score'] for p in out['products']] == [91, 88]


def test_category_matching_ignores_case():
    out = compare([product('A', category='Serum'), product('B', category='serum')],
                  fake_engine({'A': 90, 'B': 70}))
    assert out['same_category'] is True


def test_the_component_table_only_appears_within_one_category():
    """Component sets differ between rubrics, so lining them up across
    categories would align things that are not the same measurement."""
    same = compare([product('A'), product('B')], fake_engine({'A': 90, 'B': 70}))
    assert len(same['components']) == 2

    mixed = compare([product('A', category='Serum'),
                     product('B', category='Cleanser')],
                    fake_engine({'A': 90, 'B': 70}))
    assert mixed['components'] == []


def test_the_component_table_lines_up_by_key():
    out = compare([product('A'), product('B')], fake_engine({'A': 90, 'B': 50}))
    actives = next(c for c in out['components'] if c['key'] == 'actives')
    assert actives['label'] == 'Active ingredients'
    assert len(actives['values']) == 2
    assert actives['values'][0]['pct'] > actives['values'][1]['pct']


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------

def test_every_product_appears_in_input_order():
    out = compare([product('First'), product('Second'), product('Third')],
                  fake_engine({'First': 70, 'Second': 95, 'Third': 80}))
    assert [p['product_name'] for p in out['products']] == ['First', 'Second', 'Third']


def test_price_per_ml_is_computed_per_row():
    out = compare([product('A', price=600, size=30), product('B', price=600, size=50)],
                  fake_engine({'A': 80, 'B': 80}))
    assert out['products'][0]['price_per_ml'] == 20.0
    assert out['products'][1]['price_per_ml'] == 12.0


def test_an_unnamed_product_still_renders():
    out = compare([{'ingredients': 'Aqua', 'category': 'Serum'},
                   {'ingredients': 'Aqua, Glycerin', 'category': 'Serum'}],
                  lambda d: {'formulation_score': 70, 'formulation_breakdown': []})
    assert out['products'][0]['product_name'] == 'Unnamed product'


def test_four_products_is_allowed():
    names = list('ABCD')
    out = compare([product(n) for n in names],
                  fake_engine({n: 70 + i for i, n in enumerate(names)}))
    assert len(out['products']) == 4


# ---------------------------------------------------------------------------
# Against the real engine
# ---------------------------------------------------------------------------

def test_the_real_engine_fills_every_column():
    """The fake engine above returns whatever key names the tests choose, so it
    cannot catch the summariser reading a key the engine does not emit. It did
    exactly that: the engine calls these main_worth_tier and score_title, and
    the tier column came back empty on every real comparison while the unit
    tests stayed green. This test drives the engine itself.
    """
    from scoring import analyze_product

    out = compare([
        {'product_name': 'Niacinamide 10%', 'category': 'Serum', 'price': 549,
         'size_ml': 30, 'country': 'India', 'currency': 'INR',
         'ingredients': 'Aqua, Niacinamide, Zinc PCA, Glycerin, Phenoxyethanol'},
        {'product_name': 'Plain water', 'category': 'Serum', 'price': 1200,
         'size_ml': 30, 'country': 'India', 'currency': 'INR',
         'ingredients': 'Aqua, Phenoxyethanol'},
    ], analyze_product)

    for row in out['products']:
        assert isinstance(row['formulation_score'], (int, float))
        assert row['formulation_tier'], 'tier column is empty'
        assert row['formulation_summary'], 'summary column is empty'
        assert row['breakdown'], 'no component breakdown'

    # A serum of actives against water should clear the confidence margin.
    assert out['verdict']['best_formulation'] == 'Niacinamide 10%'
    assert out['verdict']['best_value'] == 'Niacinamide 10%'

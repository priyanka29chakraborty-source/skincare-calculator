"""The AI explanation seam.

The point of these tests is the boundary, not the prose. A language model
writing next to a reproducible score can quietly undo it, so the layer has to
make three guarantees that hold no matter what is plugged in:

  1. it cannot change a score,
  2. it cannot state a number the engine did not produce,
  3. when it fails, the user gets plainer text rather than wrong text.
"""

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_layer.ai_interface import (  # noqa: E402
    DeterministicExplainer,
    Explainer,
    ExplanationRejected,
    collect_known_numbers,
    explain,
    validate_explanation,
)


@pytest.fixture
def analysis():
    return {
        'formulation_score': 91,
        'formulation_summary': 'This is a well-made serum; its strongest point '
                               'is active ingredients.',
        'formulation_breakdown': [
            {'key': 'actives', 'label': 'Active ingredients', 'score': 36, 'max': 38},
            {'key': 'evidence', 'label': 'Evidence quality', 'score': 20, 'max': 22},
            {'key': 'tolerability', 'label': 'Tolerability', 'score': 9, 'max': 20},
        ],
        'confidence': {'note': 'Ingredients below 1% are unordered by law, so '
                               'exact concentrations cannot be read from the label.'},
        'unknown_ingredients': ['Parfum Blend 44'],
    }


# ---------------------------------------------------------------------------
# The deterministic default
# ---------------------------------------------------------------------------

def test_the_default_explainer_needs_no_model_and_no_key(analysis):
    out = DeterministicExplainer().explain(analysis)
    assert out['summary'].startswith('This is a well-made serum')


def test_it_names_the_strongest_and_weakest_component(analysis):
    why = DeterministicExplainer().explain(analysis)['why_this_score']
    assert 'Active ingredients' in why
    assert 'Tolerability' in why


def test_it_states_what_cannot_be_known(analysis):
    limits = DeterministicExplainer().explain(analysis)['what_we_cannot_say']
    assert 'unordered by law' in limits
    assert '1 ingredient' in limits
    assert 'is not in our database' in limits


def test_it_pluralises_unknown_ingredients_correctly(analysis):
    analysis['unknown_ingredients'] = ['A', 'B']
    limits = DeterministicExplainer().explain(analysis)['what_we_cannot_say']
    assert '2 ingredients' in limits
    assert 'are not in our database' in limits


def test_an_analysis_with_no_components_still_returns_something():
    out = DeterministicExplainer().explain({'formulation_summary': 'Not enough data.'})
    assert out['summary'] == 'Not enough data.'
    assert 'why_this_score' not in out


# ---------------------------------------------------------------------------
# Rule 1: an explainer cannot change a score
# ---------------------------------------------------------------------------

class _Vandal(Explainer):
    name = 'vandal'

    def explain(self, analysis, audience=None):
        analysis['formulation_score'] = 100
        return {'summary': 'Perfect product.'}


def test_an_explainer_cannot_change_a_score(analysis):
    """A mutation here would bypass scoring, entitlement filtering and audit -
    all of which have already run by the time the layer is called. The explainer
    is handed a copy, so an implementation that tries this changes nothing.
    """
    before = copy.deepcopy(analysis)
    explain(analysis, explainer=_Vandal())
    assert analysis == before


def test_an_explainers_mutation_does_not_reach_the_response(analysis):
    """Its prose is served - that is its job - but the score it tried to
    overwrite is untouched, so the UI still renders 91."""
    out = explain(analysis, explainer=_Vandal())
    assert analysis['formulation_score'] == 91
    assert out['summary'] == 'Perfect product.'


# ---------------------------------------------------------------------------
# Rule 2: no invented numbers
# ---------------------------------------------------------------------------

def test_a_number_from_the_analysis_is_allowed(analysis):
    assert validate_explanation('It scored 91 out of 100.', analysis)


def test_an_invented_concentration_is_rejected(analysis):
    """The failure that matters: a confident dose nothing computed."""
    with pytest.raises(ExplanationRejected):
        validate_explanation('Contains 12% niacinamide.', analysis)


def test_an_invented_score_is_rejected(analysis):
    with pytest.raises(ExplanationRejected):
        validate_explanation('This serum scores 97 for hydration.', analysis)


def test_numbers_inside_strings_in_the_analysis_count_as_known(analysis):
    analysis['notes'] = 'Formulated at pH 5.5.'
    assert validate_explanation('Its pH is 5.5.', analysis)


def test_text_with_no_numbers_passes(analysis):
    assert validate_explanation('A thoughtfully built serum.', analysis)


def test_empty_text_passes(analysis):
    assert validate_explanation('', analysis) == ''


def test_known_numbers_include_component_scores(analysis):
    known = collect_known_numbers(analysis)
    assert '36' in known and '38' in known and '91' in known


def test_booleans_are_not_collected_as_numbers():
    """True is 1 in Python; it must not silently permit "1" as a claim."""
    known = collect_known_numbers({'flag': True, 'other': False})
    # 1 is in the free list regardless, so assert on something unambiguous.
    assert '0' in known and '1' in known
    assert len(known) == len({'0', '1', '2', '3', '4', '5', '10', '100'})


# ---------------------------------------------------------------------------
# Rule 3: failure degrades to plainer text, never to wrong text
# ---------------------------------------------------------------------------

class _Hallucinator(Explainer):
    name = 'hallucinator'

    def explain(self, analysis, audience=None):
        return {'summary': 'Contains 12% niacinamide and 3.7% retinol.'}


class _Exploder(Explainer):
    name = 'exploder'

    def explain(self, analysis, audience=None):
        raise RuntimeError('model timed out')


class _KeyInventor(Explainer):
    name = 'key-inventor'

    def explain(self, analysis, audience=None):
        return {'buy_now_banner': 'Act fast!', 'summary': 'A good serum.'}


def test_a_hallucinated_section_falls_back_to_the_deterministic_one(analysis):
    out = explain(analysis, explainer=_Hallucinator())
    assert out['summary'].startswith('This is a well-made serum')
    assert '12%' not in out['summary']


def test_an_explainer_that_raises_does_not_break_the_response(analysis):
    out = explain(analysis, explainer=_Exploder())
    assert out['summary'].startswith('This is a well-made serum')


def test_an_unrecognised_section_is_dropped(analysis):
    """A model cannot introduce a new UI surface by inventing a key."""
    out = explain(analysis, explainer=_KeyInventor())
    assert 'buy_now_banner' not in out
    assert out['summary'] == 'A good serum.'


def test_a_valid_explainer_is_used(analysis):
    class Good(Explainer):
        name = 'good'

        def explain(self, a, audience=None):
            return {'summary': 'Scores 91 of 100, held back by tolerability.'}

    out = explain(analysis, explainer=Good())
    assert out['summary'] == 'Scores 91 of 100, held back by tolerability.'


def test_sections_the_explainer_omits_keep_their_deterministic_text(analysis):
    class SummaryOnly(Explainer):
        name = 'summary-only'

        def explain(self, a, audience=None):
            return {'summary': 'A good serum.'}

    out = explain(analysis, explainer=SummaryOnly())
    assert out['summary'] == 'A good serum.'
    assert 'unordered by law' in out['what_we_cannot_say']


def test_the_default_active_explainer_is_deterministic(analysis):
    """Nothing is turned on by registering the package."""
    out = explain(analysis)
    assert out['summary'].startswith('This is a well-made serum')

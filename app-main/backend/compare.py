"""Comparing two to four products side by side.

The rule the whole app is built on applies here most visibly: **how well a
product is made and how much it costs are different questions.** So a
comparison answers both separately and never blends them into one ranking.
A cheap, well-made product and an expensive, well-made product are the same
product in formulation terms, and a table that silently rewarded the cheaper
one would be a price guide pretending to be a quality assessment.

What a comparison refuses to do
-------------------------------
* **Rank across categories.** A cleanser scoring 88 and a serum scoring 88 did
  not earn those numbers against the same rubric - a cleanser is scored on its
  surfactant system and pH, a serum on its actives and their evidence. Putting
  them in one ordered list implies a comparison that was never made, so a
  mixed-category request is still answered, but with the ranking withheld and
  the reason stated.

* **Declare a winner on a difference the method cannot support.** Below-1%
  ingredients are unordered by law, so two formulations a few points apart are
  not reliably distinguishable. Inside that margin the verdict says so rather
  than inventing a preference.

Comparison is free. It compares formulation scores, and formulation analysis
is the free tier - charging to put two free numbers next to each other would
be charging for arithmetic.
"""

import logging

logger = logging.getLogger(__name__)

MAX_PRODUCTS = 4
MIN_PRODUCTS = 2

# Below this gap the two formulations are treated as equivalent. Chosen to
# match the engine's own stated confidence limits: with sub-1% ingredients
# unordered, a few points is inside the noise of what an INCI list can tell us.
MEANINGFUL_GAP = 4


class CompareError(Exception):
    """A request we will not answer, with a reason the caller can act on."""


def _ppm(price, size_ml):
    if not price or not size_ml:
        return None
    try:
        return round(float(price) / float(size_ml), 2)
    except (TypeError, ZeroDivisionError, ValueError):
        return None


def summarise(result, request_data):
    """The subset of an analysis a comparison row needs."""
    return {
        'product_name': request_data.get('product_name') or 'Unnamed product',
        'brand': request_data.get('brand') or '',
        'category': (request_data.get('category') or '').strip() or 'Serum',
        'price': request_data.get('price') or 0,
        'size_ml': request_data.get('size_ml') or 0,
        'currency': request_data.get('currency') or 'INR',
        'formulation_score': result.get('formulation_score'),
        # The engine names these main_worth_tier and score_title for backwards
        # compatibility with existing clients. Both spellings are accepted so a
        # future rename does not silently blank these columns.
        'formulation_tier': (result.get('formulation_tier')
                             or result.get('main_worth_tier')),
        'formulation_summary': (result.get('formulation_summary')
                                or result.get('score_title')),
        'breakdown': result.get('formulation_breakdown') or [],
        'price_per_ml': _ppm(request_data.get('price'), request_data.get('size_ml')),
        'confidence': (result.get('formulation_confidence')
                       or result.get('confidence')),
    }


def _component_table(rows):
    """Line up the rubric components so a reader can see where a gap came from.

    Only meaningful within one category, since the component sets differ
    between rubrics. Returns [] otherwise rather than inventing alignment.
    """
    categories = {r['category'].lower() for r in rows}
    if len(categories) != 1:
        return []

    keys = []
    for row in rows:
        for component in row['breakdown']:
            if component.get('key') and component['key'] not in keys:
                keys.append(component['key'])

    table = []
    for key in keys:
        entry = {'key': key, 'label': key.replace('_', ' ').title(), 'values': []}
        for row in rows:
            match = next((c for c in row['breakdown'] if c.get('key') == key), None)
            if match:
                entry['label'] = match.get('label', entry['label'])
                entry['values'].append({
                    'score': match.get('score'),
                    'max': match.get('max'),
                    'pct': round(100.0 * match['score'] / match['max'], 1)
                           if match.get('max') else None,
                })
            else:
                entry['values'].append(None)
        table.append(entry)
    return table


def _verdict(rows, same_category):
    """Two separate answers: better made, and better value.

    Deliberately not combined. Someone choosing between these needs to know
    which question the recommendation answers, because the right product
    differs depending on which one they are asking.
    """
    scored = [r for r in rows if isinstance(r['formulation_score'], (int, float))]
    verdict = {
        'comparable': same_category,
        'best_formulation': None,
        'best_value': None,
        'note': None,
    }

    if not same_category:
        verdict['note'] = (
            'These are different product types, so their scores were produced '
            'by different rubrics - a cleanser is judged on its surfactant '
            'system and pH, a serum on its actives and the evidence behind '
            'them. The scores are shown, but ranking them against each other '
            'would imply a comparison that was never made.')
        return verdict

    if len(scored) < 2:
        verdict['note'] = 'Not enough ingredient information to compare these.'
        return verdict

    by_score = sorted(scored, key=lambda r: r['formulation_score'], reverse=True)
    top, second = by_score[0], by_score[1]
    gap = top['formulation_score'] - second['formulation_score']

    if gap < MEANINGFUL_GAP:
        verdict['note'] = (
            'These formulations are too close to separate. Ingredients below '
            '1% are unordered on a label by law, so a {}-point gap is inside '
            'what an INCI list can actually tell us. Choose on price, texture '
            'or how your skin has reacted to them before.'.format(gap)
        )
    else:
        verdict['best_formulation'] = top['product_name']
        verdict['note'] = '{} is the better-made formulation, by {} points.'.format(
            top['product_name'], gap)

    priced = [r for r in scored if r['price_per_ml']]
    if priced:
        cheapest = min(priced, key=lambda r: r['price_per_ml'])
        verdict['best_value'] = cheapest['product_name']

    return verdict


def compare(products, analyse):
    """Compare *products*, scoring each with the *analyse* callable.

    *analyse* is injected rather than imported so this module stays independent
    of the scoring engine's import graph, and so tests can compare known scores
    without running the engine.
    """
    if not isinstance(products, list):
        raise CompareError('Send a list of products.')
    if len(products) < MIN_PRODUCTS:
        raise CompareError('Add at least two products to compare.')
    if len(products) > MAX_PRODUCTS:
        raise CompareError('Up to %d products at a time.' % MAX_PRODUCTS)

    rows = []
    for product in products:
        if not (product.get('ingredients') or '').strip():
            raise CompareError('Every product needs an ingredient list.')
        result = analyse(product)
        rows.append(summarise(result, product))

    same_category = len({r['category'].lower() for r in rows}) == 1

    return {
        'products': rows,
        'components': _component_table(rows),
        'verdict': _verdict(rows, same_category),
        'same_category': same_category,
        # Said once, here, rather than left for the reader to infer from the
        # two separate verdicts.
        'method_note': (
            'Formulation score does not consider price. Value is reported '
            'separately so an expensive product cannot look better made than '
            'it is, and a cheap one cannot look worse.'),
    }

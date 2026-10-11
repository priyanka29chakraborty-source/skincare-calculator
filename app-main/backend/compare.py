"""Comparing two to four products side by side.

The rule the whole app is built on applies here most visibly: **how well a
product is made and how much it costs are different questions.** So a
comparison answers both separately and never blends them into one ranking.
A cheap, well-made product and an expensive, well-made product are the same
product in formulation terms, and a table that silently rewarded the cheaper
one would be a price guide pretending to be a quality assessment.

What a useful comparison actually contains
------------------------------------------
Two scores side by side is a scoreboard, not a comparison - it tells you which
number is bigger and nothing about why, or what you would be giving up. The
questions someone holding two bottles is actually asking are:

  * What is in one that is not in the other?       -> ``actives``
  * Which treats the thing I care about?            -> ``concerns``
  * Which is more likely to irritate me?            -> ``tolerability``
  * Could I just use both?                          -> ``together``
  * Am I buying the same product twice?             -> ``together.redundant``
  * So which one, and why?                          -> ``verdict.choose_if``

The last is the only one most tools attempt, and it is the least useful on its
own, because the honest answer usually depends on which trade the reader wants
to make. So the verdict names the trade rather than hiding it behind a winner.

What it refuses to do
---------------------
* **Rank across categories.** A cleanser scoring 88 and a serum scoring 88 did
  not earn those numbers against the same rubric - a cleanser is scored on its
  surfactant system and pH, a serum on its actives and their evidence. Putting
  them in one ordered list implies a comparison that was never made, so a
  mixed-category request is still answered, but with the ranking withheld and
  the reason stated.

* **Declare a winner on a difference the method cannot support.**
  Below-1% ingredients are unordered by law, so two formulations a few points
  apart are not reliably distinguishable. Inside that margin the verdict says
  so rather than inventing a preference.

The comparison itself is paid: one credit for a pair, and opening that same
pair again does not spend another. A single product's formulation score stays
free. The table is withheld until the credit is spent.
"""

import logging

logger = logging.getLogger(__name__)

MAX_PRODUCTS = 4
MIN_PRODUCTS = 2

# Below this gap the two formulations are treated as equivalent. Chosen to
# match the engine's own stated confidence limits: with sub-1% ingredients
# unordered, a few points is inside the noise of what an INCI list can tell us.
MEANINGFUL_GAP = 4

# A concern gap worth mentioning. Concern scores are coarser than formulation
# scores - they move in larger steps - so the threshold is higher.
CONCERN_GAP = 12

FAMILY_LABELS = {
    'retinoid': 'retinoids',
    'vitamin_c': 'vitamin C',
    'aha': 'AHA exfoliants',
    'bha': 'BHA exfoliants',
    'benzoyl_peroxide': 'benzoyl peroxide',
    'niacinamide': 'niacinamide',
    'peptide': 'peptides',
    'azelaic': 'azelaic acid',
}


class CompareError(Exception):
    """A request we will not answer, with a reason the caller can act on."""


def _ppm(price, size_ml):
    if not price or not size_ml:
        return None
    try:
        return round(float(price) / float(size_ml), 2)
    except (TypeError, ZeroDivisionError, ValueError):
        return None


def _family_label(family):
    return FAMILY_LABELS.get(family, str(family).replace('_', ' '))


def summarise(result, request_data):
    """The subset of an analysis a comparison row needs."""
    actives = result.get('identified_actives') or []
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
        'price_per_active': (
            round(float(request_data.get('price') or 0) / len(actives), 2)
            if actives and float(request_data.get('price') or 0) > 0 else None),
        'confidence': (result.get('formulation_confidence')
                       or result.get('confidence')),
        'actives': [
            {
                'name': a.get('name'),
                'evidence': a.get('evidence'),
                'concentration': a.get('concentration'),
                'concentration_pct': a.get('concentration_pct'),
                'position': a.get('position'),
                'targets': a.get('targets') or [],
            }
            for a in actives
        ],
        'concern_fit': {
            name: data.get('score')
            for name, data in (result.get('skin_concern_fit') or {}).items()
            if isinstance(data, dict)
        },
        'risk_level': result.get('skin_type_risk_level'),
        'skin_type_notes': ((result.get('skin_type_details') or {})
                            .get('formulation_notes') or []),
        'irritants': [n for n in (result.get('comedogenic_warnings') or [])],
        'tolerability': next(
            (c for c in (result.get('formulation_breakdown') or [])
             if c.get('key') == 'tolerability'), None),
        'families': sorted(result.get('_families') or []),
        'ingredient_count': result.get('ingredient_count'),
    }


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

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
                    'notes': match.get('notes') or [],
                })
            else:
                entry['values'].append(None)
        table.append(entry)
    return table


def _actives_table(rows):
    """Shared actives, and what each product has that the others do not.

    The single most useful line in any comparison, and the one a scoreboard
    cannot give you: two products can score the same and do entirely different
    jobs.
    """
    by_product = [{_norm_name(a['name']): a for a in row['actives'] if a.get('name')}
                  for row in rows]
    all_names = set()
    for mapping in by_product:
        all_names |= set(mapping)

    shared, unique = [], [[] for _ in rows]
    for key in sorted(all_names):
        present = [i for i, mapping in enumerate(by_product) if key in mapping]
        sample = by_product[present[0]][key]
        entry = {
            'name': sample['name'],
            'evidence': sample.get('evidence'),
            'targets': sample.get('targets') or [],
        }
        if len(present) == len(rows):
            # Shared: show each product's estimated level, since the same
            # active at two very different positions is not the same thing.
            entry['levels'] = [
                {
                    'position': by_product[i][key].get('position'),
                    'concentration': by_product[i][key].get('concentration'),
                    'concentration_pct': by_product[i][key].get('concentration_pct'),
                }
                for i in range(len(rows))
            ]
            shared.append(entry)
        else:
            for i in present:
                unique[i].append(dict(entry,
                                      position=by_product[i][key].get('position'),
                                      concentration=by_product[i][key].get('concentration')))

    return {'shared': shared, 'unique': unique}


def _norm_name(name):
    return str(name or '').strip().lower()


def _concern_table(rows):
    """Which product treats each concern better.

    Only concerns every product was scored against, so a concern selected for
    one and not another cannot produce a phantom win.
    """
    if not rows:
        return []
    common = set(rows[0]['concern_fit'])
    for row in rows[1:]:
        common &= set(row['concern_fit'])
    if not common:
        return []

    table = []
    for concern in sorted(common):
        scores = [row['concern_fit'][concern] for row in rows]
        numeric = [s for s in scores if isinstance(s, (int, float))]
        best_index, note = None, None
        if len(numeric) == len(scores) and len(scores) > 1:
            ordered = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
            gap = scores[ordered[0]] - scores[ordered[1]]
            if gap >= CONCERN_GAP:
                best_index = ordered[0]
            else:
                note = 'Too close to call on this concern.'
        table.append({
            'concern': concern,
            'scores': scores,
            'best_index': best_index,
            'note': note,
        })
    return table


def _tolerability_table(rows):
    """Irritation risk, reported per product rather than ranked.

    Two separate measures, kept separate. Rendering them in one cell produced
    "Tolerability 100% - High Risk", which reads as a contradiction and is not
    one: the first is formulation-level (fragrance, drying alcohol, known
    sensitisers - the same for everybody) and the second is specific to the
    skin type being analysed for (comedogenic ingredients matter to oily and
    acne-prone skin and barely at all to dry skin). A product can genuinely be
    free of irritants and still be a poor idea for one skin type.

    Neither is ranked. A single "gentler" label would flatten a formula with no
    known irritants and one whose irritants simply are not in our database.
    """
    out = []
    for row in rows:
        component = row['tolerability'] or {}
        pct = None
        if component.get('max'):
            pct = round(100.0 * component['score'] / component['max'], 1)
        out.append({
            'formulation_pct': pct,
            'formulation_notes': component.get('notes') or [],
            'skin_type_risk': row['risk_level'],
            'skin_type_notes': row['skin_type_notes'],
            'flagged_ingredients': row['irritants'],
            # Kept for callers written against the previous shape.
            'tolerability_pct': pct,
            'risk_level': row['risk_level'],
            'notes': component.get('notes') or [],
        })
    return out


def _together(rows):
    """Can these be used together, and would there be any point?

    Two questions a scoreboard never asks, and the ones that decide whether
    someone buys both or picks one.
    """
    from personalization import ROUTINE_INTERACTIONS, REDUNDANT_WITH_SELF

    if len(rows) != 2:
        # Pairwise interaction advice across three or four products is a matrix
        # nobody reads. Say so rather than printing a partial answer.
        return {
            'checked': False,
            'reason': 'Layering advice is given for two products at a time.',
            'conflicts': [], 'redundant': [],
        }

    a_fams, b_fams = set(rows[0]['families']), set(rows[1]['families'])

    conflicts = []
    for fam_a, fam_b, severity, message in ROUTINE_INTERACTIONS:
        hit = ((fam_a in a_fams and fam_b in b_fams)
               or (fam_b in a_fams and fam_a in b_fams))
        if hit:
            conflicts.append({
                'families': [_family_label(fam_a), _family_label(fam_b)],
                'severity': severity,
                # The stored copy is written for a routine the user typed in,
                # so it is rephrased here for two products being compared.
                'message': message.replace('You are already using', 'One of these contains'),
            })

    redundant = []
    for family in sorted(a_fams & b_fams):
        if family in REDUNDANT_WITH_SELF:
            redundant.append({
                'family': _family_label(family),
                'message': (
                    'Both contain {}. A second product in the same family '
                    'rarely adds to the result and does add to the irritation '
                    'load - and to the cost.'.format(_family_label(family))),
            })

    return {
        'checked': True,
        'conflicts': conflicts,
        'redundant': redundant,
        'clear': not conflicts and not redundant,
    }


def _choose_if(rows, concern_table, actives):
    """One line per product: the reason to pick this one over the others.

    Built from differences the analysis actually found. A product with nothing
    distinguishing gets no line rather than a manufactured one.
    """
    lines = [[] for _ in rows]

    for entry in concern_table:
        if entry['best_index'] is None:
            continue
        i = entry['best_index']
        lines[i].append('you are mainly treating {} ({} vs {})'.format(
            entry['concern'].lower(),
            _trim(entry['scores'][i]),
            _trim(max(s for j, s in enumerate(entry['scores']) if j != i))))

    for i, unique_actives in enumerate(actives['unique']):
        if unique_actives:
            names = ', '.join(a['name'] for a in unique_actives[:3])
            lines[i].append('you want {} specifically'.format(names))

    priced = [(i, r['price_per_ml']) for i, r in enumerate(rows) if r['price_per_ml']]
    if len(priced) == len(rows) and len(priced) > 1:
        cheapest = min(priced, key=lambda t: t[1])[0]
        lines[cheapest].append('cost per ml is what matters most to you')

    return [
        {'product_name': rows[i]['product_name'], 'reasons': reasons}
        for i, reasons in enumerate(lines) if reasons
    ]


def _trim(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(f)) if f == int(f) else str(round(f, 1))


def _verdict(rows, same_category, concern_table, actives):
    """Two separate answers - better made, and better value - plus the trade.

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
        'choose_if': [],
    }

    if not same_category:
        verdict['note'] = (
            'These use different rubrics, so the formulation scores are not '
            'ranked against each other. A cleanser is scored on how gently it '
            'cleans, a moisturiser on how it hydrates, a serum on its actives. '
            'The concern numbers further down still say which one treats what '
            'you selected.')
        return verdict

    if len(scored) < 2:
        verdict['note'] = 'Not enough ingredient information to compare these.'
        return verdict

    by_score = sorted(scored, key=lambda r: r['formulation_score'], reverse=True)
    top, second = by_score[0], by_score[1]
    gap = top['formulation_score'] - second['formulation_score']

    if gap < MEANINGFUL_GAP:
        verdict['note'] = (
            'These formulations are too close to separate on quality. '
            'Ingredients below 1% are unordered on a label by law, so a '
            '{}-point gap is inside what an INCI list can actually tell us. '
            'What follows is where they genuinely differ.'.format(gap)
        )
    else:
        verdict['best_formulation'] = top['product_name']
        verdict['note'] = '{} is the better-made formulation, by {} points.'.format(
            top['product_name'], gap)

    priced = [r for r in scored if r['price_per_ml']]
    if priced:
        cheapest = min(priced, key=lambda r: r['price_per_ml'])
        verdict['best_value'] = cheapest['product_name']

    verdict['choose_if'] = _choose_if(rows, concern_table, actives)
    return verdict


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

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
        result = dict(result)
        result['_families'] = _detect_families(product.get('ingredients'))
        rows.append(summarise(result, product))

    same_category = len({r['category'].lower() for r in rows}) == 1
    components = _component_table(rows)
    actives = _actives_table(rows)
    concern_table = _concern_table(rows)

    return {
        'products': rows,
        'components': components,
        'actives': actives,
        'concerns': concern_table,
        'tolerability': _tolerability_table(rows),
        'together': _together(rows),
        'verdict': _verdict(rows, same_category, concern_table, actives),
        'same_category': same_category,
        # Said once, here, rather than left for the reader to infer from the
        # separate verdicts.
        'method_note': (
            'The formulation score ignores price. Paying more does not raise it.'),
    }


def _detect_families(ingredients):
    """Active families present, for the layering and redundancy checks."""
    try:
        from personalization import detect_families
        from scoring import parse_ingredients
        return sorted(detect_families(parse_ingredients(ingredients or '')))
    except Exception:
        logger.exception('could not detect active families')
        return []

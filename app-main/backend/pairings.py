"""What to use alongside this product.

The database already holds 815 ingredients with synergy partners, but almost
none of it is usable as a recommendation straight out of the table. Niacinamide
alone lists partners like "aegle marmelos fruit extract" and "alchemilla
vulgaris extract" - real entries with real pairing data, and useless advice,
because nobody can walk into a shop and buy them. A raw dump of that table
would look like a feature and function as noise.

So the filtering is the feature, and it is deliberately severe:

* **The partner has to be something you can actually buy.** Tier 1 and 2
  actives only, with evidence that is not merely "limited". That cuts 815
  entries to a few dozen ingredients a person could reasonably find on a label.

* **It has to be absent from the product.** Suggesting niacinamide alongside a
  niacinamide serum is the kind of advice that tells a reader the tool is not
  reading their input.

* **It must not clash.** A pairing that raises irritation past what the barrier
  tolerates is not a recommendation, so anything that trips the routine
  interaction rules is either dropped or carried with its warning attached.

* **It should fix something.** Partners that address a concern the product
  scored weakly on are ranked first, because "this already works, add more"
  is worth less than "this is the gap, here is what fills it".

Three suggestions maximum. A list of ten is a way of not having an opinion.
"""

import logging

logger = logging.getLogger(__name__)

MAX_SUGGESTIONS = 3

# Evidence levels we will put in front of someone as a recommendation.
_ACCEPTABLE_EVIDENCE = ('strong', 'moderate', 'good', 'established')

# Where a person would realistically find each active. Curated rather than
# inferred: guessing a format produces advice like "look for a sunscreen with
# salicylic acid", which sends someone looking for a product that barely
# exists. Anything not in this map is described without a format.
_TYPICAL_FORMAT = {
    'salicylic acid': 'a BHA serum, toner or cleanser',
    'glycolic acid': 'an AHA toner or overnight exfoliant',
    'lactic acid': 'a lactic acid serum or gentle overnight exfoliant',
    'mandelic acid': 'a mandelic acid serum, for sensitive skin',
    'azelaic acid': 'an azelaic acid serum or cream',
    'retinol': 'a retinol serum, used at night',
    'retinal': 'a retinaldehyde serum, used at night',
    'adapalene': 'an adapalene gel, sold over the counter in many countries',
    'niacinamide': 'a niacinamide serum',
    'ascorbic acid': 'a vitamin C serum, used in the morning',
    'tetrahexyldecyl ascorbate': 'an oil-soluble vitamin C serum',
    'benzoyl peroxide': 'a benzoyl peroxide wash or spot treatment',
    'tranexamic acid': 'a tranexamic acid serum',
    'alpha arbutin': 'an alpha arbutin serum',
    'hyaluronic acid': 'a hydrating serum, applied to damp skin',
    'ceramide np': 'a ceramide moisturiser',
    'panthenol': 'a soothing serum or moisturiser',
    'zinc pca': 'a lightweight oil-control serum',
    'ferulic acid': 'a vitamin C serum that includes ferulic acid',
    'tocopherol': 'a moisturiser or facial oil containing vitamin E',
    'tocopheryl acetate': 'a moisturiser containing vitamin E',
    'bakuchiol': 'a bakuchiol serum, a gentler alternative to retinol',
    'kojic acid': 'a kojic acid serum or soap',
    'arbutin': 'an arbutin serum',
    'glycerin': 'almost any hydrating serum or moisturiser',
    'squalane': 'a squalane oil or lightweight moisturiser',
    'urea': 'a urea cream, usually for body or very dry patches',
    'allantoin': 'a soothing moisturiser',
    'centella asiatica extract': 'a centella (cica) serum or cream',
    'madecassoside': 'a centella (cica) serum or cream',
    'beta glucan': 'a soothing hydrating serum',
    'peptide': 'a peptide serum',
    'copper tripeptide-1': 'a copper peptide serum',
    'acetyl hexapeptide-8': 'a peptide serum',
    'sodium hyaluronate': 'a hydrating serum, applied to damp skin',
    'cholesterol': 'a barrier-repair moisturiser with ceramides',
    'ceramide ap': 'a ceramide moisturiser',
    'ceramide eop': 'a ceramide moisturiser',
    'titanium dioxide': 'a mineral sunscreen',
    'zinc oxide': 'a mineral sunscreen',
}


def _norm(value):
    return str(value or '').strip().lower()


def _evidence_ok(data):
    evidence = _norm(data.get('Evidence_Strength')) or _norm(data.get('Evidence_Level_Normalized'))
    return any(level in evidence for level in _ACCEPTABLE_EVIDENCE)


def _tier_ok(data):
    """Tier 1 and 2 only - the actives a person can recognise and find."""
    tier = _norm(data.get('Activity_Tier'))
    return 'tier 1' in tier or 'tier 2' in tier


def _display_name(name):
    """The database's own spelling of an ingredient, else a title-cased guess."""
    from data_loader import data_loader
    data = data_loader.get_ingredient_data(name)
    if data and data.get('INCI_Name'):
        return str(data['INCI_Name']).strip()
    return str(name).title()


def _family_of(name, routine_actives):
    n = _norm(name)
    for family, markers in routine_actives.items():
        if any(marker in n for marker in markers):
            return family
    return None


def suggest_pairings(ingredient_list, concern_fit=None, max_suggestions=MAX_SUGGESTIONS,
                      skin_type=None, category=None):
    """Actives worth using alongside this product.

    *concern_fit* is the per-concern scoring, used only for ranking: a partner
    that addresses something this product is weak on is more useful than one
    that reinforces what it already does well. Passing None is fine and simply
    removes that ordering.

    Returns a list of dicts, each naming the partner, the ingredient here it
    works with, what it would add, and any caution about using the two
    together. Never raises - a failure returns an empty list, because a missing
    recommendation is a missing nicety and a broken analysis is not.
    """
    try:
        return _suggest(ingredient_list, concern_fit or {}, max_suggestions, skin_type, category)
    except Exception:
        logger.exception('pairing suggestions failed')
        return []


_HARSH_ON_SENSITIVE = {
    'salicylic acid', 'glycolic acid', 'lactic acid', 'mandelic acid',
    'retinol', 'retinal', 'adapalene', 'benzoyl peroxide', 'ascorbic acid',
}
_DRYING_FOR_DRY = _HARSH_ON_SENSITIVE - {'retinol', 'retinal', 'adapalene', 'ascorbic acid'}
_DRYING_ALCOHOLS = ('alcohol denat', 'sd alcohol', 'isopropyl alcohol')


def _comedogenic(data):
    try:
        return float((data or {}).get('Comedogenicity_0_5') or 0)
    except (TypeError, ValueError):
        return 0.0


def _blocked_for_skin(name, data, skin_type):
    """A pairing must suit the selected skin, not only the formula.

    The same lines the compatibility score treats as a warning are enough
    to leave an ingredient off this list.
    """
    skin = (skin_type or '').strip().lower()
    if skin in ('', 'normal'):
        return False
    n = _norm(name)
    data = data or {}
    from data_loader import data_loader
    occlusive = n in (data_loader.role_sets.get('occlusive') or set())
    if skin == 'sensitive':
        if n in _HARSH_ON_SENSITIVE:
            return True
        if any(k in n for k in ('fragrance', 'parfum', 'essential oil',
                                'limonene', 'linalool', 'citronellol')):
            return True
        if any(k in n for k in _DRYING_ALCOHOLS):
            return True
        irritation = str(data.get('Irritation_Risk') or '').lower()
        sensitive_risk = str(data.get('Sensitive_Skin_Risk') or '').lower()
        return 'high' in irritation or 'high' in sensitive_risk
    if skin == 'oily':
        return _comedogenic(data) >= 3 or occlusive or 'coconut' in n
    if skin == 'dry':
        return n in _DRYING_FOR_DRY or any(k in n for k in _DRYING_ALCOHOLS)
    if skin == 'combination':
        return (
            occlusive or 'coconut' in n or _comedogenic(data) >= 4
            or any(k in n for k in ('fragrance', 'parfum', 'essential oil'))
            or any(k in n for k in _DRYING_ALCOHOLS)
        )
    return False


def _category_key(category):
    c = _norm(category).replace('moisturiser', 'moisturizer')
    if c in ('oil', 'facial oil'):
        return 'facial oil'
    return c


# Actives that belong in a facial oil. Water-based serum staples (niacinamide,
# hyaluronic acid, tranexamic acid) are left off on purpose: a face-oil
# analysis was sending people to buy those serums.
_OIL_SOLUBLE = {
    'tetrahexyldecyl ascorbate', 'tocopherol', 'tocopheryl acetate',
    'retinol', 'retinal', 'bakuchiol', 'squalane', 'ferulic acid',
}


def _fits_category(look_for, category):
    """Keep a pairing only when it is the same kind of product.

    A facial oil was told to go and buy a niacinamide serum. The format line
    is the allowlist, so the analysed category has to be in that line.
    """
    key = _category_key(category)
    text = _norm(look_for)
    if not key:
        return True
    if key == 'facial oil':
        return 'oil' in text
    if key == 'serum':
        return 'serum' in text or 'ampoule' in text
    if key == 'moisturizer':
        return 'moistur' in text or 'cream' in text
    if key == 'cleanser':
        return 'cleanser' in text or 'wash' in text
    if key == 'toner':
        return 'toner' in text
    if key == 'sunscreen':
        return 'sunscreen' in text
    if key == 'eye cream':
        return 'eye' in text
    if key == 'treatment':
        return 'treatment' in text or 'serum' in text or 'exfoliant' in text
    return True


def _suggest(ingredient_list, concern_fit, max_suggestions, skin_type=None, category=None):
    from data_loader import data_loader
    from personalization import ROUTINE_ACTIVES, ROUTINE_INTERACTIONS

    present = {_norm(i) for i in (ingredient_list or [])}
    if not present:
        return []

    present_families = {f for f in (_family_of(i, ROUTINE_ACTIVES) for i in present) if f}

    # Concerns this product does not cover well, worst first. These are what a
    # pairing would be for.
    weak_concerns = sorted(
        ((name, data.get('score')) for name, data in (concern_fit or {}).items()
         if isinstance(data, dict) and isinstance(data.get('score'), (int, float))
         and data['score'] < 55),
        key=lambda pair: pair[1])

    candidates = {}
    skipped_for_skin = []
    for ingredient in present:
        partners = data_loader.synergy_partners_map.get(ingredient) or set()
        for partner in partners:
            partner_n = _norm(partner)
            if partner_n in present or partner_n in candidates:
                continue

            data = data_loader.get_ingredient_data(partner_n)
            if not data or not _tier_ok(data) or not _evidence_ok(data):
                continue

            # The hard line: if we cannot say where to find it, we do not
            # recommend it. Tier and evidence alone still let through entries
            # like "Zingiber Officinale Root Oil" and "Glycyrrhiza Glabra Root
            # Powder" - real records, correctly paired, and not things anyone
            # can go and buy. A recommendation nobody can act on is not a
            # recommendation, so _TYPICAL_FORMAT is the allowlist as well as
            # the phrasing. Adding an entry there is how this feature grows.
            look_for = _TYPICAL_FORMAT.get(partner_n)
            if not look_for:
                continue
            if _category_key(category) == 'facial oil':
                if partner_n not in _OIL_SOLUBLE:
                    continue
                look_for = 'a facial oil containing %s' % _display_name(partner_n)
            elif not _fits_category(look_for, category):
                continue
            if _blocked_for_skin(partner_n, data, skin_type):
                skipped_for_skin.append(partner_n)
                continue

            # Would adding this clash with what is already here?
            partner_family = _family_of(partner_n, ROUTINE_ACTIVES)
            caution = None
            blocked = False
            if partner_family:
                if partner_family in present_families:
                    # Same family as something already in the product: another
                    # one adds irritation rather than effect.
                    blocked = True
                else:
                    for fam_a, fam_b, severity, message in ROUTINE_INTERACTIONS:
                        pair = {fam_a, fam_b}
                        if partner_family in pair and pair & present_families:
                            caution = message.replace(
                                'You are already using', 'This product contains')
                            break
            if blocked:
                continue

            targets = [t for t in (data.get('Skin_Concerns') or '').split(';') if t.strip()]
            targets_n = {_norm(t) for t in targets}
            addresses = next((name for name, _score in weak_concerns
                              if _norm(name) in targets_n
                              or any(_norm(name).startswith(t) for t in targets_n if t)), None)

            candidates[partner_n] = {
                'ingredient': str(data.get('INCI_Name') or partner).strip(),
                'works_with': _display_name(ingredient),
                'adds': (data.get('Primary_Benefits') or '').strip() or None,
                'evidence': (data.get('Evidence_Quality')
                             or data.get('Evidence_Strength') or '').strip() or None,
                'addresses_concern': addresses,
                'look_for': look_for,
                'caution': caution,
                '_rank': (
                    0 if addresses else 1,          # fills a gap first
                    0 if caution is None else 1,    # clean pairings before caveated ones
                    0 if 'strong' in _norm(data.get('Evidence_Strength')) else 1,
                ),
            }

    ordered = sorted(candidates.values(), key=lambda c: c['_rank'])
    for entry in ordered:
        entry.pop('_rank', None)
    picked = ordered[:max_suggestions]
    return picked

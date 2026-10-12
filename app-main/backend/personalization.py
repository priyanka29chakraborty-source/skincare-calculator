"""Personal context: Fitzpatrick tone, climate, allergies, current routine.

ARCHITECTURAL RULE, and the reason this is a separate module:

    Nothing here may ever change the formulation score.

A product is not better made because it suits your skin, and not worse made
because it does not. Fitzpatrick type, climate, allergies and what is already
on your shelf all describe YOU. They belong in the Fit score and in advisories.
Formulation quality stays price-independent and person-independent, so two
users scanning the same product always see the same number for how well it is
made - and different numbers for whether it suits them.

Everything here is optional. A user who answers nothing gets exactly the
behaviour they got before; each answer refines the Fit score only.
"""

import re

# --- Fitzpatrick ------------------------------------------------------------
# I-VI. The evidenced, practically useful signals are:
#   - higher phototypes carry substantially greater risk of post-inflammatory
#     hyperpigmentation after any inflammatory insult, so irritants matter more;
#   - lower phototypes burn faster and need UVB protection sooner.
# Both are directional and well established. We do NOT claim precise risk
# multipliers - none are published in a form that would justify one.
FITZPATRICK = {
    'I':   {'label': 'Always burns, never tans',        'pih_risk': 0.20, 'burn_risk': 1.00},
    'II':  {'label': 'Burns easily, tans minimally',    'pih_risk': 0.30, 'burn_risk': 0.90},
    'III': {'label': 'Burns moderately, tans gradually','pih_risk': 0.55, 'burn_risk': 0.70},
    'IV':  {'label': 'Burns minimally, tans easily',    'pih_risk': 0.80, 'burn_risk': 0.50},
    'V':   {'label': 'Rarely burns, tans profusely',    'pih_risk': 0.95, 'burn_risk': 0.35},
    'VI':  {'label': 'Never burns, deeply pigmented',   'pih_risk': 1.00, 'burn_risk': 0.25},
}

# --- Climate ----------------------------------------------------------------
# Humidity changes what a good moisturiser looks like: in humid air a heavy
# occlusive is uncomfortable and can aggravate congestion, while in dry air
# humectants alone can draw water from the skin rather than to it.
CLIMATE = {
    'tropical_humid': {'label': 'Tropical / humid', 'humidity': 'high',
                       'occlusion_pref': 'light',  'uv_band': 'very_high'},
    'hot_arid':       {'label': 'Hot & dry',        'humidity': 'low',
                       'occlusion_pref': 'rich',   'uv_band': 'very_high'},
    'temperate':      {'label': 'Temperate',        'humidity': 'moderate',
                       'occlusion_pref': 'medium', 'uv_band': 'moderate'},
    'cold_dry':       {'label': 'Cold & dry',       'humidity': 'low',
                       'occlusion_pref': 'rich',   'uv_band': 'low'},
}

# A country is not a climate. The reader chooses one in "How this suits you".

# --- Allergens the user can declare ----------------------------------------
# Each maps to ingredient markers. These produce PERSONAL warnings and Fit
# deductions - never a formulation penalty. A fragranced cream is not badly
# made; it is unsuitable for someone allergic to fragrance.
ALLERGEN_GROUPS = {
    'fragrance': {
        'label': 'Fragrance / parfum',
        'markers': ('parfum', 'fragrance', 'aroma', 'sugandhit', 'limonene', 'linalool',
                    'citronellol', 'geraniol', 'eugenol', 'coumarin', 'citral',
                    'benzyl benzoate', 'benzyl salicylate', 'cinnamal',
                    'hexyl cinnamal', 'isoeugenol', 'farnesol'),
    },
    'essential_oils': {
        'label': 'Essential oils',
        'markers': ('essential oil', 'citrus aurantium', 'citrus limon',
                    'citrus bergamia', 'lavandula', 'mentha piperita',
                    'eucalyptus', 'melaleuca alternifolia', 'cymbopogon',
                    'pelargonium graveolens', 'cananga odorata', 'menthol',
                    'santalum album', 'rosmarinus officinalis oil'),
    },
    'alcohol': {
        'label': 'Drying alcohols',
        'markers': ('alcohol denat', 'sd alcohol', 'isopropyl alcohol',
                    'denatured alcohol'),
    },
    'parabens': {
        'label': 'Parabens',
        'markers': ('paraben',),
    },
    'sulfates': {
        'label': 'Sulfates',
        'markers': ('lauryl sulfate', 'laureth sulfate'),
    },
    'silicones': {
        'label': 'Silicones',
        'markers': ('dimethicone', 'siloxane', 'cyclopentasiloxane',
                    'cyclohexasiloxane', 'silsesquioxane'),
    },
    'nut_oils': {
        'label': 'Nut-derived oils',
        'markers': ('prunus amygdalus', 'sweet almond', 'corylus avellana',
                    'macadamia', 'juglans regia', 'carya illinoensis',
                    'anacardium occidentale', 'bertholletia excelsa'),
    },
    'lanolin': {
        'label': 'Lanolin',
        'markers': ('lanolin',),
    },
}

# --- Active families, for routine conflict and redundancy checks ------------
ROUTINE_ACTIVES = {
    'retinoid': ('retinol', 'retinal', 'retinaldehyde', 'tretinoin', 'adapalene',
                 'hydroxypinacolone retinoate', 'retinyl palmitate', 'granactive'),
    'vitamin_c': ('ascorbic acid', 'ascorbyl', 'vitamin c', '3-o-ethyl'),
    'aha': ('glycolic acid', 'lactic acid', 'mandelic acid', 'citric acid', 'aha'),
    'bha': ('salicylic acid', 'bha'),
    'benzoyl_peroxide': ('benzoyl peroxide',),
    'niacinamide': ('niacinamide',),
    'azelaic': ('azelaic acid',),
    'peptides': ('peptide', 'palmitoyl'),
    'exfoliant_enzyme': ('papain', 'bromelain'),
}

# Combinations worth flagging, with the honest reason. Each entry is
# (family_a, family_b, severity, message). Anything contested is stated as
# contested rather than asserted.
ROUTINE_INTERACTIONS = [
    ('retinoid', 'aha', 'caution',
     "You are already using an AHA. Layering it with a retinoid in the same "
     "routine raises irritation risk for many people - most dermatologists "
     "suggest alternating nights rather than combining."),
    ('retinoid', 'bha', 'caution',
     "You are already using a BHA. Combined with a retinoid this can be more "
     "than the barrier tolerates - consider alternating nights."),
    ('retinoid', 'benzoyl_peroxide', 'caution',
     "Benzoyl peroxide can oxidise some retinoids when applied together. "
     "Using them at different times of day avoids the issue. Note this does "
     "not apply to adapalene, which is stable with benzoyl peroxide."),
    ('aha', 'bha', 'info',
     "You are already using an acid exfoliant. Adding a second one rarely "
     "improves results and does raise irritation risk."),
]

# Families where owning two products is redundant rather than additive.
# Niacinamide and azelaic acid are in here because a second product with the
# same one rarely adds a result. Peptides are left out: people often layer
# different peptides on purpose.
REDUNDANT_WITH_SELF = (
    'retinoid', 'vitamin_c', 'aha', 'bha', 'benzoyl_peroxide',
    'niacinamide', 'azelaic',
)


def _norm(s):
    return re.sub(r'\s+', ' ', str(s or '').strip().lower())


def resolve_climate(profile, country=None):
    """Only a climate the user chose.

    A country is not a climate. India is not all humid, and guessing one
    from the shipping country was showing a weather note the reader never
    asked for.
    """
    explicit = (profile or {}).get('climate')
    if explicit in CLIMATE:
        return explicit
    return None


def detect_families(ingredient_list):
    """Which active families appear in this product."""
    found = set()
    for ing in ingredient_list or []:
        n = _norm(ing)
        for family, markers in ROUTINE_ACTIVES.items():
            if any(m in n for m in markers):
                found.add(family)
    return found


def parse_routine(routine_input):
    """Accept a free-text routine or a list, return the active families in it.

    Users type things like "the ordinary retinol, vitamin c serum, cerave
    cleanser" - we only need the families, not the products.
    """
    if not routine_input:
        return set()
    text = ' '.join(routine_input) if isinstance(routine_input, (list, tuple)) \
        else str(routine_input)
    n = _norm(text)
    return {fam for fam, markers in ROUTINE_ACTIVES.items()
            if any(m in n for m in markers)}


def check_allergens(ingredient_list, declared):
    """Personal allergen matches. Returns (flags, fit_penalty).

    The penalty applies to Fit only. A product containing something this user
    reacts to is unsuitable for them at any formulation quality.
    """
    flags = []
    penalty = 0.0
    for key in (declared or []):
        group = ALLERGEN_GROUPS.get(key)
        if not group:
            continue
        hits = []
        for ing in ingredient_list or []:
            n = _norm(ing)
            if any(m in n for m in group['markers']):
                hits.append(ing)
        if hits:
            penalty += 18.0
            flags.append({
                'type': 'declared_allergen',
                'severity': 'high',
                'group': key,
                'message': "You told us you react to {}. This product contains "
                           "{}.".format(group['label'].lower(),
                                        ", ".join(sorted(set(hits))[:3])),
                'ingredients': sorted(set(hits))[:5],
            })
    return flags, min(45.0, penalty)


def check_routine(ingredient_list, routine_families):
    """Conflicts and redundancy against what the user already uses."""
    product_families = detect_families(ingredient_list)
    flags = []

    for a, b, severity, message in ROUTINE_INTERACTIONS:
        # Flag when the product brings one side and the routine has the other.
        if (a in product_families and b in routine_families) or \
           (b in product_families and a in routine_families):
            flags.append({'type': 'routine_conflict', 'severity': severity,
                          'message': message})

    for fam in product_families & routine_families:
        if fam in REDUNDANT_WITH_SELF:
            pretty = fam.replace('_', ' ')
            flags.append({
                'type': 'routine_redundant', 'severity': 'info',
                'message': "You already use {} in your routine. A second one "
                           "usually adds cost rather than results - unless you "
                           "are replacing the first.".format(pretty),
            })
    return flags, product_families


def fitzpatrick_context(profile, ingredient_list, concerns):
    """Tone-specific advisories. Directional and clearly hedged."""
    tone = (profile or {}).get('fitzpatrick')
    data = FITZPATRICK.get(tone)
    if not data:
        return []

    flags = []
    irritants = [i for i in (ingredient_list or [])
                 if any(m in _norm(i) for m in
                        ('glycolic acid', 'salicylic acid', 'retinol', 'retinal',
                         'benzoyl peroxide', 'alcohol denat'))]

    if data['pih_risk'] >= 0.75 and irritants:
        flags.append({
            'type': 'pih_risk', 'severity': 'info',
            'message': "At Fitzpatrick {}, irritation is more likely to leave a "
                       "dark mark than redness. This product contains {} - "
                       "introduce it slowly and stop if skin becomes inflamed, "
                       "since the mark is harder to undo than the irritation."
                       .format(tone, irritants[0]),
        })
    if data['burn_risk'] >= 0.85 and 'Sun Protection' not in (concerns or []):
        flags.append({
            'type': 'burn_risk', 'severity': 'info',
            'message': "At Fitzpatrick {}, skin burns quickly. Daily sun "
                       "protection matters more than any single active in your "
                       "routine.".format(tone),
        })
    return flags


def climate_context(climate_key, ingredient_list, category, skin_type=None):
    """How this texture may feel in the climate the user chose."""
    data = CLIMATE.get(climate_key)
    if not data or category not in ('moisturizer', 'facial oil', 'mask'):
        return []

    heavy = [i for i in (ingredient_list or [])
             if any(m in _norm(i) for m in
                    ('petrolatum', 'paraffinum', 'lanolin', 'cera alba',
                     'beeswax', 'shea butter', 'butyrospermum'))]
    skin = (skin_type or '').strip().lower()
    flags = []
    if data['humidity'] == 'high' and heavy:
        if skin in ('oily', 'combination'):
            feel = "On %s skin it can feel thick and sit on the surface." % skin
        elif skin == 'dry':
            feel = "On dry skin that heavier layer can still feel comfortable."
        else:
            feel = ("On oily or combination skin it can feel thick. "
                    "On dry skin it can feel comfortable.")
        flags.append({
            'type': 'climate_texture', 'severity': 'info',
            'title': 'How this may feel',
            'message': "%s is a heavy occlusive. %s" % (heavy[0], feel),
        })
    elif data['humidity'] == 'low' and not heavy and category != 'facial oil':
        # A facial oil is the sealing step. Telling someone to put a richer
        # layer over squalane or rosehip oil describes a gel, not an oil.
        if skin == 'oily':
            feel = "On oily skin a light texture is usually enough."
        else:
            feel = ("This formula is light on occlusives. On dry skin a "
                    "richer layer over it will hold water in longer.")
        flags.append({
            'type': 'climate_texture', 'severity': 'info',
            'title': 'How this may feel',
            'message': feel,
        })
    return flags



# Which flag types each question is responsible for, so a check can report
# whether its own question turned anything up.
_CHECK_FLAGS = {
    'skin_tone': ('pih_risk', 'burn_risk'),
    'climate': ('climate_texture',),
    'allergens': ('declared_allergen',),
    'routine': ('routine_conflict', 'routine_redundant'),
}


def _summarise_checks(profile, flags, climate_key, ingredient_list):
    """One row per question: what was asked, and what came back.

    Written so that an unanswered question, an answered question that found
    something, and an answered question that found nothing are three visibly
    different states. Before this they collapsed into one - an empty flag list.
    """
    by_type = {}
    for flag in flags:
        by_type.setdefault(flag.get('type'), []).append(flag)

    def row(key, label, answer, clear_text):
        found = []
        for flag_type in _CHECK_FLAGS[key]:
            found.extend(by_type.get(flag_type, []))
        if not answer:
            return {'key': key, 'label': label, 'status': 'unanswered',
                    'answer': None, 'finding': None}
        if found:
            return {'key': key, 'label': label, 'status': 'flagged',
                    'answer': answer,
                    'finding': found[0].get('message') or found[0].get('title')}
        return {'key': key, 'label': label, 'status': 'clear',
                'answer': answer, 'finding': clear_text}

    tone = profile.get('fitzpatrick')
    tone_data = FITZPATRICK.get(tone) or {}
    allergens = [a for a in (profile.get('allergens') or []) if a]
    routine_raw = str(profile.get('current_routine') or '').strip()
    routine_families = parse_routine(routine_raw)

    allergen_names = ', '.join(
        (ALLERGEN_GROUPS.get(a) or {}).get('label', a) for a in allergens)
    climate_label = (CLIMATE.get(climate_key) or {}).get('label')

    return [
        row('skin_tone', 'Skin tone',
            ('Type %s' % tone) if tone else None,
            # FITZPATRICK['label'] is a description ("Burns minimally, tans
            # easily"), not a name, so it reads as nonsense in this sentence.
            'Nothing in this formula raises dark-mark risk for type %s skin.' % tone),
        row('climate', 'Climate',
            climate_label if profile.get('climate') else None,
            'Nothing about this texture works against a %s climate.'
            % (str(climate_label or '').lower() or 'your')),
        row('allergens', 'Sensitivities',
            allergen_names or None,
            'None of the things you avoid are in this formula.'),
        row('routine', 'Current routine',
            (', '.join(sorted(routine_families)) or 'nothing recognised')
            if routine_raw else None,
            'No clash with what you already use, and nothing here duplicates it.'),
    ]


def build_personal_context(profile, ingredient_list, concerns, category, country=None,
                           skin_type=None):
    """Everything personal, in one call.

    Returns flags (advisory, user-facing) and fit_penalty (applies to the Fit
    score only - never to formulation quality).
    """
    profile = profile or {}
    flags = []

    allergen_flags, fit_penalty = check_allergens(
        ingredient_list, profile.get('allergens'))
    flags.extend(allergen_flags)

    routine_families = parse_routine(profile.get('current_routine'))
    routine_flags, product_families = check_routine(ingredient_list, routine_families)
    flags.extend(routine_flags)

    flags.extend(fitzpatrick_context(profile, ingredient_list, concerns))

    climate_key = resolve_climate(profile, country)
    if profile.get('climate'):
        flags.extend(climate_context(
            climate_key, ingredient_list, category, skin_type))

    answered = sum(1 for k in ('fitzpatrick', 'climate', 'allergens', 'current_routine')
                   if profile.get(k))
    return {
        'flags': flags,
        'checks': _summarise_checks(profile, flags, climate_key, ingredient_list),
        'fit_penalty': fit_penalty,
        'climate': climate_key,
        'climate_label': (CLIMATE.get(climate_key) or {}).get('label'),
        'fitzpatrick': profile.get('fitzpatrick'),
        'product_active_families': sorted(product_families),
        'routine_active_families': sorted(routine_families),
        'questions_answered': answered,
        'personalisation_level': (
            'high' if answered >= 3 else 'partial' if answered >= 1 else 'none'),
    }

"""
Formulation scoring - how well-made is this product, for what it is?

Design rules (deliberate; each is evidence-driven):

1.  PRICE IS NOT A QUALITY SIGNAL. This module never sees price. No published
    basis exists for judging formulation quality by price-per-ml, so value is
    scored separately and shown alongside, never folded in. A 16,000 serum and
    a 700 serum are judged against the same formulation standard.

2.  EVERY CATEGORY RUBRIC SUMS TO EXACTLY 100. A flawless product in any
    category can reach 100. Previously a moisturiser could not exceed 49 no
    matter how well formulated, which made the scale meaningless.

3.  CATEGORIES ARE SCORED ON WHAT THEY ARE FOR. A cleanser earns nothing for
    "actives" (30-60s contact, then rinsed). A sunscreen is scored on its
    filter *system*, not filter count. A mask is scored on what 15 minutes of
    occlusion can actually deliver.

4.  MORE IS NOT BETTER. Actives score by proximity to their evidenced optimal
    concentration, not by magnitude. Benzoyl peroxide at 2.5% is as effective
    as 10% with less irritation (Mills 1986), so 2.5% earns full marks.

5.  PERSONAL RISK FACTORS ARE NOT FORMULATION DEFECTS. Pregnancy status,
    fragrance sensitivity and comedogenic response vary by person. These are
    surfaced as flags and folded into the personal Fit score - never deducted
    from the product's formulation quality.

6.  WE STATE WHAT WE CANNOT KNOW. EU 1223/2009 Art. 19 permits ingredients
    under 1% to be listed in any order, so concentration below the 1% line is
    not inferable. Every score carries a confidence level that says so.
"""

import math
import re

from data_loader import data_loader

# --- Detection sets ---------------------------------------------------------

_WATER = {'aqua', 'water', 'eau', 'aqua (water)', 'water (aqua)', 'aqua/water'}

# Chelators support preservative efficacy and oxidative stability, and act
# synergistically with preservatives in challenge testing (PMID 27761899).
_CHELATORS = {
    'disodium edta', 'tetrasodium edta', 'trisodium edta',
    'tetrasodium glutamate diacetate', 'sodium phytate', 'phytic acid',
    'trisodium ethylenediamine disuccinate', 'pentasodium pentetate',
    'sodium gluconate', 'etidronic acid',
}

_ANTIOXIDANT_STABILISERS = {
    'tocopherol', 'tocopheryl acetate', 'bht', 'ferulic acid',
    'sodium metabisulfite', 'ubiquinone', 'carnosine', 'sodium sulfite',
    'rosmarinus officinalis leaf extract',
}

# Actives whose degradation makes a stabiliser genuinely load-bearing. Light,
# oxygen and metal ions dominate retinoid/ascorbic acid loss (PMID 33206444).
_OXIDATION_PRONE = {
    'retinol', 'retinal', 'retinaldehyde', 'retinyl palmitate', 'retinyl acetate',
    'hydroxypinacolone retinoate', 'ascorbic acid', 'l-ascorbic acid',
    'tetrahexyldecyl ascorbate', 'ubiquinone', 'bakuchiol', 'resveratrol',
    'epigallocatechin gallate',
}

# Raise efficacy and irritation potential together (PMC11056976). Context, not
# a defect.
_PENETRATION_ENHANCERS = {
    'propylene glycol', 'ethoxydiglycol', 'dimethyl isosorbide',
    'transcutol', 'lecithin',
}

# The three physiological barrier lipids. The evidenced signal is COMPLETENESS:
# applying one or two alone *delays* barrier recovery (Mao-Qiang 1993/1995,
# Man 1996). "Contains ceramides" on its own is a weak signal.
_CERAMIDE_MARKERS = ('ceramide',)
_CHOLESTEROL_MARKERS = ('cholesterol',)
_FATTY_ACID_MARKERS = (
    'stearic acid', 'palmitic acid', 'linoleic acid', 'oleic acid', 'lauric acid',
    'myristic acid', 'behenic acid', 'phytosphingosine', 'sphingosine',
    'sodium lauroyl lactylate', 'isostearic acid',
)

_OCCLUSIVES = (
    'petrolatum', 'paraffinum liquidum', 'mineral oil', 'cera alba', 'beeswax',
    'lanolin', 'squalane', 'dimethicone', 'cyclopentasiloxane',
    'butyrospermum parkii', 'cera microcristallina', 'hydrogenated polyisobutene',
    'caprylic/capric triglyceride', 'isopropyl palmitate', 'cetyl esters',
    'cetearyl alcohol', 'cetyl alcohol', 'stearyl alcohol', 'behenyl alcohol',
)

# Fragrance and declarable allergens. EU 2023/1545 expanded Annex III well past
# the old "26 allergens" figure. This is a PERSONAL RISK signal, not a defect:
# general-population fragrance allergy is 0.7-2.6% (PMID 32475515).
_FRAGRANCE = ('parfum', 'fragrance', 'aroma')
# Same thing on Indian and plain-language labels. Named in the tolerability
# sentence so it cannot read "no common irritants", and not scored here:
# fragrance stays a personal warning, not a general-score penalty.
_FRAGRANCE_LABELS = ('perfume', 'sugandhit')
_FRAGRANCE_ALLERGENS = (
    'limonene', 'linalool', 'citronellol', 'geraniol', 'eugenol', 'coumarin',
    'citral', 'farnesol', 'benzyl benzoate', 'benzyl salicylate',
    'cinnamal', 'cinnamyl alcohol', 'hexyl cinnamal', 'isoeugenol', 'amyl cinnamal',
    'hydroxycitronellal', 'alpha-isomethyl ionone', 'butylphenyl methylpropional',
    'anise alcohol', 'benzyl cinnamate',
)
_ESSENTIAL_OIL_MARKERS = (
    'essential oil', 'citrus aurantium', 'citrus limon', 'citrus bergamia',
    'lavandula', 'mentha piperita', 'eucalyptus', 'melaleuca alternifolia',
    'cymbopogon', 'pelargonium graveolens', 'cananga odorata', 'jasminum',
    'santalum album', 'citrus grandis peel oil', 'rosmarinus officinalis oil',
)

# NOTE: the "alcohol denat is drying" claim is NOT supported at cosmetic
# concentrations - 60-80% ethanol hand rubs are *less* irritating than soap
# (PMID 17578437, 17868216). Weighted lightly, and mainly as a penetration
# enhancer that amplifies co-formulated actives.
_DRYING_ALCOHOLS = ('alcohol denat', 'sd alcohol', 'isopropyl alcohol',
                    'denatured alcohol')

# Anionic sulfates are the most irritating; anionic+non-ionic blends measurably
# reduce irritation vs anionic alone (PMID 40795538).
_HARSH_SURFACTANTS = (
    'sodium lauryl sulfate', 'ammonium lauryl sulfate', 'sodium laureth sulfate',
    'ammonium laureth sulfate', 'sodium c14-16 olefin sulfonate',
    'sodium dodecylbenzenesulfonate', 'tea-lauryl sulfate',
)
# True soaps are alkaline by nature and shift skin pH more than syndets
# (PMID 30160004, 9407174).
_SOAP_SURFACTANTS = (
    'sodium palmate', 'sodium stearate', 'sodium cocoate', 'sodium tallowate',
    'potassium palmate', 'potassium cocoate', 'potassium stearate',
    'sodium olivate', 'potassium olivate', 'sodium palm kernelate',
)
_MILD_SURFACTANTS = (
    'cocamidopropyl betaine', 'coco-glucoside', 'decyl glucoside', 'lauryl glucoside',
    'caprylyl/capryl glucoside', 'sodium cocoyl isethionate',
    'sodium methyl cocoyl taurate', 'disodium cocoamphodiacetate',
    'sodium cocoyl glycinate', 'sodium lauroyl sarcosinate', 'coco betaine',
    'sodium lauroyl methyl isethionate', 'sodium cocoyl glutamate',
    'disodium laureth sulfosuccinate', 'sodium lauroyl glutamate',
    'polyglyceryl-4 caprate', 'lauramidopropyl betaine',
)

# Proxy for whether pH was deliberately managed.
_PH_ADJUSTERS = (
    'citric acid', 'sodium citrate', 'sodium hydroxide', 'triethanolamine',
    'potassium hydroxide', 'sodium lactate', 'gluconolactone', 'arginine',
    'aminomethyl propanol', 'sodium bicarbonate', 'malic acid', 'lactic acid',
)

# Peptides work at parts-per-million (Matrixyl at 3 ppm - PMID 18492182), so
# concentration-scaled scoring is invalid for them: presence is the signal.
_PPM_EFFECTIVE = ('peptide', 'palmitoyl', 'acetyl hexapeptide', 'copper tripeptide')

# Concept-level pseudo-INCI records that exist in the database alongside real
# ingredients. They must never be treated as a dosed active.
_CONCEPT_RECORDS = {
    'ceramides', 'humectants', 'antioxidants', 'peptides', 'preservatives',
    'occlusives', 'silicones', 'emulsifiers', 'chemical uv filters',
    'mineral uv filters', 'parabens', 'liposomes', 'niosomes', 'amino acids',
    'phospholipids', 'polyhydroxy acids', 'probiotics', 'prebiotics',
    'fatty alcohols', 'plant oils', 'retinoids', 'uv filters', 'surfactants',
}


def _norm(name):
    return re.sub(r'\s+', ' ', str(name or '').strip().lower())


def _find(ingredient_list, markers):
    """Return ingredients whose normalised name contains any marker."""
    out = []
    for ing in ingredient_list:
        n = _norm(ing)
        if any(m in n for m in markers):
            out.append(ing)
    return out


def _any(ingredient_list, markers):
    return bool(_find(ingredient_list, markers))


_WATER_TOKENS = {'aqua', 'water', 'eau'}


def _has_water(name):
    """A water token counts after a slash split.

    'Water/Aqua/Eau' and 'Purified Water' are water. A short list such as
    niacinamide and zinc PCA has neither token.
    """
    n = _norm(name)
    if n in _WATER:
        return True
    for chunk in re.split(r'[/]+', n):
        tokens = re.findall(r'[a-z]+', chunk)
        if any(tok in _WATER_TOKENS for tok in tokens):
            return True
    return False


def is_anhydrous(ingredient_list):
    """Water-free products (oils, balms, silicone systems) do not require
    preservation. Penalising them for lacking a preservative would be wrong."""
    return not any(_has_water(i) for i in ingredient_list)


_LIGHT_PHASE = (
    'coco-caprylate', 'coco caprylate', 'caprylic/capric triglyceride',
    'caprylic capric triglyceride', 'isoamyl laurate', 'dicaprylyl ether',
    'c13-15 alkane', 'c15-19 alkane', 'squalane', 'hemisqualane',
    'isopropyl myristate', 'isopropyl palmitate', 'ethylhexyl palmitate',
)
_EMULSIFIER_MARKERS = (
    'glyceryl stearate', 'cetearyl alcohol', 'cetyl alcohol', 'stearyl alcohol',
    'cetearyl glucoside', 'polysorbate', 'peg-', 'ceteareth', 'steareth',
    'sorbitan', 'lecithin', 'polyglyceryl', 'coco-glucoside',
    'sodium stearoyl', 'glyceryl oleate', 'olive oil peg', 'cetyl peg',
    'arachidyl glucoside', 'behenyl alcohol', 'inulin lauryl',
)


def _light_oil_name(name):
    n = _norm(name)
    if any(marker in n for marker in _LIGHT_PHASE):
        return True
    return n.endswith(' oil') or ' seed oil' in n or ' fruit oil' in n


def _has_emulsifier(ingredient_list):
    blob = ' '.join(_norm(ing) for ing in ingredient_list)
    return any(marker in blob for marker in _EMULSIFIER_MARKERS)


def _format_notes(ingredient_list):
    """Format facts read from the list itself.

    A water ingredient with a lightweight oil straight after it, and no
    emulsifier anywhere, is a two-phase mix. An extract that sits above the
    1% line and is not in the database is named, rather than skipped quietly.
    Neither note changes the score.
    """
    notes = []
    if (ingredient_list and _has_water(ingredient_list[0])
            and len(ingredient_list) > 1
            and _light_oil_name(ingredient_list[1])
            and not _has_emulsifier(ingredient_list)):
        oil = ingredient_list[1]
        notes.append({
            'type': 'formula_format',
            'severity': 'medium',
            'message': (
                "Water is listed with %s straight after it, and the list "
                "names no emulsifier. That is a two-phase formula: a watery "
                "layer and a lightweight oil that sit apart until they are "
                "shaken together. The oil is a large part of the texture."
                % oil
            ),
        })
    cutoff = one_percent_line(ingredient_list)
    missed = []
    for ing in ingredient_list[:cutoff]:
        n = _norm(ing)
        if data_loader.get_ingredient_data(ing):
            continue
        if not any(token in n for token in (
                'extract', ' oil', 'butter', 'juice', 'callus', 'stem cell')):
            continue
        missed.append(ing)
    if missed:
        shown = ", ".join(missed[:2])
        if len(missed) == 1:
            sentence = (
                "%s sits above the 1%% line and is not in the graded database, "
                "so this score does not include it." % shown
            )
        else:
            sentence = (
                "%s sit above the 1%% line and are not in the graded database, "
                "so this score does not include them." % shown
            )
        notes.append({
            'type': 'ungraded_ingredient',
            'severity': 'medium',
            'message': sentence,
        })
    for ing in ingredient_list:
        n = _norm(ing)
        if 'citrus nobilis' in n or n == 'mandarin peel extract':
            notes.append({
                'type': 'ingredient_role',
                'severity': 'info',
                'message': (
                    "Citrus nobilis peel extract is mandarin peel. It supplies "
                    "citrus flavonoids. It is not ascorbic acid, so it is not "
                    "a vitamin C active."
                ),
            })
            break
    for ing in ingredient_list:
        n = _norm(ing)
        if 'callus' in n or 'conditioned media' in n or 'stem cell' in n:
            notes.append({
                'type': 'ingredient_role',
                'severity': 'info',
                'message': (
                    "%s is a cell-culture medium. It is not the plant extract "
                    "of the same species, so it is not scored as that extract."
                    % ing
                ),
            })
            break
    return notes


def one_percent_line(ingredient_list):
    """Index of the first ingredient that reliably sits at or below 1%.

    Everything after this position is unordered under EU 1223/2009 Art. 19, so
    its concentration is not inferable. Returns len(list) if no marker found.
    """
    from config import CONCENTRATION_THRESHOLDS
    for i, ing in enumerate(ingredient_list):
        if any(m.lower() in _norm(ing) for m in CONCENTRATION_THRESHOLDS):
            return i
    return len(ingredient_list)


# Preservatives the ingredient database does not classify as such. Missing any
# of these produces a false "no preservative" warning on a properly preserved
# product, which is worse than useless - it tells the user a safe formula is
# unsafe.
_EXTRA_PRESERVATIVES = (
    'chlorhexidine', 'iodopropynyl butylcarbamate', 'methylisothiazolinone',
    'methylchloroisothiazolinone', 'benzalkonium chloride', 'benzethonium chloride',
    'sodium hydroxymethylglycinate', 'diazolidinyl urea', 'imidazolidinyl urea',
    'dmdm hydantoin', 'quaternium-15', 'sorbic acid',
    'zinc pyrithione', 'climbazole', 'piroctone olamine', 'undecylenic acid',
)

# Multifunctional humectants and solvents with mild antimicrobial activity.
# These BOOST a preservative system but are not adequate preservation on their
# own, so they earn partial credit rather than a clean pass.
_PRESERVATIVE_BOOSTERS = (
    'pentylene glycol', 'propanediol', '1,3-propanediol', 'butylene glycol',
    'hexylene glycol', 'glyceryl caprylate', 'glyceryl undecylenate',
    'caprylhydroxamic acid', 'ethylhexylglycerin', 'phenylpropanol',
)


def _has_preservative(ingredient_list):
    """True when the formula carries a recognised primary preservative."""
    preserved = data_loader.role_sets.get('preservative', set())
    for ing in ingredient_list:
        n = _norm(ing)
        if n in preserved:
            return True
        if any(m in n for m in _EXTRA_PRESERVATIVES):
            return True
        d = data_loader.get_ingredient_data(ing) or {}
        if 'preserv' in str(d.get('Functional_Category', '')).lower():
            return True
        if str(d.get('Ingredient_Class', '')).lower() == 'preservative':
            return True
    return False


def _has_preservative_booster(ingredient_list):
    """Multifunctionals that support preservation without replacing it."""
    return _any(ingredient_list, _PRESERVATIVE_BOOSTERS)


# --- Shared component scorers -----------------------------------------------
# Each returns (points, explanations, flags). Explanations are user-facing.


_STORY_MARKERS = (
    'spicule', 'hydrolyzed sponge', 'reedle',
    'exosome', 'extracellular vesicle', 'leaf vesicle',
    'sodium dna', 'polydeoxyribonucleotide',
)


def _is_story_ingredient(name):
    """A technology the label can name without ever stating a dose.

    Fruit-juice vesicles are citrus pulp, not exosomes.
    """
    n = _norm(name)
    if not n or 'fruit juice vesicle' in n:
        return False
    if n == 'pdrn':
        return True
    return any(m in n for m in _STORY_MARKERS)


def _dose_sentence(name, estimate, known=False):
    """Describe an estimated dose without ever contradicting the database.

    The wording used to depend on how well the active scored, not on its range,
    so a position-based estimate of 15% salicylic acid was reported as "within
    its evidenced effective range" when the database's own ceiling is 2%. The
    estimate comes from label position, which can only say "high on the list";
    it knows nothing about regulatory or safe limits. So the claim is checked
    against the ingredient's range, and an estimate above the maximum is not
    quoted at all - a number nobody could have formulated is not information.
    """
    data = data_loader.get_ingredient_data(name) or {}

    def _num(key):
        try:
            return float(str(data.get(key, '')).strip())
        except ValueError:
            return None

    lo, hi = _num('Min_Effective_%'), _num('Max_Safe_%')
    eu = _num('Max_Allowed_EU_%')

    if _is_story_ingredient(name) and not known:
        return ("The label names {} and does not state an amount. "
                "Its place in the list is not a measured dose.".format(name))
    if known and eu is not None and estimate > eu:
        return ("The label states {:g}%. Published EU ceiling for this "
                "ingredient is about {:g}%.".format(estimate, eu))
    if known and hi is not None and estimate > hi:
        return ("The label states {:g}%. Recorded maximum in this database "
                "is about {:g}%.".format(estimate, hi))
    if eu is not None and estimate > eu:
        return ("{} is high on the list. Published EU ceiling is about {:g}%. "
                "The label does not give the exact amount.".format(name, eu))
    if hi is not None and estimate > hi:
        return ("{} is high on the list. Recorded maximum in this database "
                "is about {:g}%. The label does not give the exact amount."
                .format(name, hi))
    if lo is not None and estimate < lo:
        return ("{} is estimated at {:.1f}%, below the usual starting dose "
                "of about {:g}%.".format(name, estimate, lo))
    if lo is not None and hi is not None:
        return ("{} at an estimated {:.1f}% (within its recorded range of "
                "{:g}-{:g}%)".format(name, estimate, lo, hi))
    return "{} at an estimated {:.1f}%".format(name, estimate)


def dose_band_label(name, estimate, known=False):
    """Same dose claim as _dose_sentence, for the ingredient table.

    The table used to grade an estimate with a separate scale, so one place
    could say an active was near its ceiling while another called the same
    estimate "within range".
    """
    data = data_loader.get_ingredient_data(name) or {}

    def _num(key):
        try:
            return float(str(data.get(key, '')).strip())
        except (TypeError, ValueError):
            return None

    lo, hi = _num('Min_Effective_%'), _num('Max_Safe_%')
    eu = _num('Max_Allowed_EU_%')
    try:
        estimate = float(estimate)
    except (TypeError, ValueError):
        return "Estimated from its place in the list."
    if _is_story_ingredient(name) and not known:
        return "Named on the label. No amount is stated."
    if known and eu is not None and estimate > eu:
        return ("The label states {:g}%. Published EU ceiling for this "
                "ingredient is about {:g}%.".format(estimate, eu))
    if known and hi is not None and estimate > hi:
        return ("The label states {:g}%. Recorded maximum in this database "
                "is about {:g}%.".format(estimate, hi))
    if eu is not None and estimate > eu:
        return ("High on the list. Published EU ceiling is about {:g}%. "
                "The label does not give the exact amount.".format(eu))
    if hi is not None and estimate > hi:
        return ("High on the list. Recorded maximum in this database is "
                "about {:g}%. The label does not give the exact amount.".format(hi))
    if lo is not None and estimate < lo:
        return "Under the recorded starting dose of about {:g}%.".format(lo)
    if lo is not None and hi is not None:
        if known:
            return ("Stated at {:g}%, within the recorded range of "
                    "{:g}–{:g}%.".format(estimate, lo, hi))
        return "Within the recorded range of {:g}–{:g}%.".format(lo, hi)
    if known:
        return "Stated at {:g}%.".format(estimate)
    return "Estimated from its place in the list."


_MATRIXYL_3000 = "matrixyl 3000"
_MATRIXYL_3000_PEPTIDES = (
    "palmitoyl tripeptide-1",
    "palmitoyl tetrapeptide-7",
)


def _matrixyl_trade_name_already_listed(ing, ingredient_list):
    """Matrixyl 3000 is a trade name, not a third peptide.

    A formula that only says Matrixyl 3000 is not rewritten into the two
    palmitoyl peptides. When those peptides are already on the label, the
    trade-name row is not scored again on top of them.
    """
    if _norm(ing) != _MATRIXYL_3000:
        return False
    listed = {_norm(name) for name in ingredient_list}
    return any(peptide in listed for peptide in _MATRIXYL_3000_PEPTIDES)


def _score_actives(ingredient_list, concentrations, max_pts, category,
                   known_concentrations=None):
    """Active efficacy: are actives present at concentrations with evidence?

    Scores proximity to the evidenced optimal, NOT magnitude. An active at its
    optimal dose scores full; below the minimum effective dose scores little;
    above the safe maximum is not rewarded further.
    """
    from scoring import get_concentration_factor, get_evidence_factor

    known = {(_norm(k)): v for k, v in (known_concentrations or {}).items()}
    cutoff = one_percent_line(ingredient_list)
    scored = []
    explanations = []
    flags = []
    seen_resolved = set()

    for pos, ing in enumerate(ingredient_list):
        n = _norm(ing)
        if n in _CONCEPT_RECORDS:
            continue
        data = data_loader.get_ingredient_data(ing)
        if not data:
            continue
        resolved = str(data.get('INCI_Name') or n).strip().lower()
        if resolved == _MATRIXYL_3000 and _matrixyl_trade_name_already_listed(
                resolved, ingredient_list):
            continue
        if resolved in seen_resolved:
            continue
        seen_resolved.add(resolved)
        klass = str(data.get('Ingredient_Class', '')).lower()
        if klass not in ('active', 'peptide', 'retinoid', 'brightening active'):
            continue

        est = known.get(n, concentrations.get(ing, concentrations.get(n, 0)) or 0)
        is_ppm = any(m in n for m in _PPM_EFFECTIVE) or klass == 'peptide'

        if is_ppm:
            # Peptides act at ppm; dose inference is meaningless. Presence with
            # evidence is the signal.
            conc_factor = 0.85
        else:
            conc_factor = get_concentration_factor(est, data)

        ev_factor = get_evidence_factor(data)
        tier_w = data_loader.get_activity_tier_weight(data) or 0.5

        # Below the 1% line concentration is legally unordered, so we cannot
        # claim a dose. Credit presence, but cap the claim.
        confident = pos < cutoff
        if not confident and not is_ppm:
            conc_factor = min(conc_factor, 0.55)

        contribution = conc_factor * ev_factor * max(tier_w, 0.35)
        if contribution <= 0:
            continue
        scored.append((ing, contribution, est, ev_factor, confident, is_ppm))

    if not scored:
        return 0.0, ["No actives with established evidence identified."], flags

    scored.sort(key=lambda x: x[1], reverse=True)

    # Diminishing returns: the first strong active carries most of the weight.
    # No evidence supports "more actives = better", and irritant load rises with
    # each addition, so extra actives add progressively less.
    total = 0.0
    for i, (ing, contribution, est, ev, confident, is_ppm) in enumerate(scored):
        total += contribution * (0.65 ** i)

    # Saturation point. A single optimal-dose, strong-evidence, tier-1 active
    # contributes ~0.9, so 1.0 lets one well-chosen hero active reach ~90% of
    # the budget alone - a benzoyl peroxide spot treatment is *supposed* to be
    # one active in a bland base, and should not be marked down for it.
    pts = min(max_pts, (total / 1.0) * max_pts)

    top = scored[0]
    if top[5]:
        explanations.append(
            "{} identified - peptides act at parts-per-million, so presence "
            "rather than percentage is what matters.".format(top[0])
        )
    elif top[2] > 0:
        explanations.append(_dose_sentence(top[0], top[2], _norm(top[0]) in known))
    else:
        explanations.append("{} identified.".format(top[0]))

    if len(scored) > 1:
        explanations.append(
            "Also present: {}.".format(", ".join(s[0] for s in scored[1:3]))
        )

    # Niacinamide is usually the highest contributor, so a reedle or an
    # exosome further down the list would otherwise never be mentioned.
    story = []
    for ing in ingredient_list:
        if not _is_story_ingredient(ing) or _norm(ing) in known:
            continue
        if _norm(ing) == _norm(top[0]):
            continue
        story.append(ing)
    if story:
        explanations.append(
            "The label names {} and does not state an amount. "
            "A place in the list is not a measured dose.".format(
                ", ".join(story[:3]))
        )

    unconfident = [s[0] for s in scored if not s[4] and not s[5]]
    if unconfident:
        flags.append({
            'type': 'dose_unknown',
            'severity': 'info',
            'message': "Listed below the 1% line, so the actual concentration "
                       "cannot be determined from the label: {}.".format(
                           ", ".join(unconfident[:3])),
        })

    return round(pts, 1), explanations, flags


def _score_evidence(ingredient_list, max_pts):
    """How well-supported are the actives in this formula?"""
    from scoring import get_evidence_factor

    factors = []
    for ing in ingredient_list:
        if _norm(ing) in _CONCEPT_RECORDS:
            continue
        data = data_loader.get_ingredient_data(ing)
        if not data:
            continue
        resolved = str(data.get('INCI_Name') or _norm(ing)).strip().lower()
        if resolved == _MATRIXYL_3000 and _matrixyl_trade_name_already_listed(
                resolved, ingredient_list):
            continue
        if str(data.get('Ingredient_Class', '')).lower() not in (
                'active', 'peptide', 'retinoid', 'brightening active'):
            continue
        factors.append(get_evidence_factor(data))

    if not factors:
        return 0.0, ["No actives to assess evidence for."]

    # Best-evidence-weighted mean: one well-evidenced active shouldn't be
    # dragged down by several speculative botanicals alongside it.
    factors.sort(reverse=True)
    weights = [0.55 ** i for i in range(len(factors))]
    weighted = sum(f * w for f, w in zip(factors, weights)) / sum(weights)

    pts = weighted * max_pts
    if weighted >= 0.85:
        note = "Actives here are backed by strong clinical evidence."
    elif weighted >= 0.65:
        note = "Actives here have moderate clinical support."
    elif weighted >= 0.45:
        note = "Evidence for these actives is limited."
    else:
        note = "Evidence for these actives is early or largely preliminary."
    return round(pts, 1), [note]


def _score_integrity(ingredient_list, max_pts, category):
    """Formulation integrity: preservation, stability, pH management.

    These are the signals an INCI list can genuinely support. Absence of a
    preservative in a water-containing product is the single most important
    safety signal available from a label.
    """
    explanations = []
    flags = []
    anhydrous = is_anhydrous(ingredient_list)

    # Preservation - 40% of the integrity budget.
    preserve_budget = max_pts * 0.40
    if anhydrous:
        preserve_pts = preserve_budget
        explanations.append(
            "Water-free formula - no preservative system required.")
    elif _has_preservative(ingredient_list):
        preserve_pts = preserve_budget
        explanations.append("Adequately preserved.")
    elif _has_preservative_booster(ingredient_list):
        # Multifunctional glycols raise the antimicrobial hurdle but are not
        # adequate preservation alone. Partial credit, and a softer message -
        # this is a formulation question, not an alarm.
        preserve_pts = preserve_budget * 0.5
        explanations.append(
            "Relies on multifunctional ingredients rather than a conventional "
            "preservative.")
        flags.append({
            'type': 'preservative_boosters_only',
            'severity': 'info',
            'message': "This formula appears to rely on multifunctional "
                       "ingredients (such as pentylene glycol) rather than a "
                       "conventional preservative. That can work, but it is a "
                       "narrower margin - pay attention to the shelf life once "
                       "opened.",
        })
    else:
        preserve_pts = 0.0
        explanations.append(
            "No recognised preservative in a water-containing formula.")
        flags.append({
            'type': 'no_preservative',
            'severity': 'high',
            'message': "This formula contains water but no preservative we can "
                       "identify. Water-based products need preservation to stay "
                       "microbiologically safe.",
        })

    # Oxidative / chelation support - 30%.
    stability_budget = max_pts * 0.30
    has_chelator = _any(ingredient_list, _CHELATORS)
    has_antiox = _any(ingredient_list, _ANTIOXIDANT_STABILISERS)
    prone = _find(ingredient_list, _OXIDATION_PRONE)
    if not prone:
        # 'Vitamin C' and 'HPR' are the ascorbic acid and hydroxypinacolone
        # records. The stability check has to see that record, not only the
        # shorthand written on the label.
        resolved = []
        for ing in ingredient_list:
            data = data_loader.get_ingredient_data(ing) or {}
            inci = str(data.get('INCI_Name') or '').strip()
            if inci:
                resolved.append(inci)
        prone = _find(resolved, _OXIDATION_PRONE)

    if prone:
        # A stabiliser is genuinely load-bearing here.
        if has_antiox and has_chelator:
            stability_pts = stability_budget
            explanations.append(
                "{} is oxidation-prone and this formula includes both an "
                "antioxidant and a chelator to protect it.".format(prone[0]))
        elif has_antiox or has_chelator:
            stability_pts = stability_budget * 0.65
            explanations.append(
                "{} is oxidation-prone and partially stabilised.".format(prone[0]))
        else:
            stability_pts = stability_budget * 0.15
            explanations.append(
                "{} degrades on exposure to light, air and metal ions, and no "
                "stabiliser is present.".format(prone[0]))
            flags.append({
                'type': 'unstabilised_active',
                'severity': 'medium',
                'message': "{} oxidises readily. Without an antioxidant or "
                           "chelator it may lose potency before the product is "
                           "finished. Opaque, air-tight packaging matters here."
                           .format(prone[0]),
            })
    else:
        if has_chelator or has_antiox:
            stability_pts = stability_budget
            explanations.append("Includes stability support.")
        else:
            stability_pts = stability_budget * 0.6

    # pH management - 30%.
    ph_budget = max_pts * 0.30
    if _any(ingredient_list, _PH_ADJUSTERS):
        ph_pts = ph_budget
        explanations.append("pH appears deliberately adjusted.")
    else:
        ph_pts = ph_budget * 0.55

    total = preserve_pts + stability_pts + ph_pts
    return round(min(max_pts, total), 1), explanations, flags


def _positive_float(data, field):
    raw = (data or {}).get(field)
    if raw is None or str(raw).strip() in ("", "nan", "None"):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or value <= 0:
        return None
    return value


def _eu_allowed(data):
    """Sourced EU legal cap, or None if this database has not recorded one."""
    return _positive_float(data, "Max_Allowed_EU_%")


def _recorded_max(data):
    """Database use/safety ceiling. Not a published legal limit."""
    ceilings = []
    for field in ("Typical_Use_Max_Pct", "Max_Safe_%"):
        value = _positive_float(data, field)
        if value is not None:
            ceilings.append(value)
    return min(ceilings) if ceilings else None


def _published_ceiling(data):
    """EU cap when we have one, otherwise the recorded database maximum."""
    return _eu_allowed(data) if _eu_allowed(data) is not None else _recorded_max(data)


def _declared_above_ceiling(ingredient_list, known_concentrations):
    """Declared doses above an EU cap or the recorded database maximum."""
    known = {_norm(k): v for k, v in (known_concentrations or {}).items()}
    hits = []
    for ing in ingredient_list:
        n = _norm(ing)
        if n not in known:
            continue
        try:
            declared = float(known[n])
        except (TypeError, ValueError):
            continue
        data = data_loader.get_ingredient_data(ing) or {}
        eu = _eu_allowed(data)
        recorded = _recorded_max(data)
        if eu is not None and declared > eu:
            hits.append((ing, declared, eu, "eu"))
        elif recorded is not None and declared > recorded:
            hits.append((ing, declared, recorded, "recorded"))
    return hits


def _score_tolerability(ingredient_list, max_pts, occlusive_context=False,
                        periocular=False, known_concentrations=None):
    """Irritant load, calibrated to the actual evidence.

    Fragrance is a personal risk factor (0.7-2.6% general-population allergy),
    not a formulation defect - so the deduction is modest here and the real
    weight is carried in the personal Fit score. It is weighted more heavily
    under occlusion (masks) and around the eye, where exposure is amplified.
    """
    explanations = []
    flags = []
    pts = float(max_pts)
    multiplier = 1.6 if (occlusive_context or periocular) else 1.0

    frag = _find(ingredient_list, _FRAGRANCE)
    labelled = _find(ingredient_list, _FRAGRANCE_LABELS)
    spicules = _find(ingredient_list, ('spicule', 'hydrolyzed sponge', 'reedle'))
    allergens = _find(ingredient_list, _FRAGRANCE_ALLERGENS)
    eos = _find(ingredient_list, _ESSENTIAL_OIL_MARKERS)
    alcohols = _find(ingredient_list, _DRYING_ALCOHOLS)

    if spicules:
        pts -= max_pts * 0.2
        explanations.append(
            "Contains {} (spicules). These are physical micro-needles, "
            "so stinging comes from the spicules.".format(spicules[0])
        )
        flags.append({
            'type': 'spicules',
            'severity': 'medium',
            'message': "Contains spicules ({}). They prick the skin surface. "
                       "The label does not state how many, or their size."
                       .format(spicules[0]),
        })
    if frag:
        pts -= max_pts * 0.18 * multiplier
        explanations.append("Contains fragrance.")
        flags.append({
            'type': 'fragrance',
            'severity': 'info',
            'message': "Contains fragrance.",
        })
    if allergens:
        pts -= max_pts * 0.10 * multiplier
        flags.append({
            'type': 'eu_declarable_allergens',
            'severity': 'info',
            'message': "Contains EU-declarable fragrance allergens ({}). These "
                       "become sensitising mainly once oxidised by air."
                       .format(", ".join(allergens[:3])),
        })
    if eos:
        pts -= max_pts * 0.14 * multiplier
        explanations.append("Contains essential oils.")
        flags.append({
            'type': 'essential_oils',
            'severity': 'info',
            'message': "Contains essential oils ({}). Their sensitising "
                       "potential rises as they oxidise with age and air "
                       "exposure.".format(", ".join(eos[:2])),
        })
    if alcohols:
        # Deliberately light. See module docstring - the "drying" claim is not
        # supported at cosmetic concentrations.
        pts -= max_pts * 0.08
        flags.append({
            'type': 'volatile_alcohol',
            'severity': 'info',
            'message': "Contains denatured alcohol. Contrary to common belief, "
                       "there is little evidence this damages the barrier at "
                       "cosmetic levels, but it does help other ingredients "
                       "penetrate, which can amplify their irritancy.",
        })

    over = _declared_above_ceiling(ingredient_list, known_concentrations)
    if over:
        # One modest deduction. The active still scores as the ceiling dose;
        # going further is an irritation concern, not a weaker active.
        pts -= max_pts * 0.12
        eu_hits = [h for h in over if h[3] == "eu"]
        recorded_hits = [h for h in over if h[3] != "eu"]
        if eu_hits:
            named = ", ".join(
                "{} at {:g}% (published EU ceiling about {:g}%)".format(
                    ing, dose, ceiling)
                for ing, dose, ceiling, _kind in eu_hits[:3]
            )
            explanations.append(
                "Stated above the published EU ceiling: {}.".format(named))
            flags.append({
                'type': 'above_published_ceiling',
                'severity': 'info',
                'message': "Stated above the published EU ceiling: {}. "
                           "That can increase irritation. It is not scored as a "
                           "weaker active than the dose at the ceiling.".format(named),
            })
        if recorded_hits:
            named = ", ".join(
                "{} at {:g}% (recorded maximum about {:g}%)".format(
                    ing, dose, ceiling)
                for ing, dose, ceiling, _kind in recorded_hits[:3]
            )
            explanations.append(
                "Stated above the recorded maximum in this database: {}.".format(named))
            flags.append({
                'type': 'above_recorded_maximum',
                'severity': 'info',
                'message': "Stated above the recorded maximum in this database: {}. "
                           "That can increase irritation. It is not scored as a "
                           "weaker active than the dose at the recorded maximum.".format(named),
            })

    if periocular and (frag or eos):
        flags.append({
            'type': 'periocular_irritant',
            'severity': 'medium',
            'message': "Fragrance or essential oils in an eye product. Eyelid "
                       "skin is the thinnest on the face and absorbs several "
                       "times more than facial skin.",
        })

    if pts >= max_pts:
        if labelled:
            explanations.append("Contains fragrance.")
        else:
            explanations.append("No common irritants identified.")
    return round(max(0.0, pts), 1), explanations, flags


def _score_hydration(ingredient_list, max_pts):
    """Humectant system quality. Glycerin high in the list is a strong signal
    (Fluhr 1999 - accelerates barrier recovery, mitigates SLS damage)."""
    humectants = data_loader.role_sets.get('humectant', set())
    found = []
    for pos, ing in enumerate(ingredient_list):
        n = _norm(ing)
        d = data_loader.get_ingredient_data(ing) or {}
        if (n in humectants
                or 'humectant' in str(d.get('Functional_Category', '')).lower()
                or str(d.get('Ingredient_Class', '')).lower() == 'humectant'):
            found.append((ing, pos))

    if not found:
        return 0.0, ["No humectants identified."]

    pts = 0.0
    # Position matters: a humectant in the top 5 is present at a meaningful level.
    for i, (ing, pos) in enumerate(found[:5]):
        positional = 1.0 if pos < 5 else (0.65 if pos < 10 else 0.4)
        pts += max_pts * 0.44 * positional * (0.55 ** i)

    glycerin_high = any('glycerin' in _norm(i) and p < 5 for i, p in found)
    notes = ["Hydration from {}.".format(
        ", ".join(i for i, _ in found[:3]))]
    if glycerin_high:
        notes.append("Glycerin appears high in the list, where it has the "
                     "strongest evidence for barrier support.")
    return round(min(max_pts, pts), 1), notes


def _score_barrier(ingredient_list, max_pts):
    """Barrier and occlusive system.

    The evidenced signal is lipid COMPLETENESS - ceramide plus cholesterol plus
    a fatty acid. Applying one or two of the three alone delays barrier recovery
    (Mao-Qiang 1993/1995). A complete set is rewarded strongly; ceramides alone
    are not.
    """
    has_cer = _any(ingredient_list, _CERAMIDE_MARKERS)
    has_chol = _any(ingredient_list, _CHOLESTEROL_MARKERS)
    has_fa = _any(ingredient_list, _FATTY_ACID_MARKERS)
    occl = _find(ingredient_list, _OCCLUSIVES)

    pts = 0.0
    notes = []
    lipid_budget = max_pts * 0.55

    complete = has_cer and has_chol and has_fa
    if complete:
        pts += lipid_budget
        notes.append("Contains a complete physiological lipid set - ceramides, "
                     "cholesterol and fatty acids together. This is the "
                     "combination shown to restore the skin barrier; ceramides "
                     "alone do not.")
    else:
        present = sum([has_cer, has_chol, has_fa])
        if present == 2:
            pts += lipid_budget * 0.55
            notes.append("Contains two of the three barrier lipids. The full "
                         "set (ceramide, cholesterol and fatty acid) is what "
                         "the barrier-repair evidence rests on.")
        elif present == 1:
            pts += lipid_budget * 0.30
            if has_cer:
                notes.append("Contains ceramides, but without cholesterol and "
                             "fatty acids alongside them the barrier-repair "
                             "evidence does not fully apply.")
        # No lipids: no points from this budget.

    occl_budget = max_pts * 0.45
    if occl:
        top_occl = [o for o in occl if _norm(ingredient_list[0]) != _norm(o)]
        depth = min(1.0, 0.45 + 0.20 * len(set(_norm(o) for o in occl)))
        pts += occl_budget * depth
        notes.append("Occlusive support from {}.".format(
            ", ".join(sorted(set(occl), key=lambda x: occl.index(x))[:3])))
    else:
        notes.append("No occlusive ingredients identified to slow water loss.")

    return round(min(max_pts, pts), 1), notes


def seal_label(ingredient_list):
    """How much of a film this formula leaves to slow water loss.

    Counted from occlusive ingredients only. Humectants draw water in; they
    do not seal it, so they do not raise this label.
    """
    found = _find(ingredient_list, _OCCLUSIVES)
    count = len({_norm(o) for o in found})
    if count >= 3:
        return {
            'label': 'Slowed a lot',
            'note': "Several ingredients sit on the skin and slow water from "
                    "evaporating. The finish is heavier, which helps in dry air "
                    "and can feel like too much when the air is humid.",
        }
    if count >= 1:
        return {
            'label': 'Slowed a little',
            'note': "One or two ingredients slow water loss a little. "
                    "Comfortable in humid weather. Dry skin often wants more.",
        }
    return {
        'label': 'Barely slowed',
        'note': "Almost nothing here slows water from leaving the skin. "
                "Ingredients that draw water in can still be present, but "
                "that water is easier to lose.",
    }


def _score_soothing(ingredient_list, max_pts):
    soothing = data_loader.role_sets.get('soothing', set())
    found = []
    for ing in ingredient_list:
        n = _norm(ing)
        d = data_loader.get_ingredient_data(ing) or {}
        if n in soothing or 'sooth' in str(d.get('Functional_Category', '')).lower():
            found.append(ing)
    if not found:
        return 0.0, ["No soothing agents identified."]
    pts = min(max_pts, max_pts * (0.55 + 0.22 * (len(found) - 1)))
    return round(pts, 1), ["Soothing support from {}.".format(
        ", ".join(sorted(set(found), key=found.index)[:3]))]


# --- Category-specific scorers ----------------------------------------------


def _score_surfactant_system(ingredient_list, max_pts):
    """Cleanser mildness - the dominant quality criterion for this category.

    Anionic sulfates are the most irritating; amphoteric and non-ionic systems
    are milder, and anionic+non-ionic blends measurably reduce irritation
    versus anionic alone (PMID 40795538). True soaps are alkaline by nature and
    shift skin pH more than syndets (PMID 30160004).

    Note: INCI-derived mildness is a coarse screen, not a verdict - in vitro
    and in vivo mildness measures are known to diverge (PMID 42150358).
    """
    harsh = _find(ingredient_list, _HARSH_SURFACTANTS)
    soap = _find(ingredient_list, _SOAP_SURFACTANTS)
    mild = _find(ingredient_list, _MILD_SURFACTANTS)

    # Anything the database knows is a surfactant but our lists do not name.
    known_surf = data_loader.role_sets.get('surfactant', set())
    other = [i for i in ingredient_list
             if _norm(i) in known_surf
             and i not in harsh and i not in soap and i not in mild]

    explanations = []
    flags = []

    if not (harsh or soap or mild or other):
        # No surfactant identified - likely an oil cleanser, balm or micellar.
        return round(max_pts * 0.70, 1), [
            "No conventional surfactant identified - this may be an oil, balm "
            "or micellar cleanser, which are typically gentle."], flags

    if harsh and not mild:
        pts = max_pts * 0.28
        explanations.append(
            "Built on {} - a sulfate surfactant, the harshest common class."
            .format(harsh[0]))
        flags.append({
            'type': 'harsh_surfactant',
            'severity': 'medium',
            'message': "Contains {}. Sulfate surfactants strip more lipid than "
                       "gentler alternatives and are the most likely cause of "
                       "tightness after washing.".format(harsh[0]),
        })
    elif harsh and mild:
        # Blending a non-ionic/amphoteric with an anionic genuinely reduces
        # irritation versus the anionic alone - but only meaningfully when the
        # sulfate is not still doing most of the cleansing. Position matters:
        # a sulfate listed before the gentle co-surfactants is the primary
        # agent, and the blend bonus should be small.
        _pos = {_norm(i): k for k, i in enumerate(ingredient_list)}
        harsh_first = min((_pos.get(_norm(h), 99) for h in harsh), default=99)
        mild_first = min((_pos.get(_norm(m), 99) for m in mild), default=99)
        if harsh_first < mild_first:
            pts = max_pts * 0.42
            explanations.append(
                "Built primarily on {}, a sulfate surfactant, with gentler "
                "co-surfactants further down the list."
                .format(harsh[0]))
            flags.append({
                'type': 'harsh_surfactant',
                'severity': 'info',
                'message': "{} is the main cleansing agent here. The gentler "
                           "co-surfactants soften it, but this is still a "
                           "sulfate-led formula.".format(harsh[0]),
            })
        else:
            pts = max_pts * 0.66
            explanations.append(
                "Led by gentler surfactants ({}) with {} as a secondary agent, "
                "which measurably reduces irritation versus a sulfate alone."
                .format(mild[0], harsh[0]))
    elif soap and not mild:
        pts = max_pts * 0.35
        explanations.append(
            "A true soap system, which is alkaline by nature.")
        flags.append({
            'type': 'alkaline_soap',
            'severity': 'medium',
            'message': "Soap-based cleansers are alkaline and raise skin pH "
                       "more than syndet cleansers, which measurably increases "
                       "water loss and redness.",
        })
    elif mild:
        distinct = len(set(_norm(m) for m in mild))
        pts = max_pts * min(1.0, 0.78 + 0.09 * (distinct - 1))
        explanations.append(
            "Built on gentle surfactants ({}).".format(
                ", ".join(sorted(set(mild), key=mild.index)[:3])))
    else:
        pts = max_pts * 0.60
        explanations.append("Surfactant system identified.")

    return round(min(max_pts, pts), 1), explanations, flags


def _score_cleanser_ph(ingredient_list, max_pts):
    """Cleanser pH. This is one of the few places pH evidence is genuinely
    strong: alkaline soap raises skin pH and increases water loss and erythema
    versus syndets (PMID 30160004, 9407174, 18286774)."""
    soap = _find(ingredient_list, _SOAP_SURFACTANTS)
    acidifier = _any(ingredient_list, ('citric acid', 'lactic acid',
                                       'sodium citrate', 'gluconolactone',
                                       'malic acid', 'sodium lactate'))
    if soap:
        return round(max_pts * 0.25, 1), [
            "Soap-based, so almost certainly alkaline (pH 9-10). Healthy skin "
            "sits below pH 5."]
    if acidifier:
        return round(max_pts, 1), [
            "Contains acidifiers, indicating the pH is adjusted towards skin's "
            "own acidic range."]
    return round(max_pts * 0.65, 1), [
        "Syndet-style formula. Actual pH is not stated on the label and cannot "
        "be determined from the ingredient list."]


def _score_uv_system(ingredient_list, max_pts_uva, max_pts_photo, max_pts_uvb):
    """Score the sunscreen FILTER SYSTEM, not the filter count.

    A two-filter photostable system can outperform a five-filter unstable one.
    Avobenzone is photounstable alone and needs a stabiliser partner
    (PMID 16289662, 20354650).
    """
    filters = []
    for ing in ingredient_list:
        uv = data_loader.get_uv_data(ing)
        if uv and 'filter' in str(uv.get('Ingredient_Category', '')).lower():
            filters.append((ing, uv))

    explanations = []
    flags = []
    if not filters:
        return (0.0, 0.0, 0.0,
                ["No UV filters identified in this ingredient list."],
                [{'type': 'no_uv_filter', 'severity': 'high',
                  'message': "No UV filters were identified. If this is a "
                             "sunscreen, the ingredient list may be incomplete."}])

    def _strength(v):
        v = str(v or '').strip().lower()
        return {'very high': 1.0, 'high': 0.8, 'moderate': 0.55,
                'low': 0.3, 'none': 0.0}.get(v, 0.0)

    # --- UVA protection ---
    uva_scores = sorted((_strength(uv.get('UVA_Strength')) for _, uv in filters),
                        reverse=True)
    uva_cover = 0.0
    for i, s in enumerate(uva_scores):
        uva_cover += s * (0.55 ** i)
    uva_pts = min(max_pts_uva, (uva_cover / 1.5) * max_pts_uva)

    uva1 = [ing for ing, uv in filters
            if 'uva1' in str(uv.get('UVA_Subtype_Coverage', '')).lower()]
    if uva1:
        explanations.append(
            "Covers UVA1 (the longest, deepest-penetrating wavelengths) via {}."
            .format(", ".join(uva1[:2])))
    elif uva_scores and uva_scores[0] >= 0.8:
        explanations.append("Strong UVA protection.")
    else:
        explanations.append(
            "UVA protection looks limited. UVA drives photoageing and passes "
            "through glass.")
        flags.append({
            'type': 'weak_uva',
            'severity': 'medium',
            'message': "This filter system offers limited UVA coverage. The EU "
                       "requires UVA protection of at least one third of the "
                       "labelled SPF; not all markets do.",
        })

    # --- Photostability of the system ---
    photo_pts = max_pts_photo
    unstable = [(ing, uv) for ing, uv in filters
                if str(uv.get('Photostability_Rating', '')).strip().lower()
                in ('low', 'poor', 'very low')]
    middling = [(ing, uv) for ing, uv in filters
                if str(uv.get('Photostability_Rating', '')).strip().lower()
                in ('moderate', 'medium')]
    stabilisers = [ing for ing, uv in filters
                   if str(uv.get('Photostabilizer', '')).strip().lower().startswith('yes')]
    # Film formers and SPF boosters also contribute to real-world performance.
    film_formers = [ing for ing, uv in filters
                    if str(uv.get('Film_Former', '')).strip().lower().startswith('yes')]

    if unstable and not stabilisers:
        photo_pts = max_pts_photo * 0.30
        explanations.append(
            "{} degrades in sunlight and no photostabiliser is present."
            .format(unstable[0][0]))
        flags.append({
            'type': 'photounstable_system',
            'severity': 'high',
            'message': "{} breaks down under UV exposure. Without a stabilising "
                       "partner, protection drops during sun exposure - which is "
                       "exactly when it is needed.".format(unstable[0][0]),
        })
    elif unstable and stabilisers:
        photo_pts = max_pts_photo * 0.88
        explanations.append(
            "{} is photounstable on its own but is stabilised here by {}."
            .format(unstable[0][0], stabilisers[0]))
    elif middling:
        # Partially photostable filters (octinoxate and the salicylates) lose
        # meaningful protection over a few hours of exposure. Not a failure,
        # but not the full budget either.
        photo_pts = max_pts_photo * (0.80 if stabilisers else 0.62)
        explanations.append(
            "{} is only moderately photostable, so protection declines over "
            "several hours of sun exposure.".format(middling[0][0]))
    else:
        explanations.append("Filter system is inherently photostable.")

    # --- UVB adequacy ---
    uvb_scores = sorted((_strength(uv.get('UVB_Strength')) for _, uv in filters),
                        reverse=True)
    uvb_cover = 0.0
    for i, s in enumerate(uvb_scores):
        uvb_cover += s * (0.55 ** i)
    uvb_pts = min(max_pts_uvb, (uvb_cover / 1.5) * max_pts_uvb)
    if film_formers:
        uvb_pts = min(max_pts_uvb, uvb_pts * 1.06)
        explanations.append(
            "Includes a film former, which helps the filter layer stay even.")

    explanations.append(
        "{} UV filters identified. What matters is how well the system covers "
        "the spectrum and holds up in sunlight, not how many filters there are."
        .format(len(filters)))

    # The dominant real-world failure mode is under-application, not formula.
    flags.append({
        'type': 'application_amount',
        'severity': 'info',
        'message': "Labelled SPF is measured at 2 mg/cm2. Most people apply a "
                   "quarter to a half of that, and protection falls off sharply "
                   "below the test amount - so real-world protection is usually "
                   "well under the number on the bottle.",
    })

    return (round(uva_pts, 1), round(photo_pts, 1), round(uvb_pts, 1),
            explanations, flags)


def _score_oil_lipids(ingredient_list, max_pts, skin_type='normal'):
    """Lipid profile for facial oils.

    Reuses the existing fatty-acid profiling in scoring._facial_oil_score rather
    than duplicating it - that logic already reads linoleic/oleic balance and
    oil diversity, which is the right basis. Low sebum linoleate is associated
    with comedogenesis, and topical linoleic acid reduced microcomedones
    (Downing 1986, Letawe 1998).
    """
    from scoring import _facial_oil_score
    try:
        res = _facial_oil_score(ingredient_list, 0, 0, 'India',
                                None, skin_type=skin_type)
    except Exception:
        return round(max_pts * 0.5, 1), [
            "Could not assess the lipid profile of this oil blend."]

    fa = float(res.get('fa_score', 0) or 0)          # 0-50 raw
    pts = min(max_pts, (fa / 50.0) * max_pts)

    # The fatty-acid model reads linoleic/oleic balance across a BLEND, so it
    # scores near zero for two things it should rate highly:
    #   - squalane, which is a saturated hydrocarbon, not a triglyceride, and
    #     is among the most stable and best-tolerated emollients available;
    #   - single-oil products, which have no "diversity" to measure but can be
    #     excellent (100% squalane, cold-pressed rosehip, pure jojoba).
    # Pilgrim's 100% Squalane scored 8.4/35 on lipid profile before this.
    _PREMIUM_EMOLLIENTS = {
        'squalane': 1.00,           # saturated, non-comedogenic, very stable
        'simmondsia chinensis': 0.92,   # jojoba - wax ester, sebum-mimetic
        'caprylic/capric triglyceride': 0.88,
        'argania spinosa': 0.85,
        'rosa canina': 0.82,
        'sclerocarya birrea': 0.82,     # marula
        'coco-caprylate': 0.85,
        'isoamyl laurate': 0.85,
        'sesamum indicum': 0.72,
        'helianthus annuus': 0.70,
        'prunus amygdalus dulcis': 0.72,
        'olea europaea': 0.62,
        'cocos nucifera oil': 0.40,     # highly comedogenic on facial skin
    }
    best = 0.0
    best_name = None
    for ing in ingredient_list:
        n = _norm(ing)
        for marker, quality in _PREMIUM_EMOLLIENTS.items():
            if marker in n and quality > best:
                best, best_name = quality, ing
    if best:
        # Judge the oil on the quality of its base lipid, and take whichever
        # reading is kinder - a rich blend scores through the fatty-acid model,
        # a pure single oil scores through this one.
        pts = max(pts, best * max_pts)

    notes = []
    lin = res.get('linoleic_count', 0)
    ole = res.get('oleic_count', 0)
    div = res.get('oil_diversity', 0)
    if lin and ole:
        notes.append(
            "Balanced fatty acid profile - {} linoleic-rich and {} oleic-rich "
            "oil(s).".format(lin, ole))
    elif lin:
        notes.append(
            "Linoleic-rich profile, which suits oilier and acne-prone skin.")
    elif ole:
        notes.append(
            "Oleic-rich profile, which suits drier skin but is heavier and more "
            "occlusive.")
    if div:
        notes.append("{} distinct plant oils identified.".format(div))
    if not notes:
        notes.append("No recognised plant oils identified in this formula.")
    return round(pts, 1), notes


def _score_oil_stability(ingredient_list, max_pts):
    """Oxidative stability for facial oils.

    This is the evidence-based route to comedogenicity: lipid PEROXIDES are
    comedogenic (PMID 6223652, 10845185), not the oils themselves. Scoring
    oxidative protection is defensible; scoring ingredients against the 1980s
    rabbit-ear comedogenicity scale is not (PMID 16488305).
    """
    has_antiox = _any(ingredient_list, _ANTIOXIDANT_STABILISERS)
    # Saturated / highly stable bases resist peroxidation.
    stable_base = _any(ingredient_list, (
        'squalane', 'caprylic/capric triglyceride', 'jojoba',
        'simmondsia chinensis', 'coco-caprylate', 'isoamyl laurate'))
    # Squalene (unsaturated) is NOT squalane - its peroxides are strongly
    # implicated in comedogenesis.
    raw_squalene = [i for i in ingredient_list
                    if _norm(i) == 'squalene']

    pts = max_pts * 0.35
    notes = []
    flags = []
    if has_antiox:
        pts += max_pts * 0.40
        notes.append("Contains an antioxidant to slow oxidation - important, "
                     "because it is oxidised oil, not fresh oil, that clogs pores.")
    else:
        notes.append("No antioxidant identified. Unsaturated oils oxidise over "
                     "time, and their peroxides are the comedogenic form.")
        flags.append({
            'type': 'no_oil_antioxidant',
            'severity': 'info',
            'message': "No antioxidant identified in an oil formula. Store it "
                       "away from light and heat, and replace it if it smells "
                       "sharp or metallic.",
        })
    if stable_base:
        pts += max_pts * 0.25
        notes.append("Built on an oxidation-resistant base.")
    if raw_squalene:
        pts -= max_pts * 0.20
        flags.append({
            'type': 'squalene_not_squalane',
            'severity': 'medium',
            'message': "This lists squalene rather than squalane. Squalene "
                       "oxidises readily and its peroxides are strongly linked "
                       "to comedone formation; squalane is the stable "
                       "hydrogenated form.",
        })
    return round(max(0.0, min(max_pts, pts)), 1), notes, flags


# --- Category rubrics -------------------------------------------------------
# Every rubric sums to exactly 100. Weights encode what each category is FOR.

CATEGORY_RUBRICS = {
    'serum': {
        'label': 'Serum',
        'components': [
            ('actives', 'Active Efficacy', 40),
            ('evidence', 'Evidence Quality', 20),
            ('integrity', 'Formulation Integrity', 25),
            ('tolerability', 'Tolerability', 15),
        ],
        'rationale': "A serum's job is to carry active ingredients into the "
                     "skin. Most of the score is whether those ingredients are "
                     "present at amounts that have been shown to work, and "
                     "whether the formula is built to keep them stable.",
    },
    'moisturizer': {
        'label': 'Moisturiser',
        'components': [
            ('barrier', 'Barrier & Occlusive System', 30),
            ('hydration', 'Humectant System', 25),
            ('integrity', 'Formulation Integrity', 20),
            ('tolerability', 'Tolerability', 15),
            ('actives', 'Added Actives (bonus)', 10),
        ],
        'rationale': "A moisturiser's job is to add water to the skin and hold "
                     "it there. Most of the score is the ingredients that draw "
                     "water in, and the ones that slow it from leaving. A name "
                     "such as glow or vitamin C does not change that job. How "
                     "well it treats dullness or pigmentation is a separate "
                     "score. A plain cream can still score well.",
    },
    'cleanser': {
        'label': 'Cleanser',
        'components': [
            ('surfactant', 'Surfactant Mildness', 40),
            ('ph', 'pH Suitability', 20),
            ('post_cleanse', 'Post-Cleanse Support', 15),
            ('integrity', 'Formulation Integrity', 15),
            ('tolerability', 'Tolerability', 10),
        ],
        'rationale': "A cleanser stays on the skin for under a minute, then "
                     "it is rinsed off. The score is how gently it cleans: "
                     "the surfactants, the pH, and whether the skin is left "
                     "comfortable. Actives on a wash-off product count for "
                     "very little.",
    },
    'sunscreen': {
        'label': 'Sunscreen',
        'components': [
            ('uva', 'UVA Protection', 30),
            ('photostability', 'Filter Photostability', 25),
            ('uvb', 'UVB Protection', 20),
            ('integrity', 'Formulation Integrity', 15),
            ('tolerability', 'Tolerability', 10),
        ],
        'rationale': "A sunscreen is scored on its filters. The questions are "
                     "whether they cover both UVA and UVB, and whether they "
                     "stay effective in sunlight. A longer filter list is not, "
                     "by itself, a better sunscreen.",
    },
    'toner': {
        'label': 'Toner / Essence',
        'components': [
            ('hydration', 'Humectant System', 35),
            ('soothing', 'Soothing Support', 25),
            ('actives', 'Active Efficacy', 20),
            ('tolerability', 'Tolerability', 20),
        ],
        'rationale': "A toner is a light layer left on the skin. It is "
                     "scored on hydration and how soothing it feels. It is not "
                     "expected to do the work of a serum or a moisturiser.",
    },
    'eye cream': {
        'label': 'Eye Cream',
        'components': [
            ('tolerability', 'Suitability for Eye Area', 35),
            ('hydration', 'Hydration & Barrier', 30),
            ('integrity', 'Formulation Integrity', 20),
            ('actives', 'Targeted Actives', 15),
        ],
        'rationale': "The skin around the eyes is thin and takes in more of "
                     "what is applied, so gentleness carries the most weight. "
                     "Hydration and barrier support come next. A separate eye "
                     "cream is not assumed to work better than a well-made "
                     "facial moisturiser.",
    },
    'mask': {
        'label': 'Mask',
        'components': [
            ('hydration', 'Hydration Payload', 35),
            ('tolerability', 'Comfort Under Occlusion', 30),
            ('integrity', 'Formulation Integrity', 20),
            ('actives', 'Contact-Appropriate Actives', 15),
        ],
        'rationale': "A mask stays on for about 10 to 20 minutes, then it "
                     "comes off. That is long enough to hydrate and soothe, "
                     "and too short for a full course of actives. Comfort "
                     "while it sits on the skin counts for more than the "
                     "actives.",
    },
    'facial oil': {
        'label': 'Facial Oil',
        'components': [
            ('barrier', 'Lipid & Emollient Profile', 35),
            ('stability', 'Oxidative Stability', 30),
            ('tolerability', 'Tolerability', 20),
            ('evidence', 'Ingredient Evidence', 15),
        ],
        'rationale': "An oil is scored on the lipids it is made from, and on "
                     "whether those oils stay stable. Fresh oil is not the "
                     "problem. Oil that has oxidised is.",
    },
    'treatment': {
        'label': 'Treatment',
        'components': [
            ('actives', 'Active Efficacy', 40),
            ('evidence', 'Evidence Quality', 20),
            ('integrity', 'Formulation Integrity', 20),
            ('tolerability', 'Tolerability', 20),
        ],
        'rationale': "A treatment is scored on whether its active is present "
                     "at an amount shown to work. A higher percentage is not "
                     "automatically better. Benzoyl peroxide at 2.5% works "
                     "about as well as 10%, with less irritation.",
    },
}

_CATEGORY_ALIASES = {
    'serum': 'serum', 'essence': 'toner', 'ampoule': 'serum',
    'moisturizer': 'moisturizer', 'moisturiser': 'moisturizer',
    'cream': 'moisturizer', 'lotion': 'moisturizer', 'gel': 'moisturizer',
    'cleanser': 'cleanser', 'face wash': 'cleanser', 'cleansing oil': 'cleanser',
    'sunscreen': 'sunscreen', 'sunblock': 'sunscreen', 'spf': 'sunscreen',
    'toner': 'toner', 'mist': 'toner',
    'eye cream': 'eye cream', 'eye gel': 'eye cream', 'eye serum': 'eye cream',
    'mask': 'mask', 'sheet mask': 'mask', 'sleeping mask': 'mask',
    'wash-off mask': 'mask',
    'facial oil': 'facial oil', 'oil': 'facial oil', 'face oil': 'facial oil',
    'treatment': 'treatment', 'spot treatment': 'treatment',
}


def resolve_category(category):
    key = _norm(category)
    return _CATEGORY_ALIASES.get(key, 'serum')


def _name_claim_gaps(ingredient_list, product_name):
    """The product title promises a technology the ingredient list does not name."""
    name = (product_name or '').lower()
    blob = ' '.join(ingredient_list or []).lower()
    notes = []
    if any(k in name for k in ('reedle', 'spicule')) and not any(
            k in blob for k in ('hydrolyzed sponge', 'spicule', 'reedle')):
        notes.append(
            "The name says reedle, and the ingredient list does not name "
            "hydrolyzed sponge or spicules.")
    if 'exosome' in name and not any(
            k in blob for k in ('exosome', 'extracellular vesicle', 'leaf vesicle')):
        notes.append(
            "The name says exosome, and the ingredient list does not name "
            "an exosome or extracellular vesicle.")
    if re.search(r'\bpdrn\b', name) and not any(
            k in blob for k in (
                'sodium dna', 'pdrn', 'polydeoxyribonucleotide',
                'deoxyribonucleic')) and not re.search(r'\bdna\b', blob):
        notes.append(
            "The name says PDRN, and the ingredient list does not name "
            "DNA, sodium DNA, or PDRN.")
    if any(k in name for k in ('microneedle', 'micro-needle', 'micro needle')):
        notes.append(
            "This is a dissolving microneedle patch. The score covers the "
            "ingredients on the list. The label does not state a needle "
            "size or how much those needles deliver.")
    return notes


def score_formulation(ingredient_list, concentrations, category,
                      known_concentrations=None, product_name=None):
    """Score how well-made this product is, for what it is. Price-independent.

    Returns a dict with the 0-100 score, the per-component breakdown with
    plain-language explanations, an honest confidence level, and any flags.
    """
    cat_key = resolve_category(category)
    rubric = CATEGORY_RUBRICS[cat_key]
    ingredient_list = list(ingredient_list or [])
    concentrations = concentrations or {}

    if not ingredient_list:
        return {
            'score': 0, 'category': cat_key, 'category_label': rubric['label'],
            'rationale': rubric['rationale'], 'components': [],
            'seal': seal_label([]),
            'flags': [], 'confidence': 'none',
            'confidence_note': "No ingredients were provided.",
        }

    occlusive = cat_key == 'mask'
    periocular = cat_key == 'eye cream'
    all_flags = []
    components = []

    for key, label, weight in rubric['components']:
        notes = []
        flags = []

        if key == 'actives':
            pts, notes, flags = _score_actives(
                ingredient_list, concentrations, weight, cat_key,
                known_concentrations)
        elif key == 'evidence':
            if cat_key == 'facial oil':
                # An oil's evidence rests on its lipids and antioxidants, not on
                # "actives" - 100% squalane has no active by class and was
                # scoring 0/15 despite being an excellent, well-evidenced
                # emollient.
                pts, notes = _score_evidence(ingredient_list, weight)
                if pts < weight * 0.5:
                    lipids = _find(ingredient_list, tuple(_OCCLUSIVES) + ('oil', 'squalane'))
                    if lipids:
                        pts = max(pts, weight * 0.62)
                        notes = ["Built on well-characterised emollient lipids "
                                 "({}).".format(", ".join(sorted(set(lipids))[:2]))]
            else:
                pts, notes = _score_evidence(ingredient_list, weight)
        elif key == 'integrity':
            pts, notes, flags = _score_integrity(ingredient_list, weight, cat_key)
        elif key == 'tolerability':
            pts, notes, flags = _score_tolerability(
                ingredient_list, weight,
                occlusive_context=occlusive, periocular=periocular,
                known_concentrations=known_concentrations)
        elif key == 'hydration':
            pts, notes = _score_hydration(ingredient_list, weight)
        elif key == 'barrier':
            if cat_key == 'facial oil':
                pts, notes = _score_oil_lipids(ingredient_list, weight)
            else:
                pts, notes = _score_barrier(ingredient_list, weight)
        elif key == 'soothing':
            pts, notes = _score_soothing(ingredient_list, weight)
        elif key == 'surfactant':
            pts, notes, flags = _score_surfactant_system(ingredient_list, weight)
        elif key == 'ph':
            pts, notes = _score_cleanser_ph(ingredient_list, weight)
        elif key == 'post_cleanse':
            hyd_pts, hyd_notes = _score_hydration(ingredient_list, weight * 0.6)
            bar_pts, bar_notes = _score_barrier(ingredient_list, weight * 0.4)
            pts = round(hyd_pts + bar_pts, 1)
            notes = ["Leaves supporting ingredients behind after rinsing."] \
                if pts > weight * 0.4 else \
                ["Little is left on the skin after rinsing."]
        elif key == 'stability':
            pts, notes, flags = _score_oil_stability(ingredient_list, weight)
        elif key in ('uva', 'photostability', 'uvb'):
            # Computed once for the whole filter system.
            continue
        else:
            pts, notes = 0.0, []

        components.append({
            'key': key, 'label': label, 'score': round(float(pts), 1),
            'max': weight, 'notes': notes,
        })
        all_flags.extend(flags)

    # Sunscreen: the three UV components are interdependent, so score together.
    if cat_key == 'sunscreen':
        weights = {k: w for k, _, w in
                   [(a, b, c) for a, b, c in rubric['components']]}
        uva_pts, photo_pts, uvb_pts, uv_notes, uv_flags = _score_uv_system(
            ingredient_list, weights['uva'], weights['photostability'],
            weights['uvb'])
        for key, label, pts in (
                ('uva', 'UVA Protection', uva_pts),
                ('photostability', 'Filter Photostability', photo_pts),
                ('uvb', 'UVB Protection', uvb_pts)):
            components.append({
                'key': key, 'label': label, 'score': pts,
                'max': weights[key],
                'notes': uv_notes if key == 'uva' else [],
            })
        all_flags.extend(uv_flags)
        order = [k for k, _, _ in rubric['components']]
        components.sort(key=lambda c: order.index(c['key']))

    total = sum(c['score'] for c in components)
    total = max(0.0, min(100.0, total))

    if cat_key == 'sunscreen':
        _uva = next((c for c in components if c['key'] == 'uva'), None)
        if _uva and _uva['max'] and (_uva['score'] / _uva['max']) < 0.45:
            # Capped, not zeroed: it still blocks UVB, which is worth something.
            total = min(total, 55.0)
            all_flags.append({
                'type': 'uva_gate',
                'severity': 'high',
                'message': "This filter system is weak on UVA, which is the "
                           "band that drives photoageing and passes through "
                           "glass. Its overall score is capped for that reason "
                           "even though it performs on UVB.",
            })

    for note in _format_notes(ingredient_list):
        all_flags.append(note)

    claim_notes = _name_claim_gaps(ingredient_list, product_name)
    for ing in ingredient_list:
        if _norm(ing) in ('cyanocobalamin', 'vitamin b12'):
            all_flags.append({
                'type': 'ingredient_role',
                'severity': 'info',
                'message': (
                    "Cyanocobalamin is vitamin B12. It is naturally pink, "
                    "which is what gives a pink serum its colour."
                ),
            })
            break
    if claim_notes:
        placed = False
        for comp in components:
            if comp.get('key') == 'actives':
                comp['notes'] = list(comp.get('notes') or []) + claim_notes
                placed = True
                break
        if not placed and components:
            components[0]['notes'] = list(components[0].get('notes') or []) + claim_notes
        for note in claim_notes:
            all_flags.append({'type': 'label_claim', 'severity': 'medium', 'message': note})

    # --- Honest confidence ---
    cutoff = one_percent_line(ingredient_list)
    declared_names = []
    known = known_concentrations or {}
    for ing in ingredient_list:
        if _norm(ing) in known or ing.lower().strip() in known:
            declared_names.append(ing)
    if declared_names and len(declared_names) < len(ingredient_list):
        confidence = 'moderate'
        shown = ", ".join(declared_names[:3])
        extra = len(declared_names) - 3
        if extra > 0:
            shown += " and %d more" % extra
        verb = "is" if len(declared_names) == 1 else "are"
        note = ("%s %s stated on the label. The other amounts are estimated "
                "from ingredient order." % (shown, verb))
    elif declared_names:
        confidence = 'high'
        note = ("Concentrations were declared for this product, so the active "
                "assessment is based on stated figures rather than inference.")
    elif cutoff < len(ingredient_list) and cutoff >= 4:
        confidence = 'moderate'
        note = ("Amounts are estimated from ingredient order. "
                "The 1% line is at {}. Ingredients after that line "
                "may be listed in any order, so their amounts cannot "
                "be read from the label."
                .format(ingredient_list[cutoff]))
    else:
        confidence = 'low'
        if any(c['key'] == 'actives' for c in components):
            note = ("No concentrations are declared and the ingredient list "
                    "gives few positional clues, so active doses are inferred "
                    "and may be wrong.")
        else:
            # Categories that do not score actives (cleansers, sunscreens) have
            # no dose to be wrong about; what is uncertain there is the
            # formulation detail a label cannot show.
            note = ("The ingredient list gives few positional clues, and a "
                    "label cannot show pH or the exact surfactant ratios, so "
                    "treat this assessment as an informed estimate.")

    return {
        'score': int(round(total)),
        'category': cat_key,
        'category_label': rubric['label'],
        'rationale': rubric['rationale'],
        'seal': seal_label(ingredient_list),
        'components': components,
        'flags': all_flags,
        'confidence': confidence,
        'confidence_note': note,
    }


# --- Value (kept strictly separate from formulation quality) -----------------


def score_value(price, size_ml, category, country='India'):
    """Price fairness. Deliberately NOT part of the formulation score.

    No published or standards-body basis exists for judging skincare quality by
    price-per-ml - it is a consumer cost-of-use heuristic, nothing more. Folding
    it into a quality score is what previously capped an excellent but expensive
    product at 75/100 regardless of how it was made. It is reported alongside
    the formulation score so the user can weigh both.
    """
    from config import CATEGORY_AVERAGES, CATEGORY_AVERAGES_DEFAULT

    cat_key = resolve_category(category)
    # config uses slightly different keys than our internal rubric names.
    lookup = {'moisturizer': 'moisturizer', 'facial oil': 'oil',
              'eye cream': 'eye cream', 'sunscreen': 'sunscreen',
              'cleanser': 'cleanser', 'toner': 'toner', 'mask': 'mask',
              'treatment': 'treatment', 'serum': 'serum'}.get(cat_key, 'serum')

    table = CATEGORY_AVERAGES.get(country, CATEGORY_AVERAGES_DEFAULT)
    avg = (table.get(lookup) or {}).get('avg_price_per_ml', 0)

    try:
        price = float(price or 0)
        size_ml = float(size_ml or 0)
    except (TypeError, ValueError):
        price, size_ml = 0.0, 0.0

    if price <= 0 or size_ml <= 0:
        return {
            'available': False,
            'tier': 'unknown',
            'headline': "Enter a price and size to see how this compares.",
            'price_per_ml': None, 'category_avg': avg, 'ratio': None,
            'note': "",
        }

    ppm = price / size_ml
    ratio = (ppm / avg) if avg > 0 else 1.0

    if ratio <= 0.6:
        tier, headline = 'excellent', "Well below the typical price for this category."
    elif ratio <= 1.0:
        tier, headline = 'good', "Priced at or below the category average."
    elif ratio <= 1.8:
        tier, headline = 'fair', "Priced somewhat above the category average."
    elif ratio <= 3.5:
        tier, headline = 'premium', "Priced well above the category average."
    else:
        tier, headline = 'luxury', "Priced far above the category average."

    return {
        'available': True,
        'tier': tier,
        'headline': headline,
        'price_per_ml': round(ppm, 2),
        'category_avg': avg,
        'ratio': round(ratio, 2),
        'note': "",
    }


# --- Advisory flags (informational only - never affect any score) ------------

# Only sourced restrictions surface in the product report: cannot-use, or
# use-in-limited-amounts. An empty pregnancy field, or "Can be used", is not
# a warning. Missing reproductive studies are not a pregnancy caution.
_PREGNANCY_CAUTION = (
    'cannot be used', 'do not use', 'not recommended', 'contraindicated',
    'avoid', 'limited amount', 'limited area', 'sparingly',
)
_PREGNANCY_CLEAR = ('safe', 'can be used')


def is_pregnancy_caution(raw):
    """True only for a pregnancy restriction the customer needs to see.

    Empty, 'Can be used', and 'Safe' are not warnings. Generic 'Avoid'
    notes (carcinogen, leave-on, children, acne-prone skin) are not
    pregnancy cautions. Retinoids and hydroquinone still match because
    they say cannot-be-used.
    """
    low = str(raw or '').strip().lower()
    if not low:
        return False
    if low.startswith('safe') and 'cannot' not in low:
        return False
    if (low.startswith('can be used')
            and 'limited' not in low and 'sparingly' not in low):
        return False
    if 'cannot be used' in low:
        return True
    if any(p in low for p in ('limited amount', 'limited area', 'sparingly')):
        return True
    scoped = any(w in low for w in (
        'pregnan', 'breast', 'nurs', 'foetal', 'fetal', 'teratogen',
        'acog', 'embryopath',
    ))
    if not scoped:
        return False
    if any(p in low for p in (
            'sun exposure', 'sunlight', 'acne-prone', 'acne prone',
            'barrier-damaged', 'barrier damaged')):
        return False
    return any(c in low for c in (
        'avoid', 'do not use', 'not recommended', 'contraindicated',
        'cannot be used',
    ))


def build_advisory_flags(ingredient_list):
    """Contextual advisories that depend on the PERSON, not the product.

    Pregnancy status, breastfeeding and personal sensitivities are user context.
    A retinol serum is not a worse-made product because it is unsuitable during
    pregnancy - it is simply not for that user right now. These are surfaced as
    information and used by the personal Fit score; they never reduce the
    formulation score.

    Only sourced cannot-use and limited-use notes are shown. An empty
    field, or "Can be used", is not a warning.
    """
    pregnancy = []
    for ing in ingredient_list:
        if _norm(ing) in _CONCEPT_RECORDS:
            continue
        data = data_loader.get_ingredient_data(ing)
        if not data:
            continue
        raw = str(data.get('Pregnancy_Safety', '') or '').strip()
        if not raw or not is_pregnancy_caution(raw):
            continue
        low = raw.lower()
        severity = 'high' if (
            'cannot be used' in low or 'avoid' in low
            or 'contraindicated' in low or 'do not use' in low
        ) else 'info'
        pregnancy.append({
            'ingredient': ing,
            'severity': severity,
            'guidance': raw,
        })

    flags = []
    if pregnancy:
        strict = [p for p in pregnancy if p['severity'] == 'high']
        limited = [p for p in pregnancy if p['severity'] != 'high']
        if strict and not limited:
            message = (
                "Do not use this product if you are pregnant or breastfeeding. "
                "This does not affect the product's quality score."
            )
        elif limited and not strict:
            message = (
                "These ingredients can be used during pregnancy only in "
                "limited amounts. This does not affect the product's quality score."
            )
        else:
            message = (
                "Some ingredients in this product cannot be used during "
                "pregnancy; others only in limited amounts. This does not "
                "affect the product's quality score."
            )
        flags.append({
            'type': 'pregnancy',
            'severity': 'info',
            'affects_score': False,
            'title': "If you are pregnant or breastfeeding",
            'message': message,
            'items': pregnancy[:8],
            'strict_count': len(strict),
        })
    return flags


# --- Plain-language labels --------------------------------------------------


def formulation_tier(score, category=None):
    """A label describing HOW WELL MADE the product is - not whether it is
    cheap, and not whether it suits you. Those are reported separately."""
    label = CATEGORY_RUBRICS.get(resolve_category(category or 'serum'),
                                 {}).get('label', 'product')
    # Thresholds calibrated against 90 real Indian-market products across all
    # nine categories (tests/indian_corpus.py), where the observed median was
    # 82. Most commercial skincare is competently formulated, so without this
    # calibration half the market reads as "well formulated" and the label
    # stops discriminating. "Excellent" is deliberately rare.
    if score >= 92:
        return "Excellent formulation"
    if score >= 82:
        return "Well formulated"
    if score >= 70:
        return "Solidly formulated"
    if score >= 55:
        return "Average formulation"
    if score >= 40:
        return "Weak formulation"
    return "Poorly formulated"


def formulation_summary(score, category, components, confidence):
    """One sentence a user can act on, naming the strongest and weakest part."""
    cat = CATEGORY_RUBRICS.get(resolve_category(category), {}).get(
        'label', 'product').lower()
    if not components:
        return "Not enough ingredient information to assess this {}.".format(cat)

    # Strength/weakness measured as proportion of each component's own budget,
    # so a 10-point component is not automatically "the weakest".
    ranked = sorted(components,
                    key=lambda c: (c['score'] / c['max']) if c['max'] else 0)
    weakest, strongest = ranked[0], ranked[-1]

    if score >= 82:
        stem = "This is a well-made {}".format(cat)
    elif score >= 70:
        stem = "This is a solidly formulated {}".format(cat)
    elif score >= 65:
        stem = "This is a reasonable {}".format(cat)
    elif score >= 50:
        stem = "This is an average {}".format(cat)
    else:
        stem = "This {} has real formulation weaknesses".format(cat)

    parts = [stem]
    if strongest['score'] / max(strongest['max'], 1) >= 0.7:
        parts.append("its strongest point is {}".format(
            strongest['label'].lower()))
    if weakest['score'] / max(weakest['max'], 1) < 0.55:
        parts.append("the weakest is {}".format(weakest['label'].lower()))

    sentence = parts[0]
    if len(parts) == 2:
        sentence += " - " + parts[1] + "."
    elif len(parts) == 3:
        sentence += " - " + parts[1] + ", while " + parts[2] + "."
    else:
        sentence += "."

    # Dose uncertainty only matters where actives are scored. A cleanser is
    # judged on its surfactant system and a sunscreen on its filters, so telling
    # either that "active doses are inferred" is a caveat about something that
    # category does not measure.
    actives_scored = any(c.get('key') == 'actives' for c in components)
    if confidence == 'low' and actives_scored:
        sentence += (" Confidence is low here: no concentrations are declared, "
                     "so active doses are inferred from ingredient order.")
    return sentence

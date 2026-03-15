import re
import math
from data_loader import data_loader, CONCERNS_MAP, CONCERN_INCI_PREFIXES
from config import (
    CATEGORY_AVERAGES, WORTH_MULTIPLIERS, CONCENTRATION_THRESHOLDS,
    CATEGORY_AVERAGES_DEFAULT,
    WORSENING_INGREDIENTS
)


def extract_concentrations_from_inci(ingredient_list_str):
    """Scan raw INCI text for explicit percentage annotations and return a dict
    of {normalized_lower_name: float_pct}. This must be called BEFORE any stripping
    of percentages from the text.

    Handles patterns like:
      "Niacinamide 10%", "10% Niacinamide", "Salicylic Acid (2%)", "2% Salicylic Acid"
    """
    if not ingredient_list_str:
        return {}

    found = {}
    patterns = [
        # "10% Niacinamide" — number precedes name
        re.compile(r'([\d]+\.?\d*)\s*%\s*\(?\s*([a-zA-Z][a-zA-Z0-9 \-\/]{2,40}?)\s*\)?(?=[,;\n\|+&\.]|$)', re.I),
        # "Niacinamide 10%" or "Niacinamide (10%)"
        re.compile(r'([a-zA-Z][a-zA-Z0-9 \-\/]{2,40}?)\s+\(?(\d+\.?\d*)\s*%\)?', re.I),
    ]
    for pat in patterns:
        for m in pat.finditer(ingredient_list_str):
            g = m.groups()
            try:
                if g[0][0].isdigit():
                    pct, raw_name = float(g[0]), g[1]
                else:
                    raw_name, pct = g[0], float(g[1])
                if not (0 < pct <= 60):
                    continue
                # Normalize the same way parse_ingredients() does: strip parens, lowercase
                norm = re.sub(r'\([^)]*\)', '', raw_name).strip().strip('.-/ ').lower()
                if len(norm) > 2 and not norm[0].isdigit():
                    if norm not in found:
                        found[norm] = pct
            except (ValueError, IndexError):
                pass
    return found


def parse_ingredients(ingredient_list_str):
    """Normalize and parse an INCI ingredient list.
    Handles: comma/semicolon/linebreak separators, parenthetical descriptors
    like (Vitamin B3) or (10%), and combined entries like (and)/(und)/(et).
    Also deduplicates entries.
    """
    if not ingredient_list_str:
        return []

    # Replace emojis with commas (emojis often used as separators between ingredients)
    ingredient_list_str = re.sub(
        r'[\U0001F300-\U0001F9FF\U00002700-\U000027BF'
        r'\U0000FE00-\U0000FE0F\U00002600-\U000026FF\U0001FA00-\U0001FAFF]',
        ',', ingredient_list_str
    )
    # Strip "Key Ingredients:" / "Ingredients:" / "Full Ingredients:" prefix
    marker = re.search(r'(?:key\s+)?(?:full\s+)?ingred\w*\s*:', ingredient_list_str, re.IGNORECASE)
    if marker:
        ingredient_list_str = ingredient_list_str[marker.end():]

    # Split by comma, semicolon, or line breaks
    raw_parts = re.split(r'[,;\n\r]+', ingredient_list_str)

    cleaned = []
    seen = set()

    _UI_TAILS = re.compile(
        r'\s*(read\s*more|show\s*more|view\s*more|see\s*more|load\s*more)\s*$',
        re.IGNORECASE
    )
    _MARKETING_VERBS = re.compile(
        r'\b(brighten|moisturis|moisturiz|protect|reduces?|smooth|hydrat|repair|nourish|soothe|firm|tone|revitaliz|rejuvenat)\b',
        re.IGNORECASE
    )

    for part in raw_parts:
        part = part.strip().strip('.')
        part = _UI_TAILS.sub('', part).strip()
        if not part:
            continue

        # Handle "Ingredient: marketing description" — keep only left side
        if ':' in part:
            left, right = part.split(':', 1)
            if _MARKETING_VERBS.search(right):
                part = left.strip()

        # Skip if entire segment is a marketing sentence
        if _MARKETING_VERBS.search(part) and ',' not in part and len(part) > 30:
            continue

        # Split combined "(and)" / "(und)" / "(et)" entries
        # e.g. "Caprylyl Glycol (and) Ethylhexylglycerin" → two ingredients
        sub_parts = re.split(r'\s*\((?:and|und|et)\)\s*', part, flags=re.IGNORECASE)

        for ing in sub_parts:
            ing = ing.strip()

            # Remove parenthetical descriptors: "(Vitamin B3)", "(Provitamin B5)", etc.
            ing = re.sub(r'\([^)]*\)', '', ing).strip()

            # Remove percentage annotations inline: "10%", "0.3 %", "10 percent"
            ing = re.sub(r'\s*[\d\.]+\s*(?:%|percent)\s*', '', ing, flags=re.IGNORECASE).strip()

            # Remove trailing/leading punctuation artifacts
            ing = ing.strip('.-/ ')

            if not ing:
                continue
            if len(ing) > 80:
                continue
            if ing.count(' ') > 8:
                continue
            # Skip entries that look like sentences (contain a period mid-text)
            if '.' in ing and len(ing) > 20:
                continue

            # Deduplicate (case-insensitive)
            key = ing.lower()
            if key not in seen:
                seen.add(key)
                cleaned.append(ing)

    return cleaned


def estimate_concentration(ingredient_list, known_concentrations=None):
    """Estimate ingredient concentrations using:
    1. known_concentrations overrides (from product name or scraper)
    2. 1% line detection via CONCENTRATION_THRESHOLDS preservatives
    3. High-potency exception: peptides/retinoids at low position still get credit
    4. Positional fallback based on INCI order
    """
    concentrations = {}
    if not ingredient_list:
        return concentrations

    # Apply known overrides first
    known = known_concentrations or {}

    # High-potency ingredients that are genuinely effective at sub-1% concentrations.
    # Only include actives with documented micro-dose efficacy — NOT standard-range
    # actives like niacinamide (needs 2-10%), caffeine (5%+), or tocopherol (1%+).
    HIGH_POTENCY_KEYWORDS = [
        'peptide', 'retinol', 'retinal', 'retinyl', 'adapalene', 'tretinoin',
        'ascorbic acid', 'ferulic', 'tranexamic', 'kojic', 'bakuchiol',
        'alpha arbutin', 'azelaic', 'salicylic', 'glycolic', 'lactic',
    ]

    start_idx = 0
    if ingredient_list and ('aqua' in ingredient_list[0].lower() or 'water' in ingredient_list[0].lower()):
        concentrations[ingredient_list[0]] = known.get(ingredient_list[0].lower(), 60.0)
        start_idx = 1

    one_percent_reached = False
    for i, ing in enumerate(ingredient_list):
        if i < start_idx:
            continue

        # Check if this is a 1% threshold marker
        for marker in CONCENTRATION_THRESHOLDS:
            if marker.lower() in ing.lower():
                one_percent_reached = True
                break

        ing_lower = ing.lower()

        # 1. Use scraped / product-name known concentration if available
        if ing_lower in known:
            concentrations[ing] = known[ing_lower]
            continue

        # 2. High-potency exception: even if after the 1% line, give reasonable credit
        is_high_potency = any(kw in ing_lower for kw in HIGH_POTENCY_KEYWORDS)
        if one_percent_reached and is_high_potency:
            concentrations[ing] = 0.5  # effective even at 0.1-1%
            continue

        # 3. Standard positional fallback — smooth exponential decay
        if one_percent_reached:
            est = 0.3
        else:
            position = i - start_idx
            # Smooth decay: ~15% at pos 0, ~0.6% at pos 20
            # Formula: 15 * e^(-0.20 * position), clamped to [0.5, 15.0]
            est = max(0.5, min(15.0, 15.0 * math.exp(-0.20 * position)))
        concentrations[ing] = est

    return concentrations


def _parse_concentrations_from_name(product_name):
    """Extract known concentrations from product name.
    e.g. '10% Niacinamide + 1% Zinc Serum' -> {'niacinamide': 10.0, 'zinc': 1.0}
    Handles: "Pure 10% Niacinamide", "The Ordinary Niacinamide 10%", "2% Salicylic Acid"
    """
    if not product_name:
        return {}

    STOP_WORDS = {
        'serum', 'cream', 'lotion', 'gel', 'toner', 'essence', 'oil', 'moisturizer',
        'solution', 'formula', 'treatment', 'complex', 'blend', 'mix', 'booster',
        'the', 'and', 'with', 'for', 'skin', 'face', 'body', 'anti', 'plus',
        'pure', 'in', 'a', 'of', 'by', 'new', 'best', 'natural', 'organic',
    }
    BRAND_WORDS = {
        'ordinary', 'inkey', 'paula', 'cosrx', 'cerave', 'neutrogena',
        'dermalogica', 'skinceuticals', 'olay', 'estee', 'lauder',
        'minimalist', 'foxtale', 'beaminimalist', 'dotandkey',
        'plum', 'mcaffeine', 'mamaearth', 'pilgrim',
    }

    known = {}
    patterns = [
        # "10% Niacinamide" or "2% Salicylic Acid" -- number before name
        re.compile(r'(?<!\d)(\d+\.?\d*)\s*%\s+([A-Za-z][A-Za-z0-9\-]{2,30}(?:\s+[A-Za-z][A-Za-z0-9\-]{2,20})?)', re.I),
        # "Kojic Acid 2%" -- two-word name before number
        re.compile(r'\b([A-Za-z][A-Za-z0-9\-]{2,20}\s+[A-Za-z][A-Za-z0-9\-]{2,20})\s+(\d+\.?\d*)\s*%', re.I),
        # "Niacinamide 10%" -- single word name before number
        re.compile(r'\b([A-Za-z][A-Za-z0-9\-]{3,30})\s+(\d+\.?\d*)\s*%', re.I),
    ]

    for pat in patterns:
        for m in pat.finditer(product_name):
            g = m.groups()
            try:
                if g[0][0].isdigit():
                    pct, raw_name = float(g[0]), g[1].strip().lower()
                else:
                    raw_name, pct = g[0].strip().lower(), float(g[1])
                if not (0 < pct <= 100 and len(raw_name) > 2):
                    continue
                # Strip leading/trailing stop and brand words
                name_parts = raw_name.split()
                while name_parts and name_parts[0] in STOP_WORDS | BRAND_WORDS:
                    name_parts = name_parts[1:]
                while name_parts and name_parts[-1] in STOP_WORDS | BRAND_WORDS:
                    name_parts = name_parts[:-1]
                clean_name = ' '.join(name_parts).strip()
                if len(clean_name) > 2 and clean_name not in known:
                    known[clean_name] = pct
            except (ValueError, IndexError):
                pass
    return known

def _parse_min_effective(raw):
    """Parse Min_Effective_% which can be a range string like '2.0-10.0%' or a plain number."""
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return 0
    raw_str = str(raw).strip().replace('%', '')
    if '-' in raw_str:
        parts = raw_str.split('-')
        try:
            return float(parts[0].strip())
        except (ValueError, TypeError):
            return 0
    try:
        return float(raw_str)
    except (ValueError, TypeError):
        return 0


def _parse_optimal(raw, min_eff_raw):
    """Parse Optimal_% accounting for unit inconsistency.
    If Min_Effective_% is a range string (e.g. '2.0-10.0%'), Optimal is stored as fraction (0.05 = 5%).
    Otherwise Optimal is already in percentage."""
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return 0
    try:
        val = float(raw)
    except (ValueError, TypeError):
        return 0
    if math.isnan(val):
        return 0
    min_eff_str = str(min_eff_raw or '')
    if '%' in min_eff_str or ('-' in min_eff_str and not min_eff_str.startswith('-')):
        return val * 100
    return val


def is_support_ingredient(data):
    """Return True for humectants, emollients, occlusives and other functional/support
    ingredient classes. These get a flat concentration credit (0.7) and should never
    trigger 'below effective concentration' messaging — their presence matters more
    than their exact percentage.
    """
    ing_class = str(data.get('Ingredient_Class', '')).lower().strip()
    func = str(data.get('Functional_Category', '')).lower()
    if ing_class in {"functional", "humectant", "emollient", "occlusive",
                     "surfactant", "preservative"}:
        return True
    if any(k in func for k in ["humectant", "emollient", "occlusive",
                                "barrier", "texture", "solvent"]):
        return True
    return False


def get_concentration_factor(estimated_pct, data):
    # Support ingredients (humectants, emollients, etc.) get a flat functional
    # credit. Exact % doesn't determine whether they "work" — presence does.
    if is_support_ingredient(data):
        return 0.7

    min_eff_raw = data.get('Min_Effective_%', 0)
    optimal_raw = data.get('Optimal_%', 0)
    max_safe_raw = data.get('Max_Safe_%', 100)

    min_eff = _parse_min_effective(min_eff_raw)
    optimal = _parse_optimal(optimal_raw, min_eff_raw)
    try:
        max_safe = float(max_safe_raw if max_safe_raw is not None else 100)
        if math.isnan(max_safe):
            max_safe = 100
    except (ValueError, TypeError):
        max_safe = 100

    if min_eff == 0 and optimal == 0:
        # No threshold data in DB — treat as unknown effectiveness, not likely effective
        return 0.5

    if estimated_pct < min_eff:
        return 0.0
    elif optimal > 0 and estimated_pct < optimal:
        return 0.7
    elif estimated_pct <= max_safe:
        return 1.0
    else:
        return 0.9


def get_evidence_factor(data):
    """Use Evidence_Factor from the new database, with 5-tier granularity."""
    ev_str = str(data.get('Evidence_Level_Normalized', data.get('Evidence_Strength', ''))).lower()

    if any(kw in ev_str for kw in ['multiple rct', 'peer-reviewed', 'peer reviewed', 'consensus', 'gold standard']):
        return 1.0
    elif any(kw in ev_str for kw in ['strong']):
        return 0.9
    elif any(kw in ev_str for kw in ['moderate', 'clinical trial']):
        return 0.7
    elif any(kw in ev_str for kw in ['limited', 'procedure-based', 'procedure based', 'clinical']):
        return 0.55
    elif any(kw in ev_str for kw in ['emerging', 'pilot', 'early']):
        return 0.35
    elif any(kw in ev_str for kw in ['case report', 'anecdotal']):
        return 0.20

    # Fall back to numeric Evidence_Factor from DB
    try:
        ef = float(data.get('Evidence_Factor', 0.7) or 0.7)
        if math.isnan(ef):
            ef = 0.7
    except (ValueError, TypeError):
        ef = 0.7
    return ef


def get_evidence_label(eq_factor):
    """Return display label for evidence factor."""
    if eq_factor >= 0.9:
        return "Strong clinical evidence"
    elif eq_factor >= 0.7:
        return "Moderate clinical evidence"
    elif eq_factor >= 0.5:
        return "Limited clinical evidence"
    elif eq_factor >= 0.3:
        return "Early / emerging evidence"
    else:
        return "Minimal / anecdotal evidence"


# --- Red Flag Detection ---

FILLER_INGREDIENTS = {
    'aqua', 'water', 'glycerin', 'dimethicone', 'cyclomethicone',
    'cyclopentasiloxane', 'dimethiconol', 'butylene glycol',
    'propylene glycol', 'pentylene glycol', 'silicone', 'isododecane',
}

PH_DEPENDENT_ACTIVES = {
    'glycolic acid', 'lactic acid', 'mandelic acid', 'salicylic acid',
    'ascorbic acid', 'azelaic acid', 'citric acid',
}

ALKALINE_BASES = {
    'sodium hydroxide', 'potassium hydroxide', 'triethanolamine',
    'sodium lauryl sulfate', 'sodium laureth sulfate', 'soap',
    'cocamidopropyl betaine',
}

MARKETING_BUZZWORDS = {
    'stem cell', 'exosome', 'growth factor', 'epidermal growth factor',
    'placental extract', 'caviar extract', 'gold', 'diamond',
    'truffle extract', 'pearl extract',
}


# ─── 1% Marker ────────────────────────────────────────────────────────────────

def _find_one_percent_marker(ingredient_list):
    """Find the first known ≤1% threshold ingredient in the INCI list.
    EU/US law: ingredients above 1% must be listed highest to lowest.
    Everything before this marker is confirmed >1%. Everything after may be <1%.
    Returns (index, ingredient_name) or (None, None).
    """
    from config import CONCENTRATION_THRESHOLDS
    for i, ing in enumerate(ingredient_list):
        for marker in CONCENTRATION_THRESHOLDS:
            if marker.lower() in ing.lower():
                return i, ing
    return None, None


# ─── Ingredient Conflicts ─────────────────────────────────────────────────────

_INGREDIENT_CONFLICTS = [
    {
        'triggers': ['retinol', 'glycolic acid'],
        'severity': 'moderate',
        'message': 'Retinol + Glycolic Acid in one formula can cause over-exfoliation. Better used on alternate nights.',
    },
    {
        'triggers': ['retinol', 'lactic acid'],
        'severity': 'moderate',
        'message': 'Retinol + Lactic Acid together increases irritation risk. Alternate nights recommended.',
    },
    {
        'triggers': ['retinol', 'salicylic acid'],
        'severity': 'moderate',
        'message': 'Retinol + BHA: increased irritation risk, especially for sensitive skin. Fine for oily/resilient skin.',
    },
    {
        'triggers': ['retinol', 'benzoyl peroxide'],
        'severity': 'high',
        'message': 'Benzoyl Peroxide oxidises Retinol and destroys its effectiveness. Avoid using together.',
    },
    {
        'triggers': ['retinal', 'benzoyl peroxide'],
        'severity': 'high',
        'message': 'Benzoyl Peroxide oxidises Retinal/Retinaldehyde. These conflict in the same formula.',
    },
    {
        'triggers': ['copper tripeptide', 'ascorbic acid'],
        'severity': 'high',
        'message': 'Copper peptides + Vitamin C react and reduce the effectiveness of both. Use in separate routines.',
    },
    {
        'triggers': ['copper tripeptide', 'glycolic acid'],
        'severity': 'high',
        'message': 'Copper peptides degrade in acidic pH. Avoid layering directly with AHAs.',
    },
    {
        'triggers': ['niacinamide', 'ascorbic acid'],
        'severity': 'low',
        'message': 'Old concern about Niacinamide + Vitamin C causing flushing. Modern research shows stable formulations handle this fine.',
    },
]

def detect_ingredient_conflicts(ingredient_list):
    """Check for known problematic ingredient pairings within a single product formula."""
    ing_str = ' '.join(i.strip().lower() for i in ingredient_list)
    found = []
    for conflict in _INGREDIENT_CONFLICTS:
        if all(trigger in ing_str for trigger in conflict['triggers']):
            found.append({
                'severity': conflict['severity'],
                'message': conflict['message'],
                'triggers': conflict['triggers'],
            })
    return found


# ─── pH Inference ─────────────────────────────────────────────────────────────

_PH_LOWERING = {
    'citric acid': (3.5, 5.5),
    'lactic acid': (3.5, 5.0),
    'glycolic acid': (3.0, 4.5),
    'ascorbic acid': (2.5, 3.5),
    'salicylic acid': (3.0, 4.0),
    'malic acid': (3.5, 5.5),
    'tartaric acid': (3.5, 5.5),
    'mandelic acid': (3.5, 5.0),
    'phosphoric acid': (2.5, 4.0),
    'gluconolactone': (3.5, 5.0),
}
_PH_RAISING = {
    'sodium hydroxide': (7.0, 10.0),
    'potassium hydroxide': (8.0, 12.0),
    'triethanolamine': (7.0, 9.0),
    'aminomethyl propanol': (7.0, 9.0),
    'arginine': (6.5, 8.0),
}
_PH_BUFFERING = {
    'sodium citrate': (4.5, 6.5),
    'sodium phosphate': (6.0, 8.0),
    'disodium phosphate': (6.5, 8.0),
    'sodium acetate': (4.5, 6.0),
    'sodium bicarbonate': (7.0, 8.5),
}
_PH_SENSITIVE_ACTIVES = {
    'ascorbic acid': (2.0, 3.5, 'Vitamin C needs pH below 3.5 to penetrate and be effective'),
    'glycolic acid': (3.0, 4.5, 'Glycolic acid exfoliates best at pH 3–4.5'),
    'salicylic acid': (3.0, 4.5, 'BHA works best at pH 3–4.5'),
    'lactic acid': (3.0, 4.5, 'Lactic acid is most effective at pH 3–4.5'),
    'mandelic acid': (3.0, 4.5, 'Mandelic acid needs pH 3–4.5 for exfoliation'),
    'retinol': (4.5, 7.0, 'Retinol is stable at near-neutral pH — acidic conditions can degrade it'),
}

def infer_ph_and_check(ingredient_list):
    """Infer formula pH range from buffering/adjusting ingredients.
    Only returns data when pH signals are present — no section shown for plain moisturisers.
    """
    ing_str = ' '.join(i.strip().lower() for i in ingredient_list)
    has_acid   = {k: v for k, v in _PH_LOWERING.items()  if k in ing_str}
    has_base   = {k: v for k, v in _PH_RAISING.items()   if k in ing_str}
    has_buffer = {k: v for k, v in _PH_BUFFERING.items() if k in ing_str}

    if not has_acid and not has_base and not has_buffer:
        return {}

    notes    = []
    warnings = []
    ph_range = None
    confidence = None

    if has_acid and has_base:
        lowest   = min(v[0] for v in has_acid.values())
        ph_range = (round(lowest, 1), round(lowest + 1.5, 1))
        confidence = 'medium'
        acid_names = ', '.join(k.title() for k in has_acid)
        notes.append(f"Formula contains {acid_names} + pH adjuster — likely pH {ph_range[0]}–{ph_range[1]}")
    elif has_acid:
        lowest   = min(v[0] for v in has_acid.values())
        highest  = max(v[1] for v in has_acid.values())
        ph_range = (round(lowest, 1), round(highest, 1))
        confidence = 'low'
        acid_names = ', '.join(k.title() for k in has_acid)
        notes.append(f"Acidic ingredients detected ({acid_names}) — formula likely pH {ph_range[0]}–{ph_range[1]}")
    elif has_buffer:
        lowest   = min(v[0] for v in has_buffer.values())
        highest  = max(v[1] for v in has_buffer.values())
        ph_range = (round(lowest, 1), round(highest, 1))
        confidence = 'medium'
        buffer_names = ', '.join(k.title() for k in has_buffer)
        notes.append(f"Buffering system detected ({buffer_names}) — formula likely pH {ph_range[0]}–{ph_range[1]}")
    elif has_base:
        ph_range = (7.0, 9.0)
        confidence = 'low'
        base_names = ', '.join(k.title() for k in has_base)
        notes.append(f"Alkaline adjuster detected ({base_names}) — formula likely pH 7+")

    if ph_range:
        for active, (eff_min, eff_max, reason) in _PH_SENSITIVE_ACTIVES.items():
            if active in ing_str:
                if ph_range[0] > eff_max:
                    warnings.append(f"{active.title()} present but formula pH appears too high for efficacy. {reason}.")
                elif ph_range[1] < eff_min:
                    warnings.append(f"{active.title()} present but formula pH may be too low. {reason}.")
                else:
                    notes.append(f"{active.title()} — inferred pH is within its effective range")

    return {
        'ph_range': ph_range,
        'confidence': confidence,
        'notes': notes[:4],
        'warnings': warnings[:3],
    }


# ─── Delivery Systems ─────────────────────────────────────────────────────────

_DELIVERY_KEYWORDS = {
    'liposom':       'Liposomal delivery',
    'encapsulat':    'Encapsulated',
    'nanocapsul':    'Nanocapsule technology',
    'microsphere':   'Microsphere',
    'cyclodextrin':  'Cyclodextrin complex',
    'nano':          'Nano-particle',
    'phytosome':     'Phytosome complex',
}

def detect_delivery_systems(ingredient_list):
    """Return list of delivery system findings in the formula."""
    found = []
    seen  = set()
    for ing in ingredient_list:
        il = ing.strip().lower()
        for kw, label in _DELIVERY_KEYWORDS.items():
            if kw in il and label not in seen:
                found.append({'ingredient': ing, 'label': label})
                seen.add(label)
    return found


def detect_red_flags(ingredient_list, concentrations, category):
    """Detect Worth Red Flags per blueprint spec."""
    flags = []
    penalty = 0
    ing_lower_list = [i.lower() for i in ingredient_list]
    total = len(ingredient_list)

    # 1. Filler-to-Active Ratio
    filler_count = sum(1 for i in ing_lower_list if any(f in i for f in FILLER_INGREDIENTS))
    active_count = 0
    has_delivery = False
    for ing in ingredient_list:
        data = data_loader.get_ingredient_data(ing)
        if data and str(data.get('Ingredient_Class', '')).lower() == 'active':
            active_count += 1
        if any(kw in ing.lower() for kw in ['liposom', 'encapsulat', 'nano', 'cyclodextrin']):
            has_delivery = True

    if total > 0 and filler_count / total > 0.6 and active_count == 0 and not has_delivery:
        flags.append("High filler-to-active ratio: formula is >60% basic fillers with no active ingredients or delivery systems")
        penalty -= 5

    # 2. Stability Conflict
    has_ph_active = any(any(pa in i for pa in PH_DEPENDENT_ACTIVES) for i in ing_lower_list)
    has_alkaline = any(any(ab in i for ab in ALKALINE_BASES) for i in ing_lower_list)
    if has_ph_active and has_alkaline:
        flags.append("Stability conflict: pH-dependent actives formulated with alkaline base ingredients - may neutralize effectiveness")
        penalty -= 5

    # 3. Marketing Inflation
    preservative_idx = None
    for i, ing in enumerate(ingredient_list):
        if any(m in ing.lower() for m in CONCENTRATION_THRESHOLDS):
            preservative_idx = i
            break

    if preservative_idx is not None:
        for i, ing in enumerate(ingredient_list):
            if i > preservative_idx:
                if any(bw in ing.lower() for bw in MARKETING_BUZZWORDS):
                    flags.append(f"Marketing inflation: '{ing}' listed below preservative threshold - concentration likely too low for claimed benefits")
                    penalty -= 3
                    break

    # 4. Formaldehyde-releasing preservatives
    _FORMALDEHYDE_RELEASERS = {
        'dmdm hydantoin', 'imidazolidinyl urea', 'diazolidinyl urea',
        'quaternium-15', '2-bromo-2-nitropropane-1,3-diol', 'bronopol',
        'sodium hydroxymethylglycinate',
    }
    for ing in ingredient_list:
        if ing.strip().lower() in _FORMALDEHYDE_RELEASERS:
            flags.append(f"{ing} is a formaldehyde-releasing preservative — may cause sensitisation in reactive skin types")
            penalty -= 3
            break  # flag once is enough

    return flags, penalty


def detect_formulation_notes(ingredient_list):
    """Generate formulation sensitivity notes — population-specific, non-alarmist."""
    notes = []
    for i, ing in enumerate(ingredient_list):
        ing_lower = ing.lower()
        data = data_loader.get_ingredient_data(ing)

        # Comedogenic warnings — contextual, not absolute
        if data:
            try:
                c_rating = float(data.get('Comedogenicity_0_5', 0) or 0)
                if c_rating >= 4:
                    if 'isopropyl myristate' in ing_lower or 'myristate' in ing_lower:
                        notes.append(f"{ing} — High comedogenic rating; may trigger breakouts in acne-prone skin, especially in leave-on face products.")
                    else:
                        notes.append(f"{ing} (comedogenic rating {int(c_rating)}/5) — may clog pores in acne-prone skin.")
                elif c_rating >= 3:
                    notes.append(f"{ing} (comedogenic rating {int(c_rating)}/5) — moderate pore-clogging potential for oily/acne-prone skin.")
            except (ValueError, TypeError):
                pass

        # Irritation risk — conditional language
        if data:
            irritation = str(data.get('Irritation_Risk', 'Low')).lower()
            if irritation == 'high':
                notes.append(f"{ing} — high irritation potential; patch test recommended.")
            elif irritation == 'medium' and i < 10:
                notes.append(f"{ing} — moderate irritation risk in sensitive individuals.")

        # Specific ingredients — population-specific wording
        if 'fragrance' in ing_lower or 'parfum' in ing_lower:
            notes.append(f"{ing} — Fragrance component; common contact allergen in sensitive or allergy-prone skin.")
        elif 'propylene glycol' in ing_lower:
            notes.append(f"{ing} — Common humectant; can cause irritation or allergic dermatitis in eczema-prone or very sensitive skin.")
        elif 'alcohol denat' in ing_lower or 'sd alcohol' in ing_lower:
            notes.append(f"{ing} — Can be drying; may compromise barrier with long-term use.")
        elif 'essential oil' in ing_lower:
            notes.append(f"{ing} — Potential skin sensitizer in reactive skin types.")
        elif 'limonene' in ing_lower or 'linalool' in ing_lower:
            notes.append(f"{ing} — Known fragrance allergen.")
        elif 'methylparaben' in ing_lower or 'propylparaben' in ing_lower:
            notes.append(f"{ing} — Preservative; some ongoing discussion about long-term use.")

        # Red flag tags from database
        if data:
            flag = str(data.get('Red_Flag_Tags', '') or '')
            if flag and flag != 'nan':
                allergen_keywords = ['allergen', 'sensitiz', 'barrier damage', 'stinging']
                if any(kw in flag.lower() for kw in allergen_keywords):
                    notes.append(f"{ing}: {flag}")

    return list(dict.fromkeys(notes))[:8]


def _get_evidence_weight(evidence_strength):
    """Map Evidence_Strength string to numeric weight per spec."""
    ev = str(evidence_strength).strip().lower() if evidence_strength else ''
    if 'strong' in ev:    return 8
    if 'moderate' in ev:  return 6
    if 'limited' in ev:   return 3
    return 3  # default

def _get_role_weight(ingredient_data):
    """Get role weight from DB row, falling back to role_weight_table, then defaults."""
    # 1. Role_Weight column in ingredient_database
    rw_raw = ingredient_data.get('Role_Weight', '')
    try:
        rw = float(str(rw_raw).strip())
        if not math.isnan(rw) and rw > 0:
            return rw
    except (ValueError, TypeError):
        pass

    # 2. role_weight_table by Ingredient_Class / Functional_Category
    ing_class = str(ingredient_data.get('Ingredient_Class', '')).strip().lower()
    func_cat  = str(ingredient_data.get('Functional_Category', '')).strip().lower()
    table = data_loader.role_weight_table   # loaded from ingredient_role_weight_table.csv

    for key in [ing_class, func_cat]:
        if key in table:
            return table[key]
        for role in table:
            if role in key:
                return table[role]

    # 3. Hardcoded defaults from spec
    DEFAULTS = {
        'active': 10, 'barrier': 8, 'humectant': 7, 'emollient': 6,
        'occlusive': 6, 'antioxidant': 5, 'surfactant': 5,
        'emulsifier': 3, 'preservative': 2, 'fragrance': 1, 'filler': 1,
    }
    for k, v in DEFAULTS.items():
        if k in ing_class or k in func_cat:
            return v
    return 3  # safe default


def _calc_impact_score(ingredient_name, position, ingredient_list, known_concentrations=None):
    """
    impact_score = estimated_concentration * evidence_weight * role_weight * synergy_mult

    Concentration: 15 * exp(-0.20 * position), clamped [0.1, 20]
    Water at pos 0 always = 60 (constant solvent, not counted in active scoring)
    Synergy: *1.10 if any partner present in ingredient_list (max 1.15)
    """
    data = data_loader.get_ingredient_data(ingredient_name)
    if not data:
        return 0.0, None

    # Concentration
    known = known_concentrations or {}
    ing_lower = ingredient_name.strip().lower()
    if ing_lower in known:
        conc = float(known[ing_lower])
    else:
        conc = max(0.1, min(20.0, 15.0 * math.exp(-0.20 * position)))

    ev_weight   = _get_evidence_weight(data.get('Evidence_Strength', ''))
    role_weight = _get_role_weight(data)

    # Synergy multiplier from synergy_partners_map
    product_inci_lower = {i.strip().lower() for i in ingredient_list}
    partners = data_loader.get_synergy_partners(ing_lower)
    synergy_mult = 1.10 if partners & product_inci_lower - {ing_lower} else 1.0
    synergy_mult = min(1.15, synergy_mult)

    score = conc * ev_weight * role_weight * synergy_mult
    return score, data


def _impact_confidence(position):
    if position <= 5:  return 'high'
    if position <= 10: return 'medium'
    return 'low'


def _cleanser_score(ingredient_list, price, size_ml, country, known_concentrations=None):
    """
    Cleanser scoring per spec:
      Surfactant safety   40
      Irritation risk     25
      Supporting ings     10
      pH friendliness     10
      Price fairness      15
    """
    surf_scores = []
    irritation_penalty = 0
    has_ph_adjuster = False
    supporting_count = 0
    ing_lower_list = [i.strip().lower() for i in ingredient_list]

    _PH_FRIENDLY = {'citric acid','lactic acid','sodium citrate','sodium pca','glucono-delta-lactone'}
    _SUPPORTING   = {'glycerin','panthenol','allantoin','sodium pca','betaine','aloe vera','centella asiatica',
                     'ceramide','niacinamide','bisabolol','chamomile','hyaluronic','sodium hyaluronate'}

    for i, ing in enumerate(ingredient_list):
        surf_data = data_loader.get_surfactant_data(ing)
        if surf_data:
            try:
                h = float(surf_data.get('Harshness_Score', 5))
                safety = 10 - h   # harshness 9 → safety 1; harshness 1 → safety 9
                surf_scores.append(safety)
                irr = str(surf_data.get('Irritation_Risk','')).lower()
                if irr == 'high':   irritation_penalty += 15
                elif irr == 'medium': irritation_penalty += 7
            except (ValueError, TypeError):
                pass
        ing_l = ing.strip().lower()
        if any(ph in ing_l for ph in _PH_FRIENDLY):
            has_ph_adjuster = True
        if any(sup in ing_l for sup in _SUPPORTING):
            supporting_count += 1

    # Surfactant safety (40)
    if surf_scores:
        avg_safety  = sum(surf_scores) / len(surf_scores)
        surf_component = min(40, (avg_safety / 10) * 40)
    else:
        surf_component = 20  # no surfactants detected = neutral

    # Irritation risk (25) — start at 25, deduct penalties
    irr_component = max(0, 25 - irritation_penalty)

    # Supporting ings (10)
    sup_component = min(10, supporting_count * 2)

    # pH friendliness (10)
    ph_component  = 10 if has_ph_adjuster else 5

    # Price fairness (15)
    price_pts = _price_pts(price, size_ml, 'Cleanser', country)
    price_component = int(price_pts / 10 * 15)

    raw = surf_component + irr_component + sup_component + ph_component + price_component
    return min(100, max(0, raw))


def _facial_oil_score(ingredient_list, price, size_ml, country, known_concentrations=None):
    """
    Facial Oil scoring:
      Oil quality    35
      Antioxidants   20
      Actives        15
      Irritation     10
      Price fairness 20
    """
    _DRY_OILS   = {'squalane','jojoba','rosehip','marula','sea buckthorn','bakuchiol',
                   'argan','hemp seed','pomegranate seed','sea buckthorn'}
    _HEAVY_OILS = {'coconut oil','cocos nucifera','mineral oil','petrolatum','shea','castor',
                   'isopropyl myristate','lanolin'}
    _ANTIOXIDANTS = {'tocopherol','ascorbic acid','vitamin c','ferulic acid','resveratrol',
                     'green tea','coenzyme q10','ubiquinone','astaxanthin'}

    ing_lower_list = [i.strip().lower() for i in ingredient_list]
    ing_str = ' '.join(ing_lower_list)

    # Oil quality (35)
    dry_count   = sum(1 for kw in _DRY_OILS   if kw in ing_str)
    heavy_count = sum(1 for kw in _HEAVY_OILS if kw in ing_str)
    oil_quality = min(35, dry_count * 8) - (heavy_count * 5)
    oil_quality = max(0, oil_quality)
    if dry_count == 0 and heavy_count == 0:
        oil_quality = 15  # no identifiable oils = neutral

    # Antioxidants (20)
    aox_count  = sum(1 for kw in _ANTIOXIDANTS if kw in ing_str)
    aox_pts    = min(20, aox_count * 7)

    # Actives (15) — use impact scores
    active_pts = 0
    for i, ing in enumerate(ingredient_list[:15]):
        score, data = _calc_impact_score(ing, i, ingredient_list, known_concentrations)
        if data and str(data.get('Ingredient_Class','')).lower() == 'active':
            active_pts += score
    active_pts = min(15, active_pts / 5)  # normalise: typical active ~50-80 impact → 10-15 pts

    # Irritation (10) — deduct for fragrance/essential oils in top 10
    irr_pts = 10
    for ing in ingredient_list[:10]:
        il = ing.strip().lower()
        if 'fragrance' in il or 'parfum' in il or 'essential oil' in il:
            irr_pts -= 4
    irr_pts = max(0, irr_pts)

    # Price fairness (20)
    price_pts = _price_pts(price, size_ml, 'Facial Oil', country)
    price_component = int(price_pts / 10 * 20)

    raw = oil_quality + aox_pts + active_pts + irr_pts + price_component
    return min(100, max(0, raw))


def _price_pts(price, size_ml, category, country):
    """Return price score 0-10 using category average comparison."""
    if not price or not size_ml or size_ml <= 0:
        return 5
    from config import CATEGORY_AVERAGES, CATEGORY_AVERAGES_DEFAULT
    country_avgs = CATEGORY_AVERAGES.get(country)
    if not country_avgs:
        return 5
    cat_key = category.strip().lower()
    avg_price = country_avgs.get(cat_key, {}).get('avg_price_per_ml', 1.0)
    if not avg_price:
        return 5
    ratio = (price / size_ml) / avg_price
    if ratio <= 1.0:   return 10
    if ratio <= 1.5:   return 8
    if ratio <= 2.0:   return 6
    if ratio <= 3.0:   return 4
    return 2


def calculate_main_worth_score(ingredient_list, price, size_ml, category, country='India', known_concentrations=None):
    """
    Category-specific scoring engine.

    Worth score = 0.75 * formula_quality + 0.25 * price_fairness  (normalised to 100)

    Category weights (per spec):
      Serum:      active_potency 40, evidence 20, formula_balance 15, irritation 10, price 15
      Moisturizer: barrier 35, humectant 25, active_support 15, texture 10, price 15
      Cleanser:   surfactant_safety 40, irritation 25, supporting 10, pH 10, price 15
      Toner:      humectants 30, soothing 25, actives 20, irritation 10, price 15
      Facial Oil: oil_quality 35, antioxidants 20, actives 15, irritation 10, price 20
      Sunscreen:  handled by UV scoring engine (existing)
    """
    score_breakdown = {
        'active_value': 0, 'formula_quality': 0, 'claim_accuracy': 15,
        'safety': 10, 'price_rationality': 0
    }
    component_details = {'A': [], 'B': [], 'C': [], 'D': [], 'E': []}
    concentrations = estimate_concentration(ingredient_list, known_concentrations=known_concentrations)
    identified_actives = []
    multipliers_applied = []
    cat_lower = category.strip().lower()

    # ── IMPACT SCORE for every ingredient ─────────────────────────────────────
    all_impact = []
    for i, ing in enumerate(ingredient_list):
        score, data = _calc_impact_score(ing, i, ingredient_list, known_concentrations)
        if data:
            all_impact.append((ing, i, score, data))

    # ── IDENTIFIED ACTIVES (for display) ──────────────────────────────────────
    _helpful_seen = set()
    for ing, pos, imp_score, data in all_impact:
        if str(data.get('Ingredient_Class', '')).lower() not in ('active','peptide','retinoid',
                                                                   'brightening active'):
            continue
        ing_lower = ing.strip().lower()
        if ing_lower in _helpful_seen:
            continue
        _helpful_seen.add(ing_lower)

        conc = concentrations.get(ing, 0.3)
        conc_factor = get_concentration_factor(conc, data)
        ev_label  = get_evidence_label(get_evidence_factor(data))
        eq_factor = get_evidence_factor(data)

        conc_label = (
            "likely at optimal functional level"    if conc_factor >= 1.0 else
            "likely within functional range"        if conc_factor >= 0.7 else
            "concentration range unknown"           if conc_factor >= 0.5 else
            "may be below typical functional range"
        )

        _kc = known_concentrations or {}
        _conc_is_known = ing_lower in _kc

        identified_actives.append({
            'name': ing,
            'position': pos + 1,
            'evidence': ev_label,
            'concentration': conc_label,
            'concentration_pct': round(conc, 2) if _conc_is_known else None,
            'concentration_known': _conc_is_known,
            'score_contribution': round(imp_score / 100, 2),
            'primary_benefits': (
                (lambda v: str(v).strip() if v and str(v).lower() not in ('nan','none','') else None)
                (data.get('Primary_Benefits',''))
                or (lambda v: str(v).strip() if v and str(v).lower() not in ('nan','none','') else None)
                (data.get('Functional_Category',''))
                or (lambda v: str(v).split(';')[0].strip() if v and str(v).lower() not in ('nan','none','') else None)
                (data.get('Skin_Concerns',''))
            ),
            'targets': [t.strip() for t in str(data.get('Skin_Concerns','') or '').split(';')
                        if t.strip() and t.strip() not in ('','nan')][:3],
            'functional_category': (None if not data.get('Functional_Category') or
                                    str(data.get('Functional_Category','')).lower() in ('nan','none','')
                                    else str(data['Functional_Category']).strip()),
        })

    # ── CATEGORY-SPECIFIC FORMULA QUALITY ─────────────────────────────────────
    ing_str = ' '.join(i.strip().lower() for i in ingredient_list)

    if cat_lower in ('serum', 'treatment', 'essence', 'ampoule'):
        # Active potency 40, evidence 20, formula balance 15, irritation 10
        active_impact_sum = sum(s for _, _, s, d in all_impact
                                if str(d.get('Ingredient_Class','')).lower() in
                                ('active','peptide','retinoid','brightening active'))
        active_potency = min(40, active_impact_sum / 50)

        ev_sum = sum(_get_evidence_weight(d.get('Evidence_Strength','')) for _, _, _, d in all_impact
                     if str(d.get('Ingredient_Class','')).lower() == 'active')
        active_count_for_ev = max(1, sum(1 for _, _, _, d in all_impact
                                         if str(d.get('Ingredient_Class','')).lower() == 'active'))
        evidence_score = min(20, (ev_sum / active_count_for_ev / 8) * 20)

        has_humectant = any('humectant' in str(d.get('Functional_Category','')).lower() or
                            str(d.get('Ingredient_Class','')).lower() == 'humectant'
                            for _, _, _, d in all_impact)
        has_preservative = any('preserv' in str(d.get('Functional_Category','')).lower() or
                                str(d.get('Ingredient_Class','')).lower() == 'preservative'
                                for _, _, _, d in all_impact)
        balance_score = 7
        if has_humectant:   balance_score += 4
        if has_preservative: balance_score += 4
        balance_score = min(15, balance_score)

        irr_penalty = sum(3 for ing in ingredient_list[:10]
                          if any(k in ing.lower() for k in ('fragrance','parfum','essential oil',
                                                             'alcohol denat','sd alcohol')))
        irr_score = max(0, 10 - irr_penalty)

        formula_quality = active_potency + evidence_score + balance_score + irr_score
        component_details['A'].append(f"Active potency: {active_potency:.1f}/40")
        component_details['A'].append(f"Evidence strength: {evidence_score:.1f}/20")
        component_details['B'].append(f"Formula balance: {balance_score}/15, Irritation: {irr_score}/10")

    elif cat_lower in ('moisturizer', 'cream', 'lotion', 'gel'):
        # Barrier 35, humectants 25, active support 15, texture 10, price handled separately
        _BARRIER   = {'ceramide','cholesterol','fatty acid','phytosphingosine','sphingosine',
                      'stearic acid','palmitic acid','linoleic','linolenic','squalane',
                      'shea butter','lanolin','petrolatum'}
        _HUMECTANTS = {'glycerin','sodium hyaluronate','hyaluronic','panthenol','propanediol',
                       'butylene glycol','sorbitol','urea','sodium pca','beta-glucan',
                       'polyglutamic','tremella'}
        _OCCLUSIVES = {'petrolatum','dimethicone','beeswax','lanolin','zinc oxide','shea',
                       'mineral oil','vaseline'}

        barrier_count   = sum(1 for kw in _BARRIER   if kw in ing_str)
        humectant_count = sum(1 for kw in _HUMECTANTS if kw in ing_str)
        occlusive_count = sum(1 for kw in _OCCLUSIVES if kw in ing_str)

        barrier_pts   = min(35, barrier_count * 8 + occlusive_count * 4)
        humectant_pts = min(25, humectant_count * 6)

        active_impact = sum(s for _, _, s, d in all_impact
                            if str(d.get('Ingredient_Class','')).lower() == 'active')
        active_pts = min(15, active_impact / 80)

        # Texture (10): penalise high-alcohol or fragrance, reward lightweight silicone
        texture_pts = 8
        for ing in ingredient_list[:5]:
            il = ing.strip().lower()
            if 'alcohol denat' in il or 'sd alcohol' in il:
                texture_pts -= 4
            if 'dimethicone' in il or 'cyclopentasiloxane' in il:
                texture_pts = min(10, texture_pts + 2)
        texture_pts = max(0, texture_pts)

        formula_quality = barrier_pts + humectant_pts + active_pts + texture_pts
        component_details['A'].append(f"Barrier support: {barrier_pts:.1f}/35, Humectants: {humectant_pts:.1f}/25")
        component_details['B'].append(f"Active support: {active_pts:.1f}/15, Texture: {texture_pts}/10")

    elif cat_lower == 'cleanser':
        # Use dedicated cleanser scorer (returns 0-100 directly)
        formula_quality = _cleanser_score(ingredient_list, price, size_ml, country, known_concentrations)
        component_details['A'].append("Cleanser scored on surfactant safety + irritation + support")
        # Cleanser score already includes price — skip separate price component
        price_score = _price_pts(price, size_ml, category, country)
        score_breakdown['price_rationality'] = float(price_score)
        score_breakdown['active_value'] = round(min(45, formula_quality * 0.45), 1)
        score_breakdown['formula_quality'] = round(min(20, formula_quality * 0.20), 1)
        score_breakdown['safety'] = round(min(10, formula_quality * 0.10), 1)
        score_breakdown['claim_accuracy'] = 15
        total_score = min(100, max(0, formula_quality))
        avg_price = _get_avg_price(price, size_ml, category, country)
        ratio = round((price / size_ml) / avg_price, 2) if (size_ml > 0 and avg_price > 0 and price > 0) else 1.0
        value_tier = _ratio_to_tier(ratio)
        return _build_result(total_score, score_breakdown, component_details, identified_actives,
                             all_impact, ingredient_list, price, size_ml, category, country,
                             ratio, value_tier, multipliers_applied, concentrations, known_concentrations)

    elif cat_lower in ('toner', 'mist'):
        # Humectants 30, soothing 25, actives 20, irritation 10
        _HUMECTANTS = {'glycerin','sodium hyaluronate','hyaluronic','panthenol','propanediol',
                       'butylene glycol','beta-glucan','polyglutamic','sodium pca'}
        _SOOTHING   = {'centella','allantoin','panthenol','bisabolol','aloe','chamomile',
                       'licorice','madecassoside','asiaticoside','niacinamide','cica'}
        humectant_count = sum(1 for kw in _HUMECTANTS if kw in ing_str)
        soothing_count  = sum(1 for kw in _SOOTHING   if kw in ing_str)
        humectant_pts   = min(30, humectant_count * 8)
        soothing_pts    = min(25, soothing_count  * 7)

        active_impact = sum(s for _, _, s, d in all_impact
                            if str(d.get('Ingredient_Class','')).lower() == 'active')
        active_pts = min(20, active_impact / 60)

        irr_penalty = sum(3 for ing in ingredient_list[:10]
                          if any(k in ing.lower() for k in ('fragrance','parfum','alcohol denat','sd alcohol')))
        irr_score = max(0, 10 - irr_penalty)

        formula_quality = humectant_pts + soothing_pts + active_pts + irr_score
        component_details['A'].append(f"Humectants: {humectant_pts:.1f}/30, Soothing: {soothing_pts:.1f}/25")
        component_details['B'].append(f"Actives: {active_pts:.1f}/20, Irritation: {irr_score}/10")

    elif cat_lower in ('facial oil', 'oil'):
        formula_quality = _facial_oil_score(ingredient_list, price, size_ml, country, known_concentrations)
        component_details['A'].append("Facial oil scored on oil quality + antioxidants + actives + irritation")
        total_score = min(100, max(0, formula_quality))
        price_score = _price_pts(price, size_ml, category, country)
        score_breakdown['price_rationality'] = float(price_score)
        score_breakdown['active_value'] = round(min(45, formula_quality * 0.45), 1)
        score_breakdown['formula_quality'] = round(min(20, formula_quality * 0.20), 1)
        score_breakdown['safety'] = round(min(10, formula_quality * 0.10), 1)
        score_breakdown['claim_accuracy'] = 15
        avg_price = _get_avg_price(price, size_ml, category, country)
        ratio = round((price / size_ml) / avg_price, 2) if (size_ml > 0 and avg_price > 0 and price > 0) else 1.0
        value_tier = _ratio_to_tier(ratio)
        return _build_result(total_score, score_breakdown, component_details, identified_actives,
                             all_impact, ingredient_list, price, size_ml, category, country,
                             ratio, value_tier, multipliers_applied, concentrations, known_concentrations)

    else:
        # Generic fallback — active-weighted scoring
        active_impact = sum(s for _, _, s, d in all_impact
                            if str(d.get('Ingredient_Class','')).lower() in
                            ('active','peptide','retinoid','brightening active'))
        formula_quality = min(85, active_impact / 20)
        component_details['A'].append("General scoring: active ingredient impact")

    # ── PRICE FAIRNESS ─────────────────────────────────────────────────────────
    price_score = _price_pts(price, size_ml, category, country)
    price_component = (price_score / 10) * 15  # 15% weight

    # ── FINAL WORTH SCORE ─────────────────────────────────────────────────────
    # worth_score = 0.75 * formula_quality + 0.25 * price_fairness (normalised to 100)
    formula_pct = min(85, formula_quality) / 85   # normalise formula to 0-1
    price_pct   = price_score / 10                # normalise price to 0-1
    total_score = min(100, max(0, round((0.75 * formula_pct + 0.25 * price_pct) * 100)))

    # Safety deductions (Component D)
    safety_score = 10.0
    _frag_ded = _alc_ded = _irr_ded = _preg_ded = _allergen_ded = 0.0
    safety_details = []
    for i, ing in enumerate(ingredient_list):
        il = ing.strip().lower()
        data = data_loader.get_ingredient_data(ing)
        if ('fragrance' in il or 'parfum' in il) and i < 10 and _frag_ded < 4:
            d = min(4.0 - _frag_ded, 4.0); safety_score -= d; _frag_ded += d
            safety_details.append(f"Contains fragrance ({ing})")
        if ('alcohol denat' in il or 'sd alcohol' in il) and i < 10 and _alc_ded < 3:
            d = min(3.0 - _alc_ded, 3.0); safety_score -= d; _alc_ded += d
            safety_details.append(f"Contains denatured alcohol ({ing})")
        if ('essential oil' in il or 'limonene' in il or 'linalool' in il) and _allergen_ded < 4:
            d = min(2.0, 4.0 - _allergen_ded); safety_score -= d; _allergen_ded += d
            safety_details.append(f"Contains potential allergen ({ing})")
        if data:
            irr = str(data.get('Irritation_Risk','')).lower()
            if irr == 'high' and _irr_ded < 3:
                d = min(3.0 - _irr_ded, 3.0); safety_score -= d; _irr_ded += d
                safety_details.append(f"{ing} — high irritation risk")
            elif irr in ('medium','moderate'):
                safety_score -= 0.5
            preg = str(data.get('Pregnancy_Safety','')).lower()
            if ('avoid' in preg or 'restrict' in preg) and _preg_ded < 4:
                d = min(4.0 - _preg_ded, 4.0); safety_score -= d; _preg_ded += d
                safety_details.append(f"{ing} — pregnancy safety flag")
    safety_score = round(max(0, min(10, safety_score)), 1)

    # Claim accuracy (Component C)
    claim_score = 15
    for _, _, _, data in all_impact:
        if 'Overclaim risk' in str(data.get('Red_Flag_Tags','')):
            claim_score = max(0, claim_score - 3)
    for ing, _, _, data in all_impact:
        conc = concentrations.get(ing, 0.3)
        if get_concentration_factor(conc, data) == 0.0:
            claim_score = max(0, claim_score - 2)

    score_breakdown['active_value']      = round(min(45, formula_quality / 85 * 45), 1)
    score_breakdown['formula_quality']   = round(min(20, formula_quality / 85 * 20), 1)
    score_breakdown['claim_accuracy']    = claim_score
    score_breakdown['safety']            = safety_score
    score_breakdown['price_rationality'] = float(price_score)

    if safety_score >= 9: component_details['D'].append("Low irritation risk overall")
    elif safety_score >= 6: component_details['D'].append("Some safety considerations present")
    else: component_details['D'].append("Multiple safety flags detected")
    for d in safety_details[:2]: component_details['D'].append(d)

    avg_price = _get_avg_price(price, size_ml, category, country)
    ratio = round((price / size_ml) / avg_price, 2) if (size_ml > 0 and avg_price > 0 and price > 0) else 1.0
    value_tier = _ratio_to_tier(ratio)

    price_note = None
    if not size_ml or size_ml <= 0:
        price_note = 'Size not provided — price per ml unavailable'
    elif not price or price <= 0:
        price_note = 'Price not provided — value analysis unavailable'

    if price_score >= 9: component_details['E'].append("Underpriced — excellent value at this price point")
    elif price_score >= 7: component_details['E'].append("Fairly priced for the category")
    elif price_score >= 5: component_details['E'].append("Slightly overpriced for active content")
    else: component_details['E'].append("Heavily overpriced for the active content")
    if avg_price > 0 and price > 0 and size_ml > 0:
        component_details['E'].append(f"{ratio:.1f}x vs category average ({price/size_ml:.2f}/ml vs avg {avg_price:.2f}/ml)")

    red_flags, red_flag_penalty = detect_red_flags(ingredient_list, concentrations, category)
    total_score = min(100, max(0, total_score + red_flag_penalty))

    return _build_result(total_score, score_breakdown, component_details, identified_actives,
                         all_impact, ingredient_list, price, size_ml, category, country,
                         ratio, value_tier, multipliers_applied, concentrations, known_concentrations,
                         price_note=price_note, red_flags=red_flags)


def _get_avg_price(price, size_ml, category, country):
    from config import CATEGORY_AVERAGES
    country_avgs = CATEGORY_AVERAGES.get(country, {})
    cat_key = category.strip().lower()
    return country_avgs.get(cat_key, {}).get('avg_price_per_ml', 1.0) or 1.0


def _ratio_to_tier(ratio):
    if ratio <= 0.70: return 'underpriced'
    if ratio <= 1.30: return 'fair'
    if ratio <= 2.00: return 'slightly_overpriced'
    return 'overpriced'


def _build_result(total_score, score_breakdown, component_details, identified_actives,
                  all_impact, ingredient_list, price, size_ml, category, country,
                  ratio, value_tier, multipliers_applied, concentrations, known_concentrations,
                  price_note=None, red_flags=None):
    """Assemble final return dict (same schema as before for frontend compatibility)."""
    red_flags = red_flags or []
    price_per_ml = round(price / size_ml, 2) if size_ml and size_ml > 0 and price else 0
    avg_price = _get_avg_price(price, size_ml, category, country)
    active_count = len(identified_actives)
    ing_count = len(ingredient_list)
    active_ratio = round(active_count / ing_count * 100, 1) if ing_count else 0

    # Active classes
    _AO_NAMES = {'tocopherol','ascorbic acid','ferulic acid','resveratrol','astaxanthin',
                 'coenzyme q10','ergothioneine','green tea','egcg','idebenone','quercetin'}
    _BARRIER_FC = {'barrier','emollient','occlusive','humectant'}
    _UV_FC = {'uv filter','mineral uv filter','organic uv filter','sunscreen'}

    primary_actives = []; supporting_actives = []
    antioxidant_actives = []; barrier_actives = []
    classified = set()

    for ing, pos, imp_score, data in all_impact:
        il = ing.strip().lower()
        if il in classified: continue
        ing_class = str(data.get('Ingredient_Class','')).lower()
        func_cat  = str(data.get('Functional_Category','')).lower()
        rw = _get_role_weight(data)
        if any(uv in func_cat for uv in _UV_FC) or 'uv filter' in ing_class:
            primary_actives.append(ing); classified.add(il)
        elif rw >= 8 and ing_class in ('active','peptide','retinoid','brightening active'):
            primary_actives.append(ing); classified.add(il)
        elif ing_class in ('active','peptide','retinoid','brightening active'):
            supporting_actives.append(ing); classified.add(il)
        elif any(kw in il for kw in _AO_NAMES) or 'antioxidant' in func_cat:
            antioxidant_actives.append(ing); classified.add(il)
        elif any(kw in func_cat for kw in _BARRIER_FC):
            barrier_actives.append(ing); classified.add(il)

    return {
        'score': int(total_score),
        'breakdown': score_breakdown,
        'component_details': component_details,
        'stats': {
            'price_per_ml': price_per_ml,
            'category_avg': round(avg_price, 2),
            'vs_average': round(ratio, 1),
            'active_count': active_count,
            'active_ratio': round(active_ratio, 1),
            'price_per_active': round(price / active_count, 2) if active_count and price else price or 0,
        },
        'tier_badge': get_tier_badge(total_score, value_tier),
        'score_title': get_score_title(total_score, value_tier),
        'value_tier': value_tier,
        'ratio': ratio,
        'identified_actives': identified_actives,
        'active_classes': {
            'primary': primary_actives[:8],
            'supporting': supporting_actives[:8],
            'antioxidants': antioxidant_actives[:6],
            'barrier_support': barrier_actives[:6],
        },
        'multipliers_applied': multipliers_applied,
        'price_note': price_note,
        'red_flags': red_flags,
    }


def get_tier_badge(score, value_tier=None):
    if score >= 90:
        return "Exceptional Formula"
    if score >= 75:
        if value_tier in {"overpriced", "slightly_overpriced"}:
            return "Worth Buying but Pricey"
        return "Worth Buying"
    if score >= 60:
        if value_tier in {"fair", "underpriced"}:
            return "Acceptable & Fairly Priced"
        return "Acceptable but Overpriced"
    if score >= 40:
        return "Questionable Value"
    return "Mostly Marketing"


def get_score_title(score, value_tier=None):
    if score >= 90:
        return "Outstanding formulation with strong actives"
    if score >= 75:
        if value_tier == "underpriced":
            return "Excellent actives for the price"
        if value_tier == "fair":
            return "Strong formula at reasonable price"
        return "Strong formula, paying brand premium"
    if score >= 60:
        if value_tier in {"fair", "underpriced"}:
            return "Good formula at acceptable value"
        return "Good formula, on the pricey side"
    if score >= 40:
        return "Limited actives for the cost"
    return "Mostly marketing, minimal substance"


UV_CONCERN_SET = {'Sun Protection', 'UV Damage', 'Tanning'}

# ─── INCI ALIAS RESOLUTION ────────────────────────────────────────────────────
# Bemotrizinol = Bisoctrizole = Methylene Bis-Benzotriazolyl Tetramethylbutylphenol (Tinosorb M)
# These are resolved BEFORE any lookup so we never double-count or miss entries.
INCI_ALIASES = {
    'Bemotrizinol': 'Methylene Bis-Benzotriazolyl Tetramethylbutylphenol',
    'Bisoctrizole':  'Methylene Bis-Benzotriazolyl Tetramethylbutylphenol',
    'Avobenzone':    'Butyl Methoxydibenzoylmethane',
    'Octinoxate':    'Ethylhexyl Methoxycinnamate',
    'Octisalate':    'Ethylhexyl Salicylate',
    'Ensulizole':    'Phenylbenzimidazole Sulfonic Acid',
    'Ecamsule':      'Terephthalylidene Dicamphor Sulfonic Acid',
}

# ─── UV BAND MEMBERSHIP LISTS ─────────────────────────────────────────────────
_UVB_FILTER_LIST = {
    'Ethylhexyl Methoxycinnamate', 'Octocrylene', 'Homosalate', 'Ethylhexyl Salicylate',
    'Phenylbenzimidazole Sulfonic Acid', 'Ethylhexyl Triazone', 'Titanium Dioxide',
    'Titanium Dioxide (nano)', 'Zinc Oxide', 'Diethylhexyl Butamido Triazone',
    'Polysilicone-15', 'Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine',
    'Methylene Bis-Benzotriazolyl Tetramethylbutylphenol', 'Drometrizole Trisiloxane',
    'Tris-Biphenyl Triazine', 'Isoamyl p-Methoxycinnamate', 'Camphor Benzalkonium Methosulfate',
    '4-Methylbenzylidene Camphor', 'Padimate O', 'Aminobenzoic Acid', 'Cinoxate',
    'Trolamine Salicylate', 'Oxybenzone', 'Sulisobenzone', 'Dioxybenzone',
    'Benzylidene Camphor Sulfonic Acid', '3-Benzylidene Camphor',
    'Sodium Phenylbenzimidazole Sulfonate', 'Benzophenone-9',
}

_UVA1_FILTER_LIST = {
    'Butyl Methoxydibenzoylmethane', 'Diethylamino Hydroxybenzoyl Hexyl Benzoate',
    'Terephthalylidene Dicamphor Sulfonic Acid', 'Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine',
    'Methylene Bis-Benzotriazolyl Tetramethylbutylphenol', 'Drometrizole Trisiloxane',
    'Disodium Phenyl Dibenzimidazole Tetrasulfonate', 'Zinc Oxide',
}

_UVA2_FILTER_LIST = {
    'Titanium Dioxide', 'Titanium Dioxide (nano)', 'Methylene Bis-Benzotriazolyl Tetramethylbutylphenol',
    'Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine', 'Drometrizole Trisiloxane',
    'Oxybenzone', 'Sulisobenzone', 'Dioxybenzone', 'Zinc Oxide',
    'Tris-Biphenyl Triazine', 'Diethylhexyl Butamido Triazone', 'Ecamsule',
}

# ─── FILTER STRENGTH MAP (Part 4.3 of scoring spec) ──────────────────────────
_UV_FILTER_STRENGTH_MAP = {
    # Strength 5 — Elite filters
    'Ethylhexyl Triazone':                                   5,
    'Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine':        5,
    'Methylene Bis-Benzotriazolyl Tetramethylbutylphenol':   5,
    'Tris-Biphenyl Triazine':                                5,
    # Strength 4 — High performance
    'Zinc Oxide':                                            4,
    'Diethylamino Hydroxybenzoyl Hexyl Benzoate':            4,
    'Drometrizole Trisiloxane':                              4,
    'Terephthalylidene Dicamphor Sulfonic Acid':             4,
    'Disodium Phenyl Dibenzimidazole Tetrasulfonate':        4,
    'Diethylhexyl Butamido Triazone':                        4,
    # Strength 3 — Good standard
    'Titanium Dioxide':                                      3,
    'Titanium Dioxide (nano)':                               3,
    'Butyl Methoxydibenzoylmethane':                         3,
    # Strength 2 — Moderate
    'Ethylhexyl Methoxycinnamate':                           2,
    'Octocrylene':                                           2,
    'Homosalate':                                            2,
    'Oxybenzone':                                            2,
    'Sulisobenzone':                                         2,
    'Polysilicone-15':                                       2,
    'Isoamyl p-Methoxycinnamate':                            2,
    'Phenylbenzimidazole Sulfonic Acid':                     2,
    'Benzylidene Camphor Sulfonic Acid':                     2,
    '4-Methylbenzylidene Camphor':                           2,
    'Padimate O':                                            2,
    # Strength 1 — Weak / legacy
    'Ethylhexyl Salicylate':                                 1,
    'Camphor Benzalkonium Methosulfate':                     1,
    'Dioxybenzone':                                          1,
    'Meradimate':                                            1,
    'Trolamine Salicylate':                                  1,
    'Aminobenzoic Acid':                                     1,
    'Cinoxate':                                              1,
    'Benzophenone-9':                                        1,
    '3-Benzylidene Camphor':                                 1,
    'Sodium Phenylbenzimidazole Sulfonate':                  1,
}

def _build_avobenzone_stabilizers():
    """
    Build the set of Avobenzone photostabilizers from the UV DB.
    PRIMARY source: Avobenzone's own Common_Synergy_Partners column — these are
    the ingredients listed by the DB as Avobenzone's actual stabilizers.
    SECONDARY: Photostabilizer col with "Avobenzone" mentioned explicitly in value.
    Tocopherol/Ferulic Acid have Photostabilizer=Yes but for Vit C systems, NOT Avobenzone.
    Fallback: hardcoded set if DB not loaded yet.
    """
    fallback = {
        'Octocrylene', 'Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine',
        'Methylene Bis-Benzotriazolyl Tetramethylbutylphenol',
        'Diethylamino Hydroxybenzoyl Hexyl Benzoate', 'Ethylhexyl Methoxycrylene',
        'Diethylhexyl Syringylidenemalonate',
    }
    try:
        stabilizers = set()
        avobenzone_inci = 'Butyl Methoxydibenzoylmethane'

        # Signal 1 (PRIMARY): read Avobenzone's Common_Synergy_Partners from DB
        # This is the most accurate source — Avobenzone's own row lists its stabilizers.
        avob_data = data_loader.get_uv_data(avobenzone_inci)
        if avob_data:
            partners_raw = str(avob_data.get('Common_Synergy_Partners', '') or '')
            for partner in partners_raw.split(';'):
                partner = partner.strip()
                if partner:
                    stabilizers.add(partner)

        # Signal 2 (SECONDARY): Photostabilizer col explicitly mentions "Avobenzone"
        # OR Photostability_Notes contain a POSITIVE stabilization keyword + "avobenzone".
        # Octinoxate Notes say "Degrades Avobenzone" — excluded because no positive keyword.
        # Octisalate is borderline and excluded for safety (not a reliable stabilizer).
        # Tinosorb M Notes mention "Avobenzone" as synergy partner — included correctly.
        _POSITIVE_STAB_KEYWORDS = ('stabiliz', 'quench', 'prevent avobenzone', 'protects avobenzone')
        for key, uv_data in data_loader.uv_sun_db.items():
            phot_flag  = str(uv_data.get('Photostabilizer', '')   or '').strip().lower()
            phot_notes = str(uv_data.get('Photostability_Notes', '') or '').strip().lower()
            flag_mentions_avob  = 'avobenzone' in phot_flag
            notes_positively_stab = (
                'avobenzone' in phot_notes and
                any(kw in phot_notes for kw in _POSITIVE_STAB_KEYWORDS) and
                'degrades' not in phot_notes and
                'slightly' not in phot_notes  # minor/partial help excluded
            )
            if flag_mentions_avob or notes_positively_stab:
                inci_name = uv_data.get('INCI_Name', '').strip()
                if inci_name:
                    stabilizers.add(inci_name)

        stabilizers.discard('')
        return stabilizers if stabilizers else fallback
    except Exception:
        return fallback

# Resolved at first call from DB
_AVOBENZONE_STABILIZERS_CACHE: set = set()

_FILM_FORMERS = {'VP/Hexadecene Copolymer', 'Acrylates Copolymer', 'Trimethylsiloxysilicate', 'Polyurethane-34'}
_SPF_BOOSTERS  = {'Butyloctyl Salicylate', 'Isopropyl Lauroyl Sarcosinate', 'Polyester-8'}

_BANNED_FILTERS = {
    'Aminobenzoic Acid':           'Banned EU; high sensitization risk',
    'Oxybenzone':                  'Banned Hawaii; endocrine/reef concerns',
    '3-Benzylidene Camphor':       'Endocrine concerns; avoided in modern formulas',
    '4-Methylbenzylidene Camphor': 'Endocrine review; restricted use',
}


def _uv_conc_factor(inci_name, resolved_list):
    """Position-based concentration factor for sunscreen formulas.
    Sunscreens: positions 1-4 = Water/Emollients. Filters typically start at pos 5+.
    pos < 8  → high  → 1.0
    pos < 20 → mid   → 0.75
    pos 20+  → low   → 0.5
    """
    try:
        pos = next(i for i, x in enumerate(resolved_list) if x.lower() == inci_name.lower())
    except StopIteration:
        return 0.5
    if pos < 8:    return 1.0
    elif pos < 20: return 0.75
    else:          return 0.5


def _score_uv_concern(concern, ingredient_list, concentrations, product_inci_map, product_inci_lower, synergies):
    """
    Full sunscreen scoring engine (v2.0) for Sun Protection, UV Damage, Tanning.
    Implements scoring logic from sunscreen_scoring_logic_v2_fixed.txt.

    Part 4 (0-100): Overall sunscreen quality — UV Coverage (40) + Filter Strength (30)
                    + Photostability (20) + Formulation (10)
    Part 5 per concern: Sunburn / Tanning / UV Damage specific scores (0-100)
    Part 6: Fake SPF detection, stability warnings, banned filter flags
    """

    # ── Step 0: Alias resolution ─────────────────────────────────────────────
    resolved_list = [INCI_ALIASES.get(ing, ing) for ing in ingredient_list]
    resolved_lower = {ing.lower() for ing in resolved_list}

    # ── Step 1: Detect UV filters from DB (Ingredient_Category contains 'UV Filter') ──
    # Deduplicate so each filter counts exactly once in strength calculations.
    detected_filters = []
    seen_filter_keys = set()
    for ing in resolved_list:
        canonical = INCI_ALIASES.get(ing, ing)
        uv_data = data_loader.get_uv_data(canonical) or data_loader.get_uv_data(ing)
        if uv_data:
            cat = str(uv_data.get('Ingredient_Category', '') or '').lower()
            if 'uv filter' in cat and canonical not in seen_filter_keys:
                detected_filters.append(canonical)
                seen_filter_keys.add(canonical)

    # ── Step 2: UV band presence ──────────────────────────────────────────────
    uvb_present  = any(f in _UVB_FILTER_LIST  for f in detected_filters)
    uva1_present = any(f in _UVA1_FILTER_LIST for f in detected_filters)
    uva2_present = any(f in _UVA2_FILTER_LIST for f in detected_filters)

    # ── Step 3: Avobenzone stability ──────────────────────────────────────────
    avobenzone_present  = 'Butyl Methoxydibenzoylmethane' in detected_filters
    octinoxate_present  = 'Ethylhexyl Methoxycinnamate'   in detected_filters
    # Build stabilizer set from DB (Photostabilizer col + Common_Synergy_Partners of Avobenzone)
    global _AVOBENZONE_STABILIZERS_CACHE
    if not _AVOBENZONE_STABILIZERS_CACHE:
        _AVOBENZONE_STABILIZERS_CACHE = _build_avobenzone_stabilizers()
    stabilizer_present = any(s.lower() in resolved_lower for s in _AVOBENZONE_STABILIZERS_CACHE)

    # Read Avobenzone's Photostability_Notes from DB for richer warning text
    _avob_uv = data_loader.get_uv_data('Butyl Methoxydibenzoylmethane')
    _avob_stability_note = str(_avob_uv.get('Photostability_Notes', '') or '').strip() if _avob_uv else ''
    film_former_present = any(ff.lower() in resolved_lower for ff in _FILM_FORMERS)

    warnings_list = []
    flags_list    = []
    explanation   = []

    # Avobenzone stability warnings (Part 4.4 / Part 6.3)
    if avobenzone_present and not stabilizer_present:
        # Use Photostability_Notes from DB for precise warning text
        _detail = _avob_stability_note if _avob_stability_note else "Degrades without stabilizer"
        warnings_list.append(f"⚠️ Unstable Avobenzone — {_detail}")
        flags_list.append("⚠️ Avobenzone Degradation: UVA protection drops ~50% after 1hr sun exposure")
    if avobenzone_present and octinoxate_present and not stabilizer_present:
        # Read Octinoxate's Common_Synergy_Partners / Photostability_Notes for mechanism
        _oct_uv = data_loader.get_uv_data('Ethylhexyl Methoxycinnamate')
        _oct_note = str(_oct_uv.get('Photostability_Notes', '') or '').strip() if _oct_uv else ''
        _conflict = _oct_note if _oct_note else "Octinoxate actively degrades Avobenzone"
        warnings_list.append(f"⚠️ Critical stability conflict: {_conflict}")

    # ── PART 4: OVERALL SUNSCREEN SCORE (0-100) ──────────────────────────────

    # 4.2 UV Coverage Score (max 40)
    if   not uvb_present and not uva1_present and not uva2_present: coverage_pts = 0
    elif not uvb_present and not uva1_present and     uva2_present: coverage_pts = 8
    elif     uvb_present and not uva1_present and not uva2_present: coverage_pts = 20
    elif     uvb_present and     uva2_present and not uva1_present: coverage_pts = 28
    elif     uvb_present and     uva1_present and not uva2_present: coverage_pts = 33
    else:                                                            coverage_pts = 40   # full broad spectrum

    # 4.3 Filter Strength Score (max 30)
    raw_strength = sum(
        _UV_FILTER_STRENGTH_MAP.get(f, 1) * _uv_conc_factor(f, resolved_list)
        for f in detected_filters
    )
    filter_pts = min((raw_strength / 12.0) * 30, 30)

    # 4.4 Photostability Score (max 20)
    phot_pts = 20
    if avobenzone_present and not stabilizer_present:
        phot_pts -= 10
    if avobenzone_present and octinoxate_present and not stabilizer_present:
        phot_pts -= 8

    PHOTOSTAB_PTS = {'Low': 0, 'Moderate': 1, 'High': 2, 'Very High': 3}
    photostab_bonus   = 0
    max_possible_bonus = max(len(detected_filters) * 3, 1)
    for f in detected_filters:
        uv_d = data_loader.get_uv_data(f)
        if uv_d:
            rating = str(uv_d.get('Photostability_Rating', 'Moderate') or 'Moderate').strip()
            photostab_bonus += PHOTOSTAB_PTS.get(rating, 1)

    if photostab_bonus > 0 and phot_pts < 20:
        phot_pts = min(phot_pts + (photostab_bonus / max_possible_bonus) * 8, 20)
    if film_former_present:
        phot_pts = min(phot_pts + 2, 20)
    phot_pts = max(phot_pts, 0)

    # 4.5 Formulation Score (max 10)
    form_pts = 0
    if film_former_present:
        form_pts += 3
    if any(b.lower() in resolved_lower for b in _SPF_BOOSTERS):
        form_pts += 2
    _ANTIOXIDANTS_FORM = [
        'Tocopherol', 'Ferulic Acid', 'Ascorbic Acid', 'Resveratrol', 'Astaxanthin',
        'Coenzyme Q10', 'Green Tea Extract', 'EGCG', 'Ergothioneine',
        'Polypodium Leucotomos Extract',
    ]
    aox_count = sum(1 for a in _ANTIOXIDANTS_FORM if a.lower() in resolved_lower)
    if   aox_count >= 2: form_pts += 3
    elif aox_count == 1: form_pts += 2
    if any(d.lower() in resolved_lower for d in ('photolyase', 'endonuclease')):
        form_pts += 2
    form_pts = min(form_pts, 10)

    total_score = round(coverage_pts + filter_pts + phot_pts + form_pts)

    # 4.6 SPF Estimate from filter_pts
    if   filter_pts >= 27: spf_estimate = "SPF 50+"
    elif filter_pts >= 22: spf_estimate = "SPF 40-50"
    elif filter_pts >= 16: spf_estimate = "SPF 30-40"
    elif filter_pts >= 10: spf_estimate = "SPF 20-30"
    elif filter_pts >= 5:  spf_estimate = "SPF 15-20"
    else:                  spf_estimate = "SPF < 15 (estimated)"

    # PA Rating from UVA score
    uva1_filter_count = sum(1 for f in detected_filters if f in _UVA1_FILTER_LIST)
    if   uva1_filter_count >= 2 and uva2_present: pa_estimate = "PA++++"
    elif uva1_filter_count >= 1 and uva2_present: pa_estimate = "PA+++"
    elif uva1_filter_count >= 1:                  pa_estimate = "PA++"
    elif uva2_present:                            pa_estimate = "PA+"
    else:                                         pa_estimate = "No UVA protection estimated"

    # ── PART 6: FLAGS ─────────────────────────────────────────────────────────
    reef_safe = True
    for f in detected_filters:
        if f in _BANNED_FILTERS:
            flags_list.append(f"⚠️ {f} — {_BANNED_FILTERS[f]}")
            if f == 'Oxybenzone':
                reef_safe = False

    if uvb_present and not uva1_present and not uva2_present:
        flags_list.append("⚠️ Not broad spectrum — only UVB covered, no UVA protection")
    if not uvb_present and not uva1_present and not uva2_present and len(ingredient_list) > 3:
        flags_list.append("🚨 No UV filters detected — this product does not appear to be a sunscreen")

    # Single weak filter fake-SPF check (per spec Part 6.4: exempt ZnO/TiO2 = strength ≥ 4)
    if len(detected_filters) == 1:
        only_f = detected_filters[0]
        if _UV_FILTER_STRENGTH_MAP.get(only_f, 1) < 4:
            flags_list.append(f"🚨 Single weak UV filter ({only_f}) — cannot achieve meaningful SPF alone")

    # ── PART 5: CONCERN-SPECIFIC SCORES ──────────────────────────────────────

    # ── 5.1  SUN PROTECTION ──────────────────────────────────────────────────
    if concern == 'Sun Protection':
        # Sun Protection = BROAD SPECTRUM quality (UVB + UVA + stability + formulation)
        # = total_score (already computed above from Part 4: coverage+filter+photostab+form)
        # This is distinct from Sunburn Protection (UVB-only) which is a sub-score.
        concern_score = float(total_score)

        # Sunburn sub-score (UVB-only) — stored in sunscreen_analysis for display
        uvb_strength_raw = sum(
            _UV_FILTER_STRENGTH_MAP.get(f, 1) * _uv_conc_factor(f, resolved_list)
            for f in detected_filters if f in _UVB_FILTER_LIST
        )
        sunburn_score = round(min((uvb_strength_raw / 8.0) * 100, 100))

        if not uvb_present:
            explanation.append("No UVB filters found — limited sun protection")
        elif uvb_present and uva1_present and uva2_present:
            explanation.append("Full broad spectrum: UVB + UVA1 + UVA2 coverage")
        elif uvb_present and uva1_present:
            explanation.append("Good broad spectrum: UVB + UVA1 — missing UVA2 (minor gap)")
        elif uvb_present and uva2_present:
            explanation.append("UVB + UVA2 — missing UVA1 (main tanning band)")
        else:
            explanation.append("UVB-only — no UVA protection (not broad spectrum)")

        if total_score >= 85:
            explanation.append(f"Sunscreen quality: Excellent ({total_score}/100)")
        elif total_score >= 70:
            explanation.append(f"Sunscreen quality: Good ({total_score}/100)")
        elif total_score >= 55:
            explanation.append(f"Sunscreen quality: Average ({total_score}/100)")
        else:
            explanation.append(f"Sunscreen quality: Weak ({total_score}/100)")

        if warnings_list:
            explanation.append(warnings_list[0])

        missing_actives = []
        if not uvb_present:
            missing_actives.append("UVB filter (Zinc Oxide, Titanium Dioxide, Ethylhexyl Triazone)")
        if not uva1_present and not uva2_present:
            missing_actives.append("UVA filter (Zinc Oxide, Avobenzone, Tinosorb S)")
        elif not uva1_present:
            missing_actives.append("UVA1 filter (Avobenzone, Tinosorb S, Zinc Oxide) for full spectrum")

        return {
            'score': round(concern_score),
            'present_actives': detected_filters[:5],
            'missing_actives': missing_actives[:3],
            'supporting_ingredients': [],
            'explanation': explanation[:4],
            'advisory': (
                f"SPF estimate: {spf_estimate} · PA estimate: {pa_estimate} "
                f"(tool estimates only — not lab-tested values)"
            ),
            'synergy_bonus': 0,
            'sunscreen_analysis': {
                'overall_score': total_score,
                'score_breakdown': {
                    'uv_coverage':    round(coverage_pts),
                    'filter_strength': round(filter_pts),
                    'photostability': round(phot_pts),
                    'formulation':    round(form_pts),
                },
                'spf_estimate':    spf_estimate,
                'pa_estimate':     pa_estimate,
                'pa_note':         'Approximation based on filter type; not lab-tested (PPD test required)',
                'broad_spectrum':  uvb_present and (uva1_present or uva2_present),
                'uvb_covered':     uvb_present,
                'uva1_covered':    uva1_present,
                'uva2_covered':    uva2_present,
                'reef_safe':       reef_safe,
                'sunburn_score':    sunburn_score,
                'filters_detected': detected_filters,
                'warnings':        warnings_list,
                'flags':           flags_list,
            },
        }

    # ── 5.2  TANNING PREVENTION ──────────────────────────────────────────────
    elif concern == 'Tanning':
        _BEST_ANTITAN = {
            'Butyl Methoxydibenzoylmethane':                       10,
            'Diethylamino Hydroxybenzoyl Hexyl Benzoate':          10,
            'Terephthalylidene Dicamphor Sulfonic Acid':            9,
            'Drometrizole Trisiloxane':                             9,
            'Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine':      10,
            'Methylene Bis-Benzotriazolyl Tetramethylbutylphenol':  9,
            'Zinc Oxide':                                           8,
            'Disodium Phenyl Dibenzimidazole Tetrasulfonate':       9,
        }
        uva_tan_raw = sum(_BEST_ANTITAN.get(f, 0) for f in detected_filters if f in _BEST_ANTITAN)
        uva_tan_score = min((uva_tan_raw / 20) * 60, 60)

        if not uva1_present:
            uva_tan_score *= 0.4
            warnings_list.append("⚠️ No UVA1 filter — limited tanning prevention (UVA1 causes 90% of tanning)")
        if avobenzone_present and not stabilizer_present:
            uva_tan_score *= 0.4

        _MELANIN_SUPPRESSORS = {
            'Tranexamic Acid': 10, 'Alpha Arbutin': 9, 'Niacinamide': 8,
            'Azelaic Acid':     8, 'Kojic Acid':    8, 'Ascorbic Acid': 7,
            'Cysteamine HCl':   9, 'Thiamidol':    10, 'Hexylresorcinol': 7,
        }
        suppressor_raw   = sum(v for k, v in _MELANIN_SUPPRESSORS.items() if k.lower() in resolved_lower)
        suppressor_score = min((suppressor_raw / 25) * 30, 30)
        concern_score    = min(uva_tan_score + suppressor_score, 100)

        melanin_found = [k for k in _MELANIN_SUPPRESSORS if k.lower() in resolved_lower]
        present_actives = list(dict.fromkeys(detected_filters + melanin_found))

        if melanin_found:
            explanation.append(f"Melanin suppressors: {', '.join(melanin_found[:2])}")
        else:
            explanation.append("No melanin suppressors — add Niacinamide or Alpha Arbutin")
        if uva1_present:
            explanation.append("UVA1 filter present — blocks main tanning radiation (320–400nm)")
        else:
            explanation.append("Missing UVA1 filter — main tanning band unprotected")
        if warnings_list:
            explanation.append(warnings_list[0])

        missing_actives = []
        if not melanin_found:
            missing_actives.append("Melanin suppressor (Alpha Arbutin, Tranexamic Acid, Niacinamide)")
        if not uva1_present:
            missing_actives.append("UVA1 filter (Avobenzone, Tinosorb S, Zinc Oxide)")

        if   concern_score >= 80: advisory = "Strong tanning prevention formula"
        elif concern_score >= 60: advisory = "Good tanning control — add melanin-suppressing serum underneath for best results"
        elif concern_score >= 40: advisory = "Moderate — pair with Alpha Arbutin or Tranexamic Acid serum for better tanning prevention"
        else:                     advisory = "⚠️ Weak tanning prevention — missing UVA1 filter and/or melanin suppressors"

        return {
            'score': round(concern_score),
            'present_actives': present_actives[:5],
            'missing_actives': missing_actives[:3],
            'supporting_ingredients': [],
            'explanation': explanation[:4],
            'advisory': advisory,
            'synergy_bonus': 0,
        }

    # ── 5.3  UV DAMAGE (Photoaging / DNA) ────────────────────────────────────
    elif concern == 'UV Damage':
        _BEST_UVA_DMG = {
            'Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine',
            'Diethylamino Hydroxybenzoyl Hexyl Benzoate',
            'Terephthalylidene Dicamphor Sulfonic Acid',
            'Drometrizole Trisiloxane', 'Zinc Oxide',
            'Methylene Bis-Benzotriazolyl Tetramethylbutylphenol',
            'Disodium Phenyl Dibenzimidazole Tetrasulfonate',
        }
        uva_dmg_raw = sum(
            _UV_FILTER_STRENGTH_MAP.get(f, 1) * _uv_conc_factor(f, resolved_list)
            for f in detected_filters if f in _BEST_UVA_DMG
        )
        uva_dmg_score = min((uva_dmg_raw / 8.0) * 50, 50)

        if not uva1_present and not uva2_present:
            uva_dmg_score *= 0.3
            warnings_list.append("⚠️ No UVA protection — provides no photoaging or anti-aging defense")

        _ANTIOXIDANT_WEIGHTS = {
            'Ascorbic Acid': 10, 'Ferulic Acid': 10, 'Tocopherol': 8,
            'Astaxanthin':   10, 'Resveratrol':   8, 'Polypodium Leucotomos Extract': 9,
            'Ergothioneine':  8, 'Green Tea Extract': 7, 'EGCG': 8,
            'Coenzyme Q10':   7, 'Idebenone': 8,
        }
        # Triple antioxidant synergy bonus (C + E + Ferulic)
        triple_synergy = (
            'ferulic acid' in resolved_lower and
            'ascorbic acid' in resolved_lower and
            'tocopherol' in resolved_lower
        )
        aox_raw = sum(v for k, v in _ANTIOXIDANT_WEIGHTS.items() if k.lower() in resolved_lower)
        if triple_synergy:
            aox_raw += 8
        aox_score = min((aox_raw / 20) * 35, 35)

        _DNA_REPAIR = {'Photolyase': 10, 'Endonuclease': 10}
        dna_raw   = sum(v for k, v in _DNA_REPAIR.items() if k.lower() in resolved_lower)
        dna_score = min((dna_raw / 10) * 15, 15)

        concern_score = min(uva_dmg_score + aox_score + dna_score, 100)

        antioxidants_found = [k for k in _ANTIOXIDANT_WEIGHTS if k.lower() in resolved_lower]
        present_actives = list(dict.fromkeys(detected_filters + antioxidants_found))

        if antioxidants_found:
            explanation.append(f"Antioxidants: {', '.join(antioxidants_found[:2])}")
        else:
            explanation.append("No antioxidants — UV-triggered free radicals not neutralized")
            warnings_list.append("💡 Add Vitamin C or Ferulic Acid serum for better UV damage defense")
        if triple_synergy:
            explanation.append("Triple antioxidant system (C + E + Ferulic) — enhanced photoprotection")
        if uva1_present:
            explanation.append("UVA1 filter present — key for anti-aging/photoaging defense")
        else:
            explanation.append("Missing UVA1 filter — photoaging radiation unblocked")
        if dna_score > 0:
            explanation.append("DNA repair enzyme detected — premium anti-aging formula")

        missing_actives = []
        if not antioxidants_found:
            missing_actives.append("Antioxidant (Vitamin C, Ferulic Acid, Vitamin E)")
        if not uva1_present:
            missing_actives.append("UVA1 filter (Avobenzone, Tinosorb S, Zinc Oxide)")

        if   concern_score >= 85: advisory = "Excellent UV damage prevention — professional-grade anti-aging protection"
        elif concern_score >= 70: advisory = "Good UV damage protection"
        elif concern_score >= 50: advisory = "Average — layer Vitamin C serum underneath for better UV damage defense"
        else:                     advisory = "⚠️ Weak UV damage protection — add broad-spectrum UVA filters and antioxidants"

        return {
            'score': round(concern_score),
            'present_actives': present_actives[:5],
            'missing_actives': missing_actives[:3],
            'supporting_ingredients': [],
            'explanation': explanation[:4],
            'advisory': advisory,
            'synergy_bonus': round(8 if triple_synergy else 0),
        }

    else:
        return {
            'score': 0, 'present_actives': [], 'missing_actives': [],
            'supporting_ingredients': [], 'explanation': ['Unknown concern'],
            'advisory': '', 'synergy_bonus': 0,
        }

def calculate_skin_concern_fit(ingredient_list, concerns, known_concentrations=None):
    """Skin Concern Fit: 4-component intelligent scoring model.
    A (50%): Evidence × Concentration × Synergy per active
    B (20%): Support system quality (barrier/anti-inflammatory/hydration)
    C (10%): Clinical synergy bonus from registry
    D (-30%): Worsening ingredient penalty
    """
    results = {}
    am_pm = "Suitable for: AM & PM"
    ing_str = " ".join(ingredient_list).lower()
    concentrations = estimate_concentration(ingredient_list, known_concentrations=known_concentrations)

    # Pre-lookup all product ingredients once
    product_inci_map = {}
    for ing in ingredient_list:
        data = data_loader.get_ingredient_data(ing)
        if data:
            inci = str(data.get('INCI_Name', '')).strip()
            product_inci_map[ing] = {'inci': inci, 'data': data, 'raw': ing}

    product_inci_set = {v['inci'] for v in product_inci_map.values()}
    product_inci_lower = {v['inci'].lower() for v in product_inci_map.values()}

    for concern in concerns:
        # Use specialized UV scoring for Sun Protection, UV Damage, Tanning
        if concern in UV_CONCERN_SET:
            synergies = data_loader.get_synergies(concern)
            results[concern] = _score_uv_concern(
                concern, ingredient_list, concentrations,
                product_inci_map, product_inci_lower, synergies
            )
            continue

        ideal_actives = data_loader.get_concern_actives(concern)
        ideal_supporters = data_loader.get_concern_supporters(concern)
        synergies = data_loader.get_synergies(concern)

        ideal_actives_set = set(ideal_actives)
        ideal_supporters_set = set(ideal_supporters)
        # Prefix groups for this concern (e.g. any "Ceramide *" counts for Barrier Repair)
        prefix_groups = CONCERN_INCI_PREFIXES.get(concern, [])

        def _is_concern_active(inci_name):
            """Return True if this INCI is a relevant active for the concern."""
            if inci_name in ideal_actives_set:
                return True
            inci_lower = inci_name.lower()
            for prefix in prefix_groups:
                if inci_lower.startswith(prefix.lower()):
                    return True
            return False

        # Find present actives and their data
        present_actives_data = []
        for ing, info in product_inci_map.items():
            if _is_concern_active(info['inci']):
                present_actives_data.append(info)

        present_active_names = [d['inci'] for d in present_actives_data]
        # For missing: only report top-level names user would recognise
        present_inci_set_for_missing = set(present_active_names)
        missing_actives = [
            a for a in ideal_actives
            if a not in present_inci_set_for_missing
            and not any(a.lower() == p['inci'].lower() for p in present_actives_data)
            and not any(a.lower().startswith(pfx.lower()) for pfx in prefix_groups
                        for p in present_actives_data if p['inci'].lower().startswith(pfx.lower()))
        ]

        # Is this a hydration-type concern? Used for floor + comp_b boost + messaging.
        is_hydration = concern.lower() in {"hydration", "barrier repair", "dryness"}

        # --- Component A: Effective Active Strength (0-50%) ---
        # For each relevant active: Evidence_Factor × Concentration_Factor × Synergy_Factor
        comp_a = 0
        conc_info = []
        active_contributions = []
        max_theoretical = 0

        for info in present_actives_data:
            data = info['data']
            raw_name = info['raw']

            # Evidence factor (Strong+=1.2, Strong=1.0, Moderate=0.7, Limited=0.4)
            ev_factor = get_evidence_factor(data)
            ev_norm = str(data.get('Evidence_Level_Normalized', '')).lower()
            if 'strong+' in ev_norm or ('strong' in ev_norm and 'consensus' in ev_norm):
                ev_factor = 1.2

            # Concentration factor
            est_conc = concentrations.get(raw_name, 0.3)
            conc_factor = get_concentration_factor(est_conc, data)

            # Only add conc_info bullet for true clinical actives, not support ingredients.
            # Support ingredients (humectants, emollients, etc.) don't need a % judgment.
            if not is_support_ingredient(data):
                if conc_factor >= 1.0:
                    conc_info.append(f"{info['inci']} — likely at optimal functional level (INCI estimate)")
                elif conc_factor >= 0.7:
                    conc_info.append(f"{info['inci']} — likely within functional range (INCI estimate)")
                else:
                    conc_info.append(f"{info['inci']} — may be below typical functional range (INCI estimate)")

            # Synergy factor (check if this active pairs with another present active)
            syn_factor = 1.0
            for syn in synergies:
                syn_ings = syn['ingredients']
                if info['inci'].lower() in syn_ings:
                    other_ings = [s for s in syn_ings if s != info['inci'].lower()]
                    if all(oi in product_inci_lower for oi in other_ings):
                        syn_factor = max(syn_factor, 1.1)
                        break

            contribution = ev_factor * conc_factor * syn_factor
            active_contributions.append(contribution)

        # Theoretical max: cap at 4 ideal actives for realistic normalization
        # This allows a product with 1-2 strong actives to score meaningfully
        norm_count = min(4, len(ideal_actives))
        for _ in range(norm_count):
            max_theoretical += 1.2 * 1.0 * 1.1

        if max_theoretical > 0:
            comp_a = (sum(active_contributions) / max_theoretical) * 50
        comp_a = min(50, comp_a)

        # --- Component B: Support System Quality (0-20%) ---
        has_barrier = False
        has_anti_inflammatory = False
        has_humectant = False
        has_antioxidant = False
        support_count = 0

        for ing, info in product_inci_map.items():
            inci = info['inci']
            data = info['data']
            func_cat = str(data.get('Functional_Category', '')).lower()
            ing_class = str(data.get('Ingredient_Class', '')).lower().strip()

            # Count concern-specific supporters
            if inci in ideal_supporters_set:
                support_count += 1

            # Check functional categories for general support
            if 'humectant' in func_cat or ing_class == 'humectant':
                has_humectant = True
            if any(kw in func_cat for kw in ['anti-inflam', 'soothing', 'calming']):
                has_anti_inflammatory = True
            if any(kw in func_cat for kw in ['antioxidant', 'photoprotect']):
                has_antioxidant = True
            if any(kw in func_cat for kw in ['barrier', 'ceramide', 'lipid', 'emollient', 'occlusive']):
                has_barrier = True
            # Also check ingredient names for common soothing/barrier agents
            inci_lower = inci.lower()
            if any(kw in inci_lower for kw in ['centella', 'allantoin', 'panthenol', 'bisabolol', 'madecass']):
                has_anti_inflammatory = True
            if any(kw in inci_lower for kw in ['ceramide', 'cholesterol', 'squalane', 'fatty acid']):
                has_barrier = True

        support_flags = sum([has_barrier, has_anti_inflammatory, has_humectant, has_antioxidant])
        if support_flags >= 3 and support_count >= 2:
            comp_b = 18
        elif support_flags >= 2 and support_count >= 1:
            comp_b = 14
        elif support_flags >= 2 or support_count >= 2:
            comp_b = 10
        elif support_flags >= 1 or support_count >= 1:
            comp_b = 6
        else:
            comp_b = 0

        # Hydration-specific comp_b boost: multiple humectants present even without
        # full barrier/antioxidant stack should still get meaningful support credit.
        if is_hydration:
            if has_humectant and has_barrier and support_count >= 2:
                comp_b = max(comp_b, 18)
            elif has_humectant and support_count >= 2:
                comp_b = max(comp_b, 14)

        # --- Component C: Intelligent Synergy Bonus (0-10%) ---
        comp_c = 0
        synergy_found = []
        seen_groups = set()
        for syn in synergies:
            syn_ings = syn['ingredients']
            group_id = syn.get('mechanism', '')
            if group_id in seen_groups:
                continue
            if all(si in product_inci_lower for si in syn_ings):
                comp_c += syn['bonus']
                synergy_found.append(syn['mechanism'])
                seen_groups.add(group_id)
        comp_c = min(10, comp_c)

        # --- Component D: Worsening Ingredient Penalty (max -30%) ---
        comp_d = 0
        worsening_found = []
        for trigger, penalty in WORSENING_INGREDIENTS.get(concern, []):
            if trigger in ing_str:
                comp_d += penalty
                worsening_found.append(trigger)

        # Position-weighted penalties for irritants/comedogenics
        for i, ing in enumerate(ingredient_list[:10]):
            data_item = data_loader.get_ingredient_data(ing)
            if data_item:
                try:
                    c_rating = float(data_item.get('Comedogenicity_0_5', 0) or 0)
                    if c_rating >= 4 and i < 5:
                        comp_d -= 5
                        worsening_found.append(f"{ing} (comedogenic)")
                except (ValueError, TypeError):
                    pass
                irritation = str(data_item.get('Irritation_Risk', 'Low')).lower()
                if 'high' in irritation and i < 8:
                    comp_d -= 4
                    worsening_found.append(f"{ing} (irritant)")

        comp_d = max(-30, comp_d)

        final = max(0, min(100, comp_a + comp_b + comp_c + comp_d))

        # Hydration floor: a product with ≥3 classic humectants and minimal penalty
        # should never appear as near-useless, even with few formal "ideal actives".
        if is_hydration:
            _hydrator_keywords = [
                "glycerin", "butylene glycol", "propanediol", "beta-glucan",
                "hyaluronic", "sodium hyaluronate", "polyglutamic"
            ]
            hydrator_count = sum(
                1 for ing in ingredient_list
                if any(k in ing.lower() for k in _hydrator_keywords)
            )
            if hydrator_count >= 3 and comp_d >= -10:
                final = max(final, 45)
        else:
            hydrator_count = 0  # used in explanation logic below

        # Build explanation (max 4 bullets, neutral tone)
        explanation = []

        # First bullet: override for well-stocked hydration products
        if is_hydration and final >= 45 and hydrator_count >= 3:
            explanation.append(
                "Solid hydrating base with multiple humectants; not a high-powered treatment serum."
            )
        elif present_actives_data:
            if comp_a >= 30:
                explanation.append("Strong clinically supported ingredients present")
            elif comp_a >= 15:
                explanation.append("Some clinically supported ingredients present")
            else:
                # No prominent actives but supporters present
                if support_count >= 2 or support_flags >= 2:
                    explanation.append(
                        "Supportive formula for this concern, but missing the strongest treatment actives."
                    )
                else:
                    explanation.append("Limited active ingredients for this concern")
        else:
            if support_count >= 2 or support_flags >= 2:
                explanation.append(
                    "Supportive formula for this concern, but missing the strongest treatment actives."
                )
            else:
                explanation.append("No key active ingredients found for this concern")

        if conc_info:
            explanation.append(conc_info[0])
        if synergy_found:
            explanation.append("Beneficial ingredient pairing enhances results")
        if not worsening_found:
            explanation.append("No major irritation triggers detected")
        else:
            explanation.append("Contains ingredients that may worsen condition")
        if missing_actives:
            explanation.append(f"Missing: {', '.join(missing_actives[:2])}")

        # Supporting ingredient display
        present_supporters = [info['inci'] for ing, info in product_inci_map.items()
                              if info['inci'] in ideal_supporters_set]

        results[concern] = {
            'score': round(final),
            'present_actives': present_active_names[:5],
            'missing_actives': missing_actives[:3],
            'supporting_ingredients': present_supporters[:4],
            'explanation': explanation[:4],
            'advisory': f"Ingredients like {', '.join(missing_actives[:2])} may further improve {concern.lower()} targeting." if missing_actives else "Good active coverage for this concern",
            'synergy_bonus': comp_c,
        }

    if 'retinol' in ing_str or 'tretinoin' in ing_str or 'adapalene' in ing_str or 'retinal' in ing_str:
        am_pm = "Best used: PM Only"
    elif 'glycolic' in ing_str or 'lactic' in ing_str or 'mandelic' in ing_str:
        am_pm = "Best used: PM (Sunscreen required)"

    return {'concerns': results, 'am_pm': am_pm}


def calculate_skin_type_compatibility(ingredient_list, skin_type):
    skin_type = skin_type.lower()
    base_score = 100  # All skin types start at 100 per spec
    score = base_score
    bonus = []
    penalty = []
    better_suited = []
    comedogenic_warnings = []
    allergen_warnings = []
    why_bullets = []
    helpful_ingredients = []
    look_for_suggestions = []
    total_penalty = 0  # track cumulative penalty for risk_level

    ing_str = " ".join(ingredient_list).lower()

    for i, ing in enumerate(ingredient_list):
        ing_lower = ing.lower()
        data = data_loader.get_ingredient_data(ing)

        if data:
            try:
                c_rating = float(data.get('Comedogenicity_0_5', 0) or 0)
                if c_rating >= 3:
                    label = 'Highly comedogenic' if c_rating >= 5 else 'Moderately comedogenic'
                    comedogenic_warnings.append({'name': ing, 'rating': int(c_rating), 'label': label})
            except (ValueError, TypeError):
                pass

        if data:
            flag = str(data.get('Red_Flag_Tags', '') or '')
            allergen_keywords = ['allergen', 'allergy', 'sensitiz', 'fragrance allergen',
                                 'high irritation', 'irritation risk', 'barrier damage',
                                 'stinging', 'sensitive-skin red flag']
            if flag and flag != 'nan' and any(kw in flag.lower() for kw in allergen_keywords):
                allergen_warnings.append({'name': ing, 'flag': flag})

        # Enrich helpful_ingredients using Primary_Benefits and Skin_Concerns from DB.
        # This surfaces formulator-style labels ("Glycerin (hydration)") instead of
        # generic text, and aligns with the updated ingredient database columns.
        if data:
            primary_benefit = str(data.get('Primary_Benefits', '') or '').strip()
            concerns_map = str(data.get('Skin_Concerns', '') or '').lower()

            # For dry / combination skin: flag hydration and barrier ingredients
            if skin_type in {'dry', 'combination'}:
                pb_lower = primary_benefit.lower()
                if any(k in pb_lower for k in ['hydration', 'barrier', 'moisture']):
                    # Grab first benefit token as a short label
                    benefit_label = primary_benefit.split(';')[0].strip().lower()
                    enriched = f"{ing} ({benefit_label})"
                    if enriched not in helpful_ingredients:
                        helpful_ingredients.append(enriched)

            # For oily skin: flag sebum-regulation / acne-targeting ingredients
            if skin_type == 'oily':
                if 'acne' in concerns_map or 'sebum' in concerns_map or 'pore' in concerns_map:
                    enriched = f"{ing} (acne support)"
                    if enriched not in helpful_ingredients:
                        helpful_ingredients.append(enriched)

            # For sensitive skin: flag soothing / anti-inflammatory ingredients
            if skin_type == 'sensitive':
                pb_lower = primary_benefit.lower()
                if any(k in pb_lower for k in ['sooth', 'calm', 'anti-inflam']):
                    benefit_label = primary_benefit.split(';')[0].strip().lower()
                    enriched = f"{ing} ({benefit_label})"
                    if enriched not in helpful_ingredients:
                        helpful_ingredients.append(enriched)

        if skin_type == 'oily':
            if data:
                try:
                    comedogenicity = float(data.get('Comedogenicity_0_5', 0) or 0)
                    if comedogenicity >= 4 and i < 10:
                        score -= 25
                        penalty.append(f"{ing} (Highly comedogenic, rating {int(comedogenicity)}/5)")
                        why_bullets.append(f"Warning: {ing} is highly pore-clogging (rating {int(comedogenicity)}/5)")
                    elif comedogenicity >= 3:
                        score -= 15
                        penalty.append(f"{ing} (Moderately comedogenic)")
                        why_bullets.append(f"Warning: {ing} moderately comedogenic")
                except (ValueError, TypeError):
                    pass
            if 'cocos nucifera' in ing_lower or 'coconut oil' in ing_lower or 'shea butter' in ing_lower:
                score -= 10
                penalty.append(f"{ing} (Heavy oil)")
                why_bullets.append(f"Warning: {ing} is too heavy for oily skin")
            if 'niacinamide' in ing_lower:
                score += 5
                bonus.append(f"{ing} (Sebum regulation)")
                why_bullets.append("Niacinamide helps control sebum")
                helpful_ingredients.append(f"{ing} (sebum regulation)")
            if 'zinc pca' in ing_lower or 'salicylic' in ing_lower:
                score += 5
                bonus.append(f"{ing} (Oil control)")
                why_bullets.append(f"{ing} helps with oil control")
                helpful_ingredients.append(f"{ing} (oil control)")

            look_for_suggestions = ["Products with Zinc PCA, Salicylic Acid, or mattifying agents may work better for excess sebum control."]

        elif skin_type == 'dry':
            if 'alcohol denat' in ing_lower or 'sd alcohol' in ing_lower:
                score -= 20
                penalty.append(f"{ing} (Drying)")
                why_bullets.append(f"Warning: {ing} strips moisture from dry skin")
            if 'glycerin' in ing_lower or 'ceramide' in ing_lower or 'hyaluronic' in ing_lower:
                score += 5
                bonus.append(f"{ing} (Hydrating)")
                why_bullets.append(f"{ing} provides hydration")
                helpful_ingredients.append(f"{ing} (hydrating)")
            if 'shea butter' in ing_lower or 'squalane' in ing_lower:
                score += 5
                bonus.append(f"{ing} (Moisturizing)")
                helpful_ingredients.append(f"{ing} (moisturizing)")

            look_for_suggestions = ["Look for products with Ceramides, Squalane, or Hyaluronic Acid for better moisture retention."]

        elif skin_type == 'sensitive':
            if 'fragrance' in ing_lower or 'parfum' in ing_lower:
                score -= 20
                penalty.append(f"{ing} (Fragrance)")
                why_bullets.append(f"Warning: {ing} is a common irritant for sensitive skin")
            if 'limonene' in ing_lower or 'linalool' in ing_lower:
                score -= 15
                penalty.append(f"{ing} (Allergen)")
                why_bullets.append(f"Warning: {ing} is a known allergen")
            if 'essential oil' in ing_lower:
                score -= 15
                penalty.append(f"{ing} (Essential oil)")
                why_bullets.append("Warning: Essential oils can irritate sensitive skin")
            if 'alcohol denat' in ing_lower or 'sd alcohol' in ing_lower:
                score -= 15
                penalty.append(f"{ing} (Denatured alcohol)")
            if data:
                irritation = str(data.get('Irritation_Risk', 'Low')).lower()
                if 'high' in irritation:
                    score -= 15
                    penalty.append(f"{ing} (High irritation risk)")
                    why_bullets.append(f"Warning: {ing} has high irritation potential")
                elif 'moderate' in irritation or 'medium' in irritation:
                    score -= 5
            if 'centella' in ing_lower or 'allantoin' in ing_lower or 'panthenol' in ing_lower:
                score += 5
                bonus.append(f"{ing} (Soothing)")
                why_bullets.append(f"{ing} provides soothing benefits")
                helpful_ingredients.append(f"{ing} (soothing)")

            look_for_suggestions = ["Look for products with Centella Asiatica, Allantoin, or fragrance-free formulas."]

        elif skin_type == 'combination':
            if 'cocos nucifera' in ing_lower or 'coconut oil' in ing_lower or 'shea butter' in ing_lower:
                score -= 8
                penalty.append(f"{ing} (Heavy oil - may clog T-zone)")
            if 'niacinamide' in ing_lower or 'zinc pca' in ing_lower:
                score += 4
                bonus.append(f"{ing} (Balancing)")
                helpful_ingredients.append(f"{ing} (balancing)")
            if 'fragrance' in ing_lower or 'parfum' in ing_lower:
                score -= 10
                penalty.append(f"{ing} (Fragrance)")
            if 'glycerin' in ing_lower or 'sodium hyaluronate' in ing_lower:
                score += 3
                bonus.append(f"{ing} (Hydrating)")
                helpful_ingredients.append(f"{ing} (hydrating)")
            if 'alcohol denat' in ing_lower or 'sd alcohol' in ing_lower:
                score -= 15
                penalty.append(f"{ing} (Drying)")

            # NOTE: has_oil_ctrl / has_hydrating intentionally checked per-ingredient
            # but appended only via post-loop flag (see after loop) to avoid compounding

            look_for_suggestions = ["Look for lightweight formulas with Niacinamide + Hyaluronic Acid for balanced care."]

        elif skin_type == 'normal':
            if data:
                irritation = str(data.get('Irritation_Risk', 'Low')).lower()
                if 'high' in irritation:
                    score -= 5
                    penalty.append(f"{ing} (High irritation)")
                    why_bullets.append(f"Warning: {ing} has high irritation risk")

            look_for_suggestions = ["Normal skin tolerates most formulations well."]

    # Post-loop: combination skin balanced formula bonus — applied ONCE
    if skin_type == 'combination':
        _has_oil_ctrl = any(x in ing_str for x in ['niacinamide', 'zinc pca', 'salicylic'])
        _has_hydrating = any(x in ing_str for x in ['glycerin', 'sodium hyaluronate', 'hyaluronic'])
        if _has_oil_ctrl and _has_hydrating:
            score = min(100, int(score * 1.1))
            bonus.append("Balanced formula (oil control + hydration)")
            why_bullets.append("Good balance of oil control and hydration")

    score = max(0, min(97, score))  # Cap at 97 — 100% is never scientifically credible

    # Compute net penalty for risk_level
    net_penalty = base_score - score
    if net_penalty <= 10:
        risk_level = "low"
    elif net_penalty <= 25:
        risk_level = "moderate"
    else:
        risk_level = "high"

    # base_texture_score: score excluding allergen/comedogenic penalties
    # approximated as the bonus-adjusted base minus only negative bonus contributions
    base_texture_score = min(100, max(0, 100 - max(0, net_penalty - sum(
        abs(p) for p in [0]  # bonuses already included in score
    ))))
    # Simpler: clamp at 100, floor at score (base can't be lower than final)
    base_texture_score = max(score, min(100, base_score))

    if score < 50:
        if skin_type == 'oily':
            better_suited = ['Dry', 'Normal']
        elif skin_type == 'dry':
            better_suited = ['Oily', 'Normal']
        elif skin_type == 'sensitive':
            better_suited = ['Normal']

    if not why_bullets:
        if score >= 80:
            why_bullets.append("Good overall compatibility with your skin type")
        else:
            why_bullets.append("Some ingredients may not be ideal for your skin type")

    # Generate formulation notes
    formulation_notes = detect_formulation_notes(ingredient_list)

    return {
        'score': score,
        'base_texture_score': base_texture_score,
        'risk_level': risk_level,
        'bonus_reasons': list(dict.fromkeys(bonus)),
        'penalty_reasons': list(dict.fromkeys(penalty)),
        'better_suited': better_suited,
        'comedogenic_warnings': list({w['name']: w for w in comedogenic_warnings}.values()),
        'allergen_warnings': list({w['name']: w for w in allergen_warnings}.values()),
        'why_bullets': list(dict.fromkeys(why_bullets))[:3],
        'helpful_ingredients': helpful_ingredients[:4],
        'look_for': look_for_suggestions,
        'formulation_notes': formulation_notes,
    }


def get_upgrade_suggestions(ingredient_list, concerns):
    suggestions = []
    upgrade_map = data_loader.active_upgrade_map
    ing_lower_list = [i.lower() for i in ingredient_list]
    concerns_lower = [c.lower() for c in concerns]

    if upgrade_map is not None and not upgrade_map.empty:
        for _, row in upgrade_map.iterrows():
            if str(row.get('Do_Not_Upgrade', '')).upper() == 'YES':
                continue
            primary = str(row.get('Primary_Active', '')).lower().strip()
            concern = str(row.get('Skin_Concern', '')).lower().strip()

            match_ing = any(primary in ing for ing in ing_lower_list)
            match_concern = any(concern in uc or uc in concern for uc in concerns_lower)

            if match_ing and match_concern:
                suggestions.append({
                    'active': row.get('Primary_Active'),
                    'upgrade': row.get('Upgrade_Active'),
                    'reason': row.get('Upgrade_Reason'),
                    'concern': row.get('Skin_Concern'),
                })

    if not suggestions and concerns:
        concern_upgrades = {
            'acne': [{'upgrade': 'Salicylic Acid 2% Serum', 'reason': 'BHA penetrates pores to clear congestion and control oil', 'active': 'Salicylic Acid'}],
            'pigmentation': [{'upgrade': 'Tranexamic Acid 3% Serum', 'reason': 'Strongest evidence for hyperpigmentation with minimal irritation', 'active': 'Tranexamic Acid'}],
            'aging': [{'upgrade': 'Retinol 0.5% Treatment', 'reason': 'Gold standard for collagen synthesis and cell turnover', 'active': 'Retinol'}],
            'barrier': [{'upgrade': 'Ceramide + Cholesterol Moisturizer', 'reason': 'Mimics skin lipid structure for optimal barrier restoration', 'active': 'Ceramides'}],
            'sensitive': [{'upgrade': 'Centella Asiatica Serum', 'reason': 'Clinically proven to calm inflammation and strengthen skin', 'active': 'Centella Asiatica'}],
            'hydration': [{'upgrade': 'Multi-weight Hyaluronic Acid Serum', 'reason': 'Multiple molecular weights for deep and surface hydration', 'active': 'Hyaluronic Acid'}],
            'pores': [{'upgrade': 'Niacinamide 10% + Zinc PCA', 'reason': 'Tightens pores and regulates sebum production', 'active': 'Niacinamide'}],
            'dullness': [{'upgrade': 'Vitamin C 15% Serum', 'reason': 'Potent antioxidant that boosts radiance and evens skin tone', 'active': 'Vitamin C'}],
            'texture': [{'upgrade': 'AHA/BHA Chemical Exfoliant', 'reason': 'Removes dead cells and promotes smooth, refined texture', 'active': 'Glycolic Acid'}],
            'dark circles': [{'upgrade': 'Caffeine + Peptide Eye Serum', 'reason': 'Constricts blood vessels and strengthens delicate under-eye skin', 'active': 'Caffeine'}],
            'sun': [{'upgrade': 'Broad Spectrum SPF 50 with antioxidants', 'reason': 'Essential UV protection with added photoaging defense', 'active': 'UV Filters'}],
            'uv': [{'upgrade': 'Ferulic Acid + Vitamin C + E Serum', 'reason': 'Triple antioxidant synergy for superior UV damage repair', 'active': 'Ferulic Acid'}],
            'tanning': [{'upgrade': 'Alpha Arbutin 2% + Niacinamide', 'reason': 'Tyrosinase inhibition for effective de-tanning without irritation', 'active': 'Alpha Arbutin'}],
            'puffiness': [{'upgrade': 'Caffeine 5% Eye Serum', 'reason': 'Reduces puffiness by improving microcirculation around eyes', 'active': 'Caffeine'}],
        }
        for c in concerns:
            c_lower = c.lower()
            for key, upgrades in concern_upgrades.items():
                if key in c_lower:
                    for u in upgrades:
                        suggestions.append({**u, 'concern': c})
                    break

    unique_suggestions = []
    seen = set()
    for s in suggestions:
        key = s.get('upgrade', '')
        if key not in seen:
            unique_suggestions.append(s)
            seen.add(key)
    return unique_suggestions[:3]


def analyze_product(product_data):
    raw_ingredients_str = product_data.get("ingredients", "")
    ingredient_list = parse_ingredients(raw_ingredients_str)

    # Parse known concentrations from three sources (highest to lowest priority):
    # 1. Scraped from product page (most precise — already normalized by product_fetcher)
    # 2. Parsed from INCI string itself (e.g. "Niacinamide 10%, Zinc PCA 1%")
    # 3. Parsed from product name (e.g. "10% Niacinamide Serum")
    product_name = product_data.get("product_name", "") or ""
    known_from_name = _parse_concentrations_from_name(product_name)
    known_from_inci = extract_concentrations_from_inci(raw_ingredients_str)
    scraped_conc = product_data.get("active_concentrations") or {}  # from product_fetcher
    # Merge: scraped > inci-inline > name-parsed  (later keys overwrite earlier ones)
    known_concentrations = {
        **known_from_name,
        **known_from_inci,
        **{k.lower(): v for k, v in scraped_conc.items()},
    }

    main_score = calculate_main_worth_score(
        ingredient_list,
        product_data.get("price", 0),
        product_data.get("size_ml", 30),
        product_data.get("category", "Serum"),
        product_data.get("country", "India"),
        known_concentrations=known_concentrations
    )

    concern_fit = calculate_skin_concern_fit(
        ingredient_list,
        product_data.get("concerns", []),
        known_concentrations=known_concentrations
    )

    skin_compat = calculate_skin_type_compatibility(
        ingredient_list,
        product_data.get("skin_type", "normal")
    )

    upgrade_suggestions = get_upgrade_suggestions(
        ingredient_list,
        product_data.get("concerns", [])
    )

    concern_dict = concern_fit.get('concerns', {})
    am_pm = concern_fit.get('am_pm', 'Suitable for: AM & PM')

    # New analyses — 1% marker, conflicts, pH, delivery systems
    marker_idx, marker_name = _find_one_percent_marker(ingredient_list)
    one_percent_marker = None
    if marker_idx is not None:
        one_percent_marker = {
            'index': marker_idx,
            'ingredient': marker_name,
            'above_marker': ingredient_list[:marker_idx],
            'below_marker': ingredient_list[marker_idx:],
        }

    ingredient_conflicts  = detect_ingredient_conflicts(ingredient_list)
    ph_analysis           = infer_ph_and_check(ingredient_list)
    delivery_systems      = detect_delivery_systems(ingredient_list)

    # Score confidence label
    has_confirmed_concs = any(a.get('concentration_known') for a in main_score['identified_actives'])
    if one_percent_marker:
        score_confidence = f"Based on confirmed INCI order — 1% line found at {marker_name}"
        score_confidence_level = "medium"
    elif has_confirmed_concs:
        score_confidence = "Some concentrations confirmed from product page"
        score_confidence_level = "medium"
    else:
        score_confidence = "Estimated from INCI position only — no concentration data available"
        score_confidence_level = "low"

    return {
        "main_worth_score": main_score['score'],
        "main_worth_tier": main_score['tier_badge'],
        "score_title": main_score['score_title'],
        "component_scores": {
            "A": main_score['breakdown']['active_value'],
            "B": main_score['breakdown']['formula_quality'],
            "C": main_score['breakdown']['claim_accuracy'],
            "D": main_score['breakdown']['safety'],
            "E": main_score['breakdown']['price_rationality']
        },
        "component_details": main_score['component_details'],
        "worth_multipliers_applied": main_score['multipliers_applied'],
        "red_flags": main_score.get('red_flags', []),
        "price_analysis": {
            "price_per_ml": main_score['stats']['price_per_ml'],
            "category_avg": main_score['stats'].get('category_avg', 0),
            "vs_average": str(main_score['stats']['vs_average']) + "x",
            "price_per_active": main_score['stats']['price_per_active'],
            "active_count": main_score['stats']['active_count'],
            "active_ratio": str(main_score['stats']['active_ratio']) + "%",
            "global_markup_detected": False,
            "price_note": main_score.get('price_note'),
            "value_tier": main_score.get('value_tier', 'fair'),
            "ratio": main_score.get('ratio', 1.0),
        },
        "identified_actives": main_score['identified_actives'],
        "active_classes": main_score.get('active_classes', {}),
        "skin_concern_fit": concern_dict,
        "am_pm_recommendation": am_pm,
        "skin_type_compatibility": skin_compat['score'],
        "skin_type_base_texture": skin_compat.get('base_texture_score', skin_compat['score']),
        "skin_type_risk_level": skin_compat.get('risk_level', 'low'),
        "skin_type_reasons": skin_compat['bonus_reasons'] + skin_compat['penalty_reasons'],
        "skin_type_details": {
            "why_bullets": skin_compat['why_bullets'],
            "helpful_ingredients": skin_compat['helpful_ingredients'],
            "look_for": skin_compat['look_for'],
            "formulation_notes": skin_compat['formulation_notes'],
        },
        "better_suited": skin_compat.get('better_suited', []),
        "comedogenic_warnings": skin_compat.get('comedogenic_warnings', []),
        "allergen_warnings": skin_compat.get('allergen_warnings', []),
        "upgrade_suggestions": upgrade_suggestions,
        "ingredient_count": len(ingredient_list),
        "disclaimer": "Science-based estimates. Not medical advice.",
        "one_percent_marker": one_percent_marker,
        "ingredient_conflicts": ingredient_conflicts,
        "ph_analysis": ph_analysis,
        "delivery_systems": delivery_systems,
        "score_confidence": score_confidence,
        "score_confidence_level": score_confidence_level,
    }

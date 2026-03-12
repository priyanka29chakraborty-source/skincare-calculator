import re
import math
from data_loader import data_loader, CONCERNS_MAP, CONCERN_INCI_PREFIXES
from config import (
    CATEGORY_AVERAGES, WORTH_MULTIPLIERS, CONCENTRATION_THRESHOLDS,
    CATEGORY_AVERAGES_DEFAULT,
    WORSENING_INGREDIENTS
)


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

    # High-potency ingredients that are effective even at <1% (end of list is fine)
    HIGH_POTENCY_KEYWORDS = [
        'peptide', 'retinol', 'retinal', 'retinyl', 'adapalene', 'tretinoin',
        'ascorbic acid', 'ferulic', 'tranexamic', 'kojic', 'bakuchiol',
        'alpha arbutin', 'azelaic', 'salicylic', 'glycolic', 'lactic',
        'niacinamide', 'caffeine', 'tocopherol',
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
    e.g. '10% Niacinamide + 1% Zinc Serum' → {'niacinamide': 10.0, 'zinc': 1.0}
    Avoids double-counting if ingredient name also appears in INCI list.
    """
    if not product_name:
        return {}

    # Stop words that should never be treated as ingredient names
    STOP_WORDS = {
        'serum', 'cream', 'lotion', 'gel', 'toner', 'essence', 'oil', 'moisturizer',
        'solution', 'formula', 'treatment', 'complex', 'blend', 'mix', 'booster',
        'the', 'and', 'with', 'for', 'skin', 'face', 'body', 'anti', 'plus',
    }
    # Known brand words that leak into name parsing
    BRAND_WORDS = {'ordinary', 'inkey', 'paula', 'cosrx', 'cerave', 'neutrogena',
                   'dermalogica', 'skinceuticals', 'olay', 'estee', 'lauder'}

    known = {}
    patterns = [
        # "10% Niacinamide" pattern
        re.compile(r'([\d]+\.?\d*)\s*%\s+([a-zA-Z][a-zA-Z0-9 \-]{2,30}?)(?=\s*[+&,|\n]|$|\s+\d)', re.I),
        # "Niacinamide 10%" pattern
        re.compile(r'([a-zA-Z][a-zA-Z0-9 \-]{2,30}?)\s+(\d+\.?\d*)\s*%', re.I),
    ]
    for pat in patterns:
        for m in pat.finditer(product_name):
            groups = m.groups()
            try:
                if groups[0][0].isdigit():
                    pct, name = float(groups[0]), groups[1].strip().lower()
                else:
                    name, pct = groups[0].strip().lower(), float(groups[1])
                name = name.rstrip('s').strip()
                # Skip stop words, brand words, single chars, or out-of-range %
                if 0 < pct <= 100 and len(name) > 2:
                    name_parts = name.split()
                    if not any(w in STOP_WORDS | BRAND_WORDS for w in name_parts):
                        if name not in known:
                            known[name] = pct
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


def get_concentration_factor(estimated_pct, data):
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
        return 0.7

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


def calculate_main_worth_score(ingredient_list, price, size_ml, category, country='India', known_concentrations=None):
    score_breakdown = {
        'active_value': 0,
        'formula_quality': 0,
        'claim_accuracy': 15,
        'safety': 10,
        'price_rationality': 0
    }
    component_details = {'A': [], 'B': [], 'C': [], 'D': [], 'E': []}
    concentrations = estimate_concentration(ingredient_list, known_concentrations=known_concentrations)
    identified_actives = []
    multipliers_applied = []

    # --- Component A: Active Ingredient Value (Max 45) ---
    # Diminishing returns: smooth decay 1/(1 + 0.5*i) so 2nd active worth 67%, 3rd 50%, etc.
    # Calibrated: 2 strong actives ≈ 40/45
    ACTIVE_NORM_FACTOR = 25

    active_contributions = []
    for ing_name in ingredient_list:
        data = data_loader.get_ingredient_data(ing_name)
        if data and str(data.get('Ingredient_Class', '')).lower() == 'active':
            try:
                esw_raw = data.get('Effect_Strength_Weight', '')
                if esw_raw == '' or str(esw_raw).strip() in ('', 'nan', '0'):
                    # Category-based ESW default for blank/unscored ingredients
                    func_cat = str(data.get('Functional_Category', '')).lower()
                    if 'humectant' in func_cat:
                        weight = 1.0
                    elif any(c in func_cat for c in ['emulsifier', 'thickener', 'solvent', 'preservative']):
                        weight = 0.5
                    else:
                        weight = 0.5  # conservative default for actives without scored weight
                else:
                    weight = float(esw_raw)
                if math.isnan(weight):
                    weight = 0.5
            except (ValueError, TypeError):
                weight = 0.5

            conc = concentrations.get(ing_name, 0.3)
            conc_factor = get_concentration_factor(conc, data)
            eq_factor = get_evidence_factor(data)
            raw_strength = weight * conc_factor * eq_factor

            conc_label = (
                "Optimal level" if conc_factor >= 1.0 else
                "Functional range" if conc_factor >= 0.7 else
                "Below optimal range"
            )
            ev_label = get_evidence_label(eq_factor)

            active_contributions.append({
                'name': ing_name, 'strength': raw_strength,
                'conc_factor': conc_factor, 'eq_factor': eq_factor, 'weight': weight,
                'conc_label': conc_label, 'ev_label': ev_label,
                'position': ingredient_list.index(ing_name)
            })
            identified_actives.append({
                'name': ing_name,
                'position': ingredient_list.index(ing_name) + 1,
                'evidence': ev_label,
                'concentration': conc_label,
                'score_contribution': round(eq_factor * conc_factor * weight, 2),
                'primary_benefits': (lambda v: None if (not v or str(v).lower() in ('nan','none','')) else str(v).strip())(data.get('Primary_Benefits', '')),
                'targets': [t.strip() for t in str(data.get('Skin_Concerns', '') or '').split(';') if t.strip() and t.strip() not in ('', ' ')][:3],
                'functional_category': (lambda v: None if (not v or str(v).lower() in ('nan','none','')) else str(v).strip())(data.get('Functional_Category', '')),
            })

    active_contributions.sort(key=lambda x: x['strength'], reverse=True)
    weighted_sum = 0
    actives_found = []
    for i, ac in enumerate(active_contributions):
        # Smooth log-based diminishing returns: 1st=1.0, 2nd=0.67, 3rd=0.50, 4th=0.40...
        mult = max(0.15, 1.0 / (1 + 0.5 * i))
        weighted_sum += ac['strength'] * mult
        actives_found.append(ac['name'])

    active_score = min(45, weighted_sum * ACTIVE_NORM_FACTOR)
    score_breakdown['active_value'] = round(active_score, 1)

    clinical_count = sum(1 for a in active_contributions if a['eq_factor'] >= 0.7)
    component_details['A'].append(f"{len(actives_found)} active ingredient{'s' if len(actives_found) != 1 else ''} with clinical backing" if clinical_count > 0 else "No clinically-backed actives found")
    for ac in active_contributions[:3]:
        component_details['A'].append(f"{ac['name']} ({ac['ev_label']})")

    # --- Component B: Functional Formula Quality (Max 20) ---
    formula_score = 10.0
    has_humectant = False
    has_emollient = False
    has_occlusive = False
    has_preservative = False
    has_delivery_system = False
    functional_count = 0

    FUNCTIONAL_CLASSES = {'functional', 'humectant', 'emollient', 'preservative',
                          'functional support', 'antioxidant support', 'occlusive',
                          'sensory modifier', 'surfactant', 'solvent'}

    for i, ing_name in enumerate(ingredient_list):
        data = data_loader.get_ingredient_data(ing_name)
        ing_lower = ing_name.lower()

        if data:
            func_cat = str(data.get('Functional_Category', '')).lower()
            ing_class = str(data.get('Ingredient_Class', '')).lower().strip()

            if ing_class in FUNCTIONAL_CLASSES:
                functional_count += 1

            if 'humectant' in func_cat or ing_class == 'humectant':
                has_humectant = True
            if 'emollient' in func_cat or ing_class == 'emollient':
                has_emollient = True
            if 'occlusive' in func_cat or ing_class == 'occlusive':
                has_occlusive = True
            if 'preservative' in func_cat or 'antimicrobial' in func_cat or ing_class == 'preservative':
                has_preservative = True

        if any(kw in ing_lower for kw in ['liposom', 'encapsulat', 'nano', 'cyclodextrin']):
            has_delivery_system = True

        if i < 5 and ('alcohol denat' in ing_lower or 'sd alcohol' in ing_lower):
            cat_lower = category.lower()
            if cat_lower in ['moisturizer', 'treatment', 'eye cream']:
                formula_score -= 3
                component_details['B'].append(f"Denatured alcohol in top 5 for {category} (-3)")

        if 'essential oil' in ing_lower and category.lower() in ['treatment', 'serum']:
            formula_score -= 4
            component_details['B'].append("Essential oils in treatment product (-4)")

        if ('fragrance' in ing_lower or 'parfum' in ing_lower) and category.lower() in ['sensitive', 'treatment']:
            formula_score -= 2

    # Functional ingredient bonus (capped at +5)
    formula_score += min(5, functional_count * 0.5)

    if has_humectant and has_emollient:
        formula_score += 3
    if has_humectant and has_emollient and has_occlusive:
        formula_score += 2

    # Broader preservative check - common systems that may not match exact keywords
    _BROAD_PRESERVATIVES = [
        'phenoxyethanol', 'ethylhexylglycerin', 'sodium benzoate', 'potassium sorbate',
        'caprylyl glycol', 'benzyl alcohol', 'dehydroacetic acid', 'chlorphenesin',
        'sodium hydroxymethylglycinate', 'methylisothiazolinone', 'chloromethylisothiazolinone',
        'iodopropynyl', 'dmdm hydantoin', 'imidazolidinyl urea', 'diazolidinyl urea',
        'ferment', 'lactobacillus', 'leuconostoc'  # ferment-based preservation
    ]
    if not has_preservative:
        has_preservative = any(p in ' '.join(ingredient_list).lower() for p in _BROAD_PRESERVATIVES)
    if not has_preservative and len(ingredient_list) > 5:
        formula_score -= 4  # reduced penalty from -8 to -4
        component_details['B'].append("No standard preservative detected (-4)")

    if has_delivery_system:
        formula_score += 3
        component_details['B'].append("Advanced delivery systems present (+3)")

    # Category-specific formula expectations (Item 7)
    cat_lower = category.strip().lower()
    if cat_lower in ('serum', 'treatment', 'essence'):
        if not actives_found:
            formula_score -= 3
            component_details['B'].append("Serum with no identified actives (-3)")
        elif len(actives_found) >= 3:
            formula_score += 2
            component_details['B'].append(f"Rich active profile for a {category} (+2)")
    elif cat_lower in ('moisturizer', 'cream', 'lotion'):
        if has_humectant and has_emollient and has_occlusive:
            formula_score += 3
            component_details['B'].append("Complete moisturization stack (+3)")
    elif cat_lower == 'sunscreen':
        has_antioxidant_boost = any(
            any(kw in i.lower() for kw in ('tocopherol', 'ascorbic acid', 'ferulic acid'))
            for i in ingredient_list
        )
        if has_antioxidant_boost:
            formula_score += 2
            component_details['B'].append("Antioxidant UV boosters present (+2)")
    elif cat_lower in ('toner', 'mist', 'essence'):
        formula_score += 1  # Lighter category — less infrastructure expected
    elif cat_lower == 'cleanser':
        has_conditioning = any(
            any(kw in i.lower() for kw in ('panthenol', 'aloe', 'glycerin', 'ceramide'))
            for i in ingredient_list
        )
        if has_conditioning:
            formula_score += 2
            component_details['B'].append("Skin-conditioning agents in cleanser (+2)")

    formula_score = round(min(20, max(0, formula_score)), 1)
    score_breakdown['formula_quality'] = formula_score

    if not component_details['B']:
        if formula_score >= 15:
            component_details['B'].append("Well-balanced humectant-emollient base")
        elif formula_score >= 10:
            component_details['B'].append("Standard formulation with adequate support")
        else:
            component_details['B'].append("Basic formulation, limited functional support")
    if has_preservative:
        component_details['B'].append("Preservative system present")

    # --- Component C: Claim-Reality Accuracy (Max 15) ---
    claim_score = 15
    claim_details = []
    for ing_name in ingredient_list:
        data = data_loader.get_ingredient_data(ing_name)
        if data and 'Overclaim risk' in str(data.get('Red_Flag_Tags', '')):
            claim_score -= 3
            claim_details.append(f"{ing_name} has overclaim risk")

    for ac in active_contributions:
        if ac['conc_factor'] == 0.0:
            claim_score -= 2
            claim_details.append(f"{ac['name']} below effective concentration")

    claim_score = max(0, claim_score)
    score_breakdown['claim_accuracy'] = claim_score

    if claim_score >= 13:
        component_details['C'].append("Claims well-supported by ingredient composition")
    elif claim_score >= 7:
        component_details['C'].append("Some claims partially supported")
    else:
        component_details['C'].append("Significant gap between claims and formulation")
    for d in claim_details[:2]:
        component_details['C'].append(d)

    # --- Component D: Safety & Suitability (Max 10) ---
    safety_score = 10.0
    safety_details = []

    for i, ing_name in enumerate(ingredient_list):
        ing_lower = ing_name.lower()
        data = data_loader.get_ingredient_data(ing_name)

        if 'fragrance' in ing_lower or 'parfum' in ing_lower:
            if i < 10:
                safety_score -= 4
                safety_details.append(f"Contains fragrance ({ing_name})")
        if 'alcohol denat' in ing_lower or 'sd alcohol' in ing_lower:
            if i < 10:
                safety_score -= 3
                safety_details.append(f"Contains denatured alcohol ({ing_name})")
        if 'essential oil' in ing_lower or 'limonene' in ing_lower or 'linalool' in ing_lower:
            safety_score -= 3
            safety_details.append(f"Contains potential allergen ({ing_name})")

        if data:
            irritation = str(data.get('Irritation_Risk', 'Low')).lower()
            if irritation == 'high':
                safety_score -= 3
                safety_details.append(f"{ing_name} has high irritation risk")
            elif irritation == 'medium':
                safety_score -= 0.5

            pregnancy = str(data.get('Pregnancy_Safety', 'Safe')).lower()
            if 'avoid' in pregnancy or 'restricted' in pregnancy:
                safety_score -= 4
                safety_details.append(f"{ing_name} flagged for pregnancy safety")

    safety_score = round(max(0, min(10, safety_score)), 1)
    score_breakdown['safety'] = safety_score

    if safety_score >= 9:
        component_details['D'].append("Low irritation risk overall")
    elif safety_score >= 6:
        component_details['D'].append("Some safety considerations present")
    else:
        component_details['D'].append("Multiple safety flags detected")
    for d in safety_details[:2]:
        component_details['D'].append(d)

    # --- Component E: Price Rationality (Max 10) ---
    price_per_ml = price / size_ml if size_ml > 0 else 0
    country_avgs = CATEGORY_AVERAGES.get(country)
    price_note = None

    # Edge case: missing size
    if size_ml <= 0 or price <= 0:
        price_note = 'Size not provided — price per ml unavailable' if size_ml <= 0 else 'Price not provided — value analysis unavailable'
        price_score = 5
        avg_price = 0
        ratio = 1.0
    elif country_avgs is None:
        price_note = 'Price comparison unavailable for this country - score reflects formula quality only'
        price_score = 5
        avg_price = 0
        ratio = 1.0
    else:
        cat_key = category.strip().lower()
        cat_avg = country_avgs.get(cat_key, {'avg_price_per_ml': 1.0})
        avg_price = cat_avg.get('avg_price_per_ml', 1.0)
        ratio = round(price_per_ml / avg_price, 4) if avg_price > 0 else 1.0

        if ratio < 0.70:
            price_score = 10
        elif ratio < 1.30:
            price_score = 8
        elif ratio < 2.00:
            price_score = 5
        else:
            price_score = 2

    score_breakdown['price_rationality'] = float(price_score)  # initial; adjusted below

    # Formula-quality adjustment: high formula quality justifies slight price premium (Item 8)
    formula_q = score_breakdown.get('formula_quality', 10)
    if formula_q >= 17 and price_score > 0:
        price_score = min(10, price_score + 1)
        component_details['E'].append("High formula quality offsets price (+1 adjustment)")
    elif formula_q <= 7 and price_score > 0:
        price_score = max(0, price_score - 1)
        component_details['E'].append("Poor formula quality worsens price value (-1 adjustment)")
    score_breakdown['price_rationality'] = float(price_score)

    # Derive value_tier from (adjusted) price_score
    if price_score >= 9:
        value_tier = "underpriced"
    elif price_score >= 7:
        value_tier = "fair"
    elif price_score >= 5:
        value_tier = "slightly_overpriced"
    else:
        value_tier = "overpriced"

    if price_score >= 9:
        component_details['E'].append("Underpriced - excellent value at this price point")
    elif price_score >= 7:
        component_details['E'].append("Fairly priced for the category")
    elif price_score >= 4:
        component_details['E'].append("Slightly overpriced - brand premium detected")
    else:
        component_details['E'].append("Heavily overpriced for the active content")
    if price_per_ml > 0 and avg_price > 0:
        component_details['E'].append(f"{ratio:.1f}x vs category average ({price_per_ml:.2f}/ml vs avg {avg_price:.2f}/ml)")
    if actives_found:
        ppa = price / len(actives_found)
        component_details['E'].append(f"Price per active ingredient: {ppa:.2f}")

    # --- Worth Red Flags ---
    red_flags, red_flag_penalty = detect_red_flags(ingredient_list, concentrations, category)
    for rf in red_flags:
        component_details['E'].append(rf)

    # Total
    total_score = sum(score_breakdown.values()) + red_flag_penalty

    # Worth Multipliers
    ing_str = " ".join(ingredient_list).lower()
    has_fragrance = any('fragrance' in i.lower() or 'parfum' in i.lower() for i in ingredient_list)
    has_denat = any('alcohol denat' in i.lower() or 'sd alcohol' in i.lower() for i in ingredient_list)

    if 'encapsulated' in ing_str and 'retinol' in ing_str:
        total_score *= WORTH_MULTIPLIERS.get('Stability Engineering', 1.0)
        multipliers_applied.append('Stability Engineering (2.0x)')

    has_ceramide = 'ceramide' in ing_str
    has_panthenol = 'panthenol' in ing_str
    if has_ceramide and has_panthenol and not has_fragrance and not has_denat:
        total_score *= WORTH_MULTIPLIERS.get('Barrier Neutrality', 1.0)
        multipliers_applied.append('Barrier Neutrality (1.3x)')

    total_score = min(100, max(0, total_score))
    active_ratio = len(actives_found) / len(ingredient_list) if ingredient_list else 0

    # --- Active Classes: four buckets (scale-aware tiered classification) ---
    # DB has two ESW scales:
    #   UV filters:      ESW 5.0  → always Primary
    #   Regular actives: ESW 0-1  → Primary ≥0.80, Supporting ≥0.50, else Antioxidant/Barrier
    ANTIOXIDANT_NAMES = {
        'tocopherol', 'ascorbic acid', 'ferulic acid', 'resveratrol', 'astaxanthin',
        'coenzyme q10', 'ergothioneine', 'green tea', 'egcg', 'idebenone', 'quercetin',
    }
    BARRIER_FUNC_CATS = {'barrier', 'emollient', 'occlusive', 'humectant'}
    UV_FUNC_CATS = {'uv filter', 'mineral uv filter', 'organic uv filter', 'sunscreen'}

    primary_actives = []
    supporting_actives = []
    antioxidant_actives = []
    barrier_actives = []
    classified_names = set()

    def _classify_active(weight, func_cat_lower, ing_class_lower):
        """Scale-aware classification. UV filters use 5.0 scale; regular actives use 0–1 scale."""
        if any(uv in func_cat_lower for uv in UV_FUNC_CATS) or 'uv filter' in ing_class_lower:
            return 'primary'   # UV filters always primary — their ESW=5.0 is a different scale
        if weight >= 0.80:
            return 'primary'
        elif weight >= 0.50:
            return 'supporting'
        elif weight >= 0.30:
            return 'antioxidant'
        else:
            return 'barrier_support'

    for ac in active_contributions:
        name = ac['name']
        classified_names.add(name.lower())
        data = data_loader.get_ingredient_data(name)
        func_cat_lower = str(data.get('Functional_Category', '') if data else '').lower()
        ing_class_lower = str(data.get('Ingredient_Class', '') if data else '').lower()
        bucket = _classify_active(ac['weight'], func_cat_lower, ing_class_lower)
        if bucket == 'primary':
            primary_actives.append(name)
        elif bucket == 'supporting':
            supporting_actives.append(name)
        elif bucket == 'antioxidant':
            antioxidant_actives.append(name)
        else:
            barrier_actives.append(name)

    for ing_name in ingredient_list:
        ing_lower = ing_name.lower()
        if ing_lower in classified_names:
            continue
        data = data_loader.get_ingredient_data(ing_name)
        if not data:
            continue
        func_cat = str(data.get('Functional_Category', '')).lower()
        ing_class = str(data.get('Ingredient_Class', '')).lower()
        if any(kw in ing_lower for kw in ANTIOXIDANT_NAMES) or 'antioxidant' in func_cat:
            antioxidant_actives.append(ing_name)
            classified_names.add(ing_lower)
        elif any(kw in func_cat for kw in BARRIER_FUNC_CATS) or any(kw in ing_class for kw in BARRIER_FUNC_CATS):
            barrier_actives.append(ing_name)
            classified_names.add(ing_lower)

    active_classes = {
        'primary': primary_actives[:8],
        'supporting': supporting_actives[:8],
        'antioxidants': antioxidant_actives[:6],
        'barrier_support': barrier_actives[:6],
    }

    return {
        'score': int(total_score),
        'breakdown': score_breakdown,
        'component_details': component_details,
        'stats': {
            'price_per_ml': round(price_per_ml, 2),
            'category_avg': round(avg_price, 2),
            'vs_average': round(ratio, 1),
            'active_count': len(actives_found),
            'active_ratio': round(active_ratio * 100, 1),
            'price_per_active': round(price / len(actives_found), 2) if actives_found else price
        },
        'tier_badge': get_tier_badge(total_score),
        'score_title': get_score_title(total_score),
        'value_tier': value_tier,
        'ratio': round(ratio, 2),
        'identified_actives': identified_actives,
        'active_classes': active_classes,
        'multipliers_applied': multipliers_applied,
        'price_note': price_note,
        'red_flags': red_flags,
    }


def get_tier_badge(score):
    if score >= 90:
        return "Exceptional Value"
    if score >= 75:
        return "Worth Buying"
    if score >= 60:
        return "Acceptable but Overpriced"
    if score >= 40:
        return "Poor Value"
    return "Marketing-Driven Product"


def get_score_title(score):
    if score >= 90:
        return "Outstanding formulation at fair price"
    if score >= 75:
        return "Solid product with good value"
    if score >= 60:
        return "Good formula, paying brand premium"
    if score >= 40:
        return "Overpriced - alternatives exist"
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

        # Build explanation (max 4 bullets, neutral tone)
        explanation = []
        if present_actives_data:
            if comp_a >= 30:
                explanation.append("Strong clinically supported ingredients present")
            elif comp_a >= 15:
                explanation.append("Some clinically supported ingredients present")
            else:
                explanation.append("Limited active ingredients for this concern")
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
    ingredient_list = parse_ingredients(product_data.get("ingredients", ""))

    # Parse known concentrations from product name (e.g. "10% Niacinamide Serum")
    # and merge with any concentrations scraped from the product page
    product_name = product_data.get("product_name", "") or ""
    known_from_name = _parse_concentrations_from_name(product_name)
    scraped_conc = product_data.get("active_concentrations") or {}  # from product_fetcher
    # scraped_conc takes priority over name-parsed (more precise), name over positional
    known_concentrations = {**known_from_name, **{k.lower(): v for k, v in scraped_conc.items()}}

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
        "disclaimer": "Science-based estimates. Not medical advice."
    }

import re
import math
from data_loader import data_loader, CONCERNS_MAP, CONCERN_INCI_PREFIXES
from config import (
    CATEGORY_AVERAGES, WORTH_MULTIPLIERS, CONCENTRATION_THRESHOLDS,
    CATEGORY_AVERAGES_DEFAULT,
    WORSENING_INGREDIENTS
)


def parse_ingredients(ingredient_list_str):
    if not ingredient_list_str:
        return []
    
    # Strip descriptions inside parentheses if they look like descriptions
    # e.g. "Water (Aqua)" -> "Water", "Glycerin (Humectant)" -> "Glycerin"
    # But keep "Polysorbate 20 (and) ..." or chemical names with parens
    
    # 1. Remove generic description patterns
    cleaned_str = re.sub(r'\s*\((?:active|preservative|solvent|surfactant|emollient|humectant|fragrance|source|function|grade|unbleached|organic|natural|certified)[^)]*\)', '', ingredient_list_str, flags=re.IGNORECASE)
    
    # 2. Remove simple " (Common Name)" if it's just one or two words
    # This is risky for chemical names, so be conservative. 
    # Better strategy: clean individual items after splitting.

    marker = re.search(r'(?:full\s+)?ingred\w*\s*:', cleaned_str, re.IGNORECASE)
    if marker:
        cleaned_str = cleaned_str[marker.end():]
        
    raw_ingredients = [x.strip() for x in cleaned_str.split(',')]
    cleaned = []
    
    for ing in raw_ingredients:
        ing = ing.strip().strip('.')
        if not ing:
            continue
            
        # Remove parentheses content if it seems to be a description
        # e.g. "Aloe Barbadensis (Aloe Vera) Leaf Juice" -> "Aloe Barbadensis Leaf Juice"
        # e.g. "Water (Aqua)" -> "Water"
        
        # Strategy: if paren content is short and looks like a synonym or description
        ing_clean = re.sub(r'\s*\([^)]+\)', '', ing)
        
        # If cleaning resulted in empty string (e.g. ingredient was just "(...)"), keep original
        if not ing_clean.strip():
            ing_clean = ing
            
        ing_clean = ing_clean.strip()

        if len(ing_clean) > 80:
            continue
        if ing_clean.count(' ') > 8:
            continue
        if '.' in ing_clean and len(ing_clean) > 20:
            continue
            
        cleaned.append(ing_clean)
        
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

        # 3. Standard positional fallback
        if one_percent_reached:
            est = 0.3
        else:
            position = i - start_idx
            if position < 3:
                est = 10.0   # top 3 non-water = likely high concentration
            elif position < 6:
                est = 5.0
            elif position < 10:
                est = 2.0
            elif position < 15:
                est = 1.0
            else:
                est = 0.3
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
    """Use Evidence_Factor from the new database directly."""
    try:
        ef = float(data.get('Evidence_Factor', 0.7) or 0.7)
        if math.isnan(ef):
            return 0.7
        return ef
    except (ValueError, TypeError):
        pass
    ev_str = str(data.get('Evidence_Level_Normalized', data.get('Evidence_Strength', ''))).lower()
    if 'strong' in ev_str or 'peer' in ev_str:
        return 1.0
    elif 'limited' in ev_str or 'emerging' in ev_str:
        return 0.4
    return 0.7


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
    """Generate detailed formulation notes listing specific problematic ingredients."""
    notes = []
    for i, ing in enumerate(ingredient_list):
        ing_lower = ing.lower()
        data = data_loader.get_ingredient_data(ing)

        # Comedogenic warnings
        if data:
            try:
                c_rating = float(data.get('Comedogenicity_0_5', 0) or 0)
                if c_rating >= 4:
                    notes.append(f"Contains {ing} (comedogenic rating {int(c_rating)}/5 - highly pore-clogging)")
                elif c_rating >= 3:
                    notes.append(f"Contains {ing} (comedogenic rating {int(c_rating)}/5 - moderately comedogenic)")
            except (ValueError, TypeError):
                pass

        # Irritation risk
        if data:
            irritation = str(data.get('Irritation_Risk', 'Low')).lower()
            if irritation == 'high':
                notes.append(f"Contains {ing} (high irritation risk)")
            elif irritation == 'medium' and i < 10:
                notes.append(f"Contains {ing} (moderate irritation risk)")

        # Specific harmful ingredients
        if 'fragrance' in ing_lower or 'parfum' in ing_lower:
            notes.append(f"Contains {ing} (may irritate sensitive skin, common allergen)")
        elif 'alcohol denat' in ing_lower or 'sd alcohol' in ing_lower:
            notes.append(f"Contains {ing} (can be drying, damages skin barrier with long-term use)")
        elif 'essential oil' in ing_lower:
            notes.append(f"Contains {ing} (potential skin sensitizer)")
        elif 'limonene' in ing_lower or 'linalool' in ing_lower:
            notes.append(f"Contains {ing} (fragrance allergen)")
        elif 'methylparaben' in ing_lower or 'propylparaben' in ing_lower:
            notes.append(f"Contains {ing} (preservative - some concerns about long-term use)")

        # Red flag tags from database
        if data:
            flag = str(data.get('Red_Flag_Tags', '') or '')
            if flag and flag != 'nan':
                allergen_keywords = ['allergen', 'sensitiz', 'barrier damage', 'stinging']
                if any(kw in flag.lower() for kw in allergen_keywords):
                    notes.append(f"Contains {ing}: {flag}")

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
    # Per spec: raw strength per active, diminishing returns, normalize to 45
    DIMINISHING = [1.0, 1.0, 0.70, 0.50, 0.30]
    ACTIVE_NORM_FACTOR = 25  # Calibrated: 2 strong actives ≈ 40/45

    active_contributions = []
    for ing_name in ingredient_list:
        data = data_loader.get_ingredient_data(ing_name)
        if data and str(data.get('Ingredient_Class', '')).lower() == 'active':
            try:
                weight = float(data.get('Effect_Strength_Weight', 0.5) or 0.5)
                if math.isnan(weight):
                    weight = 0.5
            except (ValueError, TypeError):
                weight = 0.5

            conc = concentrations.get(ing_name, 0.3)
            conc_factor = get_concentration_factor(conc, data)
            eq_factor = get_evidence_factor(data)
            raw_strength = weight * conc_factor * eq_factor

            conc_label = "at optimal concentration" if conc_factor >= 1.0 else (
                "at effective concentration" if conc_factor >= 0.7 else "below effective concentration"
            )
            ev_label = "strong" if eq_factor >= 1.0 else ("moderate" if eq_factor >= 0.7 else "limited")

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
                'concentration': conc_label
            })

    active_contributions.sort(key=lambda x: x['strength'], reverse=True)
    weighted_sum = 0
    actives_found = []
    for i, ac in enumerate(active_contributions):
        mult = DIMINISHING[i] if i < len(DIMINISHING) else 0.30
        weighted_sum += ac['strength'] * mult
        actives_found.append(ac['name'])

    active_score = min(45, weighted_sum * ACTIVE_NORM_FACTOR)
    score_breakdown['active_value'] = round(active_score, 1)

    clinical_count = sum(1 for a in active_contributions if a['eq_factor'] >= 0.7)
    component_details['A'].append(f"{len(actives_found)} active ingredient{'s' if len(actives_found) != 1 else ''} with clinical backing" if clinical_count > 0 else "No clinically-backed actives found")
    for ac in active_contributions[:3]:
        component_details['A'].append(f"{ac['name']} {ac['conc_label']} ({ac['ev_label']} evidence)")

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

    if not has_preservative and len(ingredient_list) > 5:
        formula_score -= 8
        component_details['B'].append("No preservative system detected (-8)")

    if has_delivery_system:
        formula_score += 3
        component_details['B'].append("Advanced delivery systems present (+3)")

    formula_score = round(min(20, max(0, formula_score)), 1)
    score_breakdown['formula_quality'] = formula_score

    if not component_details['B']:
        if formula_score >= 15:
            component_details['B'].append("Well-balanced humectant-emollient base")
        elif formula_score >= 10:
            component_details['B'].append("Standard formulation with adequate support")
        else:
            component_details['B'].append("Basic formulation, limited functional support")
    if has_humectant and has_emollient:
        component_details['B'].append("Good humectant-emollient balance")
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

    score_breakdown['price_rationality'] = float(price_score)

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
        'identified_actives': identified_actives,
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


def _score_uv_concern(concern, ingredient_list, concentrations, product_inci_map, product_inci_lower, synergies):
    """Specialized scoring for Sun Protection, UV Damage, and Tanning.
    Uses the UV/Sun/Tanning database with concern-specific Component A splits."""

    # Classify ingredients by their UV roles
    uv_filters = []     # (inci, uv_data, raw_name, conc)
    antioxidants = []    # (inci, uv_data, raw_name, conc)
    melanin_suppressors = []  # (inci, uv_data, raw_name, conc)
    secondary_supporters = []

    role_key = {
        'Sun Protection': 'Sun_Protection_Role',
        'UV Damage': 'UV_Damage_Role',
        'Tanning': 'Tanning_Role',
    }[concern]

    for ing, info in product_inci_map.items():
        inci = info['inci']
        raw = info['raw']
        est_conc = concentrations.get(raw, 0.3)

        # Check UV/Sun/Tanning DB first
        uv_data = data_loader.get_uv_data(inci)
        if not uv_data:
            uv_data = data_loader.get_uv_data(raw)
        if not uv_data:
            continue

        role = str(uv_data.get(role_key, '') or '').strip()
        if not role or role == 'nan':
            continue

        if 'Primary UV Filter' in role or 'Primary UV Block' in role:
            uv_filters.append((inci, uv_data, raw, est_conc))
        elif 'Primary Antioxidant' in role:
            antioxidants.append((inci, uv_data, raw, est_conc))
        elif 'Primary Melanin Suppressor' in role:
            melanin_suppressors.append((inci, uv_data, raw, est_conc))
        else:
            secondary_supporters.append((inci, uv_data, raw, est_conc))

    has_uv_filters = len(uv_filters) > 0
    explanation = []
    conc_info = []

    # --- Classify UV spectrum coverage ---
    has_uva = False
    has_uvb = False
    for inci, uv_data, raw, conc in uv_filters:
        spectrum = str(uv_data.get('UV_Spectrum_Coverage', '') or '').lower()
        if 'broad' in spectrum or ('uva' in spectrum and 'uvb' in spectrum):
            has_uva = True
            has_uvb = True
        elif 'uva' in spectrum:
            has_uva = True
        elif 'uvb' in spectrum:
            has_uvb = True
        filter_type = str(uv_data.get('UV_Filter_Type', '') or '').lower()
        if 'mineral' in filter_type:
            has_uva = True
            has_uvb = True

    # ============================
    # SUN PROTECTION SCORING
    # ============================
    if concern == 'Sun Protection':
        # Component A: 40% UV Filter Coverage + 10% Photostability
        uv_coverage_score = 0
        photostability_score = 0

        if uv_filters:
            filter_strengths = []
            stability_ratings = []
            for inci, uv_data, raw, conc in uv_filters:
                spf_weight = 3.0
                try:
                    spf_weight = float(uv_data.get('Estimated_SPF_Contribution_Weight', 3) or 3)
                    if math.isnan(spf_weight):
                        spf_weight = 3.0
                except (ValueError, TypeError):
                    pass
                conc_factor = min(1.0, conc / 3.0) if conc > 0 else 0.5
                stability = str(uv_data.get('Photostability_Rating', 'Moderate') or 'Moderate').lower()
                stab_mod = 1.1 if 'high' in stability else (1.0 if 'moderate' in stability else 0.8)
                strength = spf_weight * conc_factor * stab_mod
                filter_strengths.append(strength)
                stability_ratings.append(stability)
                conc_info.append(f"{inci}: SPF contribution weight {spf_weight}")

            # Theoretical max = 5 filters at max strength
            theoretical_max = 5 * 5.0 * 1.0 * 1.1
            raw_uv = (sum(filter_strengths) / theoretical_max) * 40
            uv_coverage_score = min(40, raw_uv)

            # Photostability bonus (0-10)
            high_count = sum(1 for s in stability_ratings if 'high' in s)
            if high_count == len(stability_ratings):
                photostability_score = min(10, 8 + len(stability_ratings) * 0.5)
            elif high_count > 0:
                photostability_score = 5 + (high_count / len(stability_ratings)) * 2
            else:
                photostability_score = 2 + len(stability_ratings) * 0.5

            explanation.append(f"{len(uv_filters)} UV filter(s) detected")
            if has_uva and has_uvb:
                explanation.append("Broad spectrum: Both UVA + UVB coverage")
            elif has_uva:
                explanation.append("UVA coverage only - missing UVB protection")
            elif has_uvb:
                explanation.append("UVB coverage only - missing UVA protection")
        else:
            explanation.append("No UV filters found - limited sun protection")

        # Spectrum balance cap
        if has_uva and has_uvb:
            comp_a = uv_coverage_score + photostability_score
        elif has_uva or has_uvb:
            comp_a = min(30, uv_coverage_score + photostability_score)  # cap at 60% of 50
            explanation.append("Score capped: incomplete UV spectrum coverage")
        else:
            comp_a = min(10, uv_coverage_score + photostability_score)  # cap at 20% of 50
            if not uv_filters:
                explanation.append("Score capped at 20%: no UV filters")

        comp_a = min(50, comp_a)

    # ============================
    # UV DAMAGE SCORING
    # ============================
    elif concern == 'UV Damage':
        # Component A: 25% UV Filter + 25% Antioxidant Network
        uv_filter_score = 0
        antioxidant_score = 0

        if uv_filters:
            filter_strengths = []
            for inci, uv_data, raw, conc in uv_filters:
                spf_weight = 3.0
                try:
                    spf_weight = float(uv_data.get('Estimated_SPF_Contribution_Weight', 3) or 3)
                    if math.isnan(spf_weight):
                        spf_weight = 3.0
                except (ValueError, TypeError):
                    pass
                conc_factor = min(1.0, conc / 3.0) if conc > 0 else 0.5
                filter_strengths.append(spf_weight * conc_factor)
            theoretical_max = 5 * 5.0 * 1.0
            uv_filter_score = min(25, (sum(filter_strengths) / theoretical_max) * 25)
            explanation.append(f"{len(uv_filters)} UV filter(s) for damage prevention")
        else:
            explanation.append("No UV filters - UV damage prevention limited")

        if antioxidants:
            antioxidant_strengths = []
            for inci, uv_data, raw, conc in antioxidants:
                ev_factor = 0.7
                try:
                    ef = float(uv_data.get('Evidence_Factor', 0.7) or 0.7)
                    if not math.isnan(ef):
                        ev_factor = ef
                except (ValueError, TypeError):
                    pass
                conc_factor = min(1.0, conc / 1.0) if conc > 0 else 0.5
                # Synergy multiplier (e.g., Vit C + Ferulic + Vit E)
                syn_mult = 1.0
                for syn in synergies:
                    syn_ings = syn['ingredients']
                    if inci.lower() in syn_ings:
                        other = [s for s in syn_ings if s != inci.lower()]
                        if all(o in product_inci_lower for o in other):
                            syn_mult = max(syn_mult, 1.1)
                            break
                antioxidant_strengths.append(ev_factor * conc_factor * syn_mult)
            theoretical_max = 5 * 1.0 * 1.0 * 1.1
            antioxidant_score = min(25, (sum(antioxidant_strengths) / theoretical_max) * 25)
            explanation.append(f"{len(antioxidants)} antioxidant(s) for free radical protection")
            if any(s > 0.7 for s in antioxidant_strengths):
                explanation.append("Strong antioxidant network present")
        else:
            explanation.append("No key antioxidants for UV damage repair")

        comp_a = uv_filter_score + antioxidant_score
        # Cap: no UV filter = max 40%
        if not has_uv_filters:
            comp_a = min(20, comp_a)  # 40% of 50
            explanation.append("Score capped at 40%: no UV filters present")
        comp_a = min(50, comp_a)

    # ============================
    # TANNING SCORING
    # ============================
    elif concern == 'Tanning':
        # Component A: 30% UV Filter + 20% Melanin Suppression
        uv_filter_score = 0
        melanin_score = 0

        if uv_filters:
            filter_strengths = []
            for inci, uv_data, raw, conc in uv_filters:
                spf_weight = 3.0
                try:
                    spf_weight = float(uv_data.get('Estimated_SPF_Contribution_Weight', 3) or 3)
                    if math.isnan(spf_weight):
                        spf_weight = 3.0
                except (ValueError, TypeError):
                    pass
                conc_factor = min(1.0, conc / 3.0) if conc > 0 else 0.5
                filter_strengths.append(spf_weight * conc_factor)
            theoretical_max = 5 * 5.0 * 1.0
            uv_filter_score = min(30, (sum(filter_strengths) / theoretical_max) * 30)
            explanation.append(f"{len(uv_filters)} UV filter(s) blocking melanin-triggering UV")
        else:
            explanation.append("No UV filters - tanning prevention limited")

        if melanin_suppressors:
            melanin_strengths = []
            for inci, uv_data, raw, conc in melanin_suppressors:
                ev_factor = 0.7
                try:
                    ef = float(uv_data.get('Evidence_Factor', 0.7) or 0.7)
                    if not math.isnan(ef):
                        ev_factor = ef
                except (ValueError, TypeError):
                    pass
                conc_factor = min(1.0, conc / 1.0) if conc > 0 else 0.5
                syn_mult = 1.0
                for syn in synergies:
                    syn_ings = syn['ingredients']
                    if inci.lower() in syn_ings:
                        other = [s for s in syn_ings if s != inci.lower()]
                        if all(o in product_inci_lower for o in other):
                            syn_mult = max(syn_mult, 1.1)
                            break
                melanin_strengths.append(ev_factor * conc_factor * syn_mult)
            theoretical_max = 5 * 1.0 * 1.0 * 1.1
            melanin_score = min(20, (sum(melanin_strengths) / theoretical_max) * 20)
            suppressors_names = [inci for inci, _, _, _ in melanin_suppressors]
            explanation.append(f"Melanin suppression: {', '.join(suppressors_names[:3])}")
        else:
            explanation.append("No melanin suppression actives found")

        comp_a = uv_filter_score + melanin_score
        # Cap: no UV filter = max 35%
        if not has_uv_filters:
            comp_a = min(17.5, comp_a)  # 35% of 50
            explanation.append("Score capped at 35%: no UV filters (brightening serums shouldn't score high)")
        comp_a = min(50, comp_a)
    else:
        comp_a = 0

    # --- Component B: Support System Quality (0-20%) ---
    has_barrier = False
    has_anti_inflammatory = False
    has_humectant = False
    has_antioxidant = False
    support_count = len(secondary_supporters) + len(antioxidants)

    for ing, info in product_inci_map.items():
        data = info['data']
        func_cat = str(data.get('Functional_Category', '')).lower()
        ing_class = str(data.get('Ingredient_Class', '')).lower().strip()
        inci_lower = info['inci'].lower()
        if 'humectant' in func_cat or ing_class == 'humectant':
            has_humectant = True
        if any(kw in func_cat for kw in ['anti-inflam', 'soothing', 'calming']):
            has_anti_inflammatory = True
        if any(kw in func_cat for kw in ['antioxidant', 'photoprotect']):
            has_antioxidant = True
        if any(kw in func_cat for kw in ['barrier', 'ceramide', 'lipid', 'emollient', 'occlusive']):
            has_barrier = True
        if any(kw in inci_lower for kw in ['dimethicone', 'silicone', 'acrylate', 'crosspolymer']):
            support_count += 1
        if any(kw in inci_lower for kw in ['centella', 'allantoin', 'panthenol', 'bisabolol']):
            has_anti_inflammatory = True

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

    # --- Component C: Synergy Bonus (0-10%) ---
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
    if synergy_found:
        explanation.append("Beneficial synergy detected between ingredients")

    # --- Component D: Worsening Penalty (max -30%) ---
    comp_d = 0
    worsening_found = []
    ing_str = " ".join(ingredient_list).lower()
    for trigger, penalty in WORSENING_INGREDIENTS.get(concern, []):
        if trigger in ing_str:
            comp_d += penalty
            worsening_found.append(trigger)
    # Position-weighted: high alcohol/fragrance in top 5
    for i, ing in enumerate(ingredient_list[:10]):
        ing_lower = ing.lower()
        if i < 5:
            if any(kw in ing_lower for kw in ['alcohol denat', 'sd alcohol', 'isopropyl alcohol']):
                comp_d -= 5
                worsening_found.append(f"{ing} (alcohol in top 5)")
            if 'fragrance' in ing_lower or 'parfum' in ing_lower:
                comp_d -= 3
                worsening_found.append(f"{ing} (fragrance in top 5)")
    comp_d = max(-30, comp_d)
    if worsening_found:
        explanation.append(f"Worsening: {', '.join(worsening_found[:2])}")

    final = max(0, min(100, comp_a + comp_b + comp_c + comp_d))

    # Build advisory
    present_active_names = ([f for f, _, _, _ in uv_filters] +
                            [f for f, _, _, _ in antioxidants] +
                            [f for f, _, _, _ in melanin_suppressors])
    missing = []
    if concern == 'Sun Protection' and not has_uv_filters:
        missing.append("UV filters (Zinc Oxide, Titanium Dioxide)")
    if concern == 'UV Damage' and not antioxidants:
        missing.append("antioxidants (Vitamin C, Ferulic Acid, Vitamin E)")
    if concern == 'Tanning' and not melanin_suppressors:
        missing.append("melanin suppressors (Alpha Arbutin, Tranexamic Acid)")

    advisory = f"Consider adding {', '.join(missing)} for better {concern.lower()} results." if missing else "Good active coverage for this concern."

    return {
        'score': round(final),
        'present_actives': present_active_names[:5],
        'missing_actives': missing[:3],
        'supporting_ingredients': [f for f, _, _, _ in secondary_supporters[:4]],
        'explanation': explanation[:4],
        'advisory': advisory,
        'synergy_bonus': comp_c,
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
                conc_info.append(f"{info['inci']} at optimal concentration")
            elif conc_factor >= 0.7:
                conc_info.append(f"{info['inci']} within effective range")
            else:
                conc_info.append(f"{info['inci']} may be below effective concentration")

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

            has_oil_ctrl = any(x in ing_str for x in ['niacinamide', 'zinc pca', 'salicylic'])
            has_hydrating = any(x in ing_str for x in ['glycerin', 'sodium hyaluronate', 'hyaluronic'])
            if has_oil_ctrl and has_hydrating:
                score = min(100, int(score * 1.1))
                bonus.append("Balanced formula (oil control + hydration)")
                why_bullets.append("Good balance of oil control and hydration")

            look_for_suggestions = ["Look for lightweight formulas with Niacinamide + Hyaluronic Acid for balanced care."]

        elif skin_type == 'normal':
            if data:
                irritation = str(data.get('Irritation_Risk', 'Low')).lower()
                if 'high' in irritation:
                    score -= 5
                    penalty.append(f"{ing} (High irritation)")
                    why_bullets.append(f"Warning: {ing} has high irritation risk")

            look_for_suggestions = ["Normal skin tolerates most formulations well."]

    score = max(0, min(100, score))

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

    # Generate formulation notes (red flags)
    formulation_notes = detect_formulation_notes(ingredient_list)

    return {
        'score': score,
        'bonus_reasons': list(dict.fromkeys(bonus)),
        'penalty_reasons': list(dict.fromkeys(penalty)),
        'better_suited': better_suited,
        'comedogenic_warnings': list({w['name']: w for w in comedogenic_warnings}.values()),
        'allergen_warnings': list({w['name']: w for w in allergen_warnings}.values()),
        'why_bullets': why_bullets[:4],
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
        },
        "identified_actives": main_score['identified_actives'],
        "skin_concern_fit": concern_dict,
        "am_pm_recommendation": am_pm,
        "skin_type_compatibility": skin_compat['score'],
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

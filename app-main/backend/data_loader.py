import json
import os
import re
import math
import logging
import pandas as pd
from rapidfuzz import process, fuzz

logger = logging.getLogger(__name__)

CONCERN_TAG_MAP = {
    'Acne & Oily Skin': ['acne', 'oily', 'blackheads', 'oil control', 'sebum', 'acne-prone'],
    'Pigmentation': ['pih', 'melasma', 'pigmentation', 'uneven tone', 'post blemish marks', 'brightening'],
    'Aging & Fine Lines': ['aging', 'fine lines', 'wrinkles', 'anti-aging', 'elasticity', 'firming', 'mature skin', 'advanced aging', 'early aging'],
    'Barrier Repair': ['barrier', 'impaired skin barrier', 'barrier damage', 'barrier weakness'],
    'Sensitive Skin': ['sensitive', 'redness', 'rosacea', 'irritation', 'soothing', 'irritated skin'],
    'Hydration': ['dehydration', 'dehydrated skin', 'hydration', 'dryness', 'dry skin', 'dry', 'severely dry skin'],
    'Dry Skin': ['dry skin', 'dryness', 'severely dry skin', 'xerosis', 'flaking', 'flakiness', 'tight skin', 'rough skin', 'dry', 'dehydrated'],
    'Large Pores': ['enlarged pores', 'oily skin'],
    'Dullness': ['dullness', 'dull skin', 'radiance'],
    'Uneven Texture': ['texture', 'exfoliation', 'kp', 'texture improvement'],
    'Dark Circles': ['dark circles', 'under-eye circles', 'eye bags'],
    'Sun Protection': ['uv filter', 'sunscreens', 'sun protection', 'uva protec'],
    'UV Damage': ['photoaging', 'oxidative stress', 'sunburn'],
    'Tanning': ['pigmentation', 'brightening', 'uneven tone', 'pih', 'melasma', 'cosmetic tan'],
    'Puffiness': ['eye bags', 'under-eye circles', 'puffiness'],
    # ── Added: concerns with a genuinely distinct active profile ──────────
    'Post-Inflammatory Hyperpigmentation': ['pih', 'post-inflammatory', 'pigmentation',
                                            'acne marks', 'hyperpigmentation', 'melasma'],
    'Redness & Rosacea':       ['rosacea', 'redness', 'sensitive skin', 'inflammation',
                                'soothing', 'anti-inflammatory'],
    'Blackheads & Congestion': ['acne', 'blackheads', 'congestion', 'pores',
                                'comedones', 'exfoliation'],
    'Loss of Firmness':        ['firmness', 'elasticity', 'aging', 'collagen',
                                'sagging', 'anti-aging'],
    'Eczema-Prone Skin':       ['eczema', 'barrier repair', 'sensitive skin',
                                'atopic', 'soothing'],
    'Hormonal Breakouts':      ['acne', 'hormonal', 'oil control', 'sebum',
                                'anti-acne'],
}

SYNERGY_CONCERN_MAP = {
    'Dehydration': 'Hydration',
}

CONCERNS_MAP = {
    'Acne & Oily Skin':  ['Salicylic Acid', 'Benzoyl Peroxide', 'Azelaic Acid', 'Niacinamide', 'Retinol', 'Zinc PCA'],
    'Pigmentation':      ['Tranexamic Acid', 'Azelaic Acid', 'Alpha Arbutin', 'Niacinamide', 'Ascorbic Acid', 'Kojic Acid'],
    'Aging & Fine Lines': [
        'Retinol', 'Retinal', 'Bakuchiol', 'Ascorbic Acid', 'Glycolic Acid',
        'Palmitoyl Pentapeptide-4', 'Palmitoyl Tripeptide-1', 'Palmitoyl Tetrapeptide-7',
        'Acetyl Hexapeptide-8', 'Copper Tripeptide-1', 'Hexapeptide-11',
        'Palmitoyl Pentapeptide', 'Palmitoyl Tripeptide', 'Palmitoyl Tetrapeptide',
        'Oligopeptide-1', 'Oligopeptide-2', 'Sh-Oligopeptide-1',
    ],
    'Barrier Repair':    [
        'Ceramide NP', 'Ceramide AP', 'Ceramide EOP', 'Ceramide NS', 'Ceramide EOS',
        'Ceramides', 'Fermented Ceramide NP', 'Cholesterol', 'Panthenol', 'Niacinamide',
        'Linoleic Acid', 'Linolenic Acid', 'Palmitic Acid', 'Stearic Acid',
    ],
    'Sensitive Skin':    [
        'Centella Asiatica', 'Centella Asiatica Extract', 'Centella Asiatica Leaf Water',
        'Madecassoside', 'Asiaticoside', 'Madecassic Acid',
        'Panthenol', 'Allantoin', 'Ceramide NP', 'Ceramide AP', 'Ceramides',
    ],
    'Hydration':         ['Sodium Hyaluronate', 'Glycerin', 'Panthenol', 'Sodium PCA', 'Urea'],
    'Dry Skin': [
        'Petrolatum', 'Shea Butter', 'Dimethicone', 'Beeswax',
        'Squalane', 'Caprylic/Capric Triglyceride', 'Cetearyl Alcohol', 'Glyceryl Stearate',
        'Sodium Hyaluronate', 'Glycerin', 'Urea', 'Sodium PCA', 'Panthenol',
        'Ceramide NP', 'Ceramide AP', 'Ceramide EOP', 'Cholesterol', 'Linoleic Acid',
        'Palmitic Acid', 'Stearic Acid',
    ],
    'Large Pores':       ['Niacinamide', 'Salicylic Acid', 'Retinol', 'Glycolic Acid'],
    'Dullness':          [
        # AHAs belong here alongside the brighteners: exfoliation is a primary,
        # evidenced route to radiance. Lactic acid was previously absent even
        # though its own database record lists Dullness.
        'Ascorbic Acid', 'Niacinamide', 'Glycolic Acid', 'Lactic Acid',
        'Mandelic Acid',
        'Glutathione', 'Galactomyces Ferment Filtrate',
        'Alpha Arbutin', 'Arbutin', 'Ascorbyl Glucoside',
        'Glycyrrhiza Glabra Root Extract', 'Dipotassium Glycyrrhizate',
        'Glycyrrhiza Inflata Root Extract', 'Licorice Root', 'Licorice Extract',
    ],
    'Uneven Texture':    ['Glycolic Acid', 'Salicylic Acid', 'Retinol', 'Lactic Acid'],
    'Dark Circles':      [
        'Caffeine', 'Ascorbic Acid', 'Niacinamide', 'Vitamin K', 'Vitamin K1',
        'Palmitoyl Pentapeptide-4', 'Palmitoyl Tetrapeptide-7', 'Acetyl Tetrapeptide-5',
        'Palmitoyl Pentapeptide', 'Palmitoyl Tetrapeptide',
    ],
    'Sun Protection':    ['Zinc Oxide', 'Titanium Dioxide', 'Avobenzone', 'Octinoxate', 'Homosalate', 'Bemotrizinol'],
    'UV Damage':         ['Ferulic Acid', 'Ascorbic Acid', 'Resveratrol', 'Caffeine', 'Glycyrrhiza Glabra Root Extract'],
    # Tan FADING is done with brightening actives AND exfoliants - AHAs
    # accelerate turnover of pigmented corneocytes. UV filters prevent
    # tanning but do nothing to fade one that already happened.
    'Tanning':           ['Alpha Arbutin', 'Kojic Acid', 'Tranexamic Acid', 'Ascorbic Acid', 'Niacinamide', 'Glutathione', 'Glutathione Ethyl Ester', 'Lactic Acid', 'Glycolic Acid', 'Mandelic Acid'],
    'Puffiness':         ['Caffeine', 'Niacinamide', 'Acetyl Tetrapeptide-5', 'Hesperidin Methyl Chalcone', 'Centella Asiatica Extract', 'Centella Asiatica'],
    # ── Added concerns ────────────────────────────────────────────────────
    # Azelaic acid leads PIH and rosacea: it is the best-evidenced option for
    # papulopustular rosacea and works on pigment without hydroquinone's
    # regulatory baggage.
    'Post-Inflammatory Hyperpigmentation': [
        'Azelaic Acid', 'Niacinamide', 'Tranexamic Acid', 'Alpha Arbutin',
        'Ascorbic Acid', 'Retinol', 'Kojic Acid', 'Glycolic Acid', 'Lactic Acid'],
    'Redness & Rosacea': [
        'Azelaic Acid', 'Niacinamide', 'Centella Asiatica', 'Madecassoside',
        'Allantoin', 'Bisabolol', 'Panthenol', 'Green Tea Extract'],
    'Blackheads & Congestion': [
        'Salicylic Acid', 'Retinol', 'Retinal', 'Adapalene', 'Niacinamide',
        'Zinc PCA', 'Mandelic Acid', 'Azelaic Acid'],
    'Loss of Firmness': [
        'Retinol', 'Retinal', 'Palmitoyl Pentapeptide-4', 'Palmitoyl Tripeptide-1',
        'Ascorbic Acid', 'Bakuchiol', 'Niacinamide', 'Peptides'],
    'Eczema-Prone Skin': [
        'Ceramide NP', 'Cholesterol', 'Colloidal Oatmeal', 'Panthenol',
        'Glycerin', 'Allantoin', 'Bisabolol', 'Squalane', 'Niacinamide'],
    'Hormonal Breakouts': [
        'Azelaic Acid', 'Salicylic Acid', 'Niacinamide', 'Retinol',
        'Zinc PCA', 'Benzoyl Peroxide'],
}

CONCERN_INCI_PREFIXES = {
    'Acne & Oily Skin':   [],
    'Aging & Fine Lines': ['Palmitoyl', 'Acetyl Hex', 'Oligopeptide', 'Copper Tripeptide', 'Hexapeptide', 'Sh-Oligopeptide'],
    'Barrier Repair':     ['Ceramide'],
    'Sensitive Skin':     ['Ceramide', 'Centella Asiatica', 'Madecass'],
    'Dark Circles':       ['Palmitoyl', 'Acetyl Tetrapeptide'],
    'Puffiness':          ['Acetyl Tetrapeptide', 'Centella Asiatica'],
    'Dry Skin':           ['Ceramide'],
}

_INGREDIENT_ALIASES = {
    "vitamin e": "tocopherol", "vit e": "tocopherol",
    "vitamin b3": "niacinamide", "vit b3": "niacinamide",
    "vitamin b5": "panthenol", "pro-vitamin b5": "panthenol",
    "provitamin b5": "panthenol", "pro vitamin b5": "panthenol",
    "vitamin c": "ascorbic acid", "vit c": "ascorbic acid",
    "vitamin a": "retinol", "vit a": "retinol",
    "vitamin k": "phytonadione", "vitamin k1": "phytonadione",
    "dl-alpha-tocopherol": "tocopherol", "alpha-tocopherol": "tocopherol",
    "l-ascorbic acid": "ascorbic acid",
    "ha": "sodium hyaluronate",
    "bha": "salicylic acid", "pha": "gluconolactone",
    "hyaluronic acid": "sodium hyaluronate",
    "retin-a": "tretinoin", "retinaldehyde": "retinal",
    "argireline": "acetyl hexapeptide-8",
    "matrixyl": "palmitoyl pentapeptide-4",
    "coenzyme q10": "ubiquinone", "q10": "ubiquinone",
    "ectoin": "ectoine", "beta glucan": "beta-glucan",
    "licorice": "glycyrrhiza glabra root extract",
    "licorice extract": "glycyrrhiza glabra root extract",
    # PDRN is polydeoxyribonucleotide. Labels often print the parent
    # molecule, deoxyribonucleic acid, instead of the trade name.
    # Sodium DNA stays its own record.
    "deoxyribonucleic acid": "pdrn",
    "dna": "pdrn",
    "polydeoxyribonucleotide": "pdrn",
}

def _technology_target(normalized):
    """Map a delivery-technology name onto its record before fuzzy matching.

    'Centella Asiatica Leaf Vesicles' shares every token of centella extract,
    and 'Hydrolyzed Sponge' shares 'hydrolyzed' with hyaluronate, so the
    fuzzy step would score them as the wrong ingredient. An empty string
    means the name is known to be something else and must stay unmatched.
    """
    n = normalized or ''
    if 'fruit juice vesicle' in n:
        return None
    if any(k in n for k in ('hydrolyzed sponge', 'reedle', 'spicule')):
        return 'spicules'
    if n in ('milt extract', 'salmon milt extract'):
        return ''
    if any(k in n for k in ('exosome', 'extracellular vesicle', 'leaf vesicle')):
        return 'exosomes'
    return None


def _protected_tokens(text):
    words = set(re.findall(r'[a-z0-9]+', text or ''))
    return words & {
        'vesicle', 'vesicles', 'exosome', 'exosomes', 'extracellular',
        'sponge', 'reedle', 'milt',
    }


_CANONICAL_LOOKUP = {
    # Shorthand rows exist beside the real INCI. Resolve these before the
    # exact key, and do not delete the rows. BHA is not in this map.
    'hpr': 'hydroxypinacolone retinoate',
    'vitamin c': 'ascorbic acid',
    'l-ascorbic acid': 'ascorbic acid',
    'hyaluronic acid': 'sodium hyaluronate',
    'ha': 'sodium hyaluronate',
    'avobenzone': 'butyl methoxydibenzoylmethane',
    'octinoxate': 'ethylhexyl methoxycinnamate',
    'octyl methoxycinnamate': 'ethylhexyl methoxycinnamate',
    'omc': 'ethylhexyl methoxycinnamate',
    'retinaldehyde': 'retinal',
    'alpha arbutin': 'alpha-arbutin',
    'centella extract': 'centella asiatica extract',
    'cica': 'centella asiatica extract',
    'parfum': 'fragrance',
    'perfume': 'fragrance',
    'aroma': 'fragrance',
    # CIR retired this INCI: it was palmitoyl tripeptide-1 or palmitoyl hexapeptide-12.
    'palmitoyl oligopeptide': 'palmitoyl tripeptide-1',
}


def _significant_extra_tokens(query, matched):
    """Tokens the matched record adds that the query never said.

    Ethyl linoleate shares linoleate with retinyl linoleate. The extra
    retinyl is a different molecule. A longer query may still match the
    shorter record (centella leaf extract → centella extract).
    """
    query_tokens = set(re.findall(r'[a-z0-9]+', query or ''))
    match_tokens = set(re.findall(r'[a-z0-9]+', matched or ''))
    return {
        token for token in (match_tokens - query_tokens)
        if len(token) > 2 and not token.isdigit()
    }


def _trailing_number_conflict(query, matched):
    """True when the only material difference is a trailing number (3 vs 9)."""
    def parts(text):
        tokens = re.findall(r'[a-z0-9]+', (text or '').lower())
        if len(tokens) >= 2 and tokens[-1].isdigit():
            return tokens[:-1], tokens[-1]
        return tokens, None

    query_base, query_num = parts(query)
    match_base, match_num = parts(matched)
    return bool(
        query_num and match_num and query_num != match_num and query_base == match_base
    )


_INGREDIENT_FAMILY_MAP = {
    "hydrolyzed hyaluronic acid": "sodium hyaluronate",
    "sodium hyaluronate crosspolymer": "sodium hyaluronate",
    "hyaluronic acid crosspolymer": "sodium hyaluronate",
    "retinyl palmitate": "retinol", "retinyl acetate": "retinol",
    "retinyl propionate": "retinol",
    "ceramide 1": "ceramide eop", "ceramide 2": "ceramide np",
    "ceramide 3": "ceramide np", "ceramide 6 ii": "ceramide ap",
    "palmitoyl pentapeptide": "palmitoyl pentapeptide-4",
    "palmitoyl tripeptide": "palmitoyl tripeptide-1",
    "palmitoyl tetrapeptide": "palmitoyl tetrapeptide-7",
    "alpha hydroxy acid": "glycolic acid",
    "nicotinamide": "niacinamide", "nicotinic acid amide": "niacinamide",
}


def _parse_skin_concerns(raw):
    """Parse Skin_Concerns from a JSON entry (already pre-parsed on load)."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return raw.get('_skin_concerns_parsed', [])
    if not raw or str(raw).lower() in ('nan', 'none', ''):
        return []
    return [t.strip().lower() for t in str(raw).split(';') if t.strip()]


class DataLoader:
    def __init__(self, database_path=None):
        if database_path is None:
            database_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database')
        self.database_path = database_path
        # JSON-backed ingredient store — O(1) key lookup
        self._json_db = {}          # inci_lower -> entry dict
        self._json_aliases = {}     # alias_lower -> inci_lower
        # Keep ingredient_master as None (no longer a DataFrame for main DB)
        self.ingredient_master = None
        self.active_upgrade_map = None
        self.ingredient_lookup = {}  # unified lookup: inci + aliases
        self.all_inci_names = []
        self.concern_actives = {}
        self.concern_supporters = {}
        self.synergy_registry = {}
        self.synergy_partners_map = {}
        self.uv_sun_db = {}
        self.surfactant_db = {}
        self.role_weight_table = {}
        self.role_sets = {}
        self.load_data()

    def load_data(self):
        # ── Load ingredients.json (replaces ingredient_database_fixed5.csv) ──
        json_path = os.path.join(self.database_path, 'ingredients.json')
        if os.path.exists(json_path):
            self._load_json_db(json_path)
        else:
            # Fallback: try old CSV if JSON not present yet
            self._load_csv_fallback()

        try:
            upgrade_path = os.path.join(self.database_path, 'active_upgrade_map.csv')
            if os.path.exists(upgrade_path):
                self.active_upgrade_map = pd.read_csv(upgrade_path)
        except Exception as e:
            logger.error(f"Error loading upgrade map: {e}")

        # Load extra aliases from aliases.json
        try:
            aliases_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aliases.json')
            if os.path.exists(aliases_path):
                with open(aliases_path, 'r') as f:
                    extra_aliases = json.load(f)
                added = 0
                for alias_key, target_inci in extra_aliases.items():
                    alias_lower = alias_key.strip().lower()
                    target_lower = target_inci.strip().lower()
                    if target_lower in self.ingredient_lookup and alias_lower not in self.ingredient_lookup:
                        self.ingredient_lookup[alias_lower] = self.ingredient_lookup[target_lower]
                        added += 1
                logger.info(f"Loaded {added} extra aliases from aliases.json")
        except Exception as e:
            logger.warning(f"Could not load aliases.json: {e}")

        self._build_concern_maps()
        self._load_synergy_registry()
        self._load_uv_sun_tanning_db()
        self._load_surfactant_db()
        self._load_role_weight_table()
        self._build_role_sets()

    def _load_json_db(self, json_path):
        """Load ingredients.json — main ingredient database."""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._json_db = data.get('ingredients', {})
            self._json_aliases = data.get('aliases', {})

            # Populate ingredient_lookup (unified O(1) store)
            for key, entry in self._json_db.items():
                self.ingredient_lookup[key] = entry
                inci_name = entry.get('INCI_Name', '')
                if inci_name:
                    self.all_inci_names.append(inci_name)

            # Register aliases: alias_lower -> same entry as their canonical INCI
            for alias_lower, inci_lower in self._json_aliases.items():
                if inci_lower in self.ingredient_lookup and alias_lower not in self.ingredient_lookup:
                    self.ingredient_lookup[alias_lower] = self.ingredient_lookup[inci_lower]

            logger.info(f"Loaded {len(self._json_db)} ingredients from ingredients.json "
                        f"({len(self._json_aliases)} aliases registered)")
        except Exception as e:
            logger.error(f"Error loading ingredients.json: {e}")

    def _load_csv_fallback(self):
        """Fallback loader for old CSV — used only if ingredients.json not found."""
        import csv as _csv
        csv_path = os.path.join(self.database_path, 'ingredient_database_fixed5.csv')
        if not os.path.exists(csv_path):
            logger.error("Neither ingredients.json nor ingredient_database_fixed5.csv found")
            return
        try:
            with open(csv_path, encoding='utf-8-sig') as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    inci = row.get('INCI_Name', '').strip()
                    if not inci or inci == 'nan':
                        continue
                    entry = dict(row)
                    # Pre-compute same fields as JSON builder does
                    atw = entry.get('Activity_Tier_Weight', '')
                    try:
                        entry['_activity_tier_weight'] = float(atw) if str(atw).strip() not in ('', 'nan') else 0.5
                    except (ValueError, TypeError):
                        entry['_activity_tier_weight'] = 0.5
                    mw = entry.get('MW_Daltons', '')
                    try:
                        entry['_mw_daltons'] = float(mw) if str(mw).strip() not in ('', 'nan') else None
                    except (ValueError, TypeError):
                        entry['_mw_daltons'] = None
                    moa = str(entry.get('Mechanism_of_Action', '') or '').strip()
                    if not moa or moa.lower() in ('nan', 'none', ''):
                        moa = str(entry.get('Biological_Action', '') or '').strip()
                    entry['_moa'] = moa if moa and moa.lower() not in ('nan', 'none') else None
                    sc_raw = entry.get('Skin_Concerns', '')
                    entry['_skin_concerns_parsed'] = (
                        [t.strip().lower() for t in str(sc_raw).split(';') if t.strip()]
                        if sc_raw and str(sc_raw).lower() not in ('nan', '') else []
                    )
                    key = inci.lower()
                    self.ingredient_lookup[key] = entry
                    self.all_inci_names.append(inci)
                    aliases_col = str(entry.get('Aliases', '') or '')
                    if aliases_col and aliases_col not in ('nan', ''):
                        for alias in aliases_col.split(';'):
                            alias = alias.strip()
                            if alias and alias.lower() not in self.ingredient_lookup:
                                self.ingredient_lookup[alias.lower()] = entry
            logger.info(f"Fallback: loaded {len(self.all_inci_names)} ingredients from CSV")
        except Exception as e:
            logger.error(f"CSV fallback failed: {e}")

    def _add_synergy_pair(self, ing1, ing2, seen_pairs, all_synergies):
        pair_key = tuple(sorted([ing1, ing2]))
        if pair_key not in seen_pairs:
            seen_pairs.add(pair_key)
            all_synergies.append({
                'ingredients': [ing1, ing2],
                'bonus': 2,
                'type': 'synergy',
                'mechanism': f"{ing1.title()} + {ing2.title()} synergy",
            })
        if ing1 not in self.synergy_partners_map:
            self.synergy_partners_map[ing1] = set()
        self.synergy_partners_map[ing1].add(ing2)
        if ing2 not in self.synergy_partners_map:
            self.synergy_partners_map[ing2] = set()
        self.synergy_partners_map[ing2].add(ing1)

    def _load_synergy_registry(self):
        """Load synergy pairs from synergy table CSV AND main JSON DB's Synergistic_Ingredients."""
        try:
            seen_pairs = set()
            all_synergies = []

            # Source 1: dedicated synergy table CSV
            syn_path = os.path.join(self.database_path, 'ingredient_synergy_table.csv')
            if os.path.exists(syn_path):
                df = pd.read_csv(syn_path)
                for _, row in df.iterrows():
                    ing1 = str(row.get('INCI_Name', '')).strip().lower()
                    partners_raw = str(row.get('Synergistic_Ingredients', ''))
                    if not ing1 or ing1 == 'nan' or partners_raw == 'nan':
                        continue
                    for ing2 in [p.strip().lower() for p in partners_raw.split(';') if p.strip()]:
                        self._add_synergy_pair(ing1, ing2, seen_pairs, all_synergies)

            # Source 2: Synergistic_Ingredients column in JSON DB
            for entry in self._json_db.values():
                ing1 = str(entry.get('INCI_Name', '')).strip().lower()
                partners_raw = str(entry.get('Synergistic_Ingredients', '') or '')
                if not ing1 or ing1 == 'nan' or partners_raw in ('nan', ''):
                    continue
                for ing2 in [p.strip().lower() for p in partners_raw.split(';') if p.strip()]:
                    self._add_synergy_pair(ing1, ing2, seen_pairs, all_synergies)

            self.synergy_registry['__all__'] = all_synergies
            logger.info(f"Loaded {len(all_synergies)} synergy pairs, {len(self.synergy_partners_map)} mapped ingredients")
        except Exception as e:
            logger.error(f"Error loading synergy registry: {e}")

    def _build_concern_maps(self):
        """Build concern_actives and concern_supporters from JSON DB."""
        if not self._json_db:
            return
        for concern, tags in CONCERN_TAG_MAP.items():
            db_actives = []
            supporters = []
            for entry in self._json_db.values():
                inci = str(entry.get('INCI_Name', '')).strip()
                if not inci or inci == 'nan':
                    continue
                skin_concerns = entry.get('_skin_concerns_parsed', [])
                if any(tag in sc for tag in tags for sc in skin_concerns):
                    ing_class = str(entry.get('Ingredient_Class', '')).lower().strip()
                    if ing_class == 'active':
                        try:
                            ef = float(entry.get('Evidence_Factor', 0.4) or 0.4)
                            esw_raw = entry.get('Effect_Strength_Weight', '')
                            if str(esw_raw).strip() in ('', 'nan', '0'):
                                func_cat = str(entry.get('Functional_Category', '')).lower()
                                esw = 1.0 if 'humectant' in func_cat else 0.5
                            else:
                                esw = float(esw_raw)
                        except (ValueError, TypeError):
                            ef, esw = 0.4, 0.5
                        if math.isnan(ef): ef = 0.4
                        if math.isnan(esw): esw = 0.5
                        db_actives.append((inci, ef * esw))
                    elif ing_class in ('functional', 'functional support', 'antioxidant support'):
                        supporters.append(inci)

            db_actives.sort(key=lambda x: x[1], reverse=True)
            top_db_names = [name for name, _ in db_actives[:8]]
            curated = CONCERNS_MAP.get(concern, [])
            merged = list(curated)
            for name in top_db_names:
                if name not in merged:
                    merged.append(name)
            self.concern_actives[concern] = merged[:16]
            extra_actives = [name for name, _ in db_actives[8:]]
            self.concern_supporters[concern] = list(set(supporters + extra_actives))
            logger.info(f"  {concern}: {len(self.concern_actives[concern])} ideal actives")

    @staticmethod
    def _uv_filter_common_aliases(common):
        """Exact trade-name pieces from a UV Common_Name.

        A slash or semicolon separates two names. A trailing parenthetical
        that is not a nano marker is also stored without that note, so
        'Tinosorb A2B (BASF)' resolves as Tinosorb A2B. '(nano)' is never
        removed: the nano filter and the non-nano filter stay different keys.
        """
        text = str(common or "").strip()
        if not text or text.lower() == "nan":
            return []
        names = []
        for part in re.split(r"\s*[/;]\s*", text):
            part = part.strip()
            if not part:
                continue
            names.append(part)
            match = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", part)
            if not match or "nano" in match.group(2).lower():
                continue
            base = match.group(1).strip()
            if base:
                names.append(base)
        return names

    def _load_uv_sun_tanning_db(self):
        INCI_ALIASES = {
            'bemotrizinol': 'Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine',
            'bisoctrizole': 'Methylene Bis-Benzotriazolyl Tetramethylbutylphenol',
            'avobenzone': 'Butyl Methoxydibenzoylmethane',
            'octinoxate': 'Ethylhexyl Methoxycinnamate',
            'octisalate': 'Ethylhexyl Salicylate',
            'ensulizole': 'Phenylbenzimidazole Sulfonic Acid',
            'ecamsule': 'Terephthalylidene Dicamphor Sulfonic Acid',
            'benzophenone-3': 'Oxybenzone',
            'benzophenone-4': 'Sulisobenzone',
            'tinosorb s': 'Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine',
            'tinosorb m': 'Methylene Bis-Benzotriazolyl Tetramethylbutylphenol',
            'uvinul a plus': 'Diethylamino Hydroxybenzoyl Hexyl Benzoate',
            'uvinul t 150': 'Ethylhexyl Triazone',
        }
        try:
            uv_path = os.path.join(self.database_path, 'uv_sunscreen_tanning_database.csv')
            if not os.path.exists(uv_path):
                logger.warning("uv_sunscreen_tanning_database.csv not found")
                return
            df = pd.read_csv(uv_path)
            df.columns = df.columns.str.strip()
            count = 0
            common_name_claims = []
            for _, row in df.iterrows():
                inci = str(row.get('INCI_Name', '')).strip()
                if not inci or inci == 'nan':
                    continue
                entry = row.to_dict()
                for k, v in entry.items():
                    if pd.isna(v):
                        entry[k] = ''
                self.uv_sun_db[inci.lower()] = entry
                count += 1
                category = str(entry.get('Ingredient_Category') or '').lower()
                # Shadowed rows (bemotrizinol, bisoctrizole) are not sources
                # for trade names. Their Common_Name text mislabels the filter.
                if 'uv filter' not in category or inci.lower() in INCI_ALIASES:
                    continue
                for name in self._uv_filter_common_aliases(entry.get('Common_Name')):
                    common_name_claims.append((name.lower(), inci.lower()))
            for alias_lower, canonical_inci in INCI_ALIASES.items():
                canonical_key = canonical_inci.lower()
                if canonical_key in self.uv_sun_db:
                    # Override a same-named row. Bemotrizinol is stored as its
                    # own filter and must point at Tinosorb S, not that row.
                    self.uv_sun_db[alias_lower] = self.uv_sun_db[canonical_key]
            owners = {}
            for alias_lower, inci_lower in common_name_claims:
                owners.setdefault(alias_lower, set()).add(inci_lower)
            for alias_lower, incis in owners.items():
                # Exact only. An existing key wins, so Benzophenone-3 stays
                # Oxybenzone and a shared name is not guessed.
                if len(incis) != 1 or alias_lower in self.uv_sun_db:
                    continue
                target = self.uv_sun_db.get(next(iter(incis)))
                if target:
                    self.uv_sun_db[alias_lower] = target
            logger.info(f"Loaded {count} UV/sunscreen ingredients")
        except Exception as e:
            logger.error(f"Error loading UV sunscreen DB: {e}")

    def _build_role_sets(self):
        active_classes = {
            'active', 'peptide', 'retinoid', 'brightening active', 'ferment',
            'antioxidant', 'humectant', 'emollient', 'barrier', 'plant oil',
            'emollient ester', 'botanical extract', 'botanical', 'delivery system', 'delivery',
        }
        sets = {
            'active': set(), 'humectant': set(), 'barrier': set(),
            'soothing': set(), 'emollient': set(), 'occlusive': set(),
            'antioxidant': set(), 'preservative': set(), 'surfactant': set(),
            'exfoliant': set(), 'peptide': set(), 'filler': set(),
            'dry_oil': set(), 'brightening': set(), 'anti_acne': set(),
            'anti_aging': set(), 'uv_filter': set(), 'delivery': set(),
        }
        for entry in self._json_db.values():
            inci = str(entry.get('INCI_Name', '')).strip()
            if not inci or inci == 'nan':
                continue
            key = inci.lower()
            cls = str(entry.get('Ingredient_Class', '')).lower().strip()
            fc  = str(entry.get('Functional_Category', '')).lower()
            pb  = str(entry.get('Primary_Benefits', '')).lower()
            sc  = str(entry.get('Skin_Concerns', '')).lower()

            if cls in active_classes or any(x in fc for x in ['active', 'antioxidant',
               'brightening', 'anti-acne', 'anti-aging', 'anti-wrinkle', 'peptide',
               'exfoliant', 'repair', 'retinoid', 'depigmenting', 'soothing']):
                sets['active'].add(key)
            if (cls == 'humectant' or 'humectant' in fc or 'humectant' in pb
                    or 'hydration' in fc or 'water-binding' in pb or 'hygroscopic' in pb
                    or ('hydration' in sc and 'emollient' not in fc and 'oil' not in fc)):
                sets['humectant'].add(key)
            if (cls == 'barrier' or any(x in fc for x in ['barrier', 'ceramide',
                    'barrier lipid', 'barrier repair', 'barrier support', 'lipid',
                    'sphingosine', 'phytosphingosine'])
                    or any(x in pb for x in ['barrier', 'ceramide', 'lipid replenish'])):
                sets['barrier'].add(key)
            if any(x in fc for x in ['soothing', 'anti-inflammatory', 'calming', 'skin calming', 'redness']):
                sets['soothing'].add(key)
            if any(x in pb for x in ['soothing', 'anti-inflammatory', 'calming', 'reduces redness', 'calms']):
                sets['soothing'].add(key)
            if (cls in ('emollient', 'plant oil', 'emollient ester')
                    or any(x in fc for x in ['emollient', 'skin conditioning', 'conditioning', 'softening'])):
                sets['emollient'].add(key)
            if 'occlusive' in fc or 'occlusive' in pb:
                sets['occlusive'].add(key)
            if any(x in fc for x in ['dry oil', 'lightweight oil', 'non-comedogenic oil']) and 'occlusive' not in fc:
                sets['dry_oil'].add(key)
            if cls == 'antioxidant' or 'antioxidant' in fc or 'antioxidant' in pb or 'free radical' in pb:
                sets['antioxidant'].add(key)
            if cls == 'preservative' or 'preservative' in fc:
                sets['preservative'].add(key)
            if cls == 'surfactant' or any(x in fc for x in ['surfactant', 'mild surfactant', 'cleansing', 'foaming']):
                sets['surfactant'].add(key)
            if 'exfoliant' in fc or 'exfoliat' in pb or any(x in key for x in
                    ['glycolic', 'lactic', 'mandelic', 'salicylic', 'gluconolactone',
                     'malic acid', 'tartaric', 'citric acid', 'papain', 'bromelain']):
                sets['exfoliant'].add(key)
            if cls == 'peptide' or 'peptide' in fc or 'peptide' in key:
                sets['peptide'].add(key)
            if cls == 'filler' or any(x in fc for x in ['solvent', 'thickener', 'gel former',
                    'polymer', 'film former', 'viscosity', 'chelating', 'colorant', 'fragrance']):
                sets['filler'].add(key)
            if any(x in fc for x in ['brightening', 'depigmenting', 'lightening']):
                sets['brightening'].add(key)
            if ('anti-acne' in fc or 'anti-acne' in pb or 'antimicrobial' in fc
                    or 'acne' in sc or 'sebum' in fc or 'oil control' in fc or 'sebum' in pb):
                sets['anti_acne'].add(key)
            if any(x in fc for x in ['anti-aging', 'anti-wrinkle', 'anti-ageing', 'firming', 'collagen']):
                sets['anti_aging'].add(key)
            if cls in ('organic uv filter', 'mineral uv filter') or 'uv filter' in fc:
                sets['uv_filter'].add(key)
            if (cls in ('delivery system', 'delivery')
                    or any(x in fc for x in ['liposomal', 'encapsulated', 'nano', 'cyclodextrin', 'microsphere'])):
                sets['delivery'].add(key)
        self.role_sets = sets

    # ── Column accessors (unchanged public API) ──────────────────────────────

    def get_activity_tier_weight(self, ingredient_data):
        if not ingredient_data:
            return 0.5
        return ingredient_data.get('_activity_tier_weight', 0.5)

    def get_mw_daltons(self, ingredient_data):
        if not ingredient_data:
            return None
        return ingredient_data.get('_mw_daltons', None)

    def get_moa(self, ingredient_data):
        if not ingredient_data:
            return None
        text = ingredient_data.get('_moa', None)
        if not text:
            return None
        if re.search(r'superstar|holy grail|miracle ingredient|game-?changer',
                     str(text), re.I):
            return None
        return text

    def get_activity_tier_label(self, ingredient_data):
        if not ingredient_data:
            return None
        tier = str(ingredient_data.get('Activity_Tier', '') or '').strip()
        return tier if tier and tier.lower() not in ('nan', 'none', '') else None

    def get_concern_actives(self, concern):
        return self.concern_actives.get(concern, [])

    def get_concern_supporters(self, concern):
        return self.concern_supporters.get(concern, [])
    def get_synergies(self, concern):
        return self.synergy_registry.get(concern, [])

    @staticmethod
    def _normalize_ingredient(name):
        n = name.strip().lower()
        n = re.sub(r'[^\w\s]', ' ', n)
        n = re.sub(r'\s+', ' ', n).strip()
        return n

    def get_uv_data(self, ingredient_name):
        if not ingredient_name:
            return None
        key = ingredient_name.strip().lower()
        if key in self.uv_sun_db:
            return self.uv_sun_db[key]
        normalized = self._normalize_ingredient(ingredient_name)
        if normalized in self.uv_sun_db:
            return self.uv_sun_db[normalized]
        matches = process.extract(
            normalized,
            list(self.uv_sun_db.keys()),
            scorer=fuzz.token_set_ratio,
            score_cutoff=85,
            limit=5,
        ) or []
        for matched, _score, _idx in matches:
            if _trailing_number_conflict(normalized, matched):
                continue
            return self.uv_sun_db[matched]
        return None

    def get_ingredient_data(self, ingredient_name):
        if not ingredient_name:
            return None
        key = ingredient_name.strip().lower()
        key = re.sub(r'\([^)]*\)', '', key)
        key = re.sub(r'\d+\.?\d*\s*%', '', key)
        key = re.sub(r'\s+', ' ', key).strip()

        # A few shorthand rows sit beside the real INCI. Those names resolve
        # to the canonical record before the exact key can win.
        canon = _CANONICAL_LOOKUP.get(key)
        if canon and canon in self.ingredient_lookup:
            return self.ingredient_lookup[canon]

        # O(1) JSON dict lookup
        if key in self.ingredient_lookup:
            return self.ingredient_lookup[key]
        aliased = _INGREDIENT_ALIASES.get(key)
        if aliased:
            result = self.ingredient_lookup.get(aliased)
            if result:
                return result
        familied = _INGREDIENT_FAMILY_MAP.get(key)
        if familied:
            result = self.ingredient_lookup.get(familied)
            if result:
                return result
        normalized = self._normalize_ingredient(key)
        if normalized in self.ingredient_lookup:
            return self.ingredient_lookup[normalized]
        aliased_norm = _INGREDIENT_ALIASES.get(normalized)
        if aliased_norm and aliased_norm in self.ingredient_lookup:
            return self.ingredient_lookup[aliased_norm]
        familied_norm = _INGREDIENT_FAMILY_MAP.get(normalized)
        if familied_norm and familied_norm in self.ingredient_lookup:
            return self.ingredient_lookup[familied_norm]
        tech = _technology_target(normalized)
        if tech == '':
            return None
        if tech and tech in self.ingredient_lookup:
            return self.ingredient_lookup[tech]
        # Fuzzy fallback (same threshold as before). A longer name that adds
        # vesicle, sponge, or milt is not the shorter ingredient it contains.
        matches = process.extract(
            normalized,
            list(self.ingredient_lookup.keys()),
            scorer=fuzz.token_set_ratio,
            score_cutoff=85,
            limit=8,
        ) or []
        for matched, _score, _idx in matches:
            if _protected_tokens(normalized) - _protected_tokens(matched):
                continue
            if _significant_extra_tokens(normalized, matched):
                continue
            return self.ingredient_lookup[matched]
        return None

    def _load_surfactant_db(self):
        try:
            path = os.path.join(self.database_path, 'surfactant_database.csv')
            if not os.path.exists(path):
                return
            df = pd.read_csv(path)
            df.columns = df.columns.str.strip()
            for _, row in df.iterrows():
                inci = str(row.get('INCI_Name', '')).strip()
                if inci and inci != 'nan':
                    entry = row.to_dict()
                    for k, v in entry.items():
                        if isinstance(v, float) and pd.isna(v):
                            entry[k] = ''
                    self.surfactant_db[inci.lower()] = entry
            logger.info(f"Loaded {len(self.surfactant_db)} surfactants")
        except Exception as e:
            logger.error(f"Error loading surfactant DB: {e}")

    def _load_role_weight_table(self):
        try:
            path = os.path.join(self.database_path, 'ingredient_role_weight_table.csv')
            if not os.path.exists(path):
                return
            df = pd.read_csv(path)
            df.columns = df.columns.str.strip()
            for _, row in df.iterrows():
                role = str(row.get('Role', '')).strip().lower()
                if role and role != 'nan':
                    try:
                        self.role_weight_table[role] = float(row.get('Role_Weight', 3.0))
                    except (ValueError, TypeError):
                        pass
            logger.info(f"Loaded {len(self.role_weight_table)} role weights")
        except Exception as e:
            logger.error(f"Error loading role weight table: {e}")

    def get_surfactant_data(self, ingredient_name):
        if not ingredient_name:
            return None
        key = ingredient_name.strip().lower()
        if key in self.surfactant_db:
            return self.surfactant_db[key]
        return self.surfactant_db.get(self._normalize_ingredient(ingredient_name))

    def get_synergy_partners(self, ingredient_name):
        if not ingredient_name:
            return set()
        return self.synergy_partners_map.get(ingredient_name.strip().lower(), set())

    def is_loaded(self):
        return len(self.ingredient_lookup) > 0


data_loader = DataLoader()

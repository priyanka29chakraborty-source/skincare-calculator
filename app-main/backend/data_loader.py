import pandas as pd
import os
import re
import math
import logging
from rapidfuzz import process, fuzz

logger = logging.getLogger(__name__)

# Maps user-facing concern names → DB Skin_Concerns tags
CONCERN_TAG_MAP = {
    'Acne & Oily Skin': ['acne', 'oily', 'blackheads', 'oil control', 'sebum', 'acne-prone'],
    'Pigmentation': ['pih', 'melasma', 'pigmentation', 'uneven tone', 'post blemish marks', 'brightening'],
    'Aging & Fine Lines': ['aging', 'fine lines', 'wrinkles', 'anti-aging', 'elasticity', 'firming', 'mature skin', 'advanced aging', 'early aging'],
    'Barrier Repair': ['barrier', 'impaired skin barrier', 'barrier damage', 'barrier weakness'],
    'Sensitive Skin': ['sensitive', 'redness', 'rosacea', 'irritation', 'soothing', 'irritated skin'],
    'Hydration': ['dehydration', 'dehydrated skin', 'hydration', 'dryness', 'dry skin', 'dry', 'severely dry skin'],
    'Large Pores': ['enlarged pores', 'oily skin'],
    'Dullness': ['dullness', 'dull skin', 'radiance'],
    'Uneven Texture': ['texture', 'exfoliation', 'kp', 'texture improvement'],
    'Dark Circles': ['dark circles', 'under-eye circles', 'eye bags'],
    'Sun Protection': ['uv filter', 'sunscreens', 'sun protection', 'uva protec'],
    'UV Damage': ['photoaging', 'oxidative stress', 'sunburn'],
    'Tanning': ['pigmentation', 'brightening', 'uneven tone', 'pih', 'melasma', 'cosmetic tan'],
    'Puffiness': ['eye bags', 'under-eye circles', 'puffiness'],
}

# Maps synergy DB concern names to our frontend concern names
SYNERGY_CONCERN_MAP = {
    'Dehydration': 'Hydration',
}

# Curated key actives per concern (manually verified, always included)
CONCERNS_MAP = {
    'Acne & Oily Skin':  ['Salicylic Acid', 'Benzoyl Peroxide', 'Azelaic Acid', 'Niacinamide', 'Retinol', 'Zinc PCA'],
    'Pigmentation':      ['Tranexamic Acid', 'Azelaic Acid', 'Alpha Arbutin', 'Niacinamide', 'Ascorbic Acid', 'Kojic Acid'],
    'Aging & Fine Lines': [
        'Retinol', 'Retinal', 'Bakuchiol', 'Ascorbic Acid', 'Glycolic Acid',
        # All known peptide INCI names in DB
        'Palmitoyl Pentapeptide-4', 'Palmitoyl Tripeptide-1', 'Palmitoyl Tetrapeptide-7',
        'Acetyl Hexapeptide-8', 'Copper Tripeptide-1', 'Hexapeptide-11',
        'Palmitoyl Pentapeptide', 'Palmitoyl Tripeptide', 'Palmitoyl Tetrapeptide',
        'Oligopeptide-1', 'Oligopeptide-2', 'Sh-Oligopeptide-1',
    ],
    'Barrier Repair':    [
        'Ceramide NP', 'Ceramide AP', 'Ceramide EOP', 'Ceramide NS', 'Ceramide EOS',
        'Ceramides', 'Fermented Ceramide NP',
        'Cholesterol', 'Panthenol', 'Niacinamide',
        # Fatty acids that repair barrier
        'Linoleic Acid', 'Linolenic Acid', 'Palmitic Acid', 'Stearic Acid',
    ],
    'Sensitive Skin':    [
        'Centella Asiatica', 'Centella Asiatica Extract', 'Centella Asiatica Leaf Water',
        'Madecassoside', 'Asiaticoside', 'Madecassic Acid',
        'Panthenol', 'Allantoin',
        'Ceramide NP', 'Ceramide AP', 'Ceramides',
    ],
    'Hydration':         ['Sodium Hyaluronate', 'Glycerin', 'Panthenol', 'Sodium PCA', 'Urea'],
    'Large Pores':       ['Niacinamide', 'Salicylic Acid', 'Retinol', 'Glycolic Acid'],
    'Dullness':          [
        'Ascorbic Acid', 'Niacinamide', 'Glycolic Acid',
        'Glycyrrhiza Glabra Root Extract', 'Dipotassium Glycyrrhizate',
        'Glycyrrhiza Inflata Root Extract', 'Licorice Root', 'Licorice Extract',
    ],
    'Uneven Texture':    ['Glycolic Acid', 'Salicylic Acid', 'Retinol', 'Lactic Acid'],
    'Dark Circles':      [
        'Caffeine', 'Ascorbic Acid', 'Niacinamide',
        'Vitamin K', 'Vitamin K1',
        'Palmitoyl Pentapeptide-4', 'Palmitoyl Tetrapeptide-7', 'Acetyl Tetrapeptide-5',
        'Palmitoyl Pentapeptide', 'Palmitoyl Tetrapeptide',
    ],
    'Sun Protection':    ['Zinc Oxide', 'Titanium Dioxide', 'Avobenzone', 'Octinoxate', 'Homosalate', 'Bemotrizinol'],
    'UV Damage':         [
        'Ferulic Acid', 'Ascorbic Acid', 'Resveratrol', 'Caffeine',
        'Glycyrrhiza Glabra Root Extract',
    ],
    'Tanning':           [
        'Alpha Arbutin', 'Kojic Acid', 'Tranexamic Acid', 'Ascorbic Acid', 'Niacinamide',
        'Glutathione', 'Glutathione Ethyl Ester',
    ],
    'Puffiness':         [
        'Caffeine', 'Niacinamide',
        'Acetyl Tetrapeptide-5', 'Hesperidin Methyl Chalcone',
        'Centella Asiatica Extract', 'Centella Asiatica',
    ],
}

# INCI prefix groups: if product has ANY inci that starts with these prefixes,
# it counts as that concern active. Handles ceramide NP/AP/EOP variants etc.
CONCERN_INCI_PREFIXES = {
    'Acne & Oily Skin':   [],
    'Aging & Fine Lines': ['Palmitoyl', 'Acetyl Hex', 'Oligopeptide', 'Copper Tripeptide', 'Hexapeptide', 'Sh-Oligopeptide'],
    'Barrier Repair':     ['Ceramide'],
    'Sensitive Skin':     ['Ceramide', 'Centella Asiatica', 'Madecass'],
    'Dark Circles':       ['Palmitoyl', 'Acetyl Tetrapeptide'],
    'Puffiness':          ['Acetyl Tetrapeptide', 'Centella Asiatica'],
}

# ─── Ingredient Normalization Pipeline ───────────────────────────────────────
# Step 3: Common synonym aliases → canonical INCI name
_INGREDIENT_ALIASES = {
    # Vitamins
    "vitamin e": "tocopherol", "vit e": "tocopherol",
    "vitamin b3": "niacinamide", "vit b3": "niacinamide",
    "vitamin b5": "panthenol", "pro-vitamin b5": "panthenol",
    "provitamin b5": "panthenol", "pro vitamin b5": "panthenol",
    "vitamin c": "ascorbic acid", "vit c": "ascorbic acid",
    "vitamin a": "retinol", "vit a": "retinol",
    "vitamin k": "phytonadione", "vitamin k1": "phytonadione",
    # Common shorthand
    "dl-alpha-tocopherol": "tocopherol",
    "alpha-tocopherol": "tocopherol",
    "l-ascorbic acid": "ascorbic acid",
    "ha": "sodium hyaluronate",
    "aha": "glycolic acid",
    "bha": "salicylic acid",
    "pha": "gluconolactone",
    # Brand/marketing names
    "hyaluronic acid": "sodium hyaluronate",
    "retin-a": "tretinoin",
    "retinaldehyde": "retinal",
    "argireline": "acetyl hexapeptide-8",
    "matrixyl": "palmitoyl pentapeptide-4",
    "coenzyme q10": "ubiquinone",
    "q10": "ubiquinone",
    "ectoin": "ectoine",
    "beta glucan": "beta-glucan",
    "licorice": "glycyrrhiza glabra root extract",
    "licorice extract": "glycyrrhiza glabra root extract",
}

# Step 4: Family normalization — derivatives map to parent INCI for lookup
_INGREDIENT_FAMILY_MAP = {
    # Hyaluronic acid family
    "hydrolyzed hyaluronic acid": "sodium hyaluronate",
    "sodium hyaluronate crosspolymer": "sodium hyaluronate",
    "hyaluronic acid crosspolymer": "sodium hyaluronate",
    # Retinoid family
    "retinyl palmitate": "retinol",
    "retinyl acetate": "retinol",
    "retinyl propionate": "retinol",
    # Ceramide family — map to NP as representative
    "ceramide 1": "ceramide eop",
    "ceramide 2": "ceramide np",
    "ceramide 3": "ceramide np",
    "ceramide 6 ii": "ceramide ap",
    # Peptide shorthands
    "palmitoyl pentapeptide": "palmitoyl pentapeptide-4",
    "palmitoyl tripeptide": "palmitoyl tripeptide-1",
    "palmitoyl tetrapeptide": "palmitoyl tetrapeptide-7",
    # AHA family
    "alpha hydroxy acid": "glycolic acid",
    # Niacinamide forms
    "nicotinamide": "niacinamide",
    "nicotinic acid amide": "niacinamide",
}


def _parse_skin_concerns(raw):
    """Parse Skin_Concerns column: split by ";", strip whitespace, lowercase.
    Also accepts a row dict with pre-parsed '_skin_concerns_parsed' key for efficiency.
    """
    if isinstance(raw, dict):
        return raw.get('_skin_concerns_parsed', [])
    if pd.isna(raw) or not raw:
        return []
    return [t.strip().lower() for t in str(raw).split(';') if t.strip()]


class DataLoader:
    def __init__(self, database_path=None):
        if database_path is None:
            database_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database')
        self.database_path = database_path
        self.ingredient_master = None
        self.active_upgrade_map = None
        self.evidence_quality_map = None
        self.ingredient_lookup = {}
        self.all_inci_names = []
        self.concern_actives = {}
        self.concern_supporters = {}
        self.synergy_registry = {}  # concern -> list of synergy combos
        self.synergy_partners_map = {}  # inci_lower -> set of partner inci_lower
        self.uv_sun_db = {}  # INCI_Name.lower() -> row dict for UV/Sun/Tanning data
        self.surfactant_db = {}  # INCI_lower -> row dict (harshness, foam, irritation)
        self.role_weight_table = {}  # role_lower -> float weight
        self.role_sets = {}   # DB-driven ingredient role sets built at startup
        self.load_data()

    def load_data(self):
        # ── Single source of truth: ingredient_database_fixed2.csv ──────────────
        # Replaces ingredient_master.csv + ingredient_science.csv.
        # Loaded once at server start. No duplicate datasets kept in memory.
        try:
            db_path = os.path.join(self.database_path, 'ingredient_database_fixed2.csv')
            db = pd.read_csv(db_path, encoding='utf-8')
            db.columns = db.columns.str.strip()
            # Keep a reference so is_loaded() / any legacy .ingredient_master checks still work
            self.ingredient_master = db

            for _, row in db.iterrows():
                inci = str(row.get('INCI_Name', '')).strip()
                if not inci or inci == 'nan':
                    continue
                row_dict = row.to_dict()
                # Cleanup rule: pre-parse Skin_Concerns → split by ";", strip, lowercase
                raw_sc = row_dict.get('Skin_Concerns', '')
                if pd.isna(raw_sc) or not raw_sc:
                    row_dict['_skin_concerns_parsed'] = []
                else:
                    row_dict['_skin_concerns_parsed'] = [
                        t.strip().lower() for t in str(raw_sc).split(';') if t.strip()
                    ]
                self.ingredient_lookup[inci.lower()] = row_dict
                self.all_inci_names.append(inci)
                # Register aliases (semicolon-separated in Aliases column)
                aliases = str(row_dict.get('Aliases', ''))
                if aliases and aliases != 'nan':
                    for alias in aliases.split(';'):
                        alias = alias.strip()
                        if alias and alias.lower() not in self.ingredient_lookup:
                            self.ingredient_lookup[alias.lower()] = row_dict

            logger.info(f"Loaded {len(self.all_inci_names)} ingredients from ingredient_database_fixed2.csv")

            # Load aliases.json and add each alias → target INCI mapping
            try:
                import json as _json
                aliases_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aliases.json')
                if os.path.exists(aliases_path):
                    with open(aliases_path, 'r') as f:
                        extra_aliases = _json.load(f)
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

        except Exception as e:
            logger.error(f"Error loading ingredient database: {e}")

        try:
            upgrade_path = os.path.join(self.database_path, 'active_upgrade_map.csv')
            if os.path.exists(upgrade_path):
                self.active_upgrade_map = pd.read_csv(upgrade_path)
        except Exception as e:
            logger.error(f"Error loading upgrade map: {e}")

        self._build_concern_maps()
        self._load_synergy_registry()
        self._load_uv_sun_tanning_db()
        self._load_surfactant_db()
        self._load_role_weight_table()
        self._build_role_sets()


    def _build_role_sets(self):
        """Build DB-driven ingredient role sets from the master database.
        Replaces hardcoded keyword lists in scoring.py with live DB lookups.
        Exposed as data_loader.role_sets dict with lowercase INCI name sets.
        Called once at startup — O(n) over 856 rows."""
        active_classes = {
            'active', 'peptide', 'retinoid', 'brightening active',
            'ferment', 'antioxidant', 'humectant', 'emollient',
            'barrier', 'plant oil', 'emollient ester', 'botanical extract',
            'botanical', 'delivery system', 'delivery',
        }
        sets = {
            'active':      set(),
            'humectant':   set(),
            'barrier':     set(),
            'soothing':    set(),
            'emollient':   set(),
            'occlusive':   set(),
            'antioxidant': set(),
            'preservative':set(),
            'surfactant':  set(),
            'exfoliant':   set(),
            'peptide':     set(),
            'filler':      set(),
            'dry_oil':     set(),
            'brightening': set(),
            'anti_acne':   set(),
            'anti_aging':  set(),
            'uv_filter':   set(),
            'delivery':    set(),
        }

        if self.ingredient_master is None:
            self.role_sets = sets
            return

        for _, row in self.ingredient_master.iterrows():
            inci = str(row.get('INCI_Name', '')).strip()
            if not inci or inci == 'nan':
                continue
            key = inci.lower()
            cls  = str(row.get('Ingredient_Class', '')).lower().strip()
            fc   = str(row.get('Functional_Category', '')).lower()
            pb   = str(row.get('Primary_Benefits', '')).lower()
            sc   = str(row.get('Skin_Concerns', '')).lower()

            # Active — any therapeutic ingredient
            if cls in active_classes or any(x in fc for x in ['active', 'antioxidant',
               'brightening', 'anti-acne', 'anti-aging', 'anti-wrinkle', 'peptide',
               'exfoliant', 'repair', 'retinoid', 'depigmenting', 'soothing']):
                sets['active'].add(key)

            # Humectant — water-binding
            sc_lower = str(row.get('Skin_Concerns', '')).lower()
            if (cls == 'humectant' or 'humectant' in fc or 'humectant' in pb
                    or 'hydration' in fc or 'water-binding' in pb or 'hygroscopic' in pb
                    or ('hydration' in sc_lower and 'emollient' not in fc and 'oil' not in fc)):
                sets['humectant'].add(key)

            # Barrier — lipid, ceramide, fatty acid, cholesterol, sphingoid
            if (cls == 'barrier' or any(x in fc for x in [
                    'barrier', 'ceramide', 'barrier lipid', 'barrier repair',
                    'barrier support', 'lipid', 'sphingosine', 'phytosphingosine'])
                    or any(x in pb for x in ['barrier', 'ceramide', 'lipid replenish'])):
                sets['barrier'].add(key)

            # Soothing / anti-inflammatory
            if any(x in fc for x in ['soothing', 'anti-inflammatory', 'calming',
                                       'skin calming', 'redness']):
                sets['soothing'].add(key)
            if any(x in pb for x in ['soothing', 'anti-inflammatory', 'calming',
                                       'reduces redness', 'calms']):
                sets['soothing'].add(key)

            # Emollient — softening, smoothing oils and esters
            if (cls in ('emollient', 'plant oil', 'emollient ester')
                    or any(x in fc for x in ['emollient', 'skin conditioning',
                                              'conditioning', 'softening'])):
                sets['emollient'].add(key)

            # Occlusive — sealing, heavy oils/waxes
            if 'occlusive' in fc or 'occlusive' in pb:
                sets['occlusive'].add(key)

            # Dry/lightweight oils — non-comedogenic preferred oils
            if any(x in fc for x in ['dry oil', 'lightweight oil', 'non-comedogenic oil',
                                       'barrier repair oil']) and 'occlusive' not in fc:
                sets['dry_oil'].add(key)

            # Antioxidant
            if (cls == 'antioxidant' or 'antioxidant' in fc
                    or 'antioxidant' in pb or 'free radical' in pb):
                sets['antioxidant'].add(key)

            # Preservative
            if cls == 'preservative' or 'preservative' in fc:
                sets['preservative'].add(key)

            # Surfactant / cleanser
            if (cls == 'surfactant' or any(x in fc for x in
                    ['surfactant', 'mild surfactant', 'cleansing', 'foaming'])):
                sets['surfactant'].add(key)

            # Exfoliant — AHAs, BHAs, enzymes
            if 'exfoliant' in fc or 'exfoliat' in pb or any(x in key for x in
                    ['glycolic', 'lactic', 'mandelic', 'salicylic', 'gluconolactone',
                     'malic acid', 'tartaric', 'citric acid', 'papain', 'bromelain']):
                sets['exfoliant'].add(key)

            # Peptide
            if cls == 'peptide' or 'peptide' in fc or 'peptide' in key:
                sets['peptide'].add(key)

            # Filler — basic carriers with no therapeutic function
            if (cls == 'filler' or any(x in fc for x in
                    ['solvent', 'thickener', 'gel former', 'polymer', 'film former',
                     'viscosity', 'chelating', 'colorant', 'fragrance'])):
                sets['filler'].add(key)

            # Brightening
            if any(x in fc for x in ['brightening', 'depigmenting', 'lightening']):
                sets['brightening'].add(key)

            # Anti-acne — also check Skin_Concerns column
            sc_lower = str(row.get('Skin_Concerns', '')).lower()
            if ('anti-acne' in fc or 'anti-acne' in pb or 'antimicrobial' in fc
                    or 'acne' in sc_lower or 'sebum' in fc or 'oil control' in fc
                    or 'sebum' in pb):
                sets['anti_acne'].add(key)

            # Anti-aging
            if any(x in fc for x in ['anti-aging', 'anti-wrinkle', 'anti-ageing',
                                       'firming', 'collagen']):
                sets['anti_aging'].add(key)

            # UV filter
            if cls in ('organic uv filter', 'mineral uv filter') or 'uv filter' in fc:
                sets['uv_filter'].add(key)

            # Delivery system — encapsulation, liposomal
            if (cls in ('delivery system', 'delivery')
                    or any(x in fc for x in ['liposomal', 'encapsulated', 'nano',
                                              'cyclodextrin', 'microsphere'])):
                sets['delivery'].add(key)

        self.role_sets = sets

        # Log summary
        for role, s in sorted(sets.items()):
            if s:
                logger.info(f"  role_set[{role!r}]: {len(s)} ingredients")

    def _load_synergy_registry(self):
        """Load pair-based synergy data from ingredient_synergy_table.csv.
        Format: INCI_Name, Synergistic_Ingredients (semicolon-separated partners).
        Builds both a flat list for concern scoring AND a partners_map for impact_score.
        """
        try:
            syn_path = os.path.join(self.database_path, 'ingredient_synergy_table.csv')
            if not os.path.exists(syn_path):
                logger.warning("ingredient_synergy_table.csv not found")
                return
            df = pd.read_csv(syn_path)
            seen_pairs = set()
            all_synergies = []
            for _, row in df.iterrows():
                ing1 = str(row.get('INCI_Name', '')).strip().lower()
                partners_raw = str(row.get('Synergistic_Ingredients', ''))
                if not ing1 or ing1 == 'nan' or partners_raw == 'nan':
                    continue
                partners = [p.strip().lower() for p in partners_raw.split(';') if p.strip()]
                for ing2 in partners:
                    pair_key = tuple(sorted([ing1, ing2]))
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        all_synergies.append({
                            'ingredients': [ing1, ing2],
                            'bonus': 2,
                            'type': 'synergy',
                            'mechanism': f"{ing1.title()} + {ing2.title()} synergy",
                        })
                    # Build fast partners map for impact_score synergy check
                    if ing1 not in self.synergy_partners_map:
                        self.synergy_partners_map[ing1] = set()
                    self.synergy_partners_map[ing1].add(ing2)
                    if ing2 not in self.synergy_partners_map:
                        self.synergy_partners_map[ing2] = set()
                    self.synergy_partners_map[ing2].add(ing1)
            self.synergy_registry['__all__'] = all_synergies
            logger.info(f"Loaded {len(all_synergies)} synergy pairs, {len(self.synergy_partners_map)} mapped ingredients")
        except Exception as e:
            logger.error(f"Error loading synergy registry: {e}")

    def _build_concern_maps(self):
        if self.ingredient_master is None:
            return
        for concern, tags in CONCERN_TAG_MAP.items():
            db_actives = []
            supporters = []
            for _, row in self.ingredient_master.iterrows():
                inci = str(row.get('INCI_Name', '')).strip()
                if not inci or inci == 'nan':
                    continue
                skin_concerns = _parse_skin_concerns(row.get('Skin_Concerns', ''))
                if any(tag in sc for tag in tags for sc in skin_concerns):
                    ing_class = str(row.get('Ingredient_Class', '')).lower().strip()
                    if ing_class == 'active':
                        try:
                            ef = float(row.get('Evidence_Factor', 0.4) or 0.4)
                            esw_raw = row.get('Effect_Strength_Weight', '')
                            if esw_raw == '' or str(esw_raw).strip() in ('', 'nan', '0'):
                                # Category-based ESW default for blank/unscored ingredients
                                func_cat = str(row.get('Functional_Category', '')).lower()
                                if 'humectant' in func_cat:
                                    esw = 1.0
                                elif any(c in func_cat for c in ['emulsifier', 'thickener', 'solvent', 'preservative']):
                                    esw = 0.5
                                else:
                                    esw = 0.5  # conservative default for actives without scored weight
                            else:
                                esw = float(esw_raw)
                        except (ValueError, TypeError):
                            ef, esw = 0.4, 0.5
                        if math.isnan(ef):
                            ef = 0.4
                        if math.isnan(esw):
                            esw = 0.5
                        db_actives.append((inci, ef * esw))
                    elif ing_class in ('functional', 'functional support', 'antioxidant support'):
                        supporters.append(inci)

            # Rank DB actives by relevance score, take top ones
            db_actives.sort(key=lambda x: x[1], reverse=True)
            top_db_names = [name for name, _ in db_actives[:8]]

            # Merge with curated CONCERNS_MAP (these are manually verified key actives)
            curated = CONCERNS_MAP.get(concern, [])
            merged = list(curated)
            for name in top_db_names:
                if name not in merged:
                    merged.append(name)

            # Cap at 8 ideal actives for reasonable scoring ratio
            self.concern_actives[concern] = merged[:8]

            # Remaining DB actives beyond the top ones become additional supporters
            extra_actives = [name for name, _ in db_actives[8:]]
            all_supporters = list(set(supporters + extra_actives))
            self.concern_supporters[concern] = all_supporters
            logger.info(f"  {concern}: {len(self.concern_actives[concern])} ideal actives, {len(all_supporters)} supporters")

    def _load_uv_sun_tanning_db(self):
        """Load UV/Sun/Tanning data from uv_sunscreen_tanning_database.csv (32-column comprehensive DB).
        This is the primary source for all UV filter fields:
        Estimated_SPF_Contribution_Weight, Photostability_Rating, UV_Filter_Type,
        UV_Spectrum_Coverage, UVA_Subtype_Coverage, Ingredient_Category, etc.
        """
        # Alias resolution: common/trade names → canonical INCI names
        INCI_ALIASES = {
            'bemotrizinol': 'Methylene Bis-Benzotriazolyl Tetramethylbutylphenol',
            'bisoctrizole': 'Methylene Bis-Benzotriazolyl Tetramethylbutylphenol',
            'avobenzone': 'Butyl Methoxydibenzoylmethane',
            'octinoxate': 'Ethylhexyl Methoxycinnamate',
            'octisalate': 'Ethylhexyl Salicylate',
            'ensulizole': 'Phenylbenzimidazole Sulfonic Acid',
            'ecamsule': 'Terephthalylidene Dicamphor Sulfonic Acid',
        }

        try:
            uv_path = os.path.join(self.database_path, 'uv_sunscreen_tanning_database.csv')
            if not os.path.exists(uv_path):
                logger.warning("uv_sunscreen_tanning_database.csv not found")
                return

            df = pd.read_csv(uv_path)
            df.columns = df.columns.str.strip()
            count = 0

            for _, row in df.iterrows():
                inci = str(row.get('INCI_Name', '')).strip()
                if not inci or inci == 'nan':
                    continue

                entry = row.to_dict()
                # Normalise NaN → empty string for safe .get() usage in scoring
                for k, v in entry.items():
                    if pd.isna(v):
                        entry[k] = ''

                # Store by canonical INCI key (lowercase)
                key = inci.lower()
                self.uv_sun_db[key] = entry

                # Also register under any alias keys so alias lookups hit this entry
                alias_canonical = INCI_ALIASES.get(key)
                if alias_canonical:
                    # e.g. 'bemotrizinol' → store canonical INCI data under bemotrizinol key too
                    self.uv_sun_db[key] = entry  # already set above
                count += 1

            # Build reverse-alias entries: so scoring can look up 'Bemotrizinol'
            # and get Tinosorb M data (canonical INCI entry)
            for alias_lower, canonical_inci in INCI_ALIASES.items():
                canonical_key = canonical_inci.lower()
                if canonical_key in self.uv_sun_db and alias_lower not in self.uv_sun_db:
                    self.uv_sun_db[alias_lower] = self.uv_sun_db[canonical_key]

            logger.info(f"Loaded {count} UV/sunscreen ingredients from uv_sunscreen_tanning_database.csv")
        except Exception as e:
            logger.error(f"Error loading UV sunscreen DB: {e}")

        logger.info(f"Total UV/Sun/Tanning ingredients in db: {len(self.uv_sun_db)}")

    def get_concern_actives(self, concern):
        return self.concern_actives.get(concern, [])

    def get_concern_supporters(self, concern):
        return self.concern_supporters.get(concern, [])

    def get_synergies(self, concern):
        return self.synergy_registry.get(concern, [])

    @staticmethod
    def _normalize_ingredient(name):
        """Lowercase, remove punctuation, collapse spaces before fuzzy matching."""
        n = name.strip().lower()
        n = re.sub(r'[^\w\s]', ' ', n)
        n = re.sub(r'\s+', ' ', n).strip()
        return n

    def get_uv_data(self, ingredient_name):
        """Get UV/Sun/Tanning data for an ingredient by name or alias."""
        if not ingredient_name:
            return None
        key = ingredient_name.strip().lower()
        if key in self.uv_sun_db:
            return self.uv_sun_db[key]
        normalized = self._normalize_ingredient(ingredient_name)
        if normalized in self.uv_sun_db:
            return self.uv_sun_db[normalized]
        match = process.extractOne(normalized, list(self.uv_sun_db.keys()), scorer=fuzz.token_set_ratio, score_cutoff=85)
        if match:
            return self.uv_sun_db[match[0]]
        return None

    def get_ingredient_data(self, ingredient_name):
        """Multi-step normalization pipeline before DB lookup.
        Step 1: Clean (lowercase, strip brackets/percentages)
        Step 2: Direct lookup
        Step 3: Alias mapping
        Step 4: Family normalization
        Step 5: Alias column lookup (already loaded into ingredient_lookup at init)
        Step 6: Fuzzy match (RapidFuzz, threshold 85)
        """
        if not ingredient_name:
            return None

        # Step 1: Clean — lowercase, remove parens/%, collapse spaces
        key = ingredient_name.strip().lower()
        key = re.sub(r'\([^)]*\)', '', key)          # remove (Vitamin B3) style annotations
        key = re.sub(r'\d+\.?\d*\s*%', '', key)      # remove 10%, 0.5%
        key = re.sub(r'\s+', ' ', key).strip()

        # Step 2: Direct lookup (covers exact INCI names and all aliases loaded at init)
        if key in self.ingredient_lookup:
            return self.ingredient_lookup[key]

        # Step 3: Alias mapping (common marketing/vitamin names → INCI)
        aliased = _INGREDIENT_ALIASES.get(key)
        if aliased:
            result = self.ingredient_lookup.get(aliased)
            if result:
                return result

        # Step 4: Family normalization (derivatives → parent INCI)
        familied = _INGREDIENT_FAMILY_MAP.get(key)
        if familied:
            result = self.ingredient_lookup.get(familied)
            if result:
                return result

        # Step 5: Normalized form (strip punctuation for fuzzy-ready key)
        normalized = self._normalize_ingredient(key)
        if normalized in self.ingredient_lookup:
            return self.ingredient_lookup[normalized]

        # Try alias/family maps on normalized form too
        aliased_norm = _INGREDIENT_ALIASES.get(normalized)
        if aliased_norm and aliased_norm in self.ingredient_lookup:
            return self.ingredient_lookup[aliased_norm]
        familied_norm = _INGREDIENT_FAMILY_MAP.get(normalized)
        if familied_norm and familied_norm in self.ingredient_lookup:
            return self.ingredient_lookup[familied_norm]

        # Step 6: Fuzzy match — last resort, 85% threshold
        match = process.extractOne(
            normalized,
            list(self.ingredient_lookup.keys()),
            scorer=fuzz.token_set_ratio,
            score_cutoff=85
        )
        if match:
            return self.ingredient_lookup[match[0]]

        return None

    def _load_surfactant_db(self):
        """Load surfactant_database.csv → self.surfactant_db (inci_lower → row_dict)."""
        try:
            path = os.path.join(self.database_path, 'surfactant_database.csv')
            if not os.path.exists(path):
                logger.warning("surfactant_database.csv not found")
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
            logger.info(f"Loaded {len(self.surfactant_db)} surfactants from surfactant_database.csv")
        except Exception as e:
            logger.error(f"Error loading surfactant DB: {e}")

    def _load_role_weight_table(self):
        """Load ingredient_role_weight_table.csv → self.role_weight_table (role_lower → float)."""
        try:
            path = os.path.join(self.database_path, 'ingredient_role_weight_table.csv')
            if not os.path.exists(path):
                logger.warning("ingredient_role_weight_table.csv not found")
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
            logger.info(f"Loaded {len(self.role_weight_table)} role weights from ingredient_role_weight_table.csv")
        except Exception as e:
            logger.error(f"Error loading role weight table: {e}")

    def get_surfactant_data(self, ingredient_name):
        """Look up surfactant data for an ingredient."""
        if not ingredient_name:
            return None
        key = ingredient_name.strip().lower()
        if key in self.surfactant_db:
            return self.surfactant_db[key]
        normalized = self._normalize_ingredient(ingredient_name)
        return self.surfactant_db.get(normalized)

    def get_synergy_partners(self, ingredient_name):
        """Return set of synergistic partner names (lowercase) for an ingredient."""
        if not ingredient_name:
            return set()
        return self.synergy_partners_map.get(ingredient_name.strip().lower(), set())

    def is_loaded(self):
        return len(self.ingredient_lookup) > 0


data_loader = DataLoader()

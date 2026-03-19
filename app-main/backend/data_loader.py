import pandas as pd
import os
import re
import math
import logging
from rapidfuzz import process, fuzz

logger = logging.getLogger(__name__)

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
    'Large Pores':       ['Niacinamide', 'Salicylic Acid', 'Retinol', 'Glycolic Acid'],
    'Dullness':          [
        'Ascorbic Acid', 'Niacinamide', 'Glycolic Acid',
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
    'Tanning':           ['Alpha Arbutin', 'Kojic Acid', 'Tranexamic Acid', 'Ascorbic Acid', 'Niacinamide', 'Glutathione', 'Glutathione Ethyl Ester'],
    'Puffiness':         ['Caffeine', 'Niacinamide', 'Acetyl Tetrapeptide-5', 'Hesperidin Methyl Chalcone', 'Centella Asiatica Extract', 'Centella Asiatica'],
}

CONCERN_INCI_PREFIXES = {
    'Acne & Oily Skin':   [],
    'Aging & Fine Lines': ['Palmitoyl', 'Acetyl Hex', 'Oligopeptide', 'Copper Tripeptide', 'Hexapeptide', 'Sh-Oligopeptide'],
    'Barrier Repair':     ['Ceramide'],
    'Sensitive Skin':     ['Ceramide', 'Centella Asiatica', 'Madecass'],
    'Dark Circles':       ['Palmitoyl', 'Acetyl Tetrapeptide'],
    'Puffiness':          ['Acetyl Tetrapeptide', 'Centella Asiatica'],
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
    "ha": "sodium hyaluronate", "aha": "glycolic acid",
    "bha": "salicylic acid", "pha": "gluconolactone",
    "hyaluronic acid": "sodium hyaluronate",
    "retin-a": "tretinoin", "retinaldehyde": "retinal",
    "argireline": "acetyl hexapeptide-8",
    "matrixyl": "palmitoyl pentapeptide-4",
    "coenzyme q10": "ubiquinone", "q10": "ubiquinone",
    "ectoin": "ectoine", "beta glucan": "beta-glucan",
    "licorice": "glycyrrhiza glabra root extract",
    "licorice extract": "glycyrrhiza glabra root extract",
}

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
        self.synergy_registry = {}
        self.synergy_partners_map = {}
        self.uv_sun_db = {}
        self.surfactant_db = {}
        self.role_weight_table = {}
        self.role_sets = {}
        self.load_data()

    def load_data(self):
        # ── ingredient_database_fixed3.csv — new database with Activity_Tier_Weight,
        # Mechanism_of_Action, MW_Daltons, Synergistic_Ingredients, Aliases ────
        try:
            db_path = os.path.join(self.database_path, 'ingredient_database_fixed3.csv')
            db = pd.read_csv(db_path, encoding='utf-8-sig')
            db.columns = db.columns.str.strip()
            self.ingredient_master = db

            for _, row in db.iterrows():
                inci = str(row.get('INCI_Name', '')).strip()
                if not inci or inci == 'nan':
                    continue
                row_dict = row.to_dict()

                # Pre-parse Skin_Concerns
                raw_sc = row_dict.get('Skin_Concerns', '')
                if pd.isna(raw_sc) or not raw_sc:
                    row_dict['_skin_concerns_parsed'] = []
                else:
                    row_dict['_skin_concerns_parsed'] = [
                        t.strip().lower() for t in str(raw_sc).split(';') if t.strip()
                    ]

                # Pre-parse Activity_Tier_Weight (new column: 1.0/0.8/0.5/0.1)
                atw_raw = row_dict.get('Activity_Tier_Weight', '')
                try:
                    row_dict['_activity_tier_weight'] = float(atw_raw) if str(atw_raw).strip() not in ('', 'nan', 'None') else 0.5
                except (ValueError, TypeError):
                    row_dict['_activity_tier_weight'] = 0.5

                # Pre-parse MW_Daltons as float where available
                mw_raw = row_dict.get('MW_Daltons', '')
                try:
                    mw_val = float(mw_raw) if str(mw_raw).strip() not in ('', 'nan', 'None') else None
                    row_dict['_mw_daltons'] = mw_val
                except (ValueError, TypeError):
                    row_dict['_mw_daltons'] = None

                # Store MoA from Mechanism_of_Action; fallback to Biological_Action
                moa = str(row_dict.get('Mechanism_of_Action', '') or '').strip()
                if not moa or moa.lower() in ('nan', 'none', ''):
                    moa = str(row_dict.get('Biological_Action', '') or '').strip()
                row_dict['_moa'] = moa if moa and moa.lower() not in ('nan', 'none') else None

                self.ingredient_lookup[inci.lower()] = row_dict
                self.all_inci_names.append(inci)

                # Register aliases from Aliases column (semicolon-separated)
                aliases_col = str(row_dict.get('Aliases', ''))
                if aliases_col and aliases_col not in ('nan', ''):
                    for alias in aliases_col.split(';'):
                        alias = alias.strip()
                        if alias and alias.lower() not in self.ingredient_lookup:
                            self.ingredient_lookup[alias.lower()] = row_dict

            logger.info(f"Loaded {len(self.all_inci_names)} ingredients from ingredient_database_fixed3.csv")

            # Load aliases.json extra mappings
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
        """Load synergy pairs from ingredient_synergy_table.csv AND main DB's
        Synergistic_Ingredients column. Both feed the same partners map."""
        try:
            seen_pairs = set()
            all_synergies = []

            # Source 1: dedicated synergy table
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

            # Source 2: main ingredient DB's Synergistic_Ingredients column (new in fixed3)
            if self.ingredient_master is not None:
                for _, row in self.ingredient_master.iterrows():
                    ing1 = str(row.get('INCI_Name', '')).strip().lower()
                    partners_raw = str(row.get('Synergistic_Ingredients', '') or '')
                    if not ing1 or ing1 == 'nan' or partners_raw in ('nan', ''):
                        continue
                    for ing2 in [p.strip().lower() for p in partners_raw.split(';') if p.strip()]:
                        self._add_synergy_pair(ing1, ing2, seen_pairs, all_synergies)

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
                            if str(esw_raw).strip() in ('', 'nan', '0'):
                                func_cat = str(row.get('Functional_Category', '')).lower()
                                esw = 1.0 if 'humectant' in func_cat else 0.5
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

            db_actives.sort(key=lambda x: x[1], reverse=True)
            top_db_names = [name for name, _ in db_actives[:8]]
            curated = CONCERNS_MAP.get(concern, [])
            merged = list(curated)
            for name in top_db_names:
                if name not in merged:
                    merged.append(name)
            self.concern_actives[concern] = merged[:8]
            extra_actives = [name for name, _ in db_actives[8:]]
            self.concern_supporters[concern] = list(set(supporters + extra_actives))
            logger.info(f"  {concern}: {len(self.concern_actives[concern])} ideal actives")

    def _load_uv_sun_tanning_db(self):
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
                for k, v in entry.items():
                    if pd.isna(v):
                        entry[k] = ''
                self.uv_sun_db[inci.lower()] = entry
                count += 1
            for alias_lower, canonical_inci in INCI_ALIASES.items():
                canonical_key = canonical_inci.lower()
                if canonical_key in self.uv_sun_db and alias_lower not in self.uv_sun_db:
                    self.uv_sun_db[alias_lower] = self.uv_sun_db[canonical_key]
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
        if self.ingredient_master is None:
            self.role_sets = sets
            return
        for _, row in self.ingredient_master.iterrows():
            inci = str(row.get('INCI_Name', '')).strip()
            if not inci or inci == 'nan':
                continue
            key = inci.lower()
            cls = str(row.get('Ingredient_Class', '')).lower().strip()
            fc  = str(row.get('Functional_Category', '')).lower()
            pb  = str(row.get('Primary_Benefits', '')).lower()
            sc  = str(row.get('Skin_Concerns', '')).lower()

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

    # ── New column accessors ─────────────────────────────────────────────────

    def get_activity_tier_weight(self, ingredient_data):
        """Return Activity_Tier_Weight (0.1–1.0). Tier 1=1.0, Tier2=0.8, Tier3=0.5, Tier4=0.1."""
        if not ingredient_data:
            return 0.5
        return ingredient_data.get('_activity_tier_weight', 0.5)

    def get_mw_daltons(self, ingredient_data):
        """Return MW_Daltons as float if available, else None."""
        if not ingredient_data:
            return None
        return ingredient_data.get('_mw_daltons', None)

    def get_moa(self, ingredient_data):
        """Return Mechanism_of_Action string (for Tier 1/2 display in ingredient table)."""
        if not ingredient_data:
            return None
        return ingredient_data.get('_moa', None)

    def get_activity_tier_label(self, ingredient_data):
        """Return Activity_Tier label string e.g. 'Tier 1: Primary Active'."""
        if not ingredient_data:
            return None
        tier = str(ingredient_data.get('Activity_Tier', '') or '').strip()
        return tier if tier and tier.lower() not in ('nan', 'none', '') else None

    # ── Existing accessors ───────────────────────────────────────────────────

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
        match = process.extractOne(normalized, list(self.uv_sun_db.keys()), scorer=fuzz.token_set_ratio, score_cutoff=85)
        if match:
            return self.uv_sun_db[match[0]]
        return None

    def get_ingredient_data(self, ingredient_name):
        if not ingredient_name:
            return None
        key = ingredient_name.strip().lower()
        key = re.sub(r'\([^)]*\)', '', key)
        key = re.sub(r'\d+\.?\d*\s*%', '', key)
        key = re.sub(r'\s+', ' ', key).strip()

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

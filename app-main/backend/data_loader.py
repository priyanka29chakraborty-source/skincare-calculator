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


def _parse_skin_concerns(raw):
    """Parse the Skin_Concerns column which has inconsistent formatting."""
    if pd.isna(raw) or not raw:
        return []
    raw = str(raw).strip()
    if raw.startswith('['):
        items = re.findall(r"'([^']*)'", raw)
        return [i.strip().lower() for i in items if i.strip()]
    return [t.strip().lower() for t in raw.split(';') if t.strip()]


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
        self.uv_sun_db = {}  # INCI_Name.lower() -> row dict for UV/Sun/Tanning data
        self.load_data()

    def load_data(self):
        try:
            master_path = os.path.join(self.database_path, 'ingredient_master.csv')
            self.ingredient_master = pd.read_csv(master_path, encoding='utf-8')
            self.ingredient_master.columns = self.ingredient_master.columns.str.strip()

            for _, row in self.ingredient_master.iterrows():
                inci = str(row.get('INCI_Name', '')).strip()
                if inci and inci != 'nan':
                    self.ingredient_lookup[inci.lower()] = row.to_dict()
                    self.all_inci_names.append(inci)
                    aliases = str(row.get('Aliases', ''))
                    if aliases and aliases != 'nan':
                        for alias in aliases.split(';'):
                            alias = alias.strip()
                            if alias:
                                self.ingredient_lookup[alias.lower()] = row.to_dict()

            logger.info(f"Loaded {len(self.all_inci_names)} ingredients from master database")

            # Supplement master with ingredient_science.csv (extra aliases, red flags, contraindications)
            try:
                sci_path = os.path.join(self.database_path, 'ingredient_science.csv')
                if os.path.exists(sci_path):
                    sci_df = pd.read_csv(sci_path, encoding='utf-8')
                    sci_df.columns = sci_df.columns.str.strip()
                    added_sci = 0
                    for _, row in sci_df.iterrows():
                        inci = str(row.get('INCI_Name', '')).strip()
                        if not inci or inci == 'nan':
                            continue
                        key = inci.lower()
                        if key not in self.ingredient_lookup:
                            # New ingredient not in master — add it
                            self.ingredient_lookup[key] = row.to_dict()
                            self.all_inci_names.append(inci)
                            added_sci += 1
                        else:
                            # Merge missing fields into existing entry
                            existing = self.ingredient_lookup[key]
                            for col in ['Contraindications', 'Red_Flag_Tags', 'Stability_Notes']:
                                val = row.get(col)
                                if val and str(val).strip() not in ('', 'nan') and (
                                    not existing.get(col) or str(existing.get(col, '')).strip() in ('', 'nan')
                                ):
                                    existing[col] = val
                        # Also register extra aliases from science table
                        aliases = str(row.get('Aliases', ''))
                        if aliases and aliases != 'nan':
                            for alias in aliases.split(';'):
                                alias = alias.strip()
                                if alias and alias.lower() not in self.ingredient_lookup:
                                    self.ingredient_lookup[alias.lower()] = self.ingredient_lookup[key]
                    logger.info(f"Science supplement: added {added_sci} new ingredients, merged aliases")
            except Exception as e:
                logger.warning(f"Could not load ingredient_science.csv: {e}")

            # Supplement master with ingredient_scoring.csv (scoring weights/evidence for any gaps)
            try:
                score_path = os.path.join(self.database_path, 'ingredient_scoring.csv')
                if os.path.exists(score_path):
                    score_df = pd.read_csv(score_path, encoding='utf-8')
                    score_df.columns = score_df.columns.str.strip()
                    for _, row in score_df.iterrows():
                        inci = str(row.get('INCI_Name', '')).strip()
                        if not inci or inci == 'nan':
                            continue
                        key = inci.lower()
                        if key in self.ingredient_lookup:
                            existing = self.ingredient_lookup[key]
                            for col in ['Effect_Strength_Weight', 'Evidence_Factor', 'Evidence_Quality',
                                        'Evidence_Level_Normalized', 'Final_Effect_Score']:
                                val = row.get(col)
                                if val is not None and str(val).strip() not in ('', 'nan'):
                                    try:
                                        float(val) if col != 'Evidence_Quality' and col != 'Evidence_Level_Normalized' else str(val)
                                        if not existing.get(col) or str(existing.get(col, '')).strip() in ('', 'nan', '0', '0.0'):
                                            existing[col] = val
                                    except (ValueError, TypeError):
                                        pass
            except Exception as e:
                logger.warning(f"Could not load ingredient_scoring.csv: {e}")

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
            logger.error(f"Error loading ingredient master: {e}")

        try:
            upgrade_path = os.path.join(self.database_path, 'active_upgrade_map.csv')
            if os.path.exists(upgrade_path):
                self.active_upgrade_map = pd.read_csv(upgrade_path)
        except Exception as e:
            logger.error(f"Error loading upgrade map: {e}")

        self._build_concern_maps()
        self._load_synergy_registry()
        self._load_uv_sun_tanning_db()

    def _load_synergy_registry(self):
        """Load pair-based synergy data from ingredient_synergy_table.csv.
        Format: INCI_Name, Synergistic_Ingredients (semicolon-separated partners).
        Builds a flat list of pair combos stored under '__all__' key,
        returned for any concern since the table is not concern-specific.
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
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)
                    all_synergies.append({
                        'ingredients': [ing1, ing2],
                        'bonus': 2,
                        'type': 'synergy',
                        'mechanism': f"{ing1.title()} + {ing2.title()} synergy",
                    })
            # Store under '__all__' — get_synergies returns same list for any concern
            self.synergy_registry['__all__'] = all_synergies
            logger.info(f"Loaded {len(all_synergies)} synergy pairs from ingredient_synergy_table.csv")
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
                        import math
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
        if not ingredient_name:
            return None
        key = ingredient_name.strip().lower()
        if key in self.ingredient_lookup:
            return self.ingredient_lookup[key]
        normalized = self._normalize_ingredient(ingredient_name)
        if normalized in self.ingredient_lookup:
            return self.ingredient_lookup[normalized]
        match = process.extractOne(normalized, list(self.ingredient_lookup.keys()), scorer=fuzz.token_set_ratio, score_cutoff=85)
        if match:
            return self.ingredient_lookup[match[0]]
        return None

    def is_loaded(self):
        return len(self.ingredient_lookup) > 0


data_loader = DataLoader()

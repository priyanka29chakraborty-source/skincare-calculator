"""Expand the ingredient database with commonly-encountered ingredients.

WHAT THIS DOES AND DOES NOT DO
------------------------------
Nearly everything added here is a FUNCTIONAL excipient - an emulsifier,
solvent, thickener, ester, clay or pigment. Their role in a formula is standard
cosmetic chemistry and is not contested, so recording it is not a scientific
claim. What they are NOT is dosed actives, so:

  * Min_Effective_% / Optimal_% / Max_Safe_% are left EMPTY. They have no
    effective dose because they make no efficacy claim. Inventing numbers here
    would be exactly the kind of unsourced assertion this project is trying to
    get away from.
  * Activity_Tier is "Tier 4: Inert Functional" with weight 0.1, matching how
    the database already treats xanthan gum and similar - so adding them
    improves RECOGNITION without inflating any product's active score.
  * Evidence fields describe the strength of evidence for the ingredient's
    FUNCTION (that an emulsifier emulsifies), not for a skin benefit.

Pregnancy_Safety is "Safe" only for excipients with negligible systemic
absorption where this is genuinely uncontroversial. Anything with real
pharmacology - sulphur, essential oils, botanicals with actives - gets the
honest "Insufficient data" default instead of a reassurance nobody has earned.

Every record carries Data_Source so these are distinguishable from the
original data and from future citation-backed entries.

Run:  python scripts/add_ingredients.py [--dry-run]
"""

import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
DB_PATH = os.path.join(BACKEND, 'database', 'ingredients.json')

SOURCE = "Added 2026-09: INCI function per standard cosmetic chemistry references"

# (INCI, class, functional_category, formulation_role, biological_action,
#  irritation, comedogenicity, pregnancy, solubility, ph, notes)
ADDITIONS = [
    # ── Emulsifiers & surfactants ───────────────────────────────────────────
    ("Cetearyl Glucoside", "Functional", "Emulsifier", "Emulsifier", "Non-ionic emulsification", "Low", 0.0, "Safe", "Both", "", ""),
    ("Steareth-20", "Functional", "Emulsifier", "Emulsifier", "Non-ionic emulsification", "Low", 0.0, "Safe", "Both", "", ""),
    ("Polyglyceryl-3 Methylglucose Distearate", "Functional", "Emulsifier", "Emulsifier", "Non-ionic emulsification", "Low", 0.0, "Safe", "Both", "", ""),
    ("Behentrimonium Methosulfate", "Functional", "Emulsifier", "Conditioning emulsifier", "Cationic conditioning", "Low", 0.0, "Safe", "Water", "", "Mild cationic conditioner; not a quaternary preservative"),
    ("Isoceteth-20", "Functional", "Emulsifier", "Solubiliser", "Non-ionic solubilisation", "Low", 0.0, "Safe", "Both", "", ""),
    ("Laureth-23", "Functional", "Emulsifier", "Solubiliser", "Non-ionic solubilisation", "Low", 0.0, "Safe", "Water", "", ""),
    ("Sorbitan Olivate", "Functional", "Emulsifier", "Emulsifier", "Olive-derived emulsification", "Low", 0.0, "Safe", "Oil", "", ""),
    ("Cetearyl Olivate", "Functional", "Emulsifier", "Emulsifier", "Olive-derived emulsification", "Low", 0.0, "Safe", "Oil", "", ""),
    ("Sodium Stearoyl Glutamate", "Functional", "Emulsifier", "Emulsifier", "Amino-acid emulsification", "Low", 0.0, "Safe", "Both", "", ""),
    ("Poloxamer 188", "Functional", "Surfactant", "Solubiliser", "Non-ionic solubilisation", "Low", 0.0, "Safe", "Water", "", ""),
    ("Poloxamer 182", "Functional", "Surfactant", "Solubiliser", "Non-ionic solubilisation", "Low", 0.0, "Safe", "Water", "", ""),
    ("Disodium Cocoamphodiacetate", "Functional", "Surfactant", "Amphoteric surfactant", "Mild amphoteric cleansing", "Low", 0.0, "Safe", "Water", "", "Amphoteric; among the milder cleansing surfactants"),
    ("Sodium Methyl Cocoyl Taurate", "Functional", "Surfactant", "Mild anionic surfactant", "Taurate cleansing", "Low", 0.0, "Safe", "Water", "", "Mild anionic; gentler than sulfates"),
    ("Sodium Lauroyl Lactylate", "Functional", "Emulsifier", "Emulsifier", "Lactylate emulsification", "Low", 0.0, "Safe", "Both", "", ""),
    ("PEG-8", "Functional", "Humectant", "Solvent / humectant", "Polyethylene glycol carrier", "Low", 0.0, "Safe", "Water", "", ""),
    ("PEG-40 Hydrogenated Castor Oil", "Functional", "Emulsifier", "Solubiliser", "Non-ionic solubilisation", "Low", 0.0, "Safe", "Both", "", ""),

    # ── Thickeners & film formers ───────────────────────────────────────────
    ("Cellulose Gum", "Functional", "Thickener", "Thickener", "Polysaccharide gel", "Low", 0.0, "Safe", "Water", "", ""),
    ("Tamarindus Indica Seed Gum", "Functional", "Thickener", "Thickener / humectant", "Polysaccharide gel", "Low", 0.0, "Safe", "Water", "", "Also acts as a surface humectant"),
    ("Acacia Senegal Gum", "Functional", "Thickener", "Thickener / film former", "Polysaccharide film", "Low", 0.0, "Safe", "Water", "", ""),
    ("Polyvinyl Alcohol", "Functional", "Film Former", "Film former", "Synthetic film", "Low", 0.0, "Safe", "Water", "", "The peel-off film base in mask formats"),
    ("Polyacrylate-13", "Functional", "Thickener", "Thickener", "Acrylate gel network", "Low", 0.0, "Safe", "Water", "", ""),
    ("Polyisobutene", "Functional", "Film Former", "Film former / emollient", "Hydrocarbon film", "Low", 1.0, "Safe", "Oil", "", ""),
    ("C20-22 Alkyl Phosphate", "Functional", "Emulsifier", "Emulsifier", "Phosphate ester emulsification", "Low", 0.0, "Safe", "Oil", "", ""),

    # ── Solvents & humectants ───────────────────────────────────────────────
    ("Ethoxydiglycol", "Functional", "Solvent", "Penetration enhancer / solvent", "Glycol ether solvency", "Low", 0.0, "Safe", "Both", "", "Raises penetration of co-formulated actives, and their irritancy with it"),
    ("Dimethyl Isosorbide", "Functional", "Solvent", "Penetration enhancer / solvent", "Isosorbide solvency", "Low", 0.0, "Safe", "Both", "", "Raises penetration of co-formulated actives"),
    ("Methylpropanediol", "Functional", "Humectant", "Solvent / humectant", "Glycol humectancy", "Low", 0.0, "Safe", "Water", "", ""),
    ("Sorbitol", "Functional", "Humectant", "Humectant", "Polyol water binding", "Low", 0.0, "Safe", "Water", "", ""),
    ("Glycereth-26", "Functional", "Humectant", "Humectant", "Ethoxylated glycerin", "Low", 0.0, "Safe", "Water", "", ""),
    ("Xylitylglucoside", "Functional", "Humectant", "Humectant", "Sugar-derived water binding", "Low", 0.0, "Safe", "Water", "", ""),
    ("Anhydroxylitol", "Functional", "Humectant", "Humectant", "Sugar-derived water binding", "Low", 0.0, "Safe", "Water", "", ""),
    ("Xylitol", "Functional", "Humectant", "Humectant", "Polyol water binding", "Low", 0.0, "Safe", "Water", "", ""),

    # ── Emollients & esters ─────────────────────────────────────────────────
    # Comedogenicity values are the conventional published figures. The scoring
    # engine deliberately does NOT score comedogenicity from these, because the
    # rating scale was derived from rabbit-ear assays on raw materials and is
    # not predictive for finished formulas. Recorded for display only.
    ("Isopropyl Palmitate", "Functional", "Emollient", "Emollient ester", "Ester emolliency", "Low", 4.0, "Safe", "Oil", "", "Conventionally rated comedogenic; rating scale is contested"),
    ("Ethylhexyl Palmitate", "Functional", "Emollient", "Emollient ester", "Ester emolliency", "Low", 2.0, "Safe", "Oil", "", ""),
    ("Coco-Caprylate", "Functional", "Emollient", "Light emollient ester", "Ester emolliency", "Low", 0.0, "Safe", "Oil", "", "Light, oxidation-resistant"),
    ("Dicaprylyl Ether", "Functional", "Emollient", "Light emollient", "Ether emolliency", "Low", 0.0, "Safe", "Oil", "", ""),
    ("Dicaprylyl Carbonate", "Functional", "Emollient", "Light emollient", "Carbonate emolliency", "Low", 0.0, "Safe", "Oil", "", ""),
    ("C10-13 Alkane", "Functional", "Emollient", "Light emollient", "Hydrocarbon emolliency", "Low", 0.0, "Safe", "Oil", "", "Plant-derived hydrocarbon; silicone alternative"),
    ("C13-15 Alkane", "Functional", "Emollient", "Light emollient", "Hydrocarbon emolliency", "Low", 0.0, "Safe", "Oil", "", "Plant-derived hydrocarbon; silicone alternative"),
    ("Diisopropyl Adipate", "Functional", "Emollient", "Light emollient ester", "Ester emolliency", "Low", 0.0, "Safe", "Oil", "", ""),
    ("Dibutyl Adipate", "Functional", "Emollient", "Light emollient ester", "Ester emolliency", "Low", 0.0, "Safe", "Oil", "", ""),
    ("Cetyl Ethylhexanoate", "Functional", "Emollient", "Emollient ester", "Ester emolliency", "Low", 1.0, "Safe", "Oil", "", ""),
    ("Octyldodecanol", "Functional", "Emollient", "Fatty alcohol emollient", "Branched alcohol emolliency", "Low", 0.0, "Safe", "Oil", "", ""),
    ("PPG-15 Stearyl Ether", "Functional", "Emollient", "Emollient", "Polyether emolliency", "Low", 0.0, "Safe", "Oil", "", ""),

    # ── Silicones ───────────────────────────────────────────────────────────
    ("Phenyl Trimethicone", "Functional", "Occlusive", "Silicone emollient", "Silicone film", "Low", 0.0, "Safe", "Oil", "", ""),
    ("Diphenylsiloxy Phenyl Trimethicone", "Functional", "Occlusive", "Silicone emollient", "Silicone film", "Low", 0.0, "Safe", "Oil", "", "High-refractive silicone; common in sunscreen vehicles"),
    ("Bis-PEG-18 Methyl Ether Dimethyl Silane", "Functional", "Emollient", "Silicone / humectant hybrid", "Silicone-glycol emolliency", "Low", 0.0, "Safe", "Both", "", ""),
    ("Dimethicone Crosspolymer", "Functional", "Occlusive", "Silicone elastomer", "Silicone film", "Low", 0.0, "Safe", "Oil", "", "Blurs texture; used for finish"),

    # ── Preservation & stability ────────────────────────────────────────────
    ("Tetrasodium Glutamate Diacetate", "Functional", "Chelator", "Chelating agent", "Metal ion sequestration", "Low", 0.0, "Safe", "Water", "", "Readily biodegradable EDTA alternative"),
    ("Sodium Metabisulfite", "Functional", "Antioxidant", "Antioxidant / reducing agent", "Sulfite reduction", "Moderate", 0.0, "Insufficient data; consult doctor before use in pregnancy", "Water", "", "Stabilises ascorbic acid; sulfite sensitivity exists in a minority"),
    ("Octenidine HCl", "Preservative", "Preservative", "Antimicrobial", "Cationic antimicrobial", "Low", 0.0, "Insufficient data; consult doctor before use in pregnancy", "Water", "", "Antiseptic used at low levels"),

    # ── Clays, powders & pigments ───────────────────────────────────────────
    ("Kaolin", "Functional", "Absorbent", "Clay / absorbent", "Oil absorption", "Low", 0.0, "Safe", "Insoluble", "", "Absorbs surface oil; the base of most clay masks"),
    ("Bentonite", "Functional", "Absorbent", "Clay / absorbent", "Oil absorption", "Low", 0.0, "Safe", "Insoluble", "", "More absorbent than kaolin; can over-dry with frequent use"),
    ("Solum Fullonum", "Functional", "Absorbent", "Clay / absorbent", "Oil absorption", "Low", 0.0, "Safe", "Insoluble", "", "Fuller's earth / multani mitti"),
    ("Charcoal Powder", "Functional", "Absorbent", "Absorbent", "Surface adsorption", "Low", 0.0, "Safe", "Insoluble", "", "Adsorbs surface oil; claims of drawing out impurities from within pores are not supported"),
    ("Talc", "Functional", "Absorbent", "Absorbent / filler", "Mineral absorption", "Low", 0.0, "Safe", "Insoluble", "", ""),
    ("Magnesium Aluminum Silicate", "Functional", "Thickener", "Suspending agent", "Mineral suspension", "Low", 0.0, "Safe", "Insoluble", "", ""),
    ("Nylon-12", "Functional", "Absorbent", "Soft-focus powder", "Optical diffusion", "Low", 0.0, "Safe", "Insoluble", "", ""),
    ("Boron Nitride", "Functional", "Absorbent", "Soft-focus powder", "Optical diffusion", "Low", 0.0, "Safe", "Insoluble", "", ""),
    ("Mica", "Functional", "Colorant", "Pigment / pearlescent", "Optical reflection", "Low", 0.0, "Safe", "Insoluble", "", ""),
    ("CI 77891", "Functional", "Colorant", "White pigment", "Optical opacity", "Low", 0.0, "Safe", "Insoluble", "", "Titanium dioxide used as a colorant, not as a UV filter at this level"),
    ("CI 19140", "Functional", "Colorant", "Yellow colorant", "Synthetic dye", "Low", 0.0, "Safe", "Water", "", ""),
    ("CI 42090", "Functional", "Colorant", "Blue colorant", "Synthetic dye", "Low", 0.0, "Safe", "Water", "", ""),
    ("CI 12490", "Functional", "Colorant", "Red colorant", "Synthetic dye", "Low", 0.0, "Safe", "Insoluble", "", ""),
    ("CI 74160", "Functional", "Colorant", "Blue pigment", "Phthalocyanine pigment", "Low", 0.0, "Safe", "Insoluble", "", ""),

    # ── Botanicals commonly seen in the Indian market ───────────────────────
    # Botanical extracts vary enormously by extraction method and
    # standardisation, so evidence is recorded as Limited and no effective dose
    # is claimed - "Azadirachta Indica Leaf Extract" on a label says nothing
    # about how much active material is present.
    ("Cicer Arietinum Seed Powder", "Functional", "Absorbent", "Botanical powder", "Physical absorption", "Low", 0.0, "Safe", "Insoluble", "", "Besan/gram flour; traditional ubtan base"),
    ("Azadirachta Indica Leaf Extract", "Functional", "Soothing", "Botanical extract", "Traditional antimicrobial", "Low", 0.0, "Insufficient data; consult doctor before use in pregnancy", "Water", "", "Neem; traditional use is extensive, standardised clinical data in cosmetics is limited"),
    ("Ocimum Sanctum Leaf Extract", "Functional", "Soothing", "Botanical extract", "Traditional anti-inflammatory", "Low", 0.0, "Insufficient data; consult doctor before use in pregnancy", "Water", "", "Tulsi/holy basil"),
    ("Withania Somnifera Root Extract", "Functional", "Antioxidant", "Botanical extract", "Antioxidant", "Low", 0.0, "Insufficient data; consult doctor before use in pregnancy", "Water", "", "Ashwagandha; topical cosmetic evidence limited"),
    ("Citrullus Lanatus Fruit Extract", "Functional", "Humectant", "Botanical extract", "Surface hydration", "Low", 0.0, "Safe", "Water", "", "Watermelon extract"),
    ("Coffea Arabica Seed Powder", "Functional", "Absorbent", "Physical exfoliant", "Mechanical abrasion", "Moderate", 0.0, "Safe", "Insoluble", "", "Ground coffee; particle edges can abrade if scrubbed hard"),
    ("Cucumis Sativus Fruit Extract", "Functional", "Soothing", "Botanical extract", "Surface soothing", "Low", 0.0, "Safe", "Water", "", "Cucumber extract"),
    ("Cocos Nucifera Water", "Functional", "Humectant", "Botanical water", "Surface hydration", "Low", 0.0, "Safe", "Water", "", "Coconut water; not coconut oil, and not comedogenic in the way the oil is"),
    ("Hamamelis Virginiana Water", "Functional", "Soothing", "Botanical water", "Astringent", "Moderate", 0.0, "Safe", "Water", "", "Witch hazel; distillates often carry alcohol, which drives most reported irritation"),

    # ── Ingredients with real pharmacology - handled conservatively ─────────
    ("Sulphur", "Active", "Anti-Acne", "Keratolytic antimicrobial", "Keratolysis; antimicrobial", "Moderate", 0.0, "Insufficient data; consult doctor before use in pregnancy", "Insoluble", "", "OTC acne active in the US monograph at 3-10%; drying and odorous"),
    ("Citrus Limon Peel Oil", "Functional", "Fragrance", "Essential oil", "Terpene fragrance", "High", 0.0, "Insufficient data; consult doctor before use in pregnancy", "Oil", "", "Citrus peel oils are phototoxic and sensitising; limonene content oxidises with air"),
    ("Eugenia Caryophyllus Bud Oil", "Functional", "Fragrance", "Essential oil", "Eugenol fragrance", "High", 0.0, "Insufficient data; consult doctor before use in pregnancy", "Oil", "", "Clove oil; eugenol is a recognised contact sensitiser"),
    ("Menthone Glycerin Acetal", "Functional", "Fragrance", "Cooling agent", "TRPM8 cooling sensation", "Moderate", 0.0, "Safe", "Oil", "", "Provides a cooling sensation; does not lower skin temperature"),
]


def make_record(row):
    (inci, klass, func_cat, form_role, bio, irritation, comedo, pregnancy,
     solubility, ph, notes) = row
    return {
        "INCI_Name": inci,
        "Aliases": "",
        "Ingredient_Class": klass,
        "Functional_Category": func_cat,
        # Intentionally empty: these are not dosed actives and have no
        # evidenced effective concentration.
        "Min_Effective_%": "",
        "Optimal_%": "",
        "Max_Safe_%": "",
        "Primary_Benefits": form_role,
        "Mechanism_of_Action": bio,
        "Skin_Concerns": "",
        "Recommended_pH": ph,
        "Stability_Notes": "",
        "Irritation_Risk": irritation,
        "Comedogenicity_0_5": comedo,
        "Pregnancy_Safety": pregnancy,
        "Evidence_Strength": "Limited",
        "Avg_Time_To_Results": "N/A - Functional/Excipient",
        "Effect_Strength_Weight": 0.15 if klass != "Active" else 0.5,
        "Synergistic_Ingredients": "",
        "Contraindications": "",
        "Red_Flag_Tags": "",
        "Evidence_Level_Normalized": "Limited",
        "Evidence_Factor": 0.4,
        "Final_Effect_Score": 0.06,
        "Sun_Protection_Role": "",
        "UV_Damage_Role": "",
        "Tanning_Role": "",
        "Evidence_Quality": "Functional role; not an efficacy claim",
        "Role_Weight": 4.0,
        "Clinical_Weight": 4.0,
        "Sensitive_Skin_Risk": irritation,
        "Formulation_Role": form_role,
        "Biological_Action": bio,
        "Solubility": solubility,
        "Usage_Type": "Leave-on",
        "pKa": "",
        "LogP": "",
        "MW_Daltons": "",
        "Avg_Time_Category": "",
        "Avg_Time_Notes": notes or "Excipient/functional ingredient; no direct therapeutic timeline",
        "Regional_Restrictions": "",
        "Activity_Tier": "Tier 4: Inert Functional" if klass != "Active" else "Tier 2: Established Active",
        "Activity_Tier_Weight": 0.1 if klass != "Active" else 0.8,
        # Provenance. The original records carry no source field at all; every
        # record added from here on says where it came from.
        "Data_Source": SOURCE,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    db = json.load(io.open(DB_PATH, encoding='utf-8'))
    ingredients = db['ingredients']
    before = len(ingredients)

    added, skipped = [], []
    for row in ADDITIONS:
        key = row[0].strip().lower()
        if key in ingredients:
            skipped.append(row[0])
            continue
        record = make_record(row)
        record['_skin_concerns_parsed'] = []
        record['_activity_tier_weight'] = record['Activity_Tier_Weight']
        record['_moa'] = record['Biological_Action']
        record['_mw_daltons'] = None
        ingredients[key] = record
        added.append(row[0])

    print("would add" if args.dry_run else "added", len(added), "ingredients")
    if skipped:
        print("already present, skipped:", len(skipped), "->", ", ".join(skipped[:6]))
    print("database: {} -> {} records".format(before, before + len(added)))

    if args.dry_run:
        return 0

    # Preserve the minified single-line format the file is stored in.
    io.open(DB_PATH, 'w', encoding='utf-8').write(
        json.dumps(db, separators=(',', ':'), ensure_ascii=False))
    print("written to", DB_PATH)
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""Locks for the remaining review items.

Implemented only where a reproduced lookup or score was wrong and the
correction does not invent a concentration, a composition, or a new weight.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import data_loader  # noqa: E402
from formulation import (  # noqa: E402
    CATEGORY_RUBRICS,
    _EXTRA_PRESERVATIVES,
    build_advisory_flags,
    score_formulation,
)
from scoring import (  # noqa: E402
    analyze_product,
    bind_declared_concentrations,
    estimate_concentration,
    get_concentration_factor,
    get_evidence_factor,
    get_evidence_label,
    get_upgrade_suggestions,
    parse_ingredients,
)


def _formulation(ingredients, category="serum", known=None):
    parsed = parse_ingredients(ingredients)
    conc = estimate_concentration(parsed, known)
    return score_formulation(
        parsed, conc, category, known_concentrations=known)


def _component(result, key):
    return next(c["score"] for c in result["components"] if c["key"] == key)


def _uv_inci(name):
    row = data_loader.get_uv_data(name)
    if not row:
        return None
    return row.get("INCI_Name")


# --- 1. Exact UV Common_Name aliases ---------------------------------------

# Common_Name values that exact lookup used to miss, or that fuzzy lookup
# sent to a different filter. Each name is unique to one UV-filter row.
_UV_COMMON_NAMES = {
    "Nano Titanium Dioxide": "Titanium Dioxide (nano)",
    "Mexoryl SX": "Terephthalylidene Dicamphor Sulfonic Acid",
    "Mexoryl SX (alternate INCI)": "Terephthalylidene Dicamphor Sulfonic Acid",
    "Menthyl Anthranilate": "Meradimate",
    "Amiloxate": "Isoamyl p-Methoxycinnamate",
    "Iscotrizinol": "Diethylhexyl Butamido Triazone",
    "Uvasorb HEB": "Diethylhexyl Butamido Triazone",
    "Parsol SLX": "Polysilicone-15",
    "Mexoryl SO": "Camphor Benzalkonium Methosulfate",
    "Mexoryl XL": "Drometrizole Trisiloxane",
    "Ethylhexyl Dimethyl PABA": "Padimate O",
    "OD-PABA": "Padimate O",
    "TEA-Salicylate": "Trolamine Salicylate",
    "2-Ethoxyethyl p-Methoxycinnamate": "Cinoxate",
    "Benzophenone-8": "Dioxybenzone",
    "Uvinul MS 40": "Sulisobenzone",
    "Parsol 5000": "4-Methylbenzylidene Camphor",
    "Enzacamene": "4-Methylbenzylidene Camphor",
    "3-BC": "3-Benzylidene Camphor",
    "Mexoryl SL": "Benzylidene Camphor Sulfonic Acid",
    "Neo Heliopan AP": "Disodium Phenyl Dibenzimidazole Tetrasulfonate",
    "Bisdisulizole Disodium": "Disodium Phenyl Dibenzimidazole Tetrasulfonate",
    "Ensulizole (sodium salt form)": "Sodium Phenylbenzimidazole Sulfonate",
    "Tinosorb A2B": "Tris-Biphenyl Triazine",
    "Tinosorb A2B (BASF)": "Tris-Biphenyl Triazine",
    "Uvinul DS-49": "Benzophenone-9",
    "Sodium Dihydroxydimethoxybenzophenonedisulfonate": "Benzophenone-9",
    "PABA": "Aminobenzoic Acid",
}


@pytest.mark.parametrize("common,inci", sorted(_UV_COMMON_NAMES.items()))
def test_uv_common_name_resolves_to_its_inci(common, inci):
    assert _uv_inci(common) == inci


def test_benzophenone_numbers_stay_on_their_own_filters():
    assert _uv_inci("Benzophenone-3") == "Oxybenzone"
    assert _uv_inci("Benzophenone-4") == "Sulisobenzone"
    assert _uv_inci("Benzophenone-8") == "Dioxybenzone"
    assert _uv_inci("Benzophenone-9") == "Benzophenone-9"
    assert _uv_inci("Ensulizole") == "Phenylbenzimidazole Sulfonic Acid"
    assert _uv_inci("Tinosorb S") == "Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine"
    assert _uv_inci("Tinosorb A2B") != "Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine"


def test_invented_uv_name_stays_unknown():
    assert data_loader.get_uv_data("Zzqxv NotAFilter 999") is None


def test_nano_marker_is_not_stripped_to_force_a_match():
    """'(nano)' stays part of the nano row. The non-nano INCI is a different filter."""
    assert _uv_inci("Titanium Dioxide") == "Titanium Dioxide"
    assert _uv_inci("Titanium Dioxide (nano)") == "Titanium Dioxide (nano)"
    assert _uv_inci("Nano Titanium Dioxide") == "Titanium Dioxide (nano)"


# --- 2. Zinc oxide and titanium dioxide in a serum -------------------------


def test_mineral_filters_are_not_serum_actives():
    base = "Aqua, {}, Glycerin, Phenoxyethanol"
    zinc = _formulation(base.format("Zinc Oxide"))
    titanium = _formulation(base.format("Titanium Dioxide"))
    assert _component(zinc, "actives") == _component(titanium, "actives") == 0
    assert _component(zinc, "evidence") == _component(titanium, "evidence") == 0
    assert zinc["score"] == titanium["score"]
    assert data_loader.get_ingredient_data("Zinc Oxide")["Ingredient_Class"] == "Mineral UV Filter"
    assert data_loader.get_ingredient_data("Titanium Dioxide")["Ingredient_Class"] == "Mineral UV Filter"
    sun = _formulation(base.format("Zinc Oxide"), "sunscreen")
    assert not any(f["type"] == "no_uv_filter" for f in sun["flags"])


# --- 3. Matrixyl 3000 -------------------------------------------------------

_MATRIXYL = "Aqua, Matrixyl 3000, Phenoxyethanol"
_PEPTIDES = "Aqua, Palmitoyl Tripeptide-1, Palmitoyl Tetrapeptide-7, Phenoxyethanol"
_BOTH = (
    "Aqua, Matrixyl 3000, Palmitoyl Tripeptide-1, "
    "Palmitoyl Tetrapeptide-7, Phenoxyethanol"
)


def test_matrixyl_3000_alone_does_not_invent_peptides_or_outrank_them():
    alone = _formulation(_MATRIXYL)
    peptides = _formulation(_PEPTIDES)
    assert alone["score"] < peptides["score"]
    listed = " ".join(parse_ingredients(_MATRIXYL)).lower()
    assert "palmitoyl tripeptide-1" not in listed
    assert "palmitoyl tetrapeptide-7" not in listed
    notes = " ".join(
        " ".join(c.get("notes") or []) for c in alone["components"]
    ).lower()
    assert "palmitoyl tripeptide-1" not in notes
    assert "palmitoyl tetrapeptide-7" not in notes
    row = data_loader.get_ingredient_data("Matrixyl 3000")
    assert row["INCI_Name"] == "Matrixyl 3000"
    assert "strong" not in get_evidence_label(get_evidence_factor(row)).lower()
    assert row.get("Activity_Tier") == "Tier 2: Secondary Active"


def _aging(ingredients):
    result = analyze_product({
        "ingredients": ingredients,
        "category": "Serum",
        "concerns": ["Aging & Fine Lines"],
        "product_name": "",
        "price": 0,
        "size_ml": 30,
    })
    return result["skin_concern_fit"]["Aging & Fine Lines"]["score"]


def test_matrixyl_3000_listed_with_peptides_does_not_double_count():
    peptides = _formulation(_PEPTIDES)
    both = _formulation(_BOTH)
    assert _component(both, "actives") == _component(peptides, "actives")
    assert _component(both, "evidence") == _component(peptides, "evidence")
    assert both["score"] == peptides["score"]
    assert _aging(_BOTH) == _aging(_PEPTIDES)
    assert _aging(_MATRIXYL) < _aging(_PEPTIDES)


# --- 4. Over-max stays at the ceiling factor -------------------------------


def _notes(result, key):
    return " ".join(
        next(c["notes"] for c in result["components"] if c["key"] == key)
    ).lower()


def test_over_max_does_not_score_below_the_ceiling_dose():
    data = data_loader.get_ingredient_data("Niacinamide")
    at_ceiling = get_concentration_factor(10, data)
    over = get_concentration_factor(15, data)
    assert at_ceiling == 1.0
    assert over >= at_ceiling
    ceiling = _formulation(
        "Aqua, Niacinamide, Phenoxyethanol", known={"niacinamide": 10})
    above = _formulation(
        "Aqua, Niacinamide, Phenoxyethanol", known={"niacinamide": 15})
    assert _component(above, "actives") >= _component(ceiling, "actives")
    assert _component(above, "tolerability") < _component(ceiling, "tolerability")
    assert any(f["type"] == "above_recorded_maximum" for f in above["flags"])
    assert "recorded" in _notes(above, "tolerability")
    assert not any(f["type"] == "above_recorded_maximum" for f in ceiling["flags"])


# --- 6. 3-O-ethyl ascorbic acid --------------------------------------------


def test_3_o_ethyl_ascorbic_acid_exact_name_is_its_own_inci():
    for name in ("3-O-Ethyl Ascorbic Acid", "3-o-ethyl ascorbic acid"):
        data = data_loader.get_ingredient_data(name)
        assert data["INCI_Name"] == "3-O-Ethyl Ascorbic Acid"


# --- Rejected changes -------------------------------------------------------


def test_numeric_evidence_5_does_not_make_olive_oil_strong():
    # Parentheses are stripped before lookup, so the stored key is read directly.
    olive = data_loader.ingredient_lookup["olea europaea (olive) fruit oil"]
    assert str(olive.get("Evidence_Level_Normalized")) == "5.0"
    factor = get_evidence_factor(olive)
    assert factor < 0.9
    assert "strong" not in get_evidence_label(factor).lower()
    synthetic = get_evidence_factor({
        "Evidence_Level_Normalized": "5.0",
        "Evidence_Strength": "Strong",
        "Evidence_Factor": 0.4,
    })
    assert synthetic == 0.4


@pytest.mark.parametrize("ingredients", [
    "Aqua, Hydroquinone, Phenoxyethanol",
    "Aqua, Retinol, Phenoxyethanol",
    "Aqua, Tretinoin, Phenoxyethanol",
    "Aqua, Adapalene, Phenoxyethanol",
])
def test_pregnancy_actives_still_raise_an_advisory(ingredients):
    flags = build_advisory_flags(parse_ingredients(ingredients))
    assert any(f["type"] == "pregnancy" for f in flags)


def test_hydroquinone_pregnancy_text_is_cannot_use():
    data = data_loader.get_ingredient_data("Hydroquinone")
    text = str(data.get("Pregnancy_Safety") or "").lower()
    assert "cannot be used" in text
    assert "safe" not in text.replace("safety", "")


def test_salicylic_acid_is_not_the_preservative_system():
    assert "salicylic acid" not in _EXTRA_PRESERVATIVES
    sa_only = _formulation("Aqua, Salicylic Acid")
    phenoxy = _formulation("Aqua, Phenoxyethanol")
    both = _formulation("Aqua, Salicylic Acid, Phenoxyethanol")
    assert any(f["type"] == "no_preservative" for f in sa_only["flags"])
    assert "adequately preserved" not in _notes(sa_only, "integrity")
    assert not any(f["type"] == "no_preservative" for f in phenoxy["flags"])
    assert "adequately preserved" in _notes(phenoxy, "integrity")
    assert not any(f["type"] == "no_preservative" for f in both["flags"])
    assert "adequately preserved" in _notes(both, "integrity")
    assert _component(sa_only, "actives") > 0
    row = data_loader.get_ingredient_data("Salicylic Acid")
    assert row["Ingredient_Class"] == "Active"
    assert "exfoliant" in str(row.get("Functional_Category") or "").lower()


def test_bha_is_not_salicylic_acid():
    bha = data_loader.get_ingredient_data("BHA")
    named = data_loader.get_ingredient_data("butylated hydroxyanisole")
    assert bha["INCI_Name"] != "Salicylic Acid"
    assert named is None or named["INCI_Name"] != "Salicylic Acid"


def test_niacinamide_is_a_primary_active():
    row = data_loader.get_ingredient_data("Niacinamide")
    ascorbic = data_loader.get_ingredient_data("Ascorbic Acid")
    assert row["Activity_Tier"] == "Tier 1: Primary Active"
    assert row["Activity_Tier"] == ascorbic["Activity_Tier"]
    assert "tier 2" not in row["Activity_Tier"].lower()
    base = "Aqua, Niacinamide, Phenoxyethanol"
    one = _formulation(base, known={"niacinamide": 1})
    five = _formulation(base, known={"niacinamide": 5})
    ten = _formulation(base, known={"niacinamide": 10})
    assert _component(one, "actives") < _component(five, "actives")
    assert abs(_component(five, "actives") - _component(ten, "actives")) <= 0.6


def test_formulation_weights_and_evidence_ladder_stay():
    assert [(key, weight) for key, _label, weight in CATEGORY_RUBRICS["serum"]["components"]] == [
        ("actives", 40),
        ("evidence", 20),
        ("integrity", 25),
        ("tolerability", 15),
    ]
    assert [(key, weight) for key, _label, weight in CATEGORY_RUBRICS["sunscreen"]["components"]] == [
        ("uva", 30),
        ("photostability", 25),
        ("uvb", 20),
        ("integrity", 15),
        ("tolerability", 10),
    ]
    assert get_evidence_factor({"Evidence_Level_Normalized": "Strong"}) == 0.9
    assert get_evidence_factor({"Evidence_Level_Normalized": "Moderate"}) == 0.7
    assert get_evidence_factor({"Evidence_Level_Normalized": "Limited"}) == 0.55


def test_deoxyribonucleic_acid_is_the_pdrn_on_the_label():
    listed = data_loader.get_ingredient_data("Deoxyribonucleic Acid")
    named = data_loader.get_ingredient_data("PDRN")
    sodium = data_loader.get_ingredient_data("Sodium DNA")
    assert listed is named
    assert listed["INCI_Name"] == "PDRN"
    assert sodium["INCI_Name"] == "Sodium DNA"
    result = score_formulation(
        parse_ingredients(
            "Aqua, Glycerin, Niacinamide, Disodium EDTA, "
            "Deoxyribonucleic Acid, Cyanocobalamin, Phenoxyethanol"
        ),
        {},
        "serum",
        product_name="PDRN Pink Peptide Face Serum",
    )
    notes = " ".join(
        note for comp in result["components"] for note in (comp.get("notes") or [])
    ).lower()
    assert "does not name" not in notes
    roles = [f["message"].lower() for f in result["flags"] if f["type"] == "ingredient_role"]
    assert any("pink" in message and "b12" in message for message in roles)


def _upgrade_text(rows):
    return " ".join(
        " ".join(str(row.get(key) or "") for key in (
            "upgrade", "suggested_active", "reason"))
        for row in rows
    ).lower()


def _product_text(row):
    return "%s %s" % (row.get("upgrade") or "", row.get("suggested_active") or "")


def test_vehicle_follows_skin_and_climate_instead_of_naming_a_bare_ingredient():
    formula = ["Aqua", "Glycerin", "Phenoxyethanol"]
    heavy = ("cream", "balm", "butter", "oil")

    def products(rows):
        assert rows
        return [_product_text(row).lower() for row in rows]

    for skin in ("combination", "oily"):
        for climate in (None, "tropical_humid"):
            named = products(get_upgrade_suggestions(
                formula, ["Hydration"], skin_type=skin, climate=climate))
            for name in named:
                assert "urea" not in name
                assert not any(word in name for word in heavy)
                assert any(word in name for word in ("gel", "essence", "serum", "suspension"))
    humid = products(get_upgrade_suggestions(
        formula, ["Hydration"], skin_type="combination", climate="tropical_humid"))
    assert any("panthenol" in name or "polyglutamic" in name for name in humid)

    dry = products(get_upgrade_suggestions(
        formula, ["Hydration"], skin_type="dry", climate="cold_dry"))
    assert any("cream" in name for name in dry)

    normal = products(get_upgrade_suggestions(
        formula, ["Hydration"], skin_type="normal", climate="temperate"))
    assert all("urea" not in name for name in normal)
    assert any("serum" in name for name in normal)

    bright = products(get_upgrade_suggestions(
        formula, ["Tanning"], skin_type="combination", climate="tropical_humid"))
    assert any("water-based alpha arbutin essence" in name for name in bright)


def test_weak_niacinamide_for_pigmentation_recommends_azelaic_not_a_humectant():
    formula = ["Aqua", "Glycerin", "Disodium EDTA", "Niacinamide", "Phenoxyethanol"]
    fit = {
        "concerns": {
            "Pigmentation": {
                "score": 18,
                "present_actives": ["Niacinamide"],
                "explanation": [
                    "Contains Niacinamide, but it appears low in the ingredient "
                    "list, so it is likely below the concentration shown to work "
                    "for this concern."
                ],
            },
            "Hydration": {
                "score": 62,
                "present_actives": ["Glycerin"],
                "explanation": ["Contains Glycerin — well suited to this concern."],
            },
        }
    }
    rows = get_upgrade_suggestions(
        formula, ["Pigmentation", "Hydration"],
        skin_type="combination", climate="tropical_humid", concern_fit=fit,
    )
    assert rows
    lead = rows[0]
    assert "azelaic" in lead["suggested_active"].lower()
    assert lead["upgrade"].lower() == "10% azelaic acid suspension"
    assert "niacinamide" in lead["reason"].lower()
    assert "pigmentation" in lead["reason"].lower()
    for row in rows:
        assert "hydration" not in str(row.get("concern") or "").lower()
        assert "urea" not in _product_text(row).lower()
        assert not any(word in row["upgrade"].lower() for word in ("cream", "balm", "oil"))

    both = dict(fit)
    both["concerns"] = dict(fit["concerns"])
    both["concerns"]["Dullness"] = {
        "score": 13,
        "present_actives": ["Niacinamide"],
        "explanation": ["Contains Niacinamide. The dose is too low to treat this on its own."],
    }
    rows = get_upgrade_suggestions(
        formula, ["Pigmentation", "Dullness", "Hydration"],
        skin_type="combination", climate="tropical_humid", concern_fit=both,
    )
    names = [_product_text(row).lower() for row in rows]
    assert any("10% azelaic acid suspension" in name for name in names)
    assert any("water-based vitamin c essence" in name for name in names)
    assert all("urea" not in name and "cream" not in name for name in names)

    only_pigment = get_upgrade_suggestions(
        formula, ["Pigmentation"],
        skin_type="dry", climate="cold_dry", concern_fit=fit,
    )
    assert only_pigment
    assert "azelaic" in only_pigment[0]["suggested_active"].lower()
    assert "tranexamic" not in _product_text(only_pigment[0]).lower()
    assert "cream" in only_pigment[0]["upgrade"].lower()


def test_retinol_or_bha_in_the_routine_blocks_glycolic():
    formula = ["Aqua", "Glycerin", "Phenoxyethanol"]

    def blocked(routine, skin, climate):
        rows = get_upgrade_suggestions(
            formula, ["Texture"], skin_type=skin, climate=climate, routine=routine)
        assert rows
        for row in rows:
            product = _product_text(row).lower()
            assert "glycolic" not in product
            assert "salicylic" not in product
            assert "retinol" not in product
        return _upgrade_text(rows)

    humid = blocked("The Ordinary retinol 0.5%", "combination", "tropical_humid")
    assert "centella" in humid
    assert "gel" in humid
    assert "cream" not in humid

    dry = blocked("salicylic acid toner", "dry", "cold_dry")
    assert "ceramide" in dry or "centella" in dry


_HYPHEN = (
    "Aqua (Water), Coco-Caprylate, Citrus Nobilis Peel (Mandarin) Extract, "
    "Glycerin, Propanediol, Niacinamide, Sodium Polyglutamate Crosspolymer, "
    "Hippophae Rhamnoides (Sea Buckthorn) Oil, Psoralea Corylifolia (Bakuchiol), "
    "Rosa Canina Seed (Rose Hip) Oil, Centella Asiatica Callus Conditioned Media "
    "(Cica Stem Cell), Saccharide Isomerate, Sodium Levulinate, p-Anisic Acid, "
    "Xanthan Gum, Citric Acid, Phenoxyethanol"
)
_HYPHEN_CLAIMS = (
    "18% Brightening Complex: A blend of 11% Mandarin Extract, 5% Niacinamide, "
    "2% Polyglutamic Acid (PGA). 20% Collagen Complex: Bakuchiol, Rosehip Oil, "
    "Coco-Caprylate."
)


def _active(result, fragment):
    return next(
        row for row in result["identified_actives"]
        if fragment in row["name"].lower()
    )


def test_a_common_name_in_brackets_does_not_replace_the_inci():
    parsed = parse_ingredients(_HYPHEN)
    assert "Citrus Nobilis Peel Extract" in parsed
    assert "Mandarin" not in parsed
    media = data_loader.get_ingredient_data(
        "Centella Asiatica Callus Conditioned Media")
    plain = data_loader.get_ingredient_data("Centella Asiatica")
    assert media["INCI_Name"] == "Centella Asiatica Callus Conditioned Media"
    assert media["INCI_Name"] != plain["INCI_Name"]
    assert str(media.get("Evidence_Level_Normalized", "")).lower() != "strong"


def test_brand_claims_override_list_order_only_for_the_named_ingredient():
    parsed = parse_ingredients(_HYPHEN)
    bound = bind_declared_concentrations(parsed, {
        "vitamin c": 15,
        "brightening complex": 18,
        "collagen complex": 20,
    })
    assert 15 not in bound.values()
    assert 18 not in bound.values()
    assert 20 not in bound.values()

    bare = analyze_product({
        "ingredients": _HYPHEN, "price": 699, "size_ml": 50,
        "category": "Serum", "country": "India",
        "concerns": ["Pigmentation"], "skin_type": "normal",
    })
    named = analyze_product({
        "ingredients": _HYPHEN, "description": _HYPHEN_CLAIMS,
        "price": 699, "size_ml": 50, "category": "Serum", "country": "India",
        "concerns": ["Pigmentation"], "skin_type": "normal",
    })
    assert _active(bare, "niacinamide")["concentration_known"] is False
    assert _active(named, "niacinamide")["concentration_pct"] == 5
    assert _active(named, "citrus nobilis")["concentration_pct"] == 11
    assert _active(named, "polyglutamate")["concentration_pct"] == 2
    assert _active(named, "bakuchiol")["concentration_known"] is False
    present = [p.lower() for p in named["skin_concern_fit"]["Pigmentation"]["present_actives"]]
    assert any("citrus nobilis" in p for p in present)
    assert any("niacinamide" in p for p in present)
    notes = " ".join(flag["message"].lower() for flag in named["formulation_flags"])
    assert "two-phase" in notes
    assert "not ascorbic acid" in notes
    assert "cell-culture" in notes


def test_an_emulsified_cream_is_not_called_two_phase():
    result = score_formulation(
        parse_ingredients(
            "Aqua, Glycerin, Cetearyl Alcohol, Glyceryl Stearate, "
            "Caprylic/Capric Triglyceride, Phenoxyethanol"),
        {},
        "moisturizer",
    )
    notes = " ".join(flag["message"].lower() for flag in result["flags"])
    assert "two-phase" not in notes


def test_an_ungraded_extract_above_the_one_percent_line_is_named():
    result = score_formulation(
        ["Aqua", "Fictionalis Exemplaris Peel Extract", "Glycerin", "Xanthan Gum"],
        {},
        "serum",
    )
    notes = " ".join(flag["message"].lower() for flag in result["flags"])
    assert "fictionalis exemplaris peel extract" in notes
    assert "does not include" in notes

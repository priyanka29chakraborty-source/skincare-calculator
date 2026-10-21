"""Locks for the remaining review items.

Implemented only where a reproduced lookup or score was wrong and the
correction does not invent a concentration, a composition, or a new weight.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import data_loader  # noqa: E402
from evidence import _unsigned_names  # noqa: E402
from formulation import (  # noqa: E402
    CATEGORY_RUBRICS,
    _EXTRA_PRESERVATIVES,
    build_advisory_flags,
    score_formulation,
)
from scoring import (  # noqa: E402
    analyze_product,
    estimate_concentration,
    get_concentration_factor,
    get_evidence_factor,
    get_evidence_label,
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
    assert any(f["type"] == "above_published_ceiling" for f in above["flags"])
    assert "ceiling" in _notes(above, "tolerability")
    assert not any(f["type"] == "above_published_ceiling" for f in ceiling["flags"])


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


def test_pregnancy_unsigned_keeps_hydroquinone_when_text_says_safety():
    data = data_loader.get_ingredient_data("Hydroquinone")
    text = str(data.get("Pregnancy_Safety") or "").lower()
    assert "safe" in text
    pregnancy, _actives = _unsigned_names()
    assert any(name.lower() == "hydroquinone" for name in pregnancy)


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

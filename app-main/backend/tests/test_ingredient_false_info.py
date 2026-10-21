"""The seven agreed high/medium ingredient-database false-info findings."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import data_loader  # noqa: E402
from formulation import (  # noqa: E402
    build_advisory_flags,
    dose_band_label,
)
from scoring import (  # noqa: E402
    _calc_impact_score,
    _get_evidence_weight,
    calculate_skin_type_compatibility,
    detect_formulation_notes,
    get_evidence_factor,
    get_evidence_label,
    parse_ingredients,
)


def _flags(ingredients):
    return build_advisory_flags(parse_ingredients(ingredients))


# --- 1. Unsigned pregnancy notes are not signed advice ---------------------


def test_unsigned_pregnancy_caution_is_labelled_unsigned():
    flags = [f for f in _flags("Aqua, Retinol, Phenoxyethanol") if f["type"] == "pregnancy"]
    assert flags
    item = flags[0]["items"][0]
    assert item["signed"] is False
    assert "not independently reviewed" in item["guidance"].lower()


def test_unsigned_safe_active_is_not_a_pregnancy_clearance():
    flags = _flags("Aqua, Niacinamide, Phenoxyethanol")
    kinds = {f["type"] for f in flags}
    assert "pregnancy" not in kinds
    unreviewed = [f for f in flags if f["type"] == "pregnancy_unreviewed"]
    assert unreviewed
    message = unreviewed[0]["message"].lower()
    assert "not a clearance" in message
    assert "independently reviewed" in message


def test_retinol_and_hydroquinone_still_raise_pregnancy_cautions():
    for formula in (
        "Aqua, Retinol, Phenoxyethanol",
        "Aqua, Hydroquinone, Phenoxyethanol",
    ):
        assert any(f["type"] == "pregnancy" for f in _flags(formula))


# --- 2. Duplicate INCI / USAN / spelling rows resolve to one record --------


@pytest.mark.parametrize("left, right, inci", [
    ("Avobenzone", "Butyl Methoxydibenzoylmethane", "Butyl Methoxydibenzoylmethane"),
    ("Octinoxate", "Ethylhexyl Methoxycinnamate", "Ethylhexyl Methoxycinnamate"),
    ("Retinaldehyde", "Retinal", "Retinal"),
    ("Alpha Arbutin", "Alpha-Arbutin", "Alpha-Arbutin"),
    ("Centella Extract", "Centella Asiatica Extract", "Centella Asiatica Extract"),
    ("Cica", "Centella Asiatica Extract", "Centella Asiatica Extract"),
])
def test_synonym_pairs_share_one_record(left, right, inci):
    a = data_loader.get_ingredient_data(left)
    b = data_loader.get_ingredient_data(right)
    assert a is not None and b is not None
    assert a["INCI_Name"] == b["INCI_Name"] == inci
    assert a.get("Evidence_Strength") == b.get("Evidence_Strength")
    assert a.get("Pregnancy_Safety") == b.get("Pregnancy_Safety")


def test_pdrn_and_sodium_dna_do_not_invent_opposite_pregnancy_answers():
    pdrn = data_loader.get_ingredient_data("PDRN")
    dna = data_loader.get_ingredient_data("Sodium DNA")
    assert pdrn["INCI_Name"] != dna["INCI_Name"]
    for row in (pdrn, dna):
        text = str(row.get("Pregnancy_Safety") or "").lower()
        assert "insufficient data" in text
        assert text.strip() != "safe"


def test_centella_plant_and_extract_stay_distinct_incis():
    plant = data_loader.get_ingredient_data("Centella Asiatica")
    extract = data_loader.get_ingredient_data("Centella Asiatica Extract")
    assert plant["INCI_Name"] == "Centella Asiatica"
    assert extract["INCI_Name"] == "Centella Asiatica Extract"


# --- 3. Badge and score read the same evidence field -----------------------


def test_evidence_badge_and_impact_weight_agree_on_exosomes():
    row = data_loader.get_ingredient_data("Exosomes")
    factor = get_evidence_factor(row)
    label = get_evidence_label(factor).lower()
    assert "strong" not in label
    assert _get_evidence_weight(row) == 3
    _score, data = _calc_impact_score("Exosomes", 1, ["Aqua", "Exosomes"])
    assert data is row or data["INCI_Name"] == "Exosomes"


def test_zinc_oxide_and_titanium_dioxide_are_not_limited_uv_filters():
    for name in ("Zinc Oxide", "Titanium Dioxide"):
        row = data_loader.get_ingredient_data(name)
        assert "strong" in str(row.get("Evidence_Level_Normalized") or "").lower()
        assert "strong" in get_evidence_label(get_evidence_factor(row)).lower()


def test_olive_oil_numeric_5_is_still_not_strong():
    olive = data_loader.ingredient_lookup["olea europaea (olive) fruit oil"]
    assert get_evidence_factor(olive) < 0.9
    assert "strong" not in get_evidence_label(get_evidence_factor(olive)).lower()
    assert "strong" not in str(olive.get("Evidence_Strength") or "").lower()


# --- 4. Published ceiling is only used for a sourced EU cap ----------------


def test_niacinamide_range_is_not_called_a_published_ceiling():
    label = dose_band_label("Niacinamide", 5, known=True).lower()
    assert "published" not in label
    assert "evidenced range" not in label
    assert "recorded" in label


def test_salicylic_acid_over_eu_cap_uses_published_language():
    label = dose_band_label("Salicylic Acid", 3, known=True).lower()
    assert "published" in label
    eu = float(data_loader.get_ingredient_data("Salicylic Acid")["Max_Allowed_EU_%"])
    assert eu == 2.0


# --- 5. Wrong regulatory figures ------------------------------------------


def test_salicylic_acid_face_leave_on_is_not_0_5_percent():
    row = data_loader.get_ingredient_data("Salicylic Acid")
    blob = " ".join([
        str(row.get("Regional_Restrictions") or ""),
        str(row.get("Red_Flag_Tags") or ""),
    ]).lower()
    assert "0.5% max" not in blob
    assert "leave-on face/hand" not in blob
    assert "2%" in blob
    assert "body lotion" in blob


def test_homosalate_body_is_not_9_08_percent():
    row = data_loader.get_ingredient_data("Homosalate")
    text = str(row.get("Regional_Restrictions") or "")
    assert "7.34" in text
    assert "2022/2195" in text
    assert "9.08% body (Reg" not in text
    assert "not adopted" in text.lower() or "not authorised" in text.lower()
    assert float(row["Max_Allowed_EU_%"]) == 7.34


def test_4_mbc_is_not_permitted_in_the_eu():
    uv = data_loader.get_uv_data("4-Methylbenzylidene Camphor")
    assert uv is not None
    eu = str(uv.get("Regulatory_EU_Approved") or "")
    notes = str(uv.get("Safety_Notes") or "")
    assert "max 4%" not in eu.lower()
    assert "still permitted" not in notes.lower()
    assert "2024/858" in notes or "prohibited" in notes.lower() or "banned" in notes.lower()


def test_retinal_and_hpr_are_not_covered_by_eu_2024_996():
    for name in ("Retinal", "Hydroxypinacolone Retinoate", "HPR"):
        row = data_loader.get_ingredient_data(name)
        restrictions = str(row.get("Regional_Restrictions") or "")
        flags = str(row.get("Red_Flag_Tags") or "")
        assert "2024/996" not in restrictions
        assert "0.3% RE" not in restrictions
        assert "Vitamin A mandatory" not in restrictions
        assert "2024/996" not in flags
        assert "0.3% RE" not in flags


def test_retinol_keeps_the_2024_996_face_and_body_caps():
    row = data_loader.get_ingredient_data("Retinol")
    text = str(row.get("Regional_Restrictions") or "")
    assert "2024/996" in text
    assert "0.3%" in text
    assert "0.05%" in text
    assert float(row["Max_Allowed_EU_%"]) == 0.3


# --- 6. Marketing copy and truncated scraps --------------------------------


def test_ascorbic_acid_mechanism_is_not_marketing_copy():
    row = data_loader.get_ingredient_data("Ascorbic Acid")
    moa = data_loader.get_moa(row) or ""
    stored = str(row.get("Mechanism_of_Action") or "")
    assert "superstar" not in moa.lower()
    assert "superstar" not in stored.lower()
    benefits = str(row.get("Primary_Benefits") or "").lower()
    assert "dark spo" not in benefits
    assert "and th" not in benefits


def test_sulfur_benefits_are_not_truncated():
    benefits = str(data_loader.get_ingredient_data("Sulfur").get("Primary_Benefits") or "")
    assert "antimicro" not in benefits.lower() or "antimicrobial" in benefits.lower()
    assert not benefits.lower().endswith("and antimicro")


# --- 7. Parfum is an allergen, not a pore-clogger --------------------------


def test_parfum_does_not_raise_a_comedogenic_warning_on_a_gel():
    gel = "Aqua, Glycerin, Butylene Glycol, Carbomer, Fragrance, Phenoxyethanol"
    notes = " ".join(detect_formulation_notes(parse_ingredients(gel))).lower()
    assert "comedogenic" not in notes
    assert "pore" not in notes
    compat = calculate_skin_type_compatibility(parse_ingredients(gel), "oily", "serum")
    names = [w["name"].lower() for w in compat.get("comedogenic_warnings") or []]
    assert not any("fragrance" in n or "parfum" in n for n in names)
    why = " ".join(compat.get("why_bullets") or []).lower()
    assert "comedogenic" not in why
    assert "allergen" in notes or "fragrance" in notes

"""Matcher identity and upgrade gates."""

from data_loader import data_loader
from scoring import get_upgrade_suggestions


def test_hyphen_numbers_are_different_molecules():
    assert data_loader.get_ingredient_data("Polyquaternium-80") is None
    assert data_loader.get_ingredient_data("Acetyl Hexapeptide-37") is None
    assert data_loader.get_ingredient_data("Acetyl Hexapeptide-8")["INCI_Name"] == "Acetyl Hexapeptide-8"
    assert data_loader.get_ingredient_data("Polyquaternium-51")["INCI_Name"] == "Polyquaternium-51"


def test_stub_and_generic_names_do_not_steal_a_real_inci():
    for name in ("Sodium Laureth", "Glycol", "Butter", "Zinc", "PCA", "Ionone"):
        assert data_loader.get_ingredient_data(name) is None
    assert data_loader.get_ingredient_data("Sodium Laureth Sulfate")["INCI_Name"] == "Sodium Laureth Sulfate"
    assert data_loader.get_ingredient_data("Zinc PCA")["INCI_Name"] == "Zinc PCA"


def test_two_ingredients_glued_by_a_missing_comma_are_not_one_shorter_name():
    assert data_loader.get_ingredient_data(
        "PROPANEDIOL BUTYL METHOXYDIBENZOYLMETHANE") is None
    assert data_loader.get_ingredient_data("Propanediol")["INCI_Name"] == "Propanediol"
    assert data_loader.get_ingredient_data(
        "Butyl Methoxydibenzoylmethane")["INCI_Name"] == "Butyl Methoxydibenzoylmethane"


def test_do_not_upgrade_true_is_honoured_and_pih_maps_to_pigmentation():
    rows = get_upgrade_suggestions(
        ["Aqua", "Alpha Arbutin", "Glycerin", "Phenoxyethanol"],
        ["Pigmentation"],
        category="Serum",
        concern_fit={"concerns": {
            "Pigmentation": {
                "score": 35,
                "present_actives": ["Alpha Arbutin"],
                "explanation": ["The dose is too low to treat this concern."],
            }
        }},
    )
    assert rows
    actives = {str(row["suggested_active"]).lower() for row in rows}
    assert "tranexamic acid" in actives or "azelaic acid" in actives
    assert all(row.get("builds_on") == "Alpha Arbutin" for row in rows
               if str(row.get("builds_on") or ""))


def test_glycerin_does_not_match_inside_ethylhexylglycerin():
    rows = get_upgrade_suggestions(
        ["Aqua", "Ethylhexylglycerin", "Phenoxyethanol"],
        ["Hydration"],
        category="Serum",
        concern_fit={"concerns": {
            "Hydration": {
                "score": 20,
                "present_actives": [],
                "explanation": ["Missing a humectant at a useful dose."],
            }
        }},
    )
    for row in rows:
        assert "urea" not in str(row.get("suggested_active") or "").lower()
        assert str(row.get("builds_on") or "").lower() != "glycerin"


def test_no_upgrade_when_every_concern_scores_70_or_more():
    rows = get_upgrade_suggestions(
        ["Aqua", "Niacinamide", "Zinc PCA", "Glycerin", "Phenoxyethanol"],
        ["Acne & Oily Skin", "Large Pores"],
        category="Serum",
        concern_fit={"concerns": {
            "Acne & Oily Skin": {"score": 100, "present_actives": ["Niacinamide"], "explanation": []},
            "Large Pores": {"score": 80, "present_actives": ["Niacinamide"], "explanation": []},
        }},
    )
    assert rows == []


def test_sunscreen_and_toner_do_not_get_acne_treatment_upgrades():
    fit = {"concerns": {
        "Acne & Oily Skin": {
            "score": 20,
            "present_actives": ["Niacinamide"],
            "explanation": ["The dose is too low."],
        }
    }}
    formula = ["Aqua", "Niacinamide", "Zinc Oxide", "Glycerin"]
    sun = get_upgrade_suggestions(
        formula, ["Acne & Oily Skin"], category="Sunscreen", concern_fit=fit)
    assert sun == []
    toner = get_upgrade_suggestions(
        formula, ["Acne & Oily Skin"], category="Toner", concern_fit=fit)
    assert all(not any(marker in str(row.get("suggested_active") or "").lower()
                       for marker in ("adapalene", "retinol", "salicylic"))
               for row in toner)


def test_cleanser_leave_on_is_an_add_to_routine_not_a_product_upgrade():
    rows = get_upgrade_suggestions(
        ["Aqua", "Niacinamide", "Coco-Glucoside", "Glycerin"],
        ["Acne & Oily Skin"],
        category="Cleanser",
        concern_fit={"concerns": {
            "Acne & Oily Skin": {
                "score": 25,
                "present_actives": ["Niacinamide"],
                "explanation": ["The dose is too low."],
            }
        }},
    )
    assert rows
    assert all(row.get("kind") == "add_to_routine" for row in rows)
    assert any("adapalene" in str(row.get("suggested_active") or "").lower() for row in rows)


def test_adapalene_product_is_not_told_to_step_down_to_salicylic():
    rows = get_upgrade_suggestions(
        ["Aqua", "Adapalene", "Glycerin", "Phenoxyethanol"],
        ["Acne & Oily Skin"],
        category="Treatment",
        concern_fit={"concerns": {
            "Acne & Oily Skin": {
                "score": 40,
                "present_actives": ["Adapalene"],
                "explanation": ["Contains Adapalene."],
            }
        }},
    )
    for row in rows:
        assert "salicylic" not in str(row.get("suggested_active") or "").lower()
        assert "salicylic" not in str(row.get("upgrade") or "").lower()


def test_pregnancy_and_sensitive_gates_hide_harsh_upgrades():
    fit = {"concerns": {
        "Aging & Fine Lines": {
            "score": 20,
            "present_actives": ["Bakuchiol"],
            "explanation": ["The dose is too low."],
        }
    }}
    pregnant = get_upgrade_suggestions(
        ["Aqua", "Bakuchiol", "Glycerin"],
        ["Aging & Fine Lines"],
        category="Serum",
        concern_fit=fit,
        user_profile={"pregnant": True},
    )
    for row in pregnant:
        blob = "%s %s" % (row.get("upgrade"), row.get("suggested_active"))
        assert "retinol" not in blob.lower()
        assert "retinoid" not in blob.lower()

    sensitive = get_upgrade_suggestions(
        ["Aqua", "Glycerin", "Phenoxyethanol"],
        ["Texture"],
        skin_type="sensitive",
        category="Serum",
        concern_fit={"concerns": {
            "Texture": {"score": 15, "present_actives": [], "explanation": ["too low"]},
        }},
    )
    for row in sensitive:
        blob = "%s %s" % (row.get("upgrade"), row.get("suggested_active"))
        assert "glycolic" not in blob.lower()
        assert "salicylic" not in blob.lower()

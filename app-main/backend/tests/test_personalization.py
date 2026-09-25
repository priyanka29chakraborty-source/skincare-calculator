"""Personal context: Fitzpatrick, climate, allergies, current routine.

The invariant these tests exist to protect:

    Personal context may change the Fit score and raise advisories.
    It may NEVER change the formulation score.

A product is not better made because it suits your skin, and not worse made
because you are allergic to something in it. If that separation ever breaks,
two users scanning the same product see different answers to "how well is this
made", which is the one thing that score is supposed to mean.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from personalization import (  # noqa: E402
    ALLERGEN_GROUPS,
    CLIMATE,
    FITZPATRICK,
    build_personal_context,
    check_routine,
    detect_families,
    parse_routine,
)
from scoring import analyze_product, parse_ingredients  # noqa: E402

FRAGRANCED_AHA = ("Aqua, Glycolic Acid, Glycerin, Niacinamide, Parfum, Limonene, "
                  "Panthenol, Phenoxyethanol")


def _analyze(profile=None, ingredients=FRAGRANCED_AHA, concerns=None):
    return analyze_product({
        "ingredients": ingredients, "price": 599, "size_ml": 30,
        "category": "Serum", "concerns": concerns or ["Uneven Texture"],
        "skin_type": "combination", "country": "India", "currency": "INR",
        "user_profile": profile or {}})


def _fit(result):
    return {k: (v.get("score") if isinstance(v, dict) else v)
            for k, v in result["skin_concern_fit"].items()}


# --- The core invariant -----------------------------------------------------


def test_personal_context_never_changes_the_formulation_score():
    plain = _analyze()
    personalised = _analyze({
        "fitzpatrick": "V", "climate": "tropical_humid",
        "allergens": ["fragrance"], "current_routine": "The Ordinary Retinol 0.5%"})
    assert plain["formulation_score"] == personalised["formulation_score"], (
        "personal context leaked into formulation quality")


@pytest.mark.parametrize("profile", [
    {"fitzpatrick": "I"}, {"fitzpatrick": "VI"},
    {"climate": "tropical_humid"}, {"climate": "cold_dry"},
    {"allergens": ["fragrance", "essential_oils", "silicones"]},
    {"current_routine": "retinol, vitamin c, glycolic acid"},
])
def test_no_single_answer_changes_formulation(profile):
    assert _analyze(profile)["formulation_score"] == _analyze()["formulation_score"]


def test_scoring_module_does_not_consult_personal_fields():
    """Structural guard, so this cannot regress when someone adds a scorer."""
    import inspect

    import formulation

    for name, fn in vars(formulation).items():
        if not inspect.isfunction(fn):
            continue
        if not (name.startswith("_score") or name == "score_formulation"):
            continue
        src = inspect.getsource(fn)
        # Only USER-PROFILE fields are forbidden here. A product legitimately
        # contains EU-declarable allergens, and noting that is formulation
        # information - what must not appear is anything about who the user is.
        for field in ("fitzpatrick", "current_routine", "user_profile",
                      "declared_allergen\"", "climate_pref"):
            assert field not in src, (
                "{} reads personal field {} - that belongs in personalization.py"
                .format(name, field))


# --- Answering nothing must reproduce previous behaviour --------------------


def test_empty_profile_is_completely_inert():
    ctx = build_personal_context({}, parse_ingredients(FRAGRANCED_AHA),
                                 ["Uneven Texture"], "serum", None)
    assert ctx["fit_penalty"] == 0
    assert ctx["flags"] == []
    assert ctx["personalisation_level"] == "none"


def test_climate_is_suggested_from_country_but_never_invented():
    assert build_personal_context({}, [], [], "serum", "India")["climate"] == "tropical_humid"
    assert build_personal_context({}, [], [], "serum", "Atlantis")["climate"] is None


# --- Allergies --------------------------------------------------------------


def test_declared_allergy_reduces_fit_but_not_quality():
    plain, allergic = _analyze(), _analyze({"allergens": ["fragrance"]})
    assert allergic["formulation_score"] == plain["formulation_score"]
    plain_fit = _fit(plain)
    assert all(score < plain_fit[c] for c, score in _fit(allergic).items())
    assert any(f["type"] == "declared_allergen" for f in allergic["advisory_flags"])


def test_allergy_that_does_not_match_changes_nothing():
    """Declaring a lanolin allergy on a lanolin-free product must be a no-op."""
    plain, declared = _analyze(), _analyze({"allergens": ["lanolin"]})
    assert _fit(declared) == _fit(plain)
    assert not any(f["type"] == "declared_allergen" for f in declared["advisory_flags"])


@pytest.mark.parametrize("group", sorted(ALLERGEN_GROUPS))
def test_every_allergen_group_is_detectable(group):
    marker = ALLERGEN_GROUPS[group]["markers"][0]
    ctx = build_personal_context({"allergens": [group]},
                                 ["Aqua", marker.title(), "Phenoxyethanol"],
                                 [], "serum", None)
    assert any(f["type"] == "declared_allergen" for f in ctx["flags"]), group


# --- Routine ----------------------------------------------------------------


def test_routine_free_text_is_parsed_into_families():
    assert "retinoid" in parse_routine("I use The Ordinary Retinol 0.5% at night")
    assert "vitamin_c" in parse_routine(["Klairs Vitamin C serum", "a moisturiser"])
    assert parse_routine("") == set()


def test_retinoid_plus_acid_is_flagged_as_a_conflict():
    flags, _ = check_routine(parse_ingredients(FRAGRANCED_AHA), {"retinoid"})
    assert any(f["type"] == "routine_conflict" for f in flags)


def test_buying_a_second_of_the_same_active_is_flagged_as_redundant():
    flags, _ = check_routine(parse_ingredients("Aqua, Retinol, Squalane"), {"retinoid"})
    assert any(f["type"] == "routine_redundant" for f in flags)


def test_unrelated_routine_raises_nothing():
    flags, _ = check_routine(parse_ingredients("Aqua, Glycerin, Panthenol"),
                             {"niacinamide"})
    assert flags == []


def test_detect_families_finds_actives_in_the_product():
    families = detect_families(parse_ingredients(FRAGRANCED_AHA))
    assert "aha" in families
    assert "niacinamide" in families


# --- Fitzpatrick ------------------------------------------------------------


@pytest.mark.parametrize("tone", sorted(FITZPATRICK))
def test_every_fitzpatrick_tone_is_accepted(tone):
    assert _analyze({"fitzpatrick": tone})["formulation_score"] > 0


def test_higher_phototypes_get_a_pih_advisory_on_irritants():
    high = _analyze({"fitzpatrick": "V"})
    assert any(f["type"] == "pih_risk" for f in high["advisory_flags"])


def test_low_phototype_gets_burn_advisory_not_pih():
    low = _analyze({"fitzpatrick": "I"})
    types = {f["type"] for f in low["advisory_flags"]}
    assert "burn_risk" in types
    assert "pih_risk" not in types


# --- Climate ----------------------------------------------------------------


@pytest.mark.parametrize("climate", sorted(CLIMATE))
def test_every_climate_is_accepted(climate):
    assert _analyze({"climate": climate})["formulation_score"] > 0


def test_humid_climate_flags_heavy_occlusive_as_comfort_not_defect():
    result = analyze_product({
        "ingredients": "Aqua, Glycerin, Petrolatum, Cetearyl Alcohol, Phenoxyethanol",
        "price": 500, "size_ml": 100, "category": "Moisturizer",
        "concerns": ["Hydration"], "skin_type": "oily", "country": "India",
        "currency": "INR", "user_profile": {"climate": "tropical_humid"}})
    flags = [f for f in result["advisory_flags"] if f["type"] == "climate_texture"]
    assert flags
    assert flags[0]["severity"] == "info", "texture comfort is not a formulation defect"


# --- Reporting --------------------------------------------------------------


def test_personalisation_level_reflects_answers_given():
    assert _analyze()["personalisation"]["level"] == "none"
    assert _analyze({"fitzpatrick": "IV"})["personalisation"]["level"] == "partial"
    assert _analyze({"fitzpatrick": "IV", "climate": "temperate",
                     "allergens": ["fragrance"]})["personalisation"]["level"] == "high"


@pytest.mark.parametrize("concern", [
    "Post-Inflammatory Hyperpigmentation", "Redness & Rosacea",
    "Blackheads & Congestion", "Loss of Firmness",
    "Eczema-Prone Skin", "Hormonal Breakouts",
])
def test_new_concerns_are_scorable(concern):
    """The added concerns must produce real scores, not silently fall through
    to a default the way an unrecognised concern would."""
    result = _analyze(
        concerns=[concern],
        ingredients="Aqua, Azelaic Acid, Niacinamide, Glycerin, Panthenol, "
                    "Allantoin, Ceramide NP, Phenoxyethanol")
    score = _fit(result).get(concern)
    assert score is not None, "{} produced no score".format(concern)
    assert 0 <= score <= 100

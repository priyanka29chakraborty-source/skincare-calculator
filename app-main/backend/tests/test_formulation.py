"""Tests for the formulation scoring engine.

These are not coverage padding. Each test encodes a property the product is
supposed to guarantee, and most of them correspond to a bug that was actually
found in the previous engine:

  - the headline score did not match the breakdown shown beside it
  - price was 25% of a *quality* score, capping excellent-but-expensive
    products at 75 regardless of how they were made
  - a moisturiser could not exceed 49/100 however well formulated
  - sunscreen had no category branch at all and fell through to a generic path
  - a negative price returned the *maximum* price score
  - pregnancy data was wired into scoring in a way that penalised products for
    a user-specific circumstance

Run with:  python -m pytest tests/ -q     (from the backend/ directory)
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from formulation import (  # noqa: E402
    CATEGORY_RUBRICS,
    build_advisory_flags,
    resolve_category,
    score_formulation,
    score_value,
)
from scoring import analyze_product, estimate_concentration, parse_ingredients  # noqa: E402


# --- Fixtures: real products, used as calibration anchors -------------------

CERAVE_CREAM = (
    "Aqua, Glycerin, Cetearyl Alcohol, Caprylic/Capric Triglyceride, Cetyl "
    "Alcohol, Ceramide NP, Ceramide AP, Ceramide EOP, Carbomer, Dimethicone, "
    "Behentrimonium Methosulfate, Sodium Lauroyl Lactylate, Sodium Hyaluronate, "
    "Cholesterol, Phenoxyethanol, Disodium EDTA, Dipotassium Phosphate, "
    "Potassium Phosphate, Tocopherol, Phytosphingosine, Xanthan Gum, "
    "Ethylhexylglycerin"
)
CE_FERULIC = (
    "Aqua, Ethoxydiglycol, Ascorbic Acid, Propylene Glycol, Glycerin, "
    "Laureth-23, Panthenol, Ferulic Acid, Tocopherol, Sodium Hyaluronate, "
    "Triethanolamine, Phenoxyethanol"
)
ORDINARY_NIACINAMIDE = (
    "Aqua, Niacinamide, Pentylene Glycol, Zinc PCA, Dimethyl Isosorbide, "
    "Tamarindus Indica Seed Gum, Xanthan Gum, Isoceteth-20, Ethoxydiglycol, "
    "Phenoxyethanol, Chlorphenesin"
)
BOJ_SUNSCREEN = (
    "Aqua, Oryza Sativa Extract, Dibutyl Adipate, Glycerin, Diphenylsiloxy "
    "Phenyl Trimethicone, Niacinamide, Ethylhexyl Triazone, Butyl "
    "Methoxydibenzoylmethane, Cetyl Ethylhexanoate, Bis-Ethylhexyloxyphenol "
    "Methoxyphenyl Triazine, Diethylamino Hydroxybenzoyl Hexyl Benzoate, "
    "Pentylene Glycol, Panthenol, Butyrospermum Parkii Butter, Centella "
    "Asiatica Extract, Tocopherol"
)
FILLER_SERUM = "Aqua, Glycerin, Phenoxyethanol, Parfum"
IRRITANT_SERUM = (
    "Aqua, Alcohol Denat, Parfum, Limonene, Linalool, Cocos Nucifera Oil, "
    "Citrus Bergamia Oil, Phenoxyethanol"
)


def score(ingredients, category, known=None):
    il = parse_ingredients(ingredients)
    conc = estimate_concentration(il, known)
    return score_formulation(il, conc, category, known_concentrations=known)


# --- Structural invariants --------------------------------------------------


@pytest.mark.parametrize("cat_key", sorted(CATEGORY_RUBRICS))
def test_every_rubric_sums_to_100(cat_key):
    """The headline score must be the sum of the components shown beside it.

    In the previous engine the displayed A-E breakdown summed to 100 while the
    real score was 0.75*formula + 0.25*price, so two of the five components
    shown to the user did not affect the number at all.
    """
    total = sum(w for _, _, w in CATEGORY_RUBRICS[cat_key]["components"])
    assert total == 100, "{} rubric sums to {}".format(cat_key, total)


@pytest.mark.parametrize("cat_key", sorted(CATEGORY_RUBRICS))
def test_breakdown_sums_to_headline_score(cat_key):
    result = score(CERAVE_CREAM, cat_key)
    component_total = sum(c["score"] for c in result["components"])
    assert abs(component_total - result["score"]) <= 1.0, (
        "{}: components sum to {} but score is {}".format(
            cat_key, component_total, result["score"]))


@pytest.mark.parametrize("cat_key", sorted(CATEGORY_RUBRICS))
def test_no_component_exceeds_its_budget(cat_key):
    result = score(CERAVE_CREAM, cat_key)
    for c in result["components"]:
        assert 0 <= c["score"] <= c["max"], (
            "{}/{}: {} outside 0..{}".format(
                cat_key, c["label"], c["score"], c["max"]))


# --- The ceiling must be reachable in every category ------------------------
# This is the property the whole redesign exists to guarantee. Previously a
# moisturiser capped at 49 and a sunscreen at 60, so the scale was meaningless.

IDEAL = {
    "serum": "Aqua, Niacinamide, Ascorbic Acid, Glycerin, Panthenol, Sodium "
             "Hyaluronate, Ceramide NP, Cholesterol, Stearic Acid, Tocopherol, "
             "Ferulic Acid, Citric Acid, Disodium EDTA, Phenoxyethanol",
    "moisturizer": "Aqua, Glycerin, Ceramide NP, Ceramide AP, Cholesterol, "
                   "Stearic Acid, Squalane, Petrolatum, Dimethicone, Sodium "
                   "Hyaluronate, Panthenol, Niacinamide, Tocopherol, Citric "
                   "Acid, Disodium EDTA, Phenoxyethanol",
    "cleanser": "Aqua, Cocamidopropyl Betaine, Coco-Glucoside, Sodium Cocoyl "
                "Isethionate, Glycerin, Panthenol, Ceramide NP, Cholesterol, "
                "Stearic Acid, Sodium Hyaluronate, Citric Acid, Disodium EDTA, "
                "Phenoxyethanol",
    "sunscreen": "Aqua, Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine, "
                 "Ethylhexyl Triazone, Diethylamino Hydroxybenzoyl Hexyl "
                 "Benzoate, Zinc Oxide, Glycerin, Niacinamide, Tocopherol, "
                 "Panthenol, Citric Acid, Disodium EDTA, Phenoxyethanol",
    "toner": "Aqua, Glycerin, Sodium Hyaluronate, Panthenol, Centella Asiatica "
             "Extract, Allantoin, Niacinamide, Betaine, Sodium PCA, Citric "
             "Acid, Phenoxyethanol",
    "eye cream": "Aqua, Glycerin, Sodium Hyaluronate, Panthenol, Ceramide NP, "
                 "Cholesterol, Stearic Acid, Caffeine, Palmitoyl Pentapeptide-4, "
                 "Niacinamide, Tocopherol, Citric Acid, Disodium EDTA, "
                 "Phenoxyethanol",
    "mask": "Aqua, Glycerin, Sodium Hyaluronate, Panthenol, Betaine, Centella "
            "Asiatica Extract, Allantoin, Madecassoside, Niacinamide, Citric "
            "Acid, Disodium EDTA, Phenoxyethanol",
    "facial oil": "Rosa Canina Fruit Oil, Simmondsia Chinensis Seed Oil, "
                  "Helianthus Annuus Seed Oil, Squalane, Tocopherol, Bisabolol",
    "treatment": "Aqua, Benzoyl Peroxide, Glycerin, Panthenol, Allantoin, "
                 "Sodium Hyaluronate, Citric Acid, Disodium EDTA, Phenoxyethanol",
}


@pytest.mark.parametrize("cat_key,ingredients", sorted(IDEAL.items()))
def test_excellent_formula_can_score_highly(cat_key, ingredients):
    result = score(ingredients, cat_key)
    assert result["score"] >= 85, (
        "A deliberately excellent {} scores only {}/100 - the scale is not "
        "reachable in this category".format(cat_key, result["score"]))


# --- Price must never influence formulation quality -------------------------


def test_price_cannot_change_the_formulation_score():
    """The core separation. An excellent expensive product and the same formula
    priced cheaply must score identically on formulation."""
    cheap = analyze_product({
        "ingredients": CE_FERULIC, "price": 200, "size_ml": 30,
        "category": "Serum", "concerns": [], "skin_type": "normal",
        "country": "India", "currency": "INR"})
    dear = analyze_product({
        "ingredients": CE_FERULIC, "price": 25000, "size_ml": 30,
        "category": "Serum", "concerns": [], "skin_type": "normal",
        "country": "India", "currency": "INR"})
    assert cheap["formulation_score"] == dear["formulation_score"]
    # ...but the value verdict must differ.
    assert cheap["value_assessment"]["tier"] != dear["value_assessment"]["tier"]


def test_expensive_excellent_product_is_not_capped():
    """CE Ferulic at its real price. Under the old engine this could not exceed
    75 because price was 25% of the score; it scored 46."""
    result = analyze_product({
        "ingredients": CE_FERULIC, "price": 16000, "size_ml": 30,
        "category": "Serum", "concerns": [], "skin_type": "normal",
        "country": "India", "currency": "INR"})
    assert result["formulation_score"] >= 85
    assert result["value_assessment"]["tier"] in ("premium", "luxury")


def test_negative_price_does_not_produce_a_good_value_verdict():
    """Previously `not price` was False for negatives, so a negative price fell
    through to the ratio branch and returned the maximum price score."""
    v = score_value(-500, 30, "Serum", "India")
    assert v["available"] is False
    assert v["tier"] == "unknown"


@pytest.mark.parametrize("price,size", [(0, 30), (100, 0), (100, -5), (-1, -1)])
def test_value_handles_degenerate_price_and_size(price, size):
    v = score_value(price, size, "Serum", "India")
    assert v["available"] is False


# --- Pregnancy is user context, never a formulation defect ------------------


def test_pregnancy_guidance_does_not_reduce_the_formulation_score():
    """A retinol serum is not badly made because it is unsuitable in pregnancy.

    Retinol is the strongest possible case: the database marks it "Strictly
    Avoid - teratogenic". It is also an excellent, well-evidenced anti-ageing
    active. A well-built retinol serum must therefore still score highly, with
    the pregnancy issue surfaced as advice rather than as a deduction.
    """
    retinol = "Aqua, Glycerin, Retinol, Squalane, Tocopherol, Phenoxyethanol"
    result = score(retinol, "serum")
    flags = build_advisory_flags(parse_ingredients(retinol))
    preg = [f for f in flags if f["type"] == "pregnancy"]

    assert preg, "retinol should raise a pregnancy advisory"
    assert preg[0]["affects_score"] is False
    assert result["score"] >= 85, (
        "a well-formulated retinol serum scored only {} - a pregnancy "
        "contraindication appears to be penalising formulation quality"
        .format(result["score"]))


def test_scoring_engine_never_reads_pregnancy_data():
    """Structural guarantee, not a behavioural one.

    The scoring functions must not consult Pregnancy_Safety at all - it is
    consumed exclusively by build_advisory_flags. This is the invariant that
    keeps user circumstance out of product quality permanently, even if someone
    later adds a new component scorer.
    """
    import inspect

    import formulation

    scorers = [obj for name, obj in vars(formulation).items()
               if inspect.isfunction(obj)
               and (name.startswith("_score") or name == "score_formulation")]
    assert scorers, "no scoring functions found to check"
    for fn in scorers:
        src = inspect.getsource(fn)
        assert "Pregnancy" not in src, (
            "{} reads pregnancy data; it must stay in build_advisory_flags"
            .format(fn.__name__))


def test_pregnancy_advisory_catches_insufficient_data_wording():
    """The old substring check matched only 'avoid'/'restrict', missing
    "Insufficient data; consult doctor before use in pregnancy" - about a
    quarter of the ingredient database."""
    from formulation import _PREGNANCY_CAUTION
    phrase = "insufficient data; consult doctor before use in pregnancy"
    assert any(c in phrase for c in _PREGNANCY_CAUTION)


# --- Category logic must reflect what the product is for --------------------


def test_cleanser_does_not_reward_actives():
    """A cleanser is rinsed off in under a minute. Loading it with actives is a
    marketing move, not a formulation improvement, and must not raise the score
    the way it would for a leave-on serum."""
    plain = "Aqua, Cocamidopropyl Betaine, Coco-Glucoside, Glycerin, Phenoxyethanol"
    stuffed = ("Aqua, Cocamidopropyl Betaine, Coco-Glucoside, Glycerin, "
               "Niacinamide, Retinol, Ascorbic Acid, Salicylic Acid, "
               "Phenoxyethanol")
    assert score(stuffed, "cleanser")["score"] <= score(plain, "cleanser")["score"] + 6
    keys = {c["key"] for c in score(stuffed, "cleanser")["components"]}
    assert "actives" not in keys, "cleanser rubric must not contain an actives component"


def test_harsh_surfactant_scores_below_mild():
    sls = "Aqua, Sodium Lauryl Sulfate, Sodium Chloride, Citric Acid, Phenoxyethanol"
    mild = ("Aqua, Cocamidopropyl Betaine, Coco-Glucoside, Sodium Cocoyl "
            "Isethionate, Citric Acid, Phenoxyethanol")
    assert score(sls, "cleanser")["score"] < score(mild, "cleanser")["score"]


def test_unstabilised_avobenzone_is_penalised():
    """Avobenzone is photounstable alone and needs a stabilising partner."""
    unstable = "Aqua, Butyl Methoxydibenzoylmethane, Glycerin, Carbomer, Phenoxyethanol"
    result = score(unstable, "sunscreen")
    photo = next(c for c in result["components"] if c["key"] == "photostability")
    assert photo["score"] < photo["max"] * 0.5
    assert any(f["type"] == "photounstable_system" for f in result["flags"])


def test_sunscreen_is_scored_on_its_filter_system_not_filter_count():
    """A compact photostable system must beat a larger unstable one."""
    few_stable = ("Aqua, Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine, "
                  "Zinc Oxide, Glycerin, Phenoxyethanol")
    many_unstable = ("Aqua, Butyl Methoxydibenzoylmethane, Ethylhexyl "
                     "Methoxycinnamate, Glycerin, Phenoxyethanol")
    assert score(few_stable, "sunscreen")["score"] > score(many_unstable, "sunscreen")["score"]


def test_sunscreen_without_filters_scores_near_zero():
    result = score("Aqua, Glycerin, Niacinamide, Phenoxyethanol", "sunscreen")
    assert result["score"] < 30
    assert any(f["type"] == "no_uv_filter" for f in result["flags"])


def test_complete_lipid_set_beats_ceramides_alone():
    """Applying one or two of the three physiological lipids delays barrier
    recovery; only the complete set restores it (Mao-Qiang 1993/1995, Man 1996).
    """
    complete = ("Aqua, Glycerin, Ceramide NP, Cholesterol, Stearic Acid, "
                "Squalane, Phenoxyethanol")
    ceramide_only = "Aqua, Glycerin, Ceramide NP, Squalane, Phenoxyethanol"
    c_barrier = next(c for c in score(complete, "moisturizer")["components"]
                     if c["key"] == "barrier")
    o_barrier = next(c for c in score(ceramide_only, "moisturizer")["components"]
                     if c["key"] == "barrier")
    assert c_barrier["score"] > o_barrier["score"]


def test_moisturiser_without_actives_is_not_punished():
    """An excellent plain cream is still an excellent cream. Actives are a
    bonus component in this category, not a requirement."""
    plain = ("Aqua, Glycerin, Ceramide NP, Cholesterol, Stearic Acid, "
             "Petrolatum, Squalane, Sodium Hyaluronate, Citric Acid, "
             "Disodium EDTA, Phenoxyethanol")
    assert score(plain, "moisturizer")["score"] >= 75


def test_anhydrous_product_not_penalised_for_lacking_preservative():
    """Water-free formulas do not support microbial growth."""
    oil = "Squalane, Rosa Canina Fruit Oil, Tocopherol"
    result = score(oil, "facial oil")
    assert not any(f["type"] == "no_preservative" for f in result["flags"])


def test_water_based_product_without_preservative_is_flagged():
    result = score("Aqua, Glycerin, Niacinamide", "serum")
    assert any(f["type"] == "no_preservative" for f in result["flags"])


# --- Calibration against real products (regression guard) -------------------


@pytest.mark.parametrize("name,ingredients,category,floor", [
    ("CeraVe Moisturising Cream", CERAVE_CREAM, "moisturizer", 75),
    ("SkinCeuticals CE Ferulic", CE_FERULIC, "serum", 85),
    ("The Ordinary Niacinamide", ORDINARY_NIACINAMIDE, "serum", 80),
    ("Beauty of Joseon Relief Sun", BOJ_SUNSCREEN, "sunscreen", 80),
])
def test_well_regarded_products_score_well(name, ingredients, category, floor):
    result = score(ingredients, category)
    assert result["score"] >= floor, "{} scored {}".format(name, result["score"])


@pytest.mark.parametrize("name,ingredients,category,ceiling", [
    ("filler serum", FILLER_SERUM, "serum", 45),
    ("irritant serum", IRRITANT_SERUM, "serum", 50),
])
def test_poor_products_score_poorly(name, ingredients, category, ceiling):
    result = score(ingredients, category)
    assert result["score"] <= ceiling, "{} scored {}".format(name, result["score"])


def test_good_and_bad_are_clearly_separated():
    good = score(CERAVE_CREAM, "moisturizer")["score"]
    bad = score("Aqua, Alcohol Denat, Parfum, Limonene, Carbomer, Phenoxyethanol",
                "moisturizer")["score"]
    assert good - bad >= 30, (
        "only {} points separate an excellent moisturiser from a bad one"
        .format(good - bad))


# --- Robustness -------------------------------------------------------------


@pytest.mark.parametrize("ingredients", [
    "", "   ", "asdkjh 123 !!! qqq", "Aqua", ", , , ,",
    ", ".join(["Niacinamide"] * 20),
    ", ".join("Fakeingredient{}".format(i) for i in range(500)),
    "Aqua, Niacinamide \U0001F4A7, Glycérine",
    "Ceramides, Humectants, Antioxidants",
])
def test_scoring_never_crashes_and_stays_in_range(ingredients):
    for category in ("serum", "moisturizer", "cleanser", "sunscreen"):
        result = score(ingredients, category)
        assert 0 <= result["score"] <= 100


def test_concept_records_are_not_treated_as_dosed_actives():
    """The database contains concept-level pseudo-ingredients ("Ceramides",
    "Humectants") alongside real INCI entries. They must not be scored as if a
    product contained a dosed active by that name."""
    result = score("Aqua, Ceramides, Peptides, Antioxidants, Phenoxyethanol",
                   "serum")
    actives = next(c for c in result["components"] if c["key"] == "actives")
    assert actives["score"] == 0


def test_unknown_category_falls_back_without_crashing():
    assert resolve_category("Potion") == "serum"
    assert score(CERAVE_CREAM, "Potion")["score"] > 0


def test_confidence_is_reported_honestly():
    """Below the 1% line, EU 1223/2009 Art. 19 permits any order, so dose is not
    inferable and the product must say so."""
    declared = score(ORDINARY_NIACINAMIDE, "serum",
                     known={"Niacinamide": 10.0})
    assert declared["confidence"] == "high"
    inferred = score(ORDINARY_NIACINAMIDE, "serum")
    assert inferred["confidence"] in ("moderate", "low")
    assert "1%" in inferred["confidence_note"] or "inferred" in inferred["confidence_note"]


def test_analyze_product_exposes_the_new_contract():
    result = analyze_product({
        "ingredients": CERAVE_CREAM, "price": 1500, "size_ml": 340,
        "category": "Moisturizer", "concerns": ["Barrier Repair"],
        "skin_type": "dry", "country": "India", "currency": "INR"})
    for key in ("formulation_score", "formulation_breakdown", "value_assessment",
                "advisory_flags", "formulation_confidence", "main_worth_score"):
        assert key in result, "missing {}".format(key)
    # Legacy field must agree with the new one so old and new surfaces never
    # show contradictory numbers.
    assert result["main_worth_score"] == result["formulation_score"]

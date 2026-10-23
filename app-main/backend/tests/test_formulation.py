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


def test_pregnancy_advisory_does_not_treat_missing_studies_as_a_warning():
    from formulation import is_pregnancy_caution
    assert is_pregnancy_caution("Cannot be used — retinoid")
    assert is_pregnancy_caution("Can be used in limited amounts")
    assert is_pregnancy_caution("Avoid pregnancy")
    assert not is_pregnancy_caution("Can be used")
    assert not is_pregnancy_caution("Safe")
    assert not is_pregnancy_caution("")
    assert not is_pregnancy_caution(
        "Insufficient data; consult doctor before use in pregnancy")
    assert not is_pregnancy_caution("Avoid - IARC Group 1 carcinogen")
    assert not is_pregnancy_caution("Avoid leave-on; rinse-off only")
    assert not is_pregnancy_caution("Avoid in children")


def test_empty_pregnancy_fields_do_not_open_the_caution_box():
    from formulation import build_advisory_flags
    flags = build_advisory_flags(parse_ingredients(
        "Aqua, Acetyl Tetrapeptide-3, Palmitoyl Tripeptide-5, "
        "Cyanocobalamin, Niacinamide, Phenoxyethanol"))
    assert not any(f["type"] == "pregnancy" for f in flags)


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
    """High means every ingredient on the list has a declared amount. Declaring
    only some of them is partial, so the score says moderate rather than high.
    Below the 1% line, EU 1223/2009 Art. 19 permits any order, so an undeclared
    list must say the doses are inferred."""
    partial = score(ORDINARY_NIACINAMIDE, "serum",
                    known={"Niacinamide": 10.0})
    assert partial["confidence"] == "moderate"
    names = [part.strip().lower() for part in ORDINARY_NIACINAMIDE.split(",") if part.strip()]
    complete = score(ORDINARY_NIACINAMIDE, "serum",
                     known={name: 1.0 for name in names})
    assert complete["confidence"] == "high"
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


# --- Real-market calibration (Indian brands) --------------------------------
# These guard against the specific regressions found by running 90 real
# products through the engine. See tests/indian_corpus.py.


def test_pure_squalane_oil_scores_well():
    """100% squalane scored 46/100 ("Weak formulation") because the fatty-acid
    model reads linoleic/oleic balance across a blend, and squalane is a
    saturated hydrocarbon with neither. It is among the most stable and
    best-tolerated emollients available."""
    assert score("Squalane", "facial oil")["score"] >= 75


def test_single_ingredient_oils_are_not_penalised_for_lacking_diversity():
    for oil in ("Simmondsia Chinensis Seed Oil, Tocopherol",
                "Rosa Canina Fruit Oil, Tocopherol",
                "Argania Spinosa Kernel Oil, Tocopherol"):
        assert score(oil, "facial oil")["score"] >= 60, oil


def test_sulfate_led_cleanser_scores_below_sulfate_free():
    """Position matters: a sulfate listed before the gentle co-surfactants is
    doing most of the cleansing, so the blend bonus should be small."""
    sulfate_led = ("Aqua, Sodium Laureth Sulfate, Cocamidopropyl Betaine, "
                   "Glycerin, Sodium Chloride, Phenoxyethanol")
    mild_led = ("Aqua, Sodium Cocoyl Isethionate, Cocamidopropyl Betaine, "
                "Coco-Glucoside, Glycerin, Phenoxyethanol")
    assert score(sulfate_led, "cleanser")["score"] < score(mild_led, "cleanser")["score"] - 15


def test_weak_uva_sunscreen_is_capped():
    """A sunscreen that fails on UVA has failed at the job, however strong its
    UVB numbers. An octinoxate + titanium dioxide formula scored 77/100 before
    this gate, on UVB performance alone."""
    weak = ("Aqua, Ethylhexyl Methoxycinnamate, Titanium Dioxide, Glycerin, "
            "Carbomer, Triethanolamine, Fragrance")
    result = score(weak, "sunscreen")
    assert result["score"] <= 60
    assert any(f["type"] == "uva_gate" for f in result["flags"])


def test_moderately_photostable_filters_do_not_score_full_marks():
    """Octinoxate is rated 'Moderate' photostability and was receiving the full
    photostability budget, which is only correct for inherently stable filters."""
    moderate = ("Aqua, Ethylhexyl Methoxycinnamate, Zinc Oxide, Glycerin, "
                "Phenoxyethanol")
    photo = next(c for c in score(moderate, "sunscreen")["components"]
                 if c["key"] == "photostability")
    assert photo["score"] < photo["max"]


def test_modern_filter_system_outranks_legacy_one():
    modern = ("Aqua, Ethylhexyl Triazone, Diethylamino Hydroxybenzoyl Hexyl "
              "Benzoate, Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine, Zinc "
              "Oxide, Glycerin, Tocopherol, Phenoxyethanol")
    legacy = ("Aqua, Ethylhexyl Methoxycinnamate, Titanium Dioxide, Glycerin, "
              "Carbomer, Fragrance, Methylparaben")
    assert score(modern, "sunscreen")["score"] - score(legacy, "sunscreen")["score"] >= 30


def test_real_market_corpus_has_no_crashes_and_ranks_sensibly():
    """Every product in the Indian-market corpus must score without error, and
    the best-formulated products must outrank the worst."""
    import sys as _sys
    import os as _os
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__))))
    from indian_corpus import CORPUS

    scored = {}
    for name, brand, cat, price, size, concerns, skin, expect, inci in CORPUS:
        result = analyze_product({
            "ingredients": inci, "price": price, "size_ml": size,
            "category": cat, "concerns": concerns, "skin_type": skin,
            "country": "India", "currency": "INR", "product_name": name})
        s = result["formulation_score"]
        assert 0 <= s <= 100, "{} scored {}".format(name, s)
        scored["{} {}".format(brand, name)] = s

    # A modern, well-built product must beat a fragrance-and-alcohol one.
    assert scored["Re'equil Oxybenzone Free Sunscreen SPF 50"] > scored["Lotus Herbals Sunscreen Gel SPF 40"]
    assert scored["Minimalist Niacinamide 10% + Zinc 1%"] > scored["Mamaearth Glow Serum with Vitamin C"]
    assert scored["Re'equil Ceramide & Hyaluronic Moisturiser"] > scored["Patanjali Aloe Vera Gel"]
    assert scored["Re'equil Oil Control Face Wash"] > scored["Himalaya Neem Face Wash"]

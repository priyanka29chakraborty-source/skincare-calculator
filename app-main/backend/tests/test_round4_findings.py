"""Round 4 defect tests. Each one failed before the matching fix."""

import os
import sys
import tempfile
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import data_loader  # noqa: E402
from formulation import (  # noqa: E402
    build_advisory_flags,
    formulation_summary,
    formulation_tier,
    is_anhydrous,
    score_formulation,
)
from scoring import (  # noqa: E402
    _parse_concentrations_from_name,
    analyze_product,
    estimate_concentration,
    parse_ingredients,
)

TRIAZINE = "Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine"
TINOSORB_M = "Methylene Bis-Benzotriazolyl Tetramethylbutylphenol"


def _analyze(ingredients, category="Serum", concerns=None, product_name=""):
    return analyze_product({
        "ingredients": ingredients,
        "category": category,
        "concerns": concerns or ["Aging & Fine Lines"],
        "product_name": product_name,
        "price": 0,
        "size_ml": 30,
    })


def _sun(ingredients):
    result = _analyze(ingredients, category="Sunscreen", concerns=["Sun Protection"])
    fit = result["skin_concern_fit"]["Sun Protection"]
    analysis = fit["sunscreen_analysis"]
    return analysis


def _formulation(ingredients, category="serum", known=None):
    parsed = parse_ingredients(ingredients)
    conc = estimate_concentration(parsed, known)
    return score_formulation(
        parsed, conc, category, known_concentrations=known)


def _actives(ingredients, known=None):
    result = _formulation(ingredients, "serum", known)
    return next(c["score"] for c in result["components"] if c["key"] == "actives")


def _concern_score(result, concern):
    fit = result["skin_concern_fit"][concern]
    if isinstance(fit, dict):
        return fit["score"]
    return fit


def _pregnancy(ingredients):
    flags = build_advisory_flags(parse_ingredients(ingredients))
    return [f for f in flags if f["type"] == "pregnancy"]


def _safety_text(ingredients):
    result = _analyze(ingredients)
    details = result.get("component_details", {}).get("D", [])
    return " ".join(str(d) for d in details).lower()


# --- A1 -------------------------------------------------------------------


def test_bemotrizinol_matches_tinosorb_s_photostability():
    inn = _sun("Aqua, Avobenzone, Bemotrizinol")
    lower = _sun("Aqua, Avobenzone, bemotrizinol")
    inci = _sun("Aqua, Avobenzone, %s" % TRIAZINE)

    assert inn["score_breakdown"]["photostability"] == inci["score_breakdown"]["photostability"]
    assert lower["score_breakdown"]["photostability"] == inci["score_breakdown"]["photostability"]
    for analysis in (inn, lower):
        warnings = " ".join(analysis["warnings"])
        assert "Unstable Avobenzone" not in warnings
        assert TRIAZINE in analysis["filters_detected"]
        assert TINOSORB_M not in analysis["filters_detected"]

    mapped = data_loader.get_uv_data("Bemotrizinol")
    assert mapped["INCI_Name"] == TRIAZINE
    biso = data_loader.get_uv_data("Bisoctrizole")
    assert biso["INCI_Name"] == TINOSORB_M


# --- A2 / A5 --------------------------------------------------------------


def test_benzophenone_numbers_do_not_collapse_onto_benzophenone_9():
    three = data_loader.get_uv_data("Benzophenone-3")
    four = data_loader.get_uv_data("Benzophenone-4")
    assert three is not None and three["INCI_Name"] == "Oxybenzone"
    assert four is not None and four["INCI_Name"] == "Sulisobenzone"
    stray = data_loader.get_uv_data("Benzophenone-1")
    assert stray is None or stray["INCI_Name"] != "Benzophenone-9"


@pytest.mark.parametrize("query,inci", [
    ("Tinosorb S", TRIAZINE),
    ("Tinosorb M", TINOSORB_M),
    ("Uvinul A Plus", "Diethylamino Hydroxybenzoyl Hexyl Benzoate"),
    ("Uvinul T 150", "Ethylhexyl Triazone"),
])
def test_trade_uv_aliases_resolve(query, inci):
    data = data_loader.get_uv_data(query)
    assert data is not None
    assert data["INCI_Name"] == inci


# --- A3 / A9 --------------------------------------------------------------


def test_hpr_matches_hydroxypinacolone_retinoate_score():
    short = _formulation("Aqua, HPR, Phenoxyethanol")
    full = _formulation("Aqua, Hydroxypinacolone Retinoate, Phenoxyethanol")
    assert short["score"] == full["score"]
    hpr = data_loader.get_ingredient_data("hpr")
    assert hpr["INCI_Name"] == "Hydroxypinacolone Retinoate"


def test_vitamin_c_aliases_match_ascorbic_acid():
    concern = "Dullness"
    base = "Aqua, {}, Phenoxyethanol"

    def pack(name):
        result = _analyze(base.format(name), concerns=[concern])
        return result["formulation_score"], _concern_score(result, concern)

    ascorbic = pack("Ascorbic Acid")
    assert pack("Vitamin C") == ascorbic
    assert pack("L-Ascorbic Acid") == ascorbic
    assert data_loader.get_ingredient_data("vitamin c")["INCI_Name"] == "Ascorbic Acid"
    assert data_loader.get_ingredient_data("l-ascorbic acid")["INCI_Name"] == "Ascorbic Acid"


def test_hyaluronic_aliases_match_sodium_hyaluronate():
    concern = "Dry Skin"
    base = "Aqua, {}, Phenoxyethanol"

    def pack(name):
        result = _analyze(base.format(name), concerns=[concern])
        return result["formulation_score"], _concern_score(result, concern)

    canonical = pack("Sodium Hyaluronate")
    assert pack("Hyaluronic Acid") == canonical
    assert pack("HA") == canonical
    assert data_loader.get_ingredient_data("ha")["INCI_Name"] == "Sodium Hyaluronate"


def test_bha_record_is_not_replaced_by_salicylic_acid():
    data = data_loader.get_ingredient_data("BHA")
    assert data["INCI_Name"] != "Salicylic Acid"


# --- A4 -------------------------------------------------------------------


def test_solvent_alias_is_not_benzene():
    data = data_loader.get_ingredient_data("solvent")
    assert data is None or data.get("INCI_Name") != "Benzene"


# --- A6 -------------------------------------------------------------------


@pytest.mark.parametrize("ingredients", [
    "Aqua, Glycolic Acid, Phenoxyethanol",
    "Aqua, Isopropyl Myristate, Phenoxyethanol",
    "Aqua, Alcohol Denat, Phenoxyethanol",
])
def test_non_pregnancy_avoid_notes_do_not_raise_pregnancy_advisory(ingredients):
    assert _pregnancy(ingredients) == []
    assert "pregnant" not in _safety_text(ingredients)


@pytest.mark.parametrize("ingredients", [
    "Aqua, Retinol, Phenoxyethanol",
    "Aqua, Tretinoin, Phenoxyethanol",
    "Aqua, Adapalene, Phenoxyethanol",
    "Aqua, Hydroquinone, Phenoxyethanol",
])
def test_real_pregnancy_warnings_stay(ingredients):
    assert _pregnancy(ingredients)
    assert "pregnant" in _safety_text(ingredients)


# --- A7 -------------------------------------------------------------------


def test_niacinamide_dose_uses_real_concentration_factor():
    one = _actives("Aqua, Niacinamide, Phenoxyethanol", {"niacinamide": 1})
    five = _actives("Aqua, Niacinamide, Phenoxyethanol", {"niacinamide": 5})
    ten = _actives("Aqua, Niacinamide, Phenoxyethanol", {"niacinamide": 10})
    undeclared = _actives("Aqua, Niacinamide, Phenoxyethanol")
    assert one < five
    assert abs(five - ten) <= 0.6
    assert undeclared <= max(five, ten) + 0.2

    parsed = parse_ingredients("Aqua, Niacinamide, Phenoxyethanol")
    estimated = estimate_concentration(parsed)["Niacinamide"]
    assert estimated <= 10


# --- A8 -------------------------------------------------------------------


@pytest.mark.parametrize("ingredients", [
    "Water/Aqua/Eau, Niacinamide",
    "Aqua/Water/Eau, Niacinamide",
    "Purified Water, Niacinamide",
])
def test_slashed_or_qualified_water_is_not_anhydrous(ingredients):
    parsed = parse_ingredients(ingredients)
    assert is_anhydrous(parsed) is False
    result = _formulation(ingredients, "serum")
    notes = " ".join(n for c in result["components"] for n in c["notes"]).lower()
    assert "water-free" not in notes
    assert "no preservative system required" not in notes


def test_squalane_and_short_water_free_lists_stay_anhydrous():
    assert is_anhydrous(parse_ingredients("Squalane")) is True
    assert is_anhydrous(parse_ingredients("Niacinamide, Zinc PCA")) is True
    result = _formulation("Squalane", "serum")
    notes = " ".join(n for c in result["components"] for n in c["notes"]).lower()
    assert "water-free" in notes


# --- A10 ------------------------------------------------------------------


def test_ethyl_linoleate_is_not_retinyl_linoleate():
    data = data_loader.get_ingredient_data("Ethyl Linoleate")
    assert data is None or data.get("INCI_Name") != "Retinyl Linoleate"
    assert _pregnancy("Aqua, Ethyl Linoleate, Phenoxyethanol") == []
    leaf = data_loader.get_ingredient_data("Centella Asiatica Leaf Extract")
    short = data_loader.get_ingredient_data("Centella leaf extract")
    assert leaf and "centella" in leaf["INCI_Name"].lower()
    assert short and "centella" in short["INCI_Name"].lower()


# --- A11 ------------------------------------------------------------------


def test_niacinamide_and_nicotinamide_are_not_double_counted():
    concern = "Aging & Fine Lines"
    alone = _analyze("Aqua, Niacinamide, Phenoxyethanol", concerns=[concern])
    both = _analyze(
        "Aqua, Niacinamide, Nicotinamide, Phenoxyethanol", concerns=[concern])
    assert both["formulation_score"] == alone["formulation_score"]
    assert _concern_score(both, concern) == _concern_score(alone, concern)


# --- A12 ------------------------------------------------------------------


def test_bare_aha_is_not_scored_as_glycolic_acid():
    aha = _formulation("Aqua, AHA, Phenoxyethanol")["score"]
    glycolic = _formulation("Aqua, Glycolic Acid, Phenoxyethanol")["score"]
    assert aha != glycolic
    data = data_loader.get_ingredient_data("AHA")
    assert data is None or data.get("INCI_Name") != "Glycolic Acid"


def test_product_name_parser_still_reads_aha_percent():
    known = _parse_concentrations_from_name("The Ordinary 10% AHA Serum")
    assert known.get("glycolic acid") == 10 or known.get("aha") == 10


# --- A13 ------------------------------------------------------------------


def test_cache_key_uses_the_full_ingredient_string():
    from server import _make_cache_key
    prefix = "Aqua, " + ("Glycerin, " * 40)
    assert len(prefix) > 200
    first = _make_cache_key({"ingredients": prefix + "Niacinamide", "concerns": []})
    second = _make_cache_key({"ingredients": prefix + "Retinol", "concerns": []})
    assert first != second


# --- A14 ------------------------------------------------------------------


@pytest.fixture
def hist(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="history-round4-")
    monkeypatch.setenv("WALLET_DB_PATH", os.path.join(tmp, "wallet.db"))
    monkeypatch.delenv("AIVEN_PG_URL", raising=False)
    for mod in ("wallet", "history"):
        sys.modules.pop(mod, None)
    import wallet as w
    import history as h
    w._initialised = False
    w._local = threading.local()
    w.init_storage()
    h.ensure_schema()
    return h


def test_reanalysis_refreshes_ingredients_without_blanking_name(hist):
    import wallet
    account = wallet.get_or_create_account("round4@example.com")
    original = {
        "product_name": "Serum A", "brand": "Minimalist", "category": "Serum",
        "price": 549, "size_ml": 30, "currency": "INR", "skin_type": "oily",
        "skin_concerns": [], "ingredients": "Aqua, Niacinamide",
    }
    hist.record(account, "key1", {"formulation_score": 70, "formulation_tier": "Solidly formulated"},
                original, was_paid=False)
    updated = dict(original)
    updated["product_name"] = "Serum B"
    updated["brand"] = ""
    updated["ingredients"] = "Aqua, Glycerin, Niacinamide"
    hist.record(account, "key1", {"formulation_score": 80, "formulation_tier": "Solidly formulated"},
                updated, was_paid=True)
    entry = hist.get(account, hist.recent(account)[0]["entry_id"])
    assert entry["ingredients"] == "Aqua, Glycerin, Niacinamide"
    assert entry["product_name"] == "Serum B"
    assert entry["brand"] == "Minimalist"


# --- A16 ------------------------------------------------------------------


def _barrier_notes(ingredients):
    result = _formulation(ingredients, "moisturizer")
    barrier = next(c for c in result["components"] if c["key"] == "barrier")
    return " ".join(barrier["notes"]).lower()


def test_caprylic_capric_triglyceride_is_not_a_fatty_acid():
    notes = _barrier_notes(
        "Aqua, Ceramide NP, Cholesterol, Caprylic/Capric Triglyceride, Phenoxyethanol")
    assert "complete physiological lipid set" not in notes
    complete = _barrier_notes(
        "Aqua, Ceramide NP, Cholesterol, Stearic Acid, Phenoxyethanol")
    assert "complete physiological lipid set" in complete


# --- A17 ------------------------------------------------------------------


def test_score_80_badge_and_sentence_agree():
    components = [
        {"key": "actives", "label": "Active Efficacy", "score": 32, "max": 40},
        {"key": "evidence", "label": "Evidence Quality", "score": 16, "max": 20},
    ]
    tier = formulation_tier(80, "serum")
    summary = formulation_summary(80, "serum", components, "high")
    assert "solidly" in tier.lower()
    assert "well-made" not in summary.lower()
    assert "solidly" in summary.lower()
    assert "well-made" in formulation_summary(82, "serum", components, "high").lower()

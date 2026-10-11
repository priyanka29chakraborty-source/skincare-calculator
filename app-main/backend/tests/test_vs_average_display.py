"""The "vs average" grid tile and the Price check line describe the same
comparison, so they must print the same 2-decimal ratio.

599 INR / 30 ml serum in India: 19.97/ml against a 20.5/ml average is 0.974.
The grid used to re-round that to 1 decimal and showed "1.0x" while the
Price check showed "0.97x".
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scoring import analyze_product  # noqa: E402


def _result():
    return analyze_product({
        "ingredients": "Aqua, Niacinamide, Glycerin, Zinc PCA, Phenoxyethanol",
        "price": 599, "size_ml": 30, "category": "Serum",
        "concerns": ["Pigmentation"], "skin_type": "combination",
        "country": "India", "currency": "INR"})


def test_grid_and_price_check_show_same_ratio():
    result = _result()
    assert result["value_assessment"]["ratio"] == 0.97
    assert result["price_analysis"]["ratio"] == 0.97
    # Single display format: two decimals followed by the multiplication sign.
    assert result["price_analysis"]["vs_average"] == "0.97×"
    assert result["price_analysis"]["vs_average"] not in ("1.0x", "1.0×")


def test_component_detail_uses_two_decimals():
    details = _result()["component_details"]["E"]
    line = next(d for d in details if "vs category average" in d)
    assert line.startswith("0.97× vs category average"), details

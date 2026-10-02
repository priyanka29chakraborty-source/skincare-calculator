"""The seam where a language model may later phrase our results.

Nothing in this package computes a score, and nothing in it is allowed to.
See ai_interface for the boundary and how it is enforced.
"""

from .ai_interface import (
    Explainer,
    DeterministicExplainer,
    ExplanationRejected,
    get_explainer,
    register_explainer,
    validate_explanation,
)

__all__ = [
    'Explainer',
    'DeterministicExplainer',
    'ExplanationRejected',
    'get_explainer',
    'register_explainer',
    'validate_explanation',
]

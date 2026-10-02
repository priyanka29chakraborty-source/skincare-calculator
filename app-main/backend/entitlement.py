"""Server-side entitlement gating.

THE ONE RULE
------------
The server never sends data the user has not paid for.

The common way paywalls fail is returning the full payload and hiding the paid
parts in the frontend. That is one press of F12 away from free: open the
Network tab, read the JSON, done. Any check written in React is a suggestion,
not a control - the user owns that runtime and can edit it.

So the free response here is a genuinely smaller object. The paid keys are
never serialised, which means there is nothing to reveal by editing client
code, replaying the request, or inspecting the response.

WHAT IS NEVER PAYWALLED
-----------------------
Safety information is always free, for everyone, signed in or not:
pregnancy advisories, missing-preservative warnings, weak-UVA sunscreen
warnings, unstable-active warnings.

Charging someone to learn that a product may be unsafe for them in pregnancy
would be indefensible, and would make the tool actively harmful to exactly the
people with most at stake. What is sold is optimisation - "how well does this
suit you specifically" - which is a preference question, not a safety one.

WHAT THIS CANNOT DO
-------------------
No paywall is unbreakable. A paying user can screenshot a result and send it to
a friend, and that is fine. The realistic goal is that bypassing costs more
effort than paying, and that no amount of client-side tampering yields paid
data - which this does achieve, because the data is not there to find.
"""

# Keys present in a free response. Everything else is stripped.
FREE_KEYS = {
    # The product-quality answer - impersonal, identical for every user,
    # cacheable and shareable. This is the acquisition engine and stays free.
    'formulation_score', 'formulation_category', 'formulation_rationale',
    'formulation_breakdown', 'formulation_confidence',
    'formulation_confidence_note', 'formulation_flags',
    'main_worth_score', 'main_worth_tier', 'score_title',

    # Price is a fact about the product, not a personalisation.
    'value_assessment', 'price_analysis',

    # What is in the bottle. Reading an ingredient list is not a premium
    # feature, and gating it would make the tool useless as a reference.
    'identified_actives', 'active_classes', 'ingredient_count',
    # What to pair the product with. Derived from the product's own
    # actives and says nothing about the person, so it sits with the
    # rest of the free formulation analysis.
    'pairs_well_with',
    # The legacy A-E breakdown and its detail bullets describe the FORMULATION
    # score, which is free. Stripping them left the category headline cards
    # (cleanser surfactant safety, oil lipid score, sunscreen UV stats) with a
    # bar and no number - the UI renders them unconditionally.
    'component_scores', 'component_details',
    'one_percent_marker', 'ingredient_conflicts', 'ph_analysis',
    'delivery_systems', 'red_flags', 'is_high_intensity',
    'high_intensity_actives', 'oil_metadata', 'am_pm_recommendation',

    # Honesty metadata must never be hidden - a user has to be able to see how
    # much confidence to place in a free result.
    'score_confidence', 'score_confidence_level', 'disclaimer',
}

# Personal analysis. This is the paid product.
PAID_KEYS = {
    'skin_concern_fit',            # how well it suits the concerns you picked
    'skin_type_compatibility', 'skin_type_base_texture', 'skin_type_risk_level',
    'skin_type_reasons', 'skin_type_details',
    'better_suited', 'upgrade_suggestions',
    'comedogenic_warnings', 'allergen_warnings',
    'personalisation',             # Fitzpatrick, climate, routine layer
}

# Advisory types that are SAFETY and therefore always free, even though they
# are produced by the personal layer.
ALWAYS_FREE_ADVISORIES = {
    'pregnancy',            # safety, and the highest-stakes information here
    'declared_allergen',    # the user told us they react to it - withholding
                            # that would be indefensible
}


def _preview(result):
    """A truthful teaser: says what exists without giving it away.

    Shows the NUMBER of concerns assessed and whether any personal warning was
    raised, so the user can judge whether unlocking is worth it - but not the
    scores themselves. Nothing here is invented or exaggerated.
    """
    fit = result.get('skin_concern_fit') or {}
    personal = result.get('personalisation') or {}
    return {
        'concerns_assessed': len(fit),
        'concern_names': sorted(fit.keys()),
        'has_skin_type_match': result.get('skin_type_compatibility') is not None,
        'personalisation_level': personal.get('level', 'none'),
        'routine_issues_found': len(personal.get('routine_conflicts') or []),
        'alternatives_available': bool(result.get('upgrade_suggestions')),
    }


def filter_for_entitlement(result, entitled, reason=None):
    """Return the payload this user is entitled to.

    `entitled` must be resolved server-side from a verified session and credit
    balance. It is never read from the request body - a client-supplied
    entitlement flag is just a request to be trusted, and would be the whole
    paywall in one editable field.
    """
    if entitled:
        out = dict(result)
        out['access'] = {'tier': 'full', 'locked': []}
        return out

    free = {k: v for k, v in result.items() if k in FREE_KEYS}

    # Safety advisories survive the filter; personal optimisation ones do not.
    advisories = result.get('advisory_flags') or []
    free['advisory_flags'] = [
        f for f in advisories if f.get('type') in ALWAYS_FREE_ADVISORIES]

    free['access'] = {
        'tier': 'free',
        'locked': sorted(PAID_KEYS),
        'reason': reason or 'no_credits',
        'preview': _preview(result),
        # Stated plainly so the paywall reads as honest rather than as a trick.
        'message': (
            "The formulation analysis above is complete and free. What is "
            "locked is the personal part - how well this suits your skin type, "
            "your concerns and your existing routine."),
        'safety_note': (
            "Safety warnings are never locked. Anything we found that could "
            "affect you - including pregnancy guidance and ingredients you told "
            "us you react to - is shown above in full."),
    }
    return free


def audit_no_paid_leakage(free_payload):
    """Assert a free payload carries no paid data. Used by tests and callable
    in production as a last line of defence before serialisation."""
    leaked = sorted(set(free_payload) & PAID_KEYS)
    if leaked:
        raise AssertionError(
            "free response leaked paid keys: {}".format(", ".join(leaked)))
    for flag in free_payload.get('advisory_flags') or []:
        if flag.get('type') not in ALWAYS_FREE_ADVISORIES:
            raise AssertionError(
                "free response leaked personal advisory: {}".format(flag.get('type')))
    return True

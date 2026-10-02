"""The contract any explanation layer must satisfy, and the default one.

Why this exists as an interface rather than a model call
--------------------------------------------------------

The product's claim is that a score is reproducible and traceable to a rubric.
A language model writing free text next to that score can quietly undo it: it
can invent a concentration, assert a benefit the evidence does not support, or
state a number that contradicts the engine. On a product people may use while
pregnant or on prescription retinoids, that is not a cosmetic problem.

So the boundary is explicit and enforced in code:

* **An explainer receives the finished analysis and returns prose.** It is
  given no way to change a score, a flag or a tier - those are already computed
  when it is called, and its return value is text only.

* **Every number it writes must already appear in the analysis.**
  ``validate_explanation`` extracts the numbers from the generated text and
  rejects the explanation if any of them is not in the engine's own output.
  A model that hallucinates "contains 12% niacinamide" fails this check and the
  deterministic text is served instead.

* **Failure is silent and safe.** A rejected or erroring explainer falls back
  to ``DeterministicExplainer``, which only ever restates what the engine
  computed. The user sees a plainer sentence, never a wrong one.

The default implementation calls no model and needs no API key, so the app runs
exactly as it does today. Registering a real explainer is the only step needed
to turn the layer on.
"""

import copy
import logging
import re

logger = logging.getLogger(__name__)


class ExplanationRejected(Exception):
    """Raised when generated text fails the no-invented-numbers check."""


class Explainer(object):
    """Base class for anything that turns an analysis into prose.

    Implementations override ``explain``. They must treat ``analysis`` as
    read-only: it has already been scored, filtered for entitlement and
    audited, and a mutation here would bypass all three.
    """

    name = 'base'

    def explain(self, analysis, audience=None):
        """Return a dict of {section_key: text}. Must not mutate *analysis*."""
        raise NotImplementedError

    # Sections an explainer may produce. Anything else is dropped, so a model
    # cannot introduce a new UI surface by inventing a key.
    ALLOWED_SECTIONS = (
        'summary',        # one paragraph on the formulation
        'why_this_score', # what drove the number up or down
        'how_to_use',     # practical application notes
        'what_we_cannot_say',  # limits of the analysis
    )


class DeterministicExplainer(Explainer):
    """The default. Restates the engine's own output, invents nothing.

    This is not a placeholder to be replaced - it is the fallback that every
    other explainer degrades to, so it has to be correct on its own terms.
    """

    name = 'deterministic'

    def explain(self, analysis, audience=None):
        out = {}

        # score_title is the engine's own spelling for this sentence.
        summary = (analysis.get('formulation_summary')
                   or analysis.get('score_title')
                   or (analysis.get('formulation') or {}).get('summary'))
        if summary:
            out['summary'] = summary

        why = self._why(analysis)
        if why:
            out['why_this_score'] = why

        limits = self._limits(analysis)
        if limits:
            out['what_we_cannot_say'] = limits

        return out

    @staticmethod
    def _components(analysis):
        formulation = analysis.get('formulation') or {}
        return (analysis.get('formulation_breakdown')
                or formulation.get('breakdown')
                or formulation.get('components')
                or [])

    def _why(self, analysis):
        components = self._components(analysis)
        scored = [c for c in components
                  if isinstance(c, dict) and c.get('max')]
        if not scored:
            return ''

        ranked = sorted(scored, key=lambda c: c['score'] / float(c['max']))
        weakest, strongest = ranked[0], ranked[-1]

        bits = []
        if strongest['max'] and strongest['score'] / float(strongest['max']) >= 0.7:
            bits.append('{} scored {} of {}'.format(
                strongest.get('label', 'one component'),
                _trim(strongest['score']), _trim(strongest['max'])))
        if weakest['max'] and weakest['score'] / float(weakest['max']) < 0.55:
            bits.append('{} scored {} of {}'.format(
                weakest.get('label', 'another'),
                _trim(weakest['score']), _trim(weakest['max'])))
        if not bits:
            return 'No single part of this formulation stands out, up or down.'
        return 'The number is driven mostly by two parts: ' + ', while '.join(bits) + '.'

    def _limits(self, analysis):
        """What the analysis genuinely cannot determine.

        Stated plainly because it is the honest answer, not a disclaimer: an
        INCI list below 1% is unordered by law, so exact doses are unknowable
        from the label alone.
        """
        notes = []
        confidence = analysis.get('confidence') or {}
        if isinstance(confidence, dict) and confidence.get('note'):
            notes.append(confidence['note'])
        note = analysis.get('formulation_confidence_note')
        if note and note not in notes:
            notes.append(note)
        unknown = analysis.get('unknown_ingredients') or []
        if unknown:
            notes.append(
                '{} ingredient{} in this list {} not in our database, so {} '
                'did not contribute to the score.'.format(
                    len(unknown),
                    '' if len(unknown) == 1 else 's',
                    'is' if len(unknown) == 1 else 'are',
                    'it' if len(unknown) == 1 else 'they'))
        return ' '.join(notes)


# ---------------------------------------------------------------------------
# The no-invented-numbers check
# ---------------------------------------------------------------------------

_NUMBER = re.compile(r'\d+(?:\.\d+)?')

# Numbers a sentence can contain without them being claims about the product:
# ordinals and small counts used in ordinary prose ("two parts", "1 of 3").
_FREE_NUMBERS = {'0', '1', '2', '3', '4', '5', '10', '100'}


def _trim(value):
    """Render a score without a pointless trailing .0."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(f)) if f == int(f) else str(round(f, 1))


def collect_known_numbers(analysis):
    """Every number the engine itself produced, as strings.

    Used as the allowlist for generated text. Walks the whole analysis rather
    than a fixed set of keys so that adding a field to the engine does not
    silently narrow what an explainer is permitted to mention.
    """
    known = set(_FREE_NUMBERS)

    def walk(node):
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
        elif isinstance(node, bool):
            return
        elif isinstance(node, (int, float)):
            known.add(_trim(node))
            known.add(str(node))
        elif isinstance(node, str):
            for match in _NUMBER.findall(node):
                known.add(match)
                known.add(_trim(match))

    walk(analysis)
    return known


def validate_explanation(text, analysis):
    """Raise ExplanationRejected if *text* states a number the engine did not.

    This is the one hard rule on generated prose. It does not try to judge
    whether a claim is true - no automated check can - but it does stop the
    most damaging and most common failure, which is a confident number that
    nothing computed.
    """
    if not text:
        return text
    known = collect_known_numbers(analysis)
    for raw in _NUMBER.findall(text):
        if raw in known or _trim(raw) in known:
            continue
        raise ExplanationRejected(
            'generated text states {!r}, which is not in the analysis'.format(raw))
    return text


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY = {}
_ACTIVE = DeterministicExplainer()


def register_explainer(explainer, make_active=True):
    """Register an explainer, and by default make it the one in use."""
    global _ACTIVE
    if not isinstance(explainer, Explainer):
        raise TypeError('explainer must subclass Explainer')
    _REGISTRY[explainer.name] = explainer
    if make_active:
        _ACTIVE = explainer
    return explainer


def get_explainer(name=None):
    if name is None:
        return _ACTIVE
    return _REGISTRY.get(name, DeterministicExplainer())


def explain(analysis, audience=None, explainer=None):
    """Produce validated explanation sections for *analysis*.

    Never raises and never returns an unvalidated section: anything that fails
    the number check, errors, or returns an unrecognised key is dropped, and
    the deterministic text is used instead. A worse sentence is an acceptable
    outcome here; a wrong one is not.
    """
    chosen = explainer or _ACTIVE
    fallback = DeterministicExplainer().explain(analysis, audience)

    if isinstance(chosen, DeterministicExplainer):
        return fallback

    # The explainer is handed its own copy. The interface documents analysis as
    # read-only, but a mutation would bypass scoring, entitlement filtering and
    # the paid-leakage audit - all of which already ran - so the guarantee is
    # enforced here rather than left to each implementation to honour.
    try:
        produced = chosen.explain(copy.deepcopy(analysis), audience) or {}
    except Exception:
        logger.exception('explainer %s failed; using deterministic text',
                         getattr(chosen, 'name', '?'))
        return fallback

    out = dict(fallback)
    for key, text in produced.items():
        if key not in Explainer.ALLOWED_SECTIONS:
            logger.warning('explainer %s returned unknown section %r; dropped',
                           chosen.name, key)
            continue
        try:
            out[key] = validate_explanation(text, analysis)
        except ExplanationRejected as exc:
            logger.warning('explainer %s rejected for %s: %s',
                           chosen.name, key, exc)
    return out

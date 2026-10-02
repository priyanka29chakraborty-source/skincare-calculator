"""Copy-quality checks for promptfoo.

Each function takes the provider's JSON output and returns True, or a dict with
pass=False and a reason. They encode what a careful human editor would catch,
not what a unit test would: a sentence can be well-formed, correctly computed
and still be wrong to say.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fail(reason):
    return {'pass': False, 'score': 0, 'reason': reason}


def _load(output):
    return json.loads(output)


def no_dose_above_the_safe_maximum(output, context):
    """Never quote a dose nobody could have formulated.

    A position-based estimate said 15% salicylic acid and called it "within its
    evidenced effective range" against a database ceiling of 2%.
    """
    from data_loader import data_loader
    out = _load(output)
    for text in out['all_text']:
        for name, pct in re.findall(r'([A-Z][A-Za-z\- ]+?) at an estimated ([\d.]+)%', text):
            data = data_loader.get_ingredient_data(name.strip()) or {}
            try:
                ceiling = float(data.get('Max_Safe_%', ''))
            except ValueError:
                continue
            if float(pct) > ceiling:
                return _fail('%s quoted at %s%% but its ceiling is %g%%: %r'
                             % (name.strip(), pct, ceiling, text))
    return True


def praise_agrees_with_the_number(output, context):
    """A low score must not be described in praising words, and vice versa.

    "Great formula" used to open every concern advisory regardless of score.
    """
    out = _load(output)
    praise = re.compile(r'\b(great|excellent|strong coverage|well-made|ideal)\b', re.I)
    for concern, score in out['concern_scores'].items():
        if score < 50:
            for adv in out['advisories']:
                if concern.lower() in adv.lower() and praise.search(adv):
                    return _fail('%s scored %s but is praised: %r' % (concern, score, adv))
    if out['score'] < 55 and re.search(r'well-made', out['summary'], re.I):
        return _fail('score %s described as well-made: %r' % (out['score'], out['summary']))
    return True


def advice_fits_the_product(output, context):
    """Do not tell someone to look for an active inside a product that is not
    meant to carry one."""
    out = _load(output)
    if out['category'].lower() in ('sunscreen', 'cleanser', 'toner', 'mask'):
        for adv in out['advisories']:
            if re.search(r'\bLook for\b', adv):
                return _fail('%s told to "look for" an active: %r' % (out['category'], adv))
    return True


def no_machine_leakage(output, context):
    """No placeholders, snake_case keys or internal names in front of a person."""
    out = _load(output)
    bad = re.compile(r'\b(None|null|undefined|NaN|nan)\b|[a-z]+_[a-z]+_?[a-z]*|main_worth|\{\w+\}')
    for text in out['all_text']:
        if text and bad.search(text):
            return _fail('machine text leaked: %r' % text)
    return True


def no_repeated_sentences(output, context):
    """On paper and on screen, saying a thing twice reads as padding."""
    out = _load(output)
    seen = set()
    for text in out['all_text']:
        key = re.sub(r'\W+', ' ', text or '').strip().lower()
        if key and key in seen:
            return _fail('repeated: %r' % text)
        seen.add(key)
    return True


def confidence_talks_about_the_right_thing(output, context):
    """Dose uncertainty is irrelevant where actives are not scored.

    A cleanser was told "Confidence is low: active doses are inferred" - a
    caveat about a thing that category does not measure.
    """
    out = _load(output)
    if out['category'].lower() in ('cleanser', 'sunscreen'):
        text = ' '.join([out['summary'], out['confidence_note']]).lower()
        if 'active doses' in text:
            return _fail('%s carries a caveat about active doses: %r'
                         % (out['category'], out['summary']))
    return True


def sentences_are_readable(output, context):
    """Plain English: no sentence over 45 words, none that is a bare fragment."""
    out = _load(output)
    for text in out['all_text']:
        words = len((text or '').split())
        if words > 45:
            return _fail('%d-word sentence: %r' % (words, text))
        if text and words < 2:
            return _fail('fragment: %r' % text)
    return True

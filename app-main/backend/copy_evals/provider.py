"""promptfoo provider: runs the real engine and returns every sentence a user
would read for one product, as JSON.

Nothing here calls a language model. The sentences in this app are produced by
deterministic code, which is deliberate - a model writing prose next to a
reproducible score can invent a dose. promptfoo's job here is to hold that code
to a human standard: would a thoughtful person write this sentence, and does it
agree with the number printed beside it?
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def call_api(prompt, options, context):
    from scoring import analyze_product

    v = context['vars']
    result = analyze_product({
        'ingredients': v['ingredients'],
        'price': v.get('price', 500),
        'size_ml': v.get('size_ml', 30),
        'category': v['category'],
        'country': 'India', 'currency': 'INR',
        'skin_type': v.get('skin_type', 'oily'),
        'concerns': v.get('concerns', ['Acne & Oily Skin']),
    })

    notes = [n for c in result['formulation_breakdown'] for n in c.get('notes', [])]
    out = {
        'category': v['category'],
        'score': result['formulation_score'],
        'summary': result['score_title'],
        'confidence_note': result['formulation_confidence_note'],
        'notes': notes,
        'concern_scores': {k: d['score'] for k, d in result['skin_concern_fit'].items()},
        'am_pm': result.get('am_pm_recommendation', ''),
        'advisories': [d['advisory'] for d in result['skin_concern_fit'].values()],
        'explanations': [e for d in result['skin_concern_fit'].values()
                         for e in d.get('explanation', [])],
    }
    out['all_text'] = ([out['summary'], out['confidence_note'], out['am_pm']] + notes
                       + out['advisories'] + out['explanations'])
    return {'output': json.dumps(out)}

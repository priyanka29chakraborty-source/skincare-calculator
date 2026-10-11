# -*- coding: utf-8 -*-
"""List ingredient records that still have no signed review.

Prints names only. It does not write a reviewer, a source, or a date.
Add those by hand in evidence_reviews.json:

    "niacinamide": {
      "reviewer": "Name and qualification",
      "source": "The paper or guideline",
      "evidence_level": "strong",
      "reviewed_at": "2026-01-01"
    }

    python scripts/export_evidence_queue.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import evidence  # noqa: E402


def main():
    pregnancy, actives = evidence._unsigned_names()
    print('pregnancy unsigned: %d' % len(pregnancy))
    for name in pregnancy:
        print('  %s' % name)
    print('actives missing evidence: %d' % len(actives))
    for name in actives:
        print('  %s' % name)


if __name__ == '__main__':
    main()

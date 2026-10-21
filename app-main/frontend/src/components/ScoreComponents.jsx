import React from "react";

import { ConcernBadge } from "../lib/concernIcons";
import { ScoreRing, scoreTone } from "./ds";

export function fitLevel(score) {
  if (score >= 80) return "Strong fit";
  if (score >= 60) return "Good fit";
  if (score >= 40) return "Moderate fit";
  if (score >= 20) return "Low fit";
  return "Very low fit";
}

/** One concern: how well this product treats it, and why. */
export function ConcernCard({ concern, data }) {
  const score = Number(data.score) || 0;
  const tone = scoreTone(score);
  return (
    <div className="concern" data-testid={`concern-result-${concern.replace(/\s+/g, "-").toLowerCase()}`}>
      <ScoreRing score={score} size="sm" animate={false} label={`${concern} fit`} />
      <div className="concern__body">
        <p className="concern__head">
          <ConcernBadge name={concern} size="sm" />
          <span className="t-heading-s">{concern}</span>
          <span className="concern__level" style={{ color: `var(--score-${tone})` }}>{fitLevel(score)}</span>
        </p>
        {data.explanation?.length > 0 && (
          <ul className="concern__why">{data.explanation.map((e, i) => <li key={i}>{e}</li>)}</ul>
        )}
        {data.supporting_ingredients?.length > 0 && (
          <p className="t-body-s c-secondary"><strong className="c-primary">Doing the work:</strong> {data.supporting_ingredients.join(", ")}</p>
        )}
        {data.advisory && <p className="t-body-s c-secondary"><strong className="c-primary">Worth knowing:</strong> {data.advisory}</p>}
      </div>
    </div>
  );
}

import React, { useEffect, useState } from "react";
import { Check } from "lucide-react";

import { categoryLabel } from "../constants";

/**
 * Shown while the analysis runs.
 *
 * Only the first line is ticked, because it is the only step the browser has
 * actually finished - it counted the ingredients itself. The rest describe the
 * work the engine is doing, in the order it does it; the current one is
 * highlighted but never marked done before the result exists.
 */
export default function AnalysingState({ ingredientCount, category, productName }) {
  const [current, setCurrent] = useState(1);
  const [slow, setSlow] = useState(false);
  const steps = [
    `Read ${ingredientCount || "the"} ingredient${ingredientCount === 1 ? "" : "s"}`,
    "Identifying actives and estimating their amounts",
    "Checking pairs of ingredients for clashes",
    `Comparing price per ml with other ${categoryLabel(category).toLowerCase()}s`,
    "Writing your verdict",
  ];

  useEffect(() => {
    const id = setInterval(() => setCurrent((c) => Math.min(c + 1, steps.length - 1)), 1600);
    const slowId = setTimeout(() => setSlow(true), 12000);
    return () => { clearInterval(id); clearTimeout(slowId); };
  }, [steps.length]);

  return (
    <section className="card card--raised analysing" aria-live="polite" aria-busy="true" data-testid="analysing">
      <div className="analysing__copy">
        <p className="t-eyebrow c-accent">Analysing{productName ? ` · ${productName}` : ""}</p>
        <h1 className="t-display-s">Reading the <em>formula</em>…</h1>
        <ol className="analysing__steps">
          {steps.map((s, i) => {
            const state = i === 0 ? "done" : i === current ? "active" : i < current ? "passed" : "todo";
            return (
              <li key={s} className={`analysing__step analysing__step--${state}`}>
                <span className="analysing__dot" aria-hidden="true">{state === "done" && <Check />}</span>
                <span>{s}</span>
              </li>
            );
          })}
        </ol>
        {slow && (
          <p className="t-caption c-tertiary">
            Still reading — every ingredient is checked against our database before you see a score.
          </p>
        )}
      </div>
      <div className="analysing__skeleton" aria-hidden="true">
        <div className="analysing__ring" />
        <div className="skeleton" style={{ height: 8, width: "88%" }} />
        <div className="skeleton" style={{ height: 8, width: "70%" }} />
        <div className="skeleton" style={{ height: 8, width: "80%" }} />
      </div>
    </section>
  );
}

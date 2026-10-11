import { useState } from "react";
import { track } from "../track";

/**
 * A short routine from data the analysis already produced:
 * when to use this product, what to add, and — once the personal
 * section is unlocked — what clashes or repeats the current routine.
 */
export default function RoutineCard({ result, productName }) {
  const when = result?.am_pm_recommendation;
  const adds = result?.pairs_well_with || [];
  const conflicts = result?.personalisation?.routine_conflicts || [];
  const avoid = conflicts.filter((c) => c.type === "routine_conflict");
  const alternate = conflicts.filter((c) => c.type === "routine_redundant");
  const [saved, setSaved] = useState(false);

  if (!when && adds.length === 0 && conflicts.length === 0) return null;

  function save() {
    const row = {
      productName: productName || "This product",
      when: when || "",
      add: adds.map((p) => p.ingredient),
      avoid: avoid.map((c) => c.message),
      alternate: alternate.map((c) => c.message),
    };
    const key = "urancal-routines";
    let prev = [];
    try { prev = JSON.parse(localStorage.getItem(key) || "[]"); } catch { prev = []; }
    localStorage.setItem(key, JSON.stringify([row, ...prev].slice(0, 20)));
    track("routine_saved");
    setSaved(true);
  }

  return (
    <div className="sc-card result-card" data-testid="routine-card">
      <h2 className="card-title">
        <i className="fa-regular fa-clock"></i> How to use this
      </h2>
      {when && <p data-testid="routine-when">{when}</p>}
      <ul className="pairings-list">
        <li>Keep {productName || "this product"}.</li>
        {adds.map((p) => (
          <li key={p.ingredient}>
            Add {p.ingredient}
            {p.look_for ? ` — look for ${p.look_for}` : ""}.
          </li>
        ))}
        {alternate.map((c, i) => <li key={`alt-${i}`}>Alternate: {c.message}</li>)}
        {avoid.map((c, i) => <li key={`avoid-${i}`}>Avoid together: {c.message}</li>)}
      </ul>
      <button type="button" className="clear-btn-solo" onClick={save} data-testid="routine-save">
        {saved ? "Saved on this device" : "Save this routine"}
      </button>
    </div>
  );
}

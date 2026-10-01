import React from "react";

/**
 * What a paid section looks like before it is unlocked.
 *
 * The reason this component exists: paid fields are stripped server-side, so
 * any card that renders them unconditionally produces broken UI rather than a
 * paywall. The skin-compatibility card did exactly that - it printed a bare
 * "%" with no number, and getBarColor(undefined) fell through every threshold
 * and returned red, so a locked section looked like a catastrophic score.
 *
 * A locked card must therefore be an explicit state, not an accident.
 *
 * It is also deliberately honest: it names what was assessed and what was
 * found, so the user can judge whether unlocking is worth it. It never
 * pretends the analysis did not happen, and never implies a bad result to
 * manufacture urgency.
 */
export default function LockedCard({ title, icon, access, lines, onUnlock }) {
  const preview = access?.preview || {};

  return (
    <div className="sc-card result-card locked-card" data-testid="locked-card">
      <h2 className="card-title">
        <i className={icon || "fa-solid fa-lock"}></i> {title}
        <span className="locked-pill">Locked</span>
      </h2>

      <div className="locked-body">
        <div className="locked-rows">
          {(lines || []).map((line, i) => (
            <div className="locked-row" key={i}>
              <span className="locked-row-label">{line}</span>
              {/* A neutral placeholder bar. Deliberately grey, never red:
                  a locked value is unknown, not bad. */}
              <span className="locked-bar" aria-hidden="true" />
            </div>
          ))}
        </div>

        {preview.concerns_assessed > 0 && (
          <p className="locked-found">
            <i className="fa-solid fa-circle-check"></i>{" "}
            Already assessed for{" "}
            <strong>{(preview.concern_names || []).join(", ")}</strong>
            {preview.routine_issues_found > 0 && (
              <>
                {" "}— and found{" "}
                <strong>
                  {preview.routine_issues_found} routine{" "}
                  {preview.routine_issues_found === 1 ? "issue" : "issues"}
                </strong>
              </>
            )}
            .
          </p>
        )}

        <p className="locked-msg">{access?.message}</p>

        <button className="btn btn-primary locked-cta" onClick={onUnlock} data-testid="unlock-cta">
          <i className="fa-solid fa-unlock"></i> Unlock personal analysis
        </button>

        <p className="locked-safety">
          <i className="fa-solid fa-shield-heart"></i> {access?.safety_note}
        </p>
      </div>
    </div>
  );
}

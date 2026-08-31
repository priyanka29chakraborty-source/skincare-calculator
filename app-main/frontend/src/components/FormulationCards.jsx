import React from "react";
import { ProgressBar } from "./ScoreComponents";

/**
 * Display components for the formulation scoring engine.
 *
 * The product reports three independent things, and keeping them visually
 * separate is the point:
 *   - Formulation score: how well-made the product is. Price-independent.
 *   - Value: whether the price is fair. Never folded into quality.
 *   - Fit: whether it suits this particular user.
 *
 * Advisory flags (pregnancy, sensitivities) are shown as information and are
 * explicitly labelled as not affecting the score, because they depend on the
 * person rather than the formula.
 */

const ICONS = {
  actives: "fa-solid fa-flask-vial",
  evidence: "fa-solid fa-book-medical",
  integrity: "fa-solid fa-shield-halved",
  tolerability: "fa-solid fa-feather",
  hydration: "fa-solid fa-droplet",
  barrier: "fa-solid fa-layer-group",
  soothing: "fa-solid fa-leaf",
  surfactant: "fa-solid fa-soap",
  ph: "fa-solid fa-vial",
  post_cleanse: "fa-solid fa-hand-sparkles",
  stability: "fa-solid fa-shield-virus",
  uva: "fa-solid fa-sun",
  photostability: "fa-solid fa-clock-rotate-left",
  uvb: "fa-solid fa-umbrella-beach",
};

const CONFIDENCE = {
  high: { label: "High confidence", icon: "fa-circle-check", bg: "#f0faf2", border: "#a8dab5", fg: "#1a5c2a" },
  moderate: { label: "Moderate confidence", icon: "fa-circle-info", bg: "#f7f9fc", border: "#c3d4e8", fg: "#2c4a6e" },
  low: { label: "Low confidence", icon: "fa-circle-exclamation", bg: "#faf8f3", border: "var(--border)", fg: "#7A7168" },
  none: { label: "Not enough information", icon: "fa-circle-question", bg: "#faf8f3", border: "var(--border)", fg: "#7A7168" },
};

/** Why this category is scored the way it is, plus the per-component detail. */
export function FormulationBreakdown({ result }) {
  const components = result.formulation_breakdown || [];
  if (!components.length) return null;

  return (
    <>
      {result.formulation_rationale && (
        <div
          style={{
            background: "#faf9f7",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "10px 12px",
            marginBottom: 14,
            fontSize: 13,
            lineHeight: 1.5,
            color: "#5c554d",
          }}
        >
          <strong style={{ color: "var(--text)" }}>
            How a {(result.formulation_category || "product").toLowerCase()} is scored:
          </strong>{" "}
          {result.formulation_rationale}
        </div>
      )}

      {components.map((c) => (
        <div className="bd-row" key={c.key} data-testid={`formulation-${c.key}`}>
          <div className="bd-header">
            <i className={ICONS[c.key] || "fa-solid fa-circle-dot"}></i>
            <span className="bd-label">{c.label}</span>
            <span className="bd-score">
              {c.score} / {c.max}
            </span>
          </div>
          <ProgressBar pct={c.max ? (c.score / c.max) * 100 : 0} label={c.label} />
          {c.notes?.length > 0 && (
            <ul className="bd-details">
              {c.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </>
  );
}

/** How much to trust the numbers above. */
export function ConfidenceNote({ level, note }) {
  const c = CONFIDENCE[level] || CONFIDENCE.low;
  if (!note) return null;
  return (
    <div
      data-testid="formulation-confidence"
      style={{
        display: "flex",
        gap: 8,
        alignItems: "flex-start",
        background: c.bg,
        border: `1px solid ${c.border}`,
        color: c.fg,
        borderRadius: 8,
        padding: "9px 11px",
        fontSize: 12.5,
        marginTop: 12,
      }}
    >
      <i className={`fa-solid ${c.icon} fa-xs`} style={{ marginTop: 3, flexShrink: 0 }}></i>
      <span style={{ lineHeight: 1.45 }}>
        <strong>{c.label}.</strong> {note}
      </span>
    </div>
  );
}

/**
 * Price, reported on its own. This is deliberately separate from the
 * formulation score: there is no evidence that price predicts how well a
 * product is made, so blending them would misinform.
 */
export function ValueCard({ value, currency }) {
  if (!value) return null;
  const TIERS = {
    excellent: { fg: "#1a5c2a", bg: "#f0faf2", border: "#a8dab5", icon: "fa-circle-check" },
    good: { fg: "#1a5c2a", bg: "#f0faf2", border: "#a8dab5", icon: "fa-circle-check" },
    fair: { fg: "#7a5c15", bg: "#fdfaf0", border: "#e6d9a8", icon: "fa-circle-info" },
    premium: { fg: "#8a4b1f", bg: "#fdf5f0", border: "#e8c9b0", icon: "fa-arrow-trend-up" },
    luxury: { fg: "#8a2f2f", bg: "#fdf2f2", border: "#e8b8b8", icon: "fa-gem" },
    unknown: { fg: "#7A7168", bg: "#faf8f3", border: "var(--border)", icon: "fa-circle-question" },
  };
  const t = TIERS[value.tier] || TIERS.unknown;

  return (
    <div
      data-testid="value-card"
      style={{
        background: t.bg,
        border: `1px solid ${t.border}`,
        borderRadius: 10,
        padding: "12px 14px",
        marginTop: 14,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        <i className={`fa-solid ${t.icon}`} style={{ color: t.fg }}></i>
        <strong style={{ color: t.fg, fontSize: 14 }}>Price check</strong>
        {value.available && (
          <span style={{ marginLeft: "auto", fontSize: 12.5, color: t.fg, fontWeight: 600 }}>
            {currency} {value.price_per_ml}/ml
            {value.ratio ? ` · ${value.ratio}× category average` : ""}
          </span>
        )}
      </div>
      <p style={{ margin: 0, fontSize: 13, color: t.fg, lineHeight: 1.45 }}>{value.headline}</p>
      <p style={{ margin: "6px 0 0", fontSize: 11.5, color: "#7A7168", lineHeight: 1.4 }}>
        {value.note}
      </p>
    </div>
  );
}

/**
 * Formulation issues found in the product itself (missing preservative,
 * unstabilised active, photounstable filter system). These DO affect the score.
 */
export function FormulationFlags({ flags }) {
  const list = (flags || []).filter((f) => f.severity === "high" || f.severity === "medium");
  if (!list.length) return null;
  return (
    <div style={{ marginTop: 14 }} data-testid="formulation-flags">
      <h4 style={{ fontSize: 13, margin: "0 0 8px", display: "flex", alignItems: "center", gap: 6 }}>
        <i className="fa-solid fa-triangle-exclamation" style={{ color: "#b4541e" }}></i>
        Formulation notes
      </h4>
      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, lineHeight: 1.5, color: "#5c554d" }}>
        {list.map((f, i) => (
          <li key={i} style={{ marginBottom: 5 }}>
            {f.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Advisories that depend on the person, not the product — pregnancy above all.
 *
 * These deliberately do NOT change the score. A retinol serum is not badly made
 * because it is unsuitable during pregnancy; it is simply not for that user
 * right now. The card says so explicitly, so a high score is never read as
 * "safe for everyone".
 */
export function AdvisoryFlags({ flags }) {
  const list = flags || [];
  if (!list.length) return null;
  return (
    <div style={{ marginTop: 14 }} data-testid="advisory-flags">
      {list.map((f, i) => (
        <div
          key={i}
          style={{
            background: "#f7f9fc",
            border: "1px solid #c3d4e8",
            borderRadius: 10,
            padding: "12px 14px",
            marginBottom: 8,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <i className="fa-solid fa-circle-info" style={{ color: "#2c4a6e" }}></i>
            <strong style={{ fontSize: 13.5, color: "#2c4a6e" }}>{f.title}</strong>
            <span
              style={{
                marginLeft: "auto",
                fontSize: 10.5,
                textTransform: "uppercase",
                letterSpacing: "0.04em",
                color: "#6b7f99",
                fontWeight: 700,
              }}
            >
              Does not affect score
            </span>
          </div>
          <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.5, color: "#3d4d63" }}>{f.message}</p>
          {f.items?.length > 0 && (
            <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 12, lineHeight: 1.5, color: "#4a5a70" }}>
              {f.items.map((it, j) => (
                <li key={j} style={{ marginBottom: 3 }}>
                  <strong>{it.ingredient}</strong> — {it.guidance}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

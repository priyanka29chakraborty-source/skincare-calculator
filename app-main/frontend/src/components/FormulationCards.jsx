import React from "react";
import { CircleCheck, CircleHelp, Info, TriangleAlert } from "lucide-react";

import { money, pricePlain, categoryLabel } from "../constants";
import { Badge, Callout, Card, Meter } from "./ds";

/*
 * The product reports three independent things, and keeping them visually
 * separate is the point:
 *   - Formulation score: how well-made the product is. Price-independent.
 *   - Value: whether the price is fair. Never folded into quality.
 *   - Fit: whether it suits this particular person.
 */

const CONFIDENCE = {
  high: { label: "High confidence", tone: "positive", icon: CircleCheck },
  moderate: { label: "Moderate confidence", tone: "info", icon: Info },
  low: { label: "Low confidence", tone: "neutral", icon: Info },
  none: { label: "Not enough information", tone: "neutral", icon: CircleHelp },
};

/** How much to trust the numbers above. */
export function ConfidenceNote({ level, note }) {
  const c = CONFIDENCE[level] || CONFIDENCE.low;
  if (!note) return null;
  return (
    <Callout tone={c.tone} icon={c.icon} title={c.label} data-testid="formulation-confidence">
      <p className="callout__text">{note}</p>
    </Callout>
  );
}

/** Problems in the product itself (missing preservative, unstable active). These DO affect the score. */
export function FormulationFlags({ flags }) {
  const list = (flags || []).filter((f) => f.severity === "high" || f.severity === "medium");
  if (!list.length) return null;
  return (
    <Callout tone="caution" title="Formulation notes" data-testid="formulation-flags">
      <ul className="callout__list">{list.map((f, i) => <li key={i}>{f.message}</li>)}</ul>
    </Callout>
  );
}

/**
 * Advisories that depend on the person, not the product — pregnancy above all.
 * They deliberately do NOT change the score, and say so, so a high score is
 * never read as "safe for everyone".
 */
export function AdvisoryFlags({ flags }) {
  const list = (flags || []).filter((f) => f.type !== "climate_texture");
  if (!list.length) return null;
  return (
    <>
      {list.map((f, i) => (
        <Callout key={i} tone="info" icon={TriangleAlert} title={f.title} aside="Doesn’t affect the score" data-testid="advisory-flags">
          <p className="callout__text">{f.message}</p>
          {f.items?.length > 0 && (
            <ul className="callout__list">
              {f.items.map((it, j) => <li key={j}><strong>{it.ingredient}</strong> — {it.guidance}</li>)}
            </ul>
          )}
        </Callout>
      ))}
    </>
  );
}

const VALUE_TONE = {
  excellent: ["positive", "Good value"],
  good: ["positive", "Good value"],
  fair: ["neutral", "Fair price"],
  premium: ["caution", "Premium price"],
  luxury: ["caution", "Luxury price"],
  unknown: ["neutral", "Not enough to compare"],
};

/**
 * Price, on its own. Deliberately separate from the formulation score: there
 * is no evidence that price predicts how well a product is made.
 */
export function ValueCard({ value, priceAnalysis, currency, category }) {
  if (!value) return null;
  const [tone, label] = VALUE_TONE[value.tier] || VALUE_TONE.unknown;
  const yours = Number(value.price_per_ml) || 0;
  const avg = Number(value.category_avg) || 0;
  const max = Math.max(yours, avg) * 1.15 || 1;
  return (
    <Card eyebrow="Value" title="Price, on its own"
          sub="Price never changes the formulation score. It is compared with the usual price for this type of product in your country."
          aside={<Badge tone={tone}>{label}</Badge>} data-testid="value-card">
      <p className="t-body-l value__sentence">{pricePlain(value, currency)}</p>
      {value.available && yours > 0 && avg > 0 && (
        <div className="stack" style={{ "--stack-gap": "16px", marginTop: 20 }}>
          <Meter label="This product" value={`${money(currency, value.price_per_ml)} / ml`} pct={(yours / max) * 100} tone="accent" />
          <Meter label={`Usual ${categoryLabel(category).toLowerCase()}`} value={`${money(currency, value.category_avg)} / ml`}
                 pct={(avg / max) * 100} tone="neutral" />
        </div>
      )}
      {priceAnalysis?.price_per_active ? (
        <p className="t-caption c-tertiary" style={{ marginTop: 16 }}>
          That works out to {money(currency, priceAnalysis.price_per_active)} for each active ingredient.
        </p>
      ) : null}
      {value.note ? <p className="t-caption c-tertiary" style={{ marginTop: 8 }}>{value.note}</p> : null}
    </Card>
  );
}

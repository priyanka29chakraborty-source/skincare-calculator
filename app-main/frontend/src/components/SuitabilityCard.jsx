import React from "react";

import { getBarColor } from "../constants";
import { ConcernCard, ProgressBar } from "./ScoreComponents";

/**
 * One card answering the two questions a reader actually has about themselves,
 * which used to be two cards answering them three times over.
 *
 * "Skin Concern Fit" and "<Type> Skin Compatibility" read as the same card
 * because, in content, they largely were. The engine emits four overlapping
 * lists and both cards drew from them:
 *
 *   why_bullets         "Niacinamide supports oil control"
 *   helpful_ingredients "Niacinamide (acne support)"        <- same ingredient
 *   formulation_notes   "Coconut Oil (comedogenic 4/5)..."
 *   why_bullets         "Warning: Coconut Oil is highly pore-clogging"  <- again
 *
 * So the same ingredient was named up to three times on one screen, and the
 * concern rows named it a fourth. The split now follows the only distinction
 * that matters to someone deciding whether to buy:
 *
 *   What you are treating - does this product do the job you want?
 *   Whether it suits you  - will it cause you problems?
 *
 * Everything else is deduplicated by ingredient name rather than trusted to be
 * distinct, because these lists are generated independently and will drift.
 */

/** The ingredient a generated line is about, for deduplication. */
function subjectOf(line) {
  const text = String(line || "")
    .replace(/^warning:\s*/i, "")
    .trim();
  // Lines are "<Ingredient> ...", "Contains <Ingredient>, ...", or
  // "<Ingredient> (rating...)". Take the leading proper-noun run.
  const match = text.match(/^(?:contains\s+)?([A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*)*)/);
  return match ? match[1].toLowerCase().trim() : text.toLowerCase().slice(0, 24);
}

function dedupeAgainst(lines, alreadyShown) {
  const seen = new Set(alreadyShown.map(subjectOf));
  const out = [];
  for (const line of lines || []) {
    const key = subjectOf(line);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(line);
  }
  return out;
}

/** Everything in a line after the ingredient it is about. */
function remainderOf(line) {
  const text = String(line || "").replace(/^warning:\s*/i, "").trim();
  // Drop the leading proper-noun run, then whatever joins it to the rest: a
  // parenthetical rating that belongs to the subject, then a dash or colon.
  return text
    .replace(/^(?:contains\s+)?[A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*)*/, "")
    .replace(/^\s*\([^)]*\)/, "")
    .replace(/^[\s—–:;,-]+/, "")
    .trim() || text;
}

/** The ingredient name on its own, for use as a label. */
function labelOf(line) {
  const text = String(line || "").replace(/^warning:\s*/i, "").trim();
  const match = text.match(/^(?:contains\s+)?[A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*)*/);
  return match ? match[0].replace(/^contains\s+/i, "").trim() : text;
}

/**
 * One line per ingredient, with its reasons joined.
 *
 * The engine emits a separate note per reason, so a fragranced product
 * produced three consecutive lines all opening with "Parfum" - comedogenic
 * rating, fragrance component, contact allergen. Reading the same ingredient
 * three times running makes a formula look worse than the analysis found, and
 * makes the card look like it is padding itself.
 *
 * Deduplicating one list against another was not enough: these three all came
 * from the same list, so nothing compared them to each other.
 */

/**
 * Which kind of problem a note describes.
 *
 * The engine says the same thing in several wordings - "moderate pore-clogging
 * potential", "moderately comedogenic", "(comedogenic rating 4/5)" are one
 * fact in three voices - so matching on exact text leaves all three. Bucketing
 * by theme and keeping the best phrasing in each is what actually removes the
 * repetition.
 */
function themeOf(part) {
  const text = part.toLowerCase();
  if (/comedogenic|pore[- ]clog|clog pores|breakout/.test(text)) return "pores";
  if (/allergen|sensitiser|sensitizer|fragrance-sensitive|contact aller/.test(text)) return "allergen";
  if (/irritat|sting|drying|alcohol/.test(text)) return "irritation";
  return "other";
}

function mergeBySubject(lines) {
  const order = [];
  const bySubject = new Map();

  for (const line of lines || []) {
    if (!line) continue;
    const key = subjectOf(line);
    if (!bySubject.has(key)) {
      bySubject.set(key, { label: labelOf(line), themes: new Map() });
      order.push(key);
    }
    const { themes } = bySubject.get(key);
    const part = remainderOf(line).replace(/\s*\.\s*$/, "");
    if (!part) continue;

    const theme = themeOf(part);
    const existing = themes.get(theme);
    // Keep one phrasing per theme: prefer the one carrying a rating, then the
    // one that reads as a full clause rather than a fragment left behind by
    // stripping the ingredient name ("is highly pore-clogging").
    const score = (/\d/.test(part) ? 2 : 0) + (/^[a-z]*\s*(is|are|may|can)\b/.test(part) ? -1 : 1);
    if (!existing || score > existing.score) {
      themes.set(theme, { part, score });
    }
  }

  return order.map((key) => {
    const { label, themes } = bySubject.get(key);
    const parts = [...themes.values()].map((t) => t.part);
    if (!parts.length) return label;
    // Some notes read as a continuation of the ingredient name ("is highly
    // pore-clogging"), because stripping the name is what left them. A dash in
    // front of those produces "Coconut Oil — is highly pore-clogging"; a space
    // produces the sentence the engine originally wrote.
    if (parts.length === 1 && /^(is|are|may|can|has|have|appears)\b/i.test(parts[0])) {
      return `${label} ${parts[0]}.`;
    }
    return `${label} — ${parts.join("; ")}.`;
  });
}

const RISK_COPY = {
  low: { label: "Low irritation risk overall", tone: "good" },
  moderate: { label: "Some ingredients may not suit acne-prone or sensitive skin", tone: "warn" },
  high: { label: "Multiple irritation or pore-clogging risks — read the notes", tone: "bad" },
};

export default function SuitabilityCard({ result, skinType }) {
  const concerns = result.skin_concern_fit || {};
  const details = result.skin_type_details || {};
  const compat = result.skin_type_compatibility;
  const risk = RISK_COPY[result.skin_type_risk_level];

  const hasConcerns = Object.keys(concerns).length > 0;
  const hasCompat = typeof compat === "number";
  if (!hasConcerns && !hasCompat) return null;

  // Split the "why" bullets: warnings belong with the other risks, not among
  // the reasons the product suits you.
  const allWhy = details.why_bullets || [];
  const positives = allWhy.filter((b) => !/^warning/i.test(b));
  const whyWarnings = allWhy.filter((b) => /^warning/i.test(b))
    .map((b) => b.replace(/^warning:\s*/i, ""));

  // helpful_ingredients is dropped wherever it repeats a why bullet, which in
  // practice is almost always - it is the same ingredients with a different
  // suffix. Anything genuinely new still gets through.
  const extraHelpful = dedupeAgainst(details.helpful_ingredients, positives);
  const worksFor = [...positives, ...extraHelpful];

  const notes = details.formulation_notes || [];
  // Merged by ingredient rather than deduplicated list-against-list: the three
  // Parfum lines all came from `notes`, so nothing was comparing them to each
  // other.
  const watchFor = mergeBySubject([...notes, ...whyWarnings]);

  const lookFor = details.look_for || [];
  const betterSuited = result.better_suited || [];

  return (
    <div className="sc-card result-card suitability-card" data-testid="card-suitability"
         style={{ "--anim-delay": "0.15s" }}>
      <h2 className="card-title">
        <i className="fa-solid fa-user-check"></i> How this suits you
      </h2>

      {result.am_pm_recommendation && (
        <p className="ampm-label" data-testid="ampm-label">
          <i className="fa-regular fa-clock"></i> {result.am_pm_recommendation}
        </p>
      )}

      {hasConcerns && (
        <section className="suit-section" data-testid="suit-concerns">
          <h3 className="suit-head">
            What you are treating
            <span className="suit-head-note">does it do the job you want?</span>
          </h3>
          {Object.entries(concerns).map(([concern, data]) => (
            <ConcernCard key={concern} concern={concern} data={data} />
          ))}
        </section>
      )}

      {hasCompat && (
        <section className="suit-section" data-testid="suit-type">
          <h3 className="suit-head">
            Whether it suits {String(skinType || "your").toLowerCase()} skin
            <span className="suit-head-note">will it cause you problems?</span>
          </h3>

          <div className="compat-score-row">
            <span className="compat-pct" style={{ color: getBarColor(compat) }}>{compat}%</span>
            <ProgressBar pct={compat} label="compat" />
          </div>

          {risk && (
            <p className={`suit-risk suit-risk-${risk.tone}`} data-testid="suit-risk">
              <i className={`fa-solid ${risk.tone === "good"
                ? "fa-circle-check" : "fa-triangle-exclamation"}`}></i>
              {risk.label}
            </p>
          )}

          {worksFor.length > 0 && (
            <div className="suit-list suit-list-good">
              <h4><i className="fa-solid fa-thumbs-up"></i> Works in your favour</h4>
              <ul>{worksFor.map((b, i) => <li key={i}>{b}</li>)}</ul>
            </div>
          )}

          {watchFor.length > 0 ? (
            <div className="suit-list suit-list-watch" data-testid="suit-watch">
              <h4><i className="fa-solid fa-triangle-exclamation"></i> Watch out for</h4>
              <p className="suit-list-lede">
                Safe for many people, but worth knowing about if your skin is
                acne-prone or reactive.
              </p>
              <ul>{watchFor.map((n, i) => <li key={i}>{n}</li>)}</ul>
            </div>
          ) : (
            <div className="suit-list suit-list-clean" data-testid="suit-clean">
              <h4><i className="fa-solid fa-circle-check"></i> Nothing to watch out for</h4>
              <p>No major irritation or pore-clogging risks detected in this formula.</p>
            </div>
          )}

          {lookFor.length > 0 && (
            <div className="suit-list suit-list-next">
              <h4><i className="fa-solid fa-lightbulb"></i> What would suit you better</h4>
              <p>{lookFor[0]}</p>
            </div>
          )}

          {compat < 50 && betterSuited.length > 0 && (
            <p className="better-suited">
              <i className="fa-solid fa-arrow-right"></i> Better suited to{" "}
              {betterSuited.join(", ")} skin
            </p>
          )}
        </section>
      )}
    </div>
  );
}

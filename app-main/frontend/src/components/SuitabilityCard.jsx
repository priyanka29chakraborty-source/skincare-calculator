import React from "react";
import { CircleCheck, Lightbulb, ThumbsUp, TriangleAlert, WandSparkles } from "lucide-react";

import { ConcernCard } from "./ScoreComponents";
import { Button, Card, Meter, Callout } from "./ds";

/**
 * One card answering the two questions a reader actually has about themselves:
 *
 *   What you are treating - does this product do the job you want?
 *   Whether it suits you  - will it cause you problems?
 *
 * The engine emits four overlapping lists (why_bullets, helpful_ingredients,
 * formulation_notes, warnings), so the same ingredient could be named three
 * times. Everything is deduplicated by ingredient name, then merged per
 * ingredient so one line carries all of its reasons.
 */

function subjectOf(line) {
  const text = String(line || "").replace(/^warning:\s*/i, "").trim();
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

function remainderOf(line) {
  const text = String(line || "").replace(/^warning:\s*/i, "").trim();
  return text
    .replace(/^(?:contains\s+)?[A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*)*/, "")
    .replace(/^\s*\([^)]*\)/, "")
    .replace(/^[\s—–:;,-]+/, "")
    .trim() || text;
}

function labelOf(line) {
  const text = String(line || "").replace(/^warning:\s*/i, "").trim();
  const match = text.match(/^(?:contains\s+)?[A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*)*/);
  return match ? match[0].replace(/^contains\s+/i, "").trim() : text;
}

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
    const score = (/\d/.test(part) ? 2 : 0) + (/^[a-z]*\s*(is|are|may|can)\b/.test(part) ? -1 : 1);
    if (!existing || score > existing.score) themes.set(theme, { part, score });
  }
  return order.map((key) => {
    const { label, themes } = bySubject.get(key);
    const parts = [...themes.values()].map((t) => t.part);
    if (!parts.length) return label;
    if (parts.length === 1 && /^(is|are|may|can|has|have|appears)\b/i.test(parts[0])) return `${label} ${parts[0]}.`;
    return `${label} — ${parts.join("; ")}.`;
  });
}

const RISK_COPY = {
  low: { label: "Low irritation risk overall", tone: "positive" },
  moderate: { label: "Some ingredients may not suit this skin type", tone: "caution" },
  high: { label: "Several ingredients may not suit this skin type", tone: "negative" },
};

const WATCH_LEDE = {
  dry: "These can dry the skin or weaken the barrier.",
  oily: "These can clog pores on oily skin.",
  combination: "These can be a problem on the oilier or the drier areas.",
  sensitive: "These can sting or irritate sensitive skin.",
};

const WATCH_CLEAR = {
  dry: "Nothing here works against dry skin.",
  oily: "Nothing here is likely to clog pores on oily skin.",
  combination: "Nothing here stands out as a problem for combination skin.",
  sensitive: "Nothing here is likely to sting sensitive skin.",
};

export default function SuitabilityCard({ result, skinType }) {
  const concerns = result.skin_concern_fit || {};
  const details = result.skin_type_details || {};
  const compat = result.skin_type_compatibility;
  const risk = RISK_COPY[result.skin_type_risk_level];
  const hasConcerns = Object.keys(concerns).length > 0;
  const hasCompat = typeof compat === "number";
  const skin = String(skinType || "").toLowerCase();

  const allWhy = details.why_bullets || [];
  const positives = allWhy.filter((b) => !/^warning/i.test(b));
  const whyWarnings = allWhy.filter((b) => /^warning/i.test(b)).map((b) => b.replace(/^warning:\s*/i, ""));
  const worksFor = [...positives, ...dedupeAgainst(details.helpful_ingredients, positives)];
  const watchFor = mergeBySubject([...(details.formulation_notes || []), ...whyWarnings]);
  const lookFor = details.look_for || [];
  const betterSuited = result.better_suited || [];
  if (!hasConcerns && !hasCompat) return null;

  return (
    <Card eyebrow="Personal fit" title="How this suits you"
          sub={result.am_pm_recommendation || null} data-testid="card-suitability">
      {hasConcerns && (
        <div className="fit-block" data-testid="suit-concerns">
          <p className="fit-block__head">What you’re treating <span>does it do the job you want?</span></p>
          <div className="stack" style={{ "--stack-gap": "12px" }}>
            {Object.entries(concerns).map(([concern, data]) => <ConcernCard key={concern} concern={concern} data={data} />)}
          </div>
        </div>
      )}

      {hasCompat && (
        <div className="fit-block" data-testid="suit-type">
          <p className="fit-block__head">Whether it suits {skin || "your"} skin <span>will it cause you problems?</span></p>
          <Meter label={`${skinType || "Your"} skin compatibility`} value={`${compat}%`} pct={compat} />
          {risk && (
            <Callout tone={risk.tone} title={risk.label} data-testid="suit-risk" style={{ marginTop: 16 }} />
          )}
          <div className="fit-lists">
            {worksFor.length > 0 && (
              <div className="fit-list">
                <p className="fit-list__title"><ThumbsUp aria-hidden="true" className="c-positive" />Works in your favour</p>
                <ul>{worksFor.map((b, i) => <li key={i}>{b}</li>)}</ul>
              </div>
            )}
            {watchFor.length > 0 ? (
              <div className="fit-list" data-testid="suit-watch">
                <p className="fit-list__title"><TriangleAlert aria-hidden="true" className="c-caution" />Watch out for</p>
                <p className="t-caption c-tertiary">{WATCH_LEDE[skin] || "Worth knowing about for this skin type."}</p>
                <ul>{watchFor.map((n, i) => <li key={i}>{n}</li>)}</ul>
              </div>
            ) : (
              <div className="fit-list" data-testid="suit-clean">
                <p className="fit-list__title"><CircleCheck aria-hidden="true" className="c-positive" />Nothing to watch out for</p>
                <p className="t-body-s c-secondary">{WATCH_CLEAR[skin] || "Nothing here stands out for this skin type."}</p>
              </div>
            )}
            {lookFor.length > 0 && (
              <div className="fit-list">
                <p className="fit-list__title"><Lightbulb aria-hidden="true" className="c-accent" />What would suit you better</p>
                <p className="t-body-s c-secondary">{lookFor[0]}</p>
              </div>
            )}
          </div>
          {compat < 50 && betterSuited.length > 0 && (
            <p className="t-body-s c-secondary" style={{ marginTop: 12 }}>Better suited to {betterSuited.join(", ")} skin.</p>
          )}
        </div>
      )}
    </Card>
  );
}

/** Unlocked, but the four questions have not been answered yet. */
export function SuitabilityWaiting({ skinType, onAnswer }) {
  return (
    <Card eyebrow="Personal fit" title="How this suits you" data-testid="suitability-waiting">
      <p className="t-body-m c-secondary">
        This goes further than the {String(skinType || "skin type").toLowerCase()} {skinType ? "skin you picked" : "you picked"}.
        Four quick answers let us check what matters for you:
      </p>
      <ul className="need-list">
        <li><span>Skin tone</span>dark-mark and burn risk</li>
        <li><span>Climate</span>whether the texture will work where you live</li>
        <li><span>Sensitivities</span>flags anything you react to</li>
        <li><span>Current routine</span>clashes and doubling up</li>
      </ul>
      <Button variant="secondary" icon={<WandSparkles />} onClick={onAnswer} data-testid="suitability-answer">
        Answer 4 questions
      </Button>
    </Card>
  );
}

import React, { useState } from "react";
import {
  BookOpen, Check, ChevronDown, CircleCheck, Clock, Droplet, Droplets, Feather, FlaskConical,
  Info, Layers, Leaf, Shield, ShieldCheck, Sparkles, Sun, TestTube, Umbrella, X, Zap,
} from "lucide-react";

import { money, categoryLabel } from "../constants";
import { Badge, Callout, Card, Meter, ScoreRing, StatTile, scoreBadgeTone, cx } from "./ds";
import { ConfidenceNote, FormulationFlags, AdvisoryFlags } from "./FormulationCards";

/* ------------------------------------------------------------- helpers */

function catFlags(category) {
  const cat = String(category || "").toLowerCase();
  return {
    cat,
    isSunscreen: cat === "sunscreen",
    isCleanser: cat === "cleanser",
    isMoisturizer: cat === "moisturizer" || cat === "moisturiser",
    isFacialOil: cat === "facial oil" || cat === "oil",
    isTreatment: cat === "treatment",
    isSerum: cat === "serum",
    isToner: cat === "toner",
    isMask: cat === "mask",
  };
}

/** The API sometimes sends finished sentences, sometimes "; "-joined labels. */
function benefitText(raw) {
  if (!raw) return "";
  const text = String(raw).trim();
  if (/[.!?]$/.test(text) && text.split(/\s+/).length >= 3) return text;
  const dangling = /\b(a|an|the|is|of|to|and|or|for|with)$/i;
  const cutOff = /\bis an?\s+\w+$/i;
  const parts = text.split(/[;]/).map((s) => s.trim())
    .filter((s) => s.length >= 3 && !dangling.test(s) && !cutOff.test(s));
  if (!parts.length) return "";
  const lead = (s) => s.replace(/ \/ /g, " and ").replace(/^([A-Z])(?=[a-z])/, (m) => m.toLowerCase());
  if (parts.length === 1) return `Used for ${lead(parts[0])}.`;
  const bits = parts.map(lead);
  const body = bits.length === 2 ? `${bits[0]} and ${bits[1]}` : `${bits.slice(0, -1).join(", ")}, and ${bits[bits.length - 1]}`;
  return `Used for ${body}.`;
}

const VALUE_BADGE = {
  excellent: ["positive", "Good value"],
  good: ["positive", "Good value"],
  fair: ["neutral", "Fair price"],
  premium: ["caution", "Premium price"],
  luxury: ["caution", "Luxury price"],
};

/* ------------------------------------------------------------- Verdict */

export function VerdictCard({ result, productName, brand, category, price, size, sizeUnit, currency, skinType }) {
  const { isFacialOil, isTreatment } = catFlags(category);
  const score = result.main_worth_score;
  const eyebrow = [brand, categoryLabel(category), price && money(currency, price), size && `${size} ${sizeUnit || "ml"}`]
    .filter(Boolean).join(" · ");
  const verdict = String(result.formulation_summary || result.score_title || "").replace(/ - /g, " — ");
  const value = VALUE_BADGE[result.value_assessment?.tier];
  const compat = result.skin_type_compatibility;
  const skin = String(skinType || "").toLowerCase();

  return (
    <article className="card card--raised verdict reveal" data-testid="card-main-worth">
      <div className="verdict__copy">
        {eyebrow && <p className="t-eyebrow c-accent">{eyebrow}</p>}
        <h1 className="t-display-m verdict__name">{productName || `Your ${categoryLabel(category).toLowerCase()}`}</h1>
        {verdict && <p className="t-body-l c-secondary">{verdict}</p>}
        <div className="row wrap verdict__badges">
          {result.main_worth_tier && (
            <Badge tone={scoreBadgeTone(score)} data-testid="tier-badge">{result.main_worth_tier}</Badge>
          )}
          {value && <Badge tone={value[0]}>{value[1]}</Badge>}
          {typeof compat === "number" && skin && compat >= 70 && <Badge tone="accent">Suits {skin} skin</Badge>}
          {typeof compat === "number" && skin && compat < 50 && <Badge tone="caution">May not suit {skin} skin</Badge>}
          {isTreatment && result.is_high_intensity && <Badge tone="caution">High intensity</Badge>}
        </div>
        {(isFacialOil || result.score_confidence) && (
          <p className="verdict__confidence">
            <Info aria-hidden="true" />
            <span>{isFacialOil ? "Amounts are estimated from list position and how oil-based formulas are built." : result.score_confidence}</span>
          </p>
        )}
        {result.worth_multipliers_applied?.length > 0 && (
          <p className="t-caption c-positive">Bonus applied: {result.worth_multipliers_applied.join(", ")}</p>
        )}
      </div>
      <div className="verdict__score">
        <ScoreRing score={score} size="lg" />
        <p className="t-eyebrow c-tertiary">Formulation score</p>
      </div>
    </article>
  );
}

/* --------------------------------------------------------------- Stats */

function comp(result, key) {
  const c = (result.formulation_breakdown || []).find((x) => x.key === key);
  if (!c || !c.max) return null;
  return { score: c.score, max: c.max, pct: (c.score / c.max) * 100, label: c.label, notes: c.notes || [] };
}

function priceStat(pa, currency, category) {
  return {
    label: "Price per ml",
    value: pa?.price_per_ml ? money(currency, pa.price_per_ml) : "—",
    note: pa?.vs_average ? `${pa.vs_average} the usual ${categoryLabel(category).toLowerCase()} price` : null,
  };
}

export function StatsRow({ result, category, currency }) {
  const { isSunscreen, isCleanser, isMoisturizer, isFacialOil } = catFlags(category);
  const pa = result.price_analysis || {};
  let stats;

  if (isSunscreen) {
    const sa = result.skin_concern_fit?.["Sun Protection"]?.sunscreen_analysis;
    const filters = sa?.filters_detected?.length ?? pa.active_count ?? 0;
    const { uvb_covered: uvb, uva1_covered: uva1, uva2_covered: uva2 } = sa || {};
    const photo = sa?.score_breakdown?.photostability ?? 0;
    const spectrum = (!uvb && !uva1 && !uva2) ? "No coverage"
      : (uvb && uva1 && uva2) ? "Full broad spectrum"
      : (uvb && (uva1 || uva2)) ? "Broad spectrum" : uvb ? "UVB only" : "Partial";
    stats = [
      { label: "UV filters", value: filters, note: sa?.spf_estimate ? `Lab SPF on pack: ${sa.spf_estimate}` : null },
      { label: "Spectrum", value: spectrum, text: true, note: `UVB ${uvb ? "✓" : "✗"} · UVA ${uva1 ? "✓" : uva2 ? "partial" : "✗"}` },
      { label: "Photostability", value: photo >= 16 ? "High" : photo >= 10 ? "Medium" : "Low", text: true, note: "How well the filters hold up in sunlight" },
      priceStat(pa, currency, category),
    ];
  } else if (isCleanser) {
    const surf = comp(result, "surfactant");
    const ph = comp(result, "ph");
    const idx = surf ? Math.round(surf.pct) / 10 : null;
    const mild = idx === null ? "—" : idx >= 8 ? "Gentle" : idx >= 6 ? "Mild" : idx >= 4 ? "Moderate" : "Harsh";
    const lather = /sulfate|soap/i.test(surf?.notes?.[0] || "") ? "High foam, can strip" : "Gentle, low foam";
    stats = [
      { label: "Surfactant mildness", value: idx === null ? "—" : `${idx}/10`, note: mild },
      { label: "Lather", value: lather, text: true },
      { label: "pH suitability", value: ph ? `${Math.round(ph.pct)}%` : "—", note: "For a rinse-off cleanser" },
      priceStat(pa, currency, category),
    ];
  } else if (isMoisturizer) {
    const barrier = comp(result, "barrier");
    const bi = barrier ? Math.round(barrier.pct) : null;
    stats = [
      { label: "Barrier support", value: bi === null ? "—" : bi >= 75 ? "Strong" : bi >= 50 ? "Moderate" : "Low", text: true, note: bi === null ? null : `${bi}% of what’s possible` },
      priceStat(pa, currency, category),
      { label: "Actives found", value: pa.active_count ?? "—", note: pa.active_ratio ? `${pa.active_ratio} of the ingredients` : null },
      { label: "Usual price", value: pa.category_avg ? money(currency, pa.category_avg) : "—", note: "Per ml, for a moisturiser" },
    ];
  } else if (isFacialOil) {
    const meta = result.oil_metadata || {};
    const aox = meta.antioxidant_count ?? 0;
    const fa = (meta.linoleic_count ?? 0) > (meta.oleic_count ?? 0) ? "Linoleic-rich"
      : (meta.oleic_count ?? 0) > (meta.linoleic_count ?? 0) ? "Oleic-rich" : "Balanced";
    stats = [
      { label: "Oils in the blend", value: meta.oil_diversity ?? pa.active_count ?? 0 },
      { label: "Antioxidants", value: aox, note: aox >= 5 ? "High protection" : aox >= 3 ? "Some protection" : aox >= 1 ? "Low protection" : "None found" },
      { label: "Fatty acid type", value: fa, text: true, note: fa === "Linoleic-rich" ? "Lighter, often better for oily skin" : fa === "Oleic-rich" ? "Richer, often better for dry skin" : null },
      priceStat(pa, currency, category),
    ];
  } else {
    stats = [
      priceStat(pa, currency, category),
      { label: "Usual price", value: pa.category_avg ? money(currency, pa.category_avg) : "—", note: `Per ml, for a ${categoryLabel(category).toLowerCase()}` },
      { label: "Actives found", value: pa.active_count ?? "—", note: pa.active_ratio ? `${pa.active_ratio} of the ingredients` : null },
      { label: "Price per active", value: pa.price_per_active ? money(currency, pa.price_per_active) : "—", note: "What each active costs you" },
    ];
  }

  return (
    <div className="stats reveal" style={{ "--i": 1 }} data-testid="price-grid">
      {stats.map((s) => <StatTile key={s.label} label={s.label} value={s.value} note={s.note} textValue={s.text} />)}
    </div>
  );
}

/* ---------------------------------------------------------- Advisories */

export function Advisories({ result, category, concerns }) {
  const { isTreatment } = catFlags(category);
  const highIntensity = isTreatment && result.is_high_intensity;
  const flags = (result.advisory_flags || []).filter((f) => f.type !== "climate_texture");
  const redFlags = result.red_flags || [];
  const priceNote = result.price_analysis?.price_note;
  if (!highIntensity && !flags.length && !redFlags.length && !priceNote) return null;
  const actives = result.high_intensity_actives || [];
  return (
    <div className="stack reveal" style={{ "--i": 2, "--stack-gap": "12px" }}>
      {highIntensity && (
        <Callout tone="caution" icon={Zap} title="High-intensity formula" data-testid="high-intensity-banner">
          <p className="callout__text">
            {actives.length > 0 && <><strong>{actives.join(", ")}</strong> works fast. </>}
            It can cause purging or dryness at first. Best suited for {concerns?.length ? concerns.join(", ") : "the concern you chose"}.
            Introduce it slowly and always follow with sunscreen.
          </p>
        </Callout>
      )}
      <AdvisoryFlags flags={flags} />
      {redFlags.length > 0 && (
        <Callout tone="negative" title="Worth knowing before you buy" data-testid="red-flags-section">
          <ul className="callout__list">{redFlags.map((rf, i) => <li key={i} data-testid={`red-flag-${i}`}>{rf}</li>)}</ul>
        </Callout>
      )}
      {priceNote && <Callout tone="info" title="About the price" data-testid="price-note"><p className="callout__text">{priceNote}</p></Callout>}
    </div>
  );
}

/* ----------------------------------------------------------- Breakdown */

const PART_ICONS = {
  actives: FlaskConical, evidence: BookOpen, integrity: ShieldCheck, tolerability: Feather,
  hydration: Droplet, barrier: Layers, soothing: Leaf, surfactant: Droplets, ph: TestTube,
  post_cleanse: Sparkles, stability: Shield, uva: Sun, photostability: Clock, uvb: Umbrella,
};

function BreakdownRow({ c }) {
  const [open, setOpen] = useState(false);
  const Icon = PART_ICONS[c.key] || FlaskConical;
  const notes = c.notes || [];
  const pct = c.max ? (c.score / c.max) * 100 : 0;
  const fmt = (n) => (Number.isInteger(n) ? n : Number(n).toFixed(1));
  return (
    <div className="part" data-testid={`formulation-${c.key}`}>
      <Meter icon={<Icon aria-hidden="true" />} label={c.label} value={`${fmt(c.score)} / ${c.max}`} pct={pct} />
      {notes[0] && <p className="part__note">{notes[0]}</p>}
      {notes.length > 1 && (
        <>
          <div className="reveal-panel" data-open={open}>
            <div><ul className="part__more">{notes.slice(1).map((n, i) => <li key={i}>{n}</li>)}</ul></div>
          </div>
          <button type="button" className="link part__toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
            {open ? "Less" : `${notes.length - 1} more ${notes.length - 1 === 1 ? "detail" : "details"}`}
            <ChevronDown aria-hidden="true" style={{ transform: open ? "rotate(180deg)" : "none" }} />
          </button>
        </>
      )}
    </div>
  );
}

export function BreakdownCard({ result }) {
  const parts = result.formulation_breakdown || [];
  if (!parts.length) return null;
  const score = result.formulation_score ?? result.main_worth_score;
  return (
    <Card className="reveal" style={{ "--i": 3 }} eyebrow="Formulation breakdown" title={`How the ${score} is made`}
          sub={`${parts.length} parts, weighted for this product type. They always add up to the score — and price is never one of them.`}
          data-testid="breakdown-details">
      {result.formulation_rationale && <p className="t-body-m c-secondary breakdown__intro">{result.formulation_rationale}</p>}
      <div className="parts">{parts.map((c) => <BreakdownRow key={c.key} c={c} />)}</div>
      <div className="stack" style={{ "--stack-gap": "12px", marginTop: 24 }}>
        <ConfidenceNote level={result.formulation_confidence} note={result.formulation_confidence_note} />
        <FormulationFlags flags={result.formulation_flags} />
      </div>
    </Card>
  );
}

/* --------------------------------------------------------- Ingredients */

function evidenceBadge(raw) {
  const e = String(raw || "").toLowerCase();
  if (e.startsWith("strong")) return ["positive", "Strong"];
  if (e.startsWith("moderate")) return ["caution", "Moderate"];
  if (e.startsWith("limited")) return ["neutral", "Limited"];
  if (e.startsWith("early")) return ["neutral", "Emerging"];
  return ["neutral", "Minimal"];
}

/** "Tier 1" on screen; what the tier means on hover, focus or tap. */
function TierTag({ tier }) {
  const [show, setShow] = useState(false);
  if (!tier) return null;
  const [label, ...rest] = String(tier).split(":");
  const meaning = rest.join(":").trim();
  if (!meaning) return <span className="tier-tag">{label}</span>;
  return (
    <span className="tip">
      <button type="button" className="tier-tag" aria-label={`${label}: ${meaning}`} aria-expanded={show}
              onMouseEnter={() => setShow(true)} onMouseLeave={() => setShow(false)}
              onFocus={() => setShow(true)} onBlur={() => setShow(false)} onClick={() => setShow((s) => !s)}>
        {label}
      </button>
      {show && <span className="tip__bubble" role="tooltip"><strong>{label}</strong>{meaning}</span>}
    </span>
  );
}

function OnePercentLine({ marker }) {
  const [open, setOpen] = useState(false);
  if (!marker) return null;
  const above = marker.above_marker || [];
  const below = marker.below_marker || [];
  return (
    <div className="onepct">
      <button type="button" className="onepct__toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="row" style={{ "--row-gap": "10px" }}><Layers aria-hidden="true" />
          <span>The 1% line{marker.ingredient ? ` falls around ${marker.ingredient}` : ""}</span></span>
        <ChevronDown aria-hidden="true" style={{ transform: open ? "rotate(180deg)" : "none" }} />
      </button>
      <div className="reveal-panel" data-open={open}>
        <div>
          <div className="onepct__body">
            <p className="t-body-s c-secondary">Ingredients above about 1% are listed from most to least. Below that line, the order says nothing about amount. A guide to the list, not a measurement.</p>
            {above.length > 0 && (<><p className="t-eyebrow c-positive">Above the line — usually the larger amounts</p>
              <div className="row wrap">{above.map((x, i) => <span key={i} className="inci-chip">{x}</span>)}</div></>)}
            <div className="onepct__rule"><span>≈ 1%{marker.ingredient ? ` · ${marker.ingredient}` : ""}</span></div>
            {below.length > 0 && (<><p className="t-eyebrow c-tertiary">From here on — order does not show the amount</p>
              <div className="row wrap">{below.map((x, i) => <span key={i} className="inci-chip inci-chip--muted">{x}</span>)}</div></>)}
          </div>
        </div>
      </div>
    </div>
  );
}

export function IngredientsCard({ result, category }) {
  const { isFacialOil, isSunscreen, isMask, isSerum, isTreatment, isMoisturizer, isToner } = catFlags(category);
  const actives = result.identified_actives || [];
  const conflicts = result.ingredient_conflicts;
  const ph = result.ph_analysis;
  const showPh = !isFacialOil && !isSunscreen && !isMask && ph?.ph_range;
  const showOnePct = isSerum || isTreatment || isMoisturizer || isToner;
  const anyStated = actives.some((a) => a.concentration_known);
  const count = result.ingredient_count;
  const roles = (result.formulation_flags || []).filter((f) => f.type === "ingredient_role");

  return (
    <Card eyebrow="Ingredients" title={isFacialOil ? "Botanicals, ranked by evidence" : "Actives, ranked by evidence"}
          sub={anyStated ? "Green amounts are stated by the brand. Everything else is estimated from the ingredient’s place in the list."
            : "Amounts are estimated from each ingredient’s place in the list."}
          aside={count ? <Badge>{count} ingredients</Badge> : null}
          data-testid="ingredients-card">
      {roles.map((f, i) => (
        <p key={i} className="t-body-s c-secondary" data-testid="ingredient-role">{f.message}</p>
      ))}
      {actives.length > 0 ? (
        <div className="itable" role="table" aria-label="Identified actives">
          <div className="itable__head" role="row">
            <span role="columnheader">#</span><span role="columnheader">{isFacialOil ? "Contributor" : "Ingredient"}</span>
            <span role="columnheader">Evidence</span><span role="columnheader">Amount</span>
          </div>
          {actives.map((a, i) => {
            const [tone, label] = evidenceBadge(a.evidence);
            const what = benefitText(a.primary_benefits || a.functional_category);
            const stated = a.concentration_known && a.concentration_pct != null;
            return (
              <div className="itable__row" role="row" key={`${a.name}-${i}`}>
                <span className="itable__pos t-mono" role="cell" title="Position in the ingredient list">{a.position != null ? String(a.position).padStart(2, "0") : "—"}</span>
                <div className="itable__main" role="cell">
                  <p className="itable__name">
                    <span>{a.name}</span>
                    <TierTag tier={a.activity_tier} />
                  </p>
                  {what && <p className="t-caption c-secondary">{what}</p>}
                  {a.targets?.filter((t) => t && t.trim()).length > 0 && (
                    <div className="row wrap itable__targets">
                      {a.targets.filter((t) => t && t.trim()).map((t) => <span key={t} className="inci-chip">{t}</span>)}
                    </div>
                  )}
                  {a.mw_depth && <p className="t-caption c-tertiary">{a.mw_depth}</p>}
                  {a.provenance?.source && (
                    <p className="t-mono-s c-tertiary">
                      {[a.provenance.evidence_level, a.provenance.source, a.provenance.reviewed_at && `reviewed ${a.provenance.reviewed_at}`].filter(Boolean).join(" · ")}
                    </p>
                  )}
                </div>
                <span className="itable__ev" role="cell"><Badge tone={tone} title={a.evidence}>{label}</Badge></span>
                <span className={cx("itable__amt", stated && "itable__amt--stated")} role="cell">
                  {stated ? <><Check aria-hidden="true" />{a.concentration_pct}% stated</> : (a.concentration || "Estimated")}
                </span>
              </div>
            );
          })}
        </div>
      ) : (
        <Callout tone="neutral" title="No recognised actives">
          <p className="callout__text">Nothing in this list is in our database as an active ingredient. The score above reflects the base formula.</p>
        </Callout>
      )}

      {result.delivery_systems?.length > 0 && (
        <div className="row wrap delivery">
          <span className="t-label-s c-secondary">Advanced delivery:</span>
          {result.delivery_systems.map((d, i) => <Badge key={i} tone="info" title={d.ingredient}>{d.label}</Badge>)}
        </div>
      )}

      <div className="stack" style={{ "--stack-gap": "12px", marginTop: 24 }}>
        {showOnePct && <OnePercentLine marker={result.one_percent_marker} />}
        <Conflicts conflicts={conflicts} />
        {showPh && <PhNote ph={ph} />}
      </div>
    </Card>
  );
}

function Conflicts({ conflicts }) {
  if (!Array.isArray(conflicts)) return null;
  if (conflicts.length === 0) {
    return (
      <Callout tone="positive" title="No clashes found">
        <p className="callout__text">None of the actives in this formula work against each other. Layering with other products is a separate question.</p>
      </Callout>
    );
  }
  const tone = { high: "negative", moderate: "caution", low: "info" };
  return (
    <>
      {conflicts.map((c, i) => (
        <Callout key={i} tone={tone[c.severity] || "info"} title={c.severity === "high" ? "Clash inside this formula" : "Worth knowing"}
                 aside={c.severity ? `${c.severity} severity` : null}>
          <p className="callout__text">{c.message}</p>
        </Callout>
      ))}
    </>
  );
}

function PhNote({ ph }) {
  const warn = (ph.warnings || []).length > 0 || /too high|outside the range/.test(ph.headline || "");
  return (
    <Callout tone={warn ? "caution" : "info"} icon={TestTube}
             title={`Estimated pH ${ph.ph_range[0]}–${ph.ph_range[1]}`}
             aside={ph.confidence === "medium" ? "Medium confidence" : "Estimate"}>
      {ph.headline && <p className="callout__text">{ph.headline}</p>}
      {(ph.notes || []).length > 0 && <ul className="callout__list">{ph.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
      {(ph.warnings || []).map((w, i) => <p key={i} className="callout__text" style={{ color: "var(--status-caution)" }}>{w}</p>)}
      <p className="callout__text t-caption">Inferred from the buffering ingredients — not a lab measurement.</p>
    </Callout>
  );
}

/* ----------------------------------------------------------- Sunscreen */

export function SunscreenCard({ data }) {
  const [open, setOpen] = useState(false);
  const sa = data?.sunscreen_analysis;
  if (!sa) return null;
  const b = sa.score_breakdown || {};
  const filters = sa.filters_detected || [];
  const notes = [...(sa.warnings || []), ...(sa.flags || [])];
  const reefSafe = sa.reef_safe !== false;
  const cov = [["UVB", sa.uvb_covered], ["UVA1", sa.uva1_covered], ["UVA2", sa.uva2_covered], ["Broad spectrum", sa.broad_spectrum], ["Reef-safe filters", reefSafe]];
  return (
    <Card eyebrow="Sunscreen" title="Filter system" sub="SPF and PA are lab grades of the finished product. This describes the filters; it doesn’t assign either grade."
          aside={<ScoreRing score={sa.overall_score ?? 0} size="sm" animate={false} label="Filter quality" />}
          data-testid="card-sunscreen-analysis">
      <div className="stats" style={{ "--stat-cols": 3, marginBottom: 20 }}>
        <StatTile label="Filter quality" value={sa.overall_score ?? "—"} note="Out of 100" />
        <StatTile label="Lab SPF (on pack)" value={sa.spf_estimate || "—"} textValue />
        <StatTile label="Lab PA (on pack)" value={sa.pa_estimate || "—"} textValue />
      </div>
      <div className="row wrap" style={{ marginBottom: 20 }}>
        {cov.map(([label, ok]) => (
          <span key={label} className={cx("cov", ok ? "cov--on" : "cov--off")}>{ok ? <Check aria-hidden="true" /> : <X aria-hidden="true" />}{label}</span>
        ))}
      </div>
      <div className="parts">
        {[["UV coverage", b.uv_coverage, 40], ["Filter strength", b.filter_strength, 30], ["Photostability", b.photostability, 20], ["Formulation", b.formulation, 10]].map(([l, v, m]) => (
          <Meter key={l} label={l} value={`${v ?? 0} / ${m}`} pct={((v ?? 0) / m) * 100} />
        ))}
      </div>
      {notes.length > 0 && (
        <div className="stack" style={{ "--stack-gap": "10px", marginTop: 20 }}>
          {notes.map((w, i) => (
            <Callout key={i} tone={w.startsWith("🚨") ? "negative" : "caution"}>
              <p className="callout__text">{w.replace(/^[^\p{L}\p{N}]+/u, "")}</p>
            </Callout>
          ))}
        </div>
      )}
      {filters.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <button type="button" className="link" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
            UV filters found ({filters.length})<ChevronDown aria-hidden="true" style={{ transform: open ? "rotate(180deg)" : "none" }} />
          </button>
          <div className="reveal-panel" data-open={open}>
            <div><div className="row wrap" style={{ paddingTop: 12 }}>{filters.map((f) => <span key={f} className="inci-chip">{f}</span>)}</div></div>
          </div>
        </div>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------- Method */

export function MethodNote() {
  return (
    <section className="method-note" data-testid="disclaimer">
      <p className="t-label-s"><CircleCheck aria-hidden="true" />How scores are calculated</p>
      <ul>
        <li><strong>Scores are estimates</strong> from each ingredient’s position and published clinical evidence.</li>
        <li><strong>Amounts are estimated</strong> from list order unless the product page states a percentage.</li>
        <li><strong>pH is directional</strong>, inferred from the buffering ingredients.</li>
        <li><strong>Clashes are checked within this formula only</strong> — always patch test something new.</li>
        <li><strong>Not medical advice.</strong> For a skin condition, see a dermatologist.</li>
      </ul>
      <p className="t-caption c-tertiary">Price is shown separately and never changes the formulation score.</p>
    </section>
  );
}

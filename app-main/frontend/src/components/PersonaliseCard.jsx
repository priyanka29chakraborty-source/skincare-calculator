import React, { useState } from "react";
import { Check, CircleCheck, Circle, Lock, TriangleAlert } from "lucide-react";

import { Button, Card, Badge, cx } from "./ds";

/**
 * Progressive personalisation, shown AFTER a result - never before one.
 * Nothing here changes the formulation score: these answers refine how well
 * the product suits this person, which is a different question.
 */

const FITZPATRICK = [
  { key: "I", swatch: "#F5D9C7", label: "Always burns, never tans" },
  { key: "II", swatch: "#EFC9A8", label: "Burns easily, tans a little" },
  { key: "III", swatch: "#DFAE7E", label: "Sometimes burns, tans gradually" },
  { key: "IV", swatch: "#C08A5A", label: "Rarely burns, tans easily" },
  { key: "V", swatch: "#8D5A34", label: "Very rarely burns, tans deeply" },
  { key: "VI", swatch: "#5A3420", label: "Never burns, deeply pigmented" },
];

const CLIMATES = [
  { key: "tropical_humid", label: "Humid", hint: "Coastal, monsoon, tropical" },
  { key: "hot_arid", label: "Hot & dry", hint: "Desert, arid summer" },
  { key: "temperate", label: "Temperate", hint: "Mild, four seasons" },
  { key: "cold_dry", label: "Cold & dry", hint: "Winter, heated indoors" },
];

const ALLERGENS = [
  { key: "fragrance", label: "Fragrance" },
  { key: "essential_oils", label: "Essential oils" },
  { key: "alcohol", label: "Drying alcohols" },
  { key: "sulfates", label: "Sulfates" },
  { key: "silicones", label: "Silicones" },
  { key: "parabens", label: "Parabens" },
  { key: "nut_oils", label: "Nut oils" },
  { key: "lanolin", label: "Lanolin" },
];

function draftAnswer(key, draft) {
  if (key === "skin_tone") return draft.fitzpatrick ? `Type ${draft.fitzpatrick}` : "";
  if (key === "climate") return (CLIMATES.find((c) => c.key === draft.climate) || {}).label || "";
  if (key === "allergens") {
    return draft.allergens.map((k) => (ALLERGENS.find((a) => a.key === k) || {}).label).filter(Boolean).join(", ");
  }
  if (key === "routine") return (draft.current_routine || "").trim();
  return "";
}

export default function PersonaliseCard({ profile, onApply, loading, level, locked, onUnlock, personalisation, opened, ctaLabel = "Unlock with 1 credit" }) {
  const checks = personalisation?.checks || [];
  const [showChecks, setShowChecks] = useState(false);
  const [draft, setDraft] = useState({
    fitzpatrick: profile?.fitzpatrick || "",
    climate: profile?.climate || "",
    allergens: profile?.allergens || [],
    current_routine: profile?.current_routine || "",
  });

  const toggleAllergen = (key) => setDraft((d) => ({
    ...d, allergens: d.allergens.includes(key) ? d.allergens.filter((a) => a !== key) : [...d.allergens, key],
  }));

  const answered = ["fitzpatrick", "climate", "current_routine"].filter((k) => draft[k]).length + (draft.allergens.length ? 1 : 0);

  // Locked: these questions are the paid product, so the card collects
  // nothing - taking someone's allergies and returning no warning would leave
  // them believing we had checked.
  if (locked) {
    return (
      <Card eyebrow="Personal fit" title="Tune this to your skin" aside={<Badge><Lock aria-hidden="true" style={{ width: 12, height: 12 }} />Locked</Badge>}
            data-testid="personalise-locked">
        <p className="t-body-m c-secondary">Four things change how well a product suits <em>you</em>. None of them change how well it is made, so the score above stays as it is.</p>
        <ul className="need-list">
          <li><span>Skin tone</span>dark-mark and burn risk</li>
          <li><span>Climate</span>whether the texture will work where you live</li>
          <li><span>Sensitivities</span>flags anything you react to</li>
          <li><span>Current routine</span>clashes and doubling up with what you use</li>
        </ul>
        <Button variant="accent" size="lg" block icon={<Lock />} onClick={onUnlock} data-testid="personalise-unlock">
          {ctaLabel}
        </Button>
        <p className="t-caption c-tertiary" style={{ textAlign: "center", marginTop: 10 }}>One credit covers this product for good — reopening it is free.</p>
      </Card>
    );
  }

  if (!opened && level === "none") return null;

  return (
    <Card eyebrow="Personal fit" title="Four questions for a sharper fit"
          sub="Each answer sharpens how well this product suits you. None of them change the formulation score."
          data-testid="personalise-card">
      <div className="q">
        <p className="q__label" id="q-tone">Skin tone <span>affects dark-mark and burn risk</span></p>
        <div className="row wrap" role="radiogroup" aria-labelledby="q-tone" style={{ "--row-gap": "8px" }}>
          {FITZPATRICK.map((f) => {
            const on = draft.fitzpatrick === f.key;
            return (
              <button key={f.key} type="button" role="radio" aria-checked={on} title={f.label}
                      className={cx("tone", on && "tone--on")} data-testid={`fitz-${f.key}`}
                      onClick={() => setDraft((d) => ({ ...d, fitzpatrick: on ? "" : f.key }))}>
                <span className="tone__swatch" style={{ background: f.swatch }} />
                <span className="t-mono-s">{f.key}</span>
              </button>
            );
          })}
        </div>
        {draft.fitzpatrick && <p className="t-caption c-tertiary">{FITZPATRICK.find((f) => f.key === draft.fitzpatrick)?.label}</p>}
      </div>

      <div className="q">
        <p className="q__label" id="q-climate">Your climate <span>affects how a texture feels</span></p>
        <div className="climate-grid" role="radiogroup" aria-labelledby="q-climate">
          {CLIMATES.map((c) => {
            const on = draft.climate === c.key;
            return (
              <button key={c.key} type="button" role="radio" aria-checked={on} className={cx("option", on && "option--on")}
                      data-testid={`climate-${c.key}`} onClick={() => setDraft((d) => ({ ...d, climate: on ? "" : c.key }))}>
                <span className="t-label-s">{c.label}</span>
                <span className="t-caption c-tertiary">{c.hint}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="q">
        <p className="q__label">Anything you react to? <span>we’ll warn you if it’s in there</span></p>
        <div className="chip-group">
          {ALLERGENS.map((a) => {
            const on = draft.allergens.includes(a.key);
            return (
              <button key={a.key} type="button" className="chip" aria-pressed={on} onClick={() => toggleAllergen(a.key)}
                      data-testid={`allergen-${a.key}`}>
                {on && <Check aria-hidden="true" />}{a.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="q">
        <label className="q__label" htmlFor="routine">What are you already using? <span>catches clashes and doubling up</span></label>
        <div className="field__control">
          <input id="routine" type="text" value={draft.current_routine}
                 onChange={(e) => setDraft((d) => ({ ...d, current_routine: e.target.value }))}
                 placeholder="e.g. retinol serum, vitamin C serum" data-testid="routine-input" />
        </div>
      </div>

      {showChecks && checks.length > 0 && (
        <div className="checks" data-testid="personal-checks">
          <p className="t-eyebrow c-tertiary">What your answers changed</p>
          <ul>
            {checks.map((c) => {
              const chosen = draftAnswer(c.key, draft);
              const fromCountry = c.key === "climate" && /from your country/i.test(c.answer || "");
              const pending = Boolean(chosen) && (c.status === "unanswered" || fromCountry);
              const status = pending ? "unanswered" : c.status;
              const Icon = status === "flagged" ? TriangleAlert : status === "clear" ? CircleCheck : Circle;
              return (
                <li key={c.key} className={`check check--${status}`}>
                  <Icon aria-hidden="true" />
                  <span>
                    <strong>{c.label}</strong>
                    {pending ? ` — ${chosen}. Press Update result to check this.`
                      : c.answer ? ` — ${c.answer}. ` : " — not answered yet. "}
                    {!pending && !fromCountry && (c.finding || (c.status === "unanswered" ? "Answer it and we’ll check this one too." : ""))}
                    {!pending && fromCountry && c.finding ? c.finding : ""}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <div className="row wrap" style={{ "--row-gap": "10px", marginTop: 8 }}>
        <Button variant="primary" loading={loading} loadingText="Updating…" disabled={answered === 0}
                onClick={() => { setShowChecks(true); onApply(draft); }} data-testid="personalise-apply">
          Update result
        </Button>
        <Button variant="ghost" disabled={loading}
                onClick={() => { setDraft({ fitzpatrick: "", climate: "", allergens: [], current_routine: "" }); setShowChecks(false); }}>
          Clear answers
        </Button>
      </div>
    </Card>
  );
}

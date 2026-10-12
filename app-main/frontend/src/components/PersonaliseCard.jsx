import React, { useState } from "react";

/**
 * Progressive personalisation.
 *
 * Deliberately shown AFTER a result, never before one. Asking eight questions
 * up front is a wall in front of the thing people came for - most of them are
 * holding one product and want one answer. Once they have that answer, three
 * more questions to sharpen it is a fair trade they can see the value of.
 *
 * Nothing here changes the formulation score. These answers refine how well
 * the product suits THIS person, which is a different question from how well
 * it is made, and the card says so plainly.
 */

const FITZPATRICK = [
  { key: "I", swatch: "#F5D9C7", label: "Always burns, never tans" },
  { key: "II", swatch: "#EFC9A8", label: "Burns easily, tans minimally" },
  { key: "III", swatch: "#DFAE7E", label: "Burns moderately, tans gradually" },
  { key: "IV", swatch: "#C08A5A", label: "Burns minimally, tans easily" },
  { key: "V", swatch: "#8D5A34", label: "Rarely burns, tans profusely" },
  { key: "VI", swatch: "#5A3420", label: "Never burns, deeply pigmented" },
];

const CLIMATES = [
  { key: "tropical_humid", label: "Humid", hint: "Coastal, monsoon, tropical" },
  { key: "hot_arid", label: "Hot & dry", hint: "Desert, arid summer" },
  { key: "temperate", label: "Temperate", hint: "Mild, four seasons" },
  { key: "cold_dry", label: "Cold & dry", hint: "Winter, heated indoors" },
];

function draftAnswer(key, draft) {
  if (key === "skin_tone") return draft.fitzpatrick ? `Type ${draft.fitzpatrick}` : "";
  if (key === "climate") {
    const match = CLIMATES.find((c) => c.key === draft.climate);
    return match ? match.label : "";
  }
  if (key === "allergens") {
    return draft.allergens
      .map((k) => (ALLERGENS.find((a) => a.key === k) || {}).label)
      .filter(Boolean)
      .join(", ");
  }
  if (key === "routine") return (draft.current_routine || "").trim();
  return "";
}

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

export default function PersonaliseCard({ profile, onApply, loading, level,
                                         locked, onUnlock, personalisation,
                                         opened }) {
  const checks = personalisation?.checks || [];
  const [showChecks, setShowChecks] = useState(false);
  const [draft, setDraft] = useState({
    fitzpatrick: profile?.fitzpatrick || "",
    climate: profile?.climate || "",
    allergens: profile?.allergens || [],
    current_routine: profile?.current_routine || "",
  });

  const toggleAllergen = (key) =>
    setDraft((d) => ({
      ...d,
      allergens: d.allergens.includes(key)
        ? d.allergens.filter((a) => a !== key)
        : [...d.allergens, key],
    }));

  const answered = ["fitzpatrick", "climate", "current_routine"].filter((k) => draft[k]).length
    + (draft.allergens.length ? 1 : 0);

  // Locked: the four steps are the paid product, so the card does not collect
  // them. It describes what they do and offers to unlock, and deliberately
  // asks for nothing - taking someone's allergies and then returning no
  // warning would leave them believing we had checked, which is worse than
  // never asking. The server drops a profile from an unentitled request for
  // the same reason.
  if (locked) {
    return (
      <div className="personalise-prompt personalise-locked"
           data-testid="personalise-locked">
        <div className="personalise-locked-head">
          <i className="fa-solid fa-wand-magic-sparkles"></i>
          <strong>Tune this to your skin</strong>
          <span className="personalise-locked-pill">Locked</span>
        </div>
        <p className="personalise-locked-lede">
          Four things change how well a product suits <em>you</em> — none of
          them change how well it is made, so the score above stays as it is.
        </p>
        <ul className="personalise-locked-list">
          <li><strong>Skin tone</strong> — dark-mark and burn risk</li>
          <li><strong>Climate</strong> — whether the texture will suit where you live</li>
          <li><strong>Sensitivities</strong> — flags anything you react to</li>
          <li><strong>Current routine</strong> — clashes and duplication with what you already use</li>
        </ul>
        <button className="locked-cta" onClick={onUnlock} data-testid="personalise-unlock">
          <span className="locked-cta-main">
            <i className="fa-solid fa-lock-open"></i> Unlock this section
          </span>
          <span className="locked-cta-sub">
            One credit &middot; covers this product for good
          </span>
        </button>
      </div>
    );
  }

  // The questions stay hidden until the reader asks for them from
  // "How this suits you". A banner here repeated that card.
  if (!opened && level === "none") {
    return null;
  }

  return (
    <div className="personalise-card" data-testid="personalise-card">
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <strong style={{ fontSize: 14.5 }}>Make this more accurate</strong>
        <span
          style={{
            marginLeft: "auto", fontSize: 10.5, textTransform: "uppercase",
            letterSpacing: "0.04em", color: "var(--text-sub)", fontWeight: 700,
          }}
        >
          Does not change the formulation score
        </span>
      </div>
      <p style={{ margin: "0 0 16px", fontSize: 12.5, color: "var(--text-sub)", lineHeight: 1.5 }}>
        All optional. Each answer sharpens how well this product suits you personally.
      </p>

      {/* 1 — Skin tone */}
      <div className="personalise-step">
        <div className="field-label" style={{ marginBottom: 8 }}>
          Skin tone <span style={{ fontWeight: 400, color: "var(--text-sub)" }}>— affects dark-mark and burn risk</span>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }} role="radiogroup" aria-label="Skin tone">
          {FITZPATRICK.map((f) => {
            const active = draft.fitzpatrick === f.key;
            return (
              <button
                key={f.key}
                type="button"
                role="radio"
                aria-checked={active}
                title={f.label}
                onClick={() => setDraft((d) => ({ ...d, fitzpatrick: active ? "" : f.key }))}
                data-testid={`fitz-${f.key}`}
                style={{
                  width: 52, padding: "6px 0 5px", borderRadius: 8, cursor: "pointer",
                  border: active ? "2px solid var(--dusty-rose-dark)" : "1px solid var(--border)",
                  background: "var(--warm-white)",
                }}
              >
                <span
                  style={{
                    display: "block", width: 26, height: 26, borderRadius: "50%",
                    background: f.swatch, margin: "0 auto 4px",
                    border: "1px solid rgba(0,0,0,0.08)",
                  }}
                />
                <span style={{ fontSize: 10.5, fontWeight: 600 }}>{f.key}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 2 — Climate */}
      <div className="personalise-step">
        <div className="field-label" style={{ marginBottom: 8 }}>
          Your climate <span style={{ fontWeight: 400, color: "var(--text-sub)" }}>— affects how a texture feels</span>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }} role="radiogroup" aria-label="Climate">
          {CLIMATES.map((c) => {
            const active = draft.climate === c.key;
            return (
              <button
                key={c.key}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => setDraft((d) => ({ ...d, climate: active ? "" : c.key }))}
                data-testid={`climate-${c.key}`}
                style={{
                  padding: "7px 12px", borderRadius: 8, cursor: "pointer", textAlign: "left",
                  border: active ? "2px solid var(--dusty-rose-dark)" : "1px solid var(--border)",
                  background: "var(--warm-white)",
                }}
              >
                <div style={{ fontSize: 12.5, fontWeight: 600 }}>{c.label}</div>
                <div style={{ fontSize: 10.5, color: "var(--text-sub)" }}>{c.hint}</div>
              </button>
            );
          })}
        </div>
      </div>

      {/* 3 — Sensitivities */}
      <div className="personalise-step">
        <div className="field-label" style={{ marginBottom: 8 }}>
          Anything you react to?{" "}
          <span style={{ fontWeight: 400, color: "var(--text-sub)" }}>— we will warn you if it is in there</span>
        </div>
        <div style={{ display: "flex", gap: 7, flexWrap: "wrap" }}>
          {ALLERGENS.map((a) => {
            const active = draft.allergens.includes(a.key);
            return (
              <button
                key={a.key}
                type="button"
                aria-pressed={active}
                onClick={() => toggleAllergen(a.key)}
                data-testid={`allergen-${a.key}`}
                style={{
                  padding: "5px 11px", borderRadius: 99, fontSize: 12, cursor: "pointer",
                  border: active ? "2px solid var(--dusty-rose-dark)" : "1px solid var(--border)",
                  background: active ? "var(--rose)" : "var(--warm-white)",
                  fontWeight: active ? 600 : 400,
                }}
              >
                {a.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Optional 4th — routine */}
      <div className="personalise-step">
        <div className="field-label" style={{ marginBottom: 6 }}>
          What are you already using?{" "}
          <span style={{ fontWeight: 400, color: "var(--text-sub)" }}>— optional, catches clashes</span>
        </div>
        <input
          type="text"
          value={draft.current_routine}
          onChange={(e) => setDraft((d) => ({ ...d, current_routine: e.target.value }))}
          placeholder="e.g. The Ordinary Retinol, vitamin C serum"
          aria-label="Current routine"
          data-testid="routine-input"
          style={{
            width: "100%", padding: "9px 11px", borderRadius: 8, fontSize: 13,
            border: "1px solid var(--border)", background: "var(--warm-white)",
          }}
        />
      </div>

      {/* Shown only after Update result. Before that click the rows would
          describe an analysis that has not been run yet. */}
      {showChecks && checks.length > 0 && (
        <div className="personal-checks" data-testid="personal-checks">
          <h4>What your answers changed</h4>
          <ul>
            {checks.map((c) => {
              const chosen = draftAnswer(c.key, draft);
              const fromCountry = c.key === "climate" && /from your country/i.test(c.answer || "");
              const pending = Boolean(chosen) && (c.status === "unanswered" || fromCountry);
              const status = pending ? "unanswered" : c.status;
              return (
              <li key={c.key} className={`personal-check personal-check-${status}`}>
                <i className={
                  status === "flagged" ? "fa-solid fa-triangle-exclamation"
                  : status === "clear" ? "fa-solid fa-circle-check"
                  : "fa-regular fa-circle"}></i>
                <span>
                  <strong>{c.label}</strong>
                  {pending
                    ? ` — ${chosen}. Press Update result to check this.`
                    : c.answer
                      ? ` — ${c.answer}. `
                      : " — not answered yet. "}
                  {!pending && !fromCountry && (c.finding
                    || (c.status === "unanswered"
                        ? "Answer it and we will check this one too."
                        : ""))}
                  {!pending && fromCountry && c.finding ? c.finding : ""}
                </span>
              </li>
              );
            })}
          </ul>
        </div>
      )}

      <div className="personalise-actions">
        <button
          className="personalise-update"
          onClick={() => { setShowChecks(true); onApply(draft); }}
          disabled={loading || answered === 0}
          data-testid="personalise-apply"
        >
          {loading ? (
            <>
              <i className="fa-solid fa-spinner fa-spin"></i> Updating…
            </>
          ) : (
            "Update result"
          )}
        </button>
        <button
          type="button"
          className="personalise-clear"
          disabled={loading}
          onClick={() => {
            setDraft({ fitzpatrick: "", climate: "", allergens: [], current_routine: "" });
            setShowChecks(false);
          }}
        >
          Clear
        </button>
      </div>
    </div>
  );
}

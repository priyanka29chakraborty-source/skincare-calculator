import React from "react";

import { money } from "../constants";

/**
 * The PDF.
 *
 * Export used to print the page itself, which meant the output was a picture
 * of an interface: collapsed accordions stayed collapsed, empty states printed
 * as empty boxes, and nothing on the page said which product it was once it
 * had scrolled past the header. A saved report is read weeks later, often by
 * someone who was not there when it was generated, so it has to stand alone.
 *
 * This is a separate document rather than a restyling of the app. It is hidden
 * on screen and is the only thing that prints.
 *
 * Two rules it follows throughout:
 *
 *   Nothing that was not assessed appears. Every section is conditional on its
 *   data actually existing, so the report has no empty headings and no "—"
 *   placeholders. A short report means a short analysis, which is itself worth
 *   knowing.
 *
 *   Nothing is restated. The app can afford to repeat a point across cards
 *   because you scroll past it; on paper repetition reads as padding and makes
 *   the document look longer than its evidence.
 */

function fmt(n, dp = 0) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return null;
  const num = Number(n);
  return dp === 0 ? String(Math.round(num)) : String(Number(num.toFixed(dp)));
}

function today() {
  try {
    return new Date().toLocaleDateString(undefined, {
      year: "numeric", month: "long", day: "numeric",
    });
  } catch {
    return new Date().toISOString().slice(0, 10);
  }
}

export default function PrintReport({
  result, productName, brand, category, price, size, sizeUnit,
  currency, skinType, concerns,
}) {
  if (!result) return null;

  const score = result.formulation_score ?? result.main_worth_score;
  const tier = result.formulation_tier || result.main_worth_tier;
  const summary = result.formulation_summary || result.score_title;
  const breakdown = result.formulation_breakdown || [];
  const value = result.value_assessment || {};
  const actives = result.identified_actives || [];
  const concernFit = result.skin_concern_fit || {};
  const details = result.skin_type_details || {};
  const advisories = result.advisory_flags || [];
  const flags = result.formulation_flags || [];
  const compat = result.skin_type_compatibility;

  // The server already withheld the personal sections; this is what the
  // document says about that. `access.tier` is the server's answer.
  const isFree = result.access?.tier === "free";

  const unit = sizeUnit === "g" ? "g" : "ml";
  const perUnit = (price && size) ? Number(price) / Number(size) : null;

  return (
    <div className="print-report" data-testid="print-report" aria-hidden="true">
      {/* ---------------------------------------------------------------- */}
      <header className="pr-head">
        <div>
          <div className="pr-eyebrow">Formulation analysis</div>
          <h1 className="pr-product">{productName || "Unnamed product"}</h1>
          <div className="pr-sub">
            {[brand, category].filter(Boolean).join(" · ")}
          </div>
        </div>
        <div className="pr-score-block">
          {isFree && <div className="pr-tier-badge">Formulation report</div>}
          <div className="pr-score">{fmt(score)}<span>/100</span></div>
          {tier && <div className="pr-tier">{tier}</div>}
        </div>
      </header>

      <dl className="pr-facts">
        {price ? (
          <div><dt>Price</dt><dd>{money(currency, price)}</dd></div>
        ) : null}
        {size ? (
          <div><dt>Size</dt><dd>{size} {unit}</dd></div>
        ) : null}
        {perUnit ? (
          <div><dt>Per {unit}</dt><dd>{money(currency, fmt(perUnit, 2))}</dd></div>
        ) : null}
        {skinType ? (
          <div><dt>Analysed for</dt><dd>{skinType} skin</dd></div>
        ) : null}
        {concerns && concerns.length > 0 ? (
          <div><dt>Concerns</dt><dd>{concerns.join(", ")}</dd></div>
        ) : null}
        <div><dt>Report date</dt><dd>{today()}</dd></div>
      </dl>

      {summary && <p className="pr-summary">{summary}</p>}

      {/* ------------------------------------------------- score breakdown */}
      {breakdown.length > 0 && (
        <section className="pr-section">
          <h2>How the score was reached</h2>
          {result.formulation_rationale && (
            <p className="pr-rationale">{result.formulation_rationale}</p>
          )}
          <table className="pr-table">
            <thead>
              <tr><th>Component</th><th className="pr-num">Score</th><th>What drove it</th></tr>
            </thead>
            <tbody>
              {breakdown.map((c) => (
                <tr key={c.key}>
                  <td className="pr-comp">{c.label}</td>
                  <td className="pr-num">{fmt(c.score, 1)} / {fmt(c.max)}</td>
                  <td>
                    {(c.notes || []).length > 0
                      ? (c.notes || []).join(" ")
                      : <span className="pr-muted">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* ------------------------------------------------------- the actives */}
      {actives.length > 0 && (
        <section className="pr-section">
          <h2>Active ingredients identified</h2>
          <table className="pr-table">
            <thead>
              <tr>
                <th>Ingredient</th><th className="pr-num">Position</th>
                <th>Estimated level</th><th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {actives.map((a, i) => (
                <tr key={i}>
                  <td className="pr-comp">{a.name}</td>
                  <td className="pr-num">{a.position ?? "—"}</td>
                  <td>
                    {a.concentration_known && a.concentration_pct
                      ? `${a.concentration_pct}%`
                      : (a.concentration || "Not determinable from the label")}
                  </td>
                  <td>{a.evidence || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* -------------------------------------------------------------- value */}
      {value.available && (
        <section className="pr-section">
          <h2>Price, assessed separately</h2>
          <p>
            {money(currency, value.price_per_ml)} per {unit}
            {value.category_avg
              ? ` against a category average of ${money(currency, value.category_avg)}`
              : ""}
            {value.ratio ? ` (${value.ratio}×).` : "."}
            {value.headline ? ` ${value.headline}` : ""}
          </p>
          {value.note && <p className="pr-muted">{value.note}</p>}
        </section>
      )}

      {pairings.length > 0 && (
        <section className="pr-section">
          <h2>What to pair this with</h2>
          <table className="pr-table">
            <thead>
              <tr><th>Ingredient</th><th>Works with</th><th>Where to find it</th></tr>
            </thead>
            <tbody>
              {pairings.map((p, i) => (
                <tr key={i}>
                  <td className="pr-comp">{p.ingredient}</td>
                  <td>{p.works_with}</td>
                  <td>
                    {p.look_for || "—"}
                    {p.caution ? ` (${p.caution})` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* ------------------------------------------------------- suitability */}
      {Object.keys(concernFit).length > 0 && (
        <section className="pr-section">
          <h2>Against the concerns selected</h2>
          <table className="pr-table">
            <thead>
              <tr><th>Concern</th><th className="pr-num">Fit</th><th>Why</th></tr>
            </thead>
            <tbody>
              {Object.entries(concernFit).map(([concern, data]) => (
                <tr key={concern}>
                  <td className="pr-comp">{concern}</td>
                  <td className="pr-num">{fmt(data.score)} / 100</td>
                  <td>{(data.explanation || []).join(" ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {typeof compat === "number" && (
        <section className="pr-section">
          <h2>Suitability for {String(skinType || "this").toLowerCase()} skin</h2>
          <p><strong>{compat}%</strong> compatible.</p>
          {(details.why_bullets || []).length > 0 && (
            <ul className="pr-list">
              {details.why_bullets.map((b, i) => <li key={i}>{b}</li>)}
            </ul>
          )}
          {(details.formulation_notes || []).length > 0 && (
            <>
              <h3>Worth knowing about</h3>
              <ul className="pr-list">
                {details.formulation_notes.map((n, i) => <li key={i}>{n}</li>)}
              </ul>
            </>
          )}
        </section>
      )}

      {/* ---------------------------------------------------------- warnings */}
      {(advisories.length > 0 || flags.length > 0) && (
        <section className="pr-section">
          <h2>Things to be aware of</h2>
          {advisories.map((a, i) => (
            <div className="pr-advisory" key={`a${i}`}>
              <h3>{a.title}</h3>
              <p>{a.message}</p>
              {(a.items || []).length > 0 && (
                <ul className="pr-list">
                  {a.items.map((it, j) => (
                    <li key={j}>
                      <strong>{it.ingredient}</strong>
                      {it.guidance ? ` — ${it.guidance}` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
          {flags.map((f, i) => (
            <div className="pr-advisory" key={`f${i}`}>
              <h3>{f.title || "Formulation note"}</h3>
              <p>{f.message}</p>
            </div>
          ))}
        </section>
      )}

      {isFree && (
        <section className="pr-section pr-upgrade">
          <h2>Not covered in this report</h2>
          <p>
            Everything above is about the product itself and is the same for
            every reader. It does not cover how this suits <em>you</em>: how
            well it treats the concerns you selected, whether it suits your
            skin type, what in it is likely to give you trouble, and how it
            fits alongside what you already use.
          </p>
          <p className="pr-muted">
            That part is in the full report, at urancal.com.
          </p>
        </section>
      )}

      {/* ------------------------------------------------- limits of method */}
      <section className="pr-section pr-limits">
        <h2>What this analysis cannot tell you</h2>
        <p>
          {result.formulation_confidence_note ||
            "Concentrations are estimated from the order ingredients are listed in."}
        </p>
        <p>
          Under EU Regulation 1223/2009 Article 19, ingredients present below 1%
          may be listed in any order. Anything past that point on the label
          cannot be dosed from the list alone, so its contribution here is
          bounded rather than measured.
        </p>
      </section>

      <footer className="pr-foot">
        <p>
          Generated by Urancal · urancal.com · {today()}
        </p>
        <p>
          This is an assessment of a published ingredient list, not medical
          advice, and it does not replace a consultation with a dermatologist.
          If you are pregnant, breastfeeding, or using prescription treatments,
          check with a clinician before changing a routine.
        </p>
      </footer>
    </div>
  );
}

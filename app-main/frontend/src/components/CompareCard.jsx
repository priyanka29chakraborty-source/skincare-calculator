import React, { useState } from "react";
import { createPortal } from "react-dom";

import { money, categoryLabel } from "../constants";
import { API, api, describeError } from "../api";
import { track } from "../track";

const MAX_PRODUCTS = 4;

const EMPTY = {
  product_name: "", brand: "", category: "Serum",
  price: "", size_ml: "", ingredients: "",
};

const CATEGORIES = ["Serum", "Moisturizer", "Cleanser", "Toner", "Sunscreen",
  "Eye Cream", "Mask", "Treatment", "Facial Oil"];

/**
 * Two to four products side by side.
 *
 * Paid. One credit covers this pair. Opening the same pair again does not
 * spend another. A single product's formulation score stays free.
 *
 * The first version of this was a scoreboard - two numbers and a winner. That
 * tells you which number is bigger and nothing about what you would be giving
 * up. What someone holding two bottles is actually asking is what is in one
 * that is not in the other, which one treats the thing they care about,
 * whether they could just use both, and whether buying both means buying the
 * same job twice. Those are the sections below, in that order, with the
 * verdict last because it depends on all of them.
 *
 * The server refuses to rank across categories and refuses to call a winner on
 * a gap smaller than the method can resolve. Those refusals are rendered as
 * plainly as a result, because a stated limit is more useful than a confident
 * guess.
 */
export default function CompareCard({ seed, currency, skinType, concerns, onUnlock }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function start() {
    setOpen(true);
    setRows(rows || [seed ? { ...EMPTY, ...seed } : { ...EMPTY }, { ...EMPTY }]);
  }

  function update(i, field, value) {
    setRows((prev) => prev.map((r, j) => (j === i ? { ...r, [field]: value } : r)));
  }

  function addRow() {
    setRows((prev) => (prev.length >= MAX_PRODUCTS ? prev : [...prev, { ...EMPTY }]));
  }

  function removeRow(i) {
    setRows((prev) => (prev.length <= 2 ? prev : prev.filter((_, j) => j !== i)));
  }

  async function run() {
    setBusy(true); setError(""); setResult(null);
    try {
      const { data } = await api.post(`${API}/compare`, {
        // One profile across every product: a comparison is "which of these
        // for me", so scoring each against a different skin type would answer
        // a question nobody asked.
        skin_type: (skinType || "").toLowerCase() || undefined,
        skin_concerns: concerns || [],
        products: rows.map((r) => ({
          product_name: r.product_name,
          brand: r.brand,
          category: r.category,
          price: parseFloat(r.price) || 0,
          size_ml: parseFloat(r.size_ml) || 0,
          ingredients: r.ingredients,
          currency,
        })),
      });
      setResult(data);
      track("comparison_completed");
    } catch (e) {
      setError(describeError(e));
    } finally { setBusy(false); }
  }

  if (!open) {
    return (
      <div className="card compare-prompt no-print" data-testid="compare-prompt">
        <div>
          <div className="card-label">Compare products</div>
          <p className="compare-lede">
            Two to four products side by side. One credit covers this comparison.
            Opening the same pair again does not spend another.
          </p>
        </div>
        <button className="btn btn-primary compare-start" onClick={start}
                data-testid="compare-start">
          <i className="fa-solid fa-scale-balanced"></i> Compare
        </button>
      </div>
    );
  }

  return (
    <div className="card compare-card" data-testid="compare-card">
      <div className="card-label">Compare products</div>

      <div className="compare-inputs no-print">
        {(rows || []).map((row, i) => (
          <div className="compare-input-row" key={i}>
            <div className="compare-input-head">
              <span className="field-sublabel">Product {i + 1}</span>
              {rows.length > 2 && (
                <button className="history-forget" onClick={() => removeRow(i)}
                        aria-label={`Remove product ${i + 1}`}>
                  <i className="fa-solid fa-xmark"></i>
                </button>
              )}
            </div>
            <div className="form-grid">
              <div className="field-group">
                <label className="field-label">Name</label>
                <input className="field-input" value={row.product_name}
                       onChange={(e) => update(i, "product_name", e.target.value)}
                       placeholder="e.g. Niacinamide 10%" />
              </div>
              <div className="field-group">
                <label className="field-label">Category</label>
                <select className="field-select full-w" value={row.category}
                        onChange={(e) => update(i, "category", e.target.value)}>
                  {CATEGORIES.map((c) => <option key={c} value={c}>{categoryLabel(c)}</option>)}
                </select>
              </div>
              <div className="field-group">
                <label className="field-label">Price</label>
                <input className="field-input" type="number" min="0" value={row.price}
                       onChange={(e) => update(i, "price", e.target.value)}
                       placeholder="549" />
              </div>
              <div className="field-group">
                <label className="field-label">Size (ml)</label>
                <input className="field-input" type="number" min="0" value={row.size_ml}
                       onChange={(e) => update(i, "size_ml", e.target.value)}
                       placeholder="30" />
              </div>
              <div className="field-group full">
                <label className="field-label">Ingredients (INCI)</label>
                <textarea className="field-textarea compare-textarea"
                          value={row.ingredients}
                          onChange={(e) => update(i, "ingredients", e.target.value)}
                          placeholder="Aqua, Niacinamide, Zinc PCA..." />
              </div>
            </div>
          </div>
        ))}

        <div className="compare-actions">
          {rows && rows.length < MAX_PRODUCTS && (
            <button className="clear-btn-solo" onClick={addRow} data-testid="compare-add">
              <i className="fa-solid fa-plus"></i> Add another
            </button>
          )}
          <button className="analyze-btn compare-run" onClick={run} disabled={busy}
                  data-testid="compare-run">
            {busy ? "Comparing..." : "Compare"}
          </button>
        </div>
        {error && <p className="modal-error" role="alert" data-testid="compare-error">{error}</p>}
      </div>

      {result && <CompareResult result={result} currency={currency} skinType={skinType} onUnlock={onUnlock} />}
    </div>
  );
}

/* ------------------------------------------------------------------------- */

function Row({ label, children, cols }) {
  return (
    <div className="compare-row" style={{ "--cols": cols }}>
      <span className="compare-row-label">{label}</span>
      {children}
    </div>
  );
}

function CompareResult({ result, currency, skinType, onUnlock }) {
  // The server omits the table until the comparison is paid for.
  const locked = result.access?.tier === "free";
  if (locked) {
    return (
      <section className="compare-block compare-locked" data-testid="compare-locked">
        <h3 className="compare-block-head">Comparison</h3>
        <p className="compare-locked-lede">{result.access?.message}</p>
        <ul className="compare-locked-list">
          <li><strong>Formulation and price per ml</strong> — side by side</li>
          <li><strong>What each has that the other does not</strong></li>
          <li><strong>Which one treats your concerns</strong></li>
          <li><strong>Irritation for your skin type</strong></li>
          <li><strong>Whether you could use both</strong></li>
        </ul>
        <button className="locked-cta" onClick={onUnlock} data-testid="compare-unlock">
          <span className="locked-cta-main">
            <i className="fa-solid fa-lock-open"></i> Unlock this comparison
          </span>
          <span className="locked-cta-sub">
            One credit &middot; covers this pair for good
          </span>
        </button>
      </section>
    );
  }
  const { products, components, actives, concerns, tolerability, together, verdict } = result;
  const cols = products.length;
  const names = products.map((p) => p.product_name);

  return (
    <div className="compare-result" data-testid="compare-result">
      {/* ---------------------------------------------------------- scores */}
      <div className="compare-grid">
        <div className="compare-head-row" style={{ "--cols": cols }}>
          <span />
          {products.map((p, i) => (
            <span className="compare-col-head" key={i}>
              <span className="compare-col-name">{p.product_name}</span>
              {p.brand && <span className="compare-col-brand">{p.brand}</span>}
            </span>
          ))}
        </div>

        <Row label="Formulation" cols={cols}>
          {products.map((p, i) => (
            <span className="compare-cell" key={i}>
              <strong className="compare-score">{p.formulation_score ?? "—"}</strong>
              <span className="compare-tier">{p.formulation_tier}</span>
            </span>
          ))}
        </Row>

        <Row label="Price per ml" cols={cols}>
          {products.map((p, i) => (
            <span className="compare-cell" key={i}>
              {p.price_per_ml ? money(p.currency || currency, p.price_per_ml) : "—"}
            </span>
          ))}
        </Row>

        <Row label="Price per active" cols={cols}>
          {products.map((p, i) => (
            <span className="compare-cell" key={i}>
              {p.price_per_active ? money(p.currency || currency, p.price_per_active) : "—"}
            </span>
          ))}
        </Row>

        {components.map((component) => (
          <Row key={component.key} label={component.label} cols={cols}>
            {component.values.map((value, i) => (
              <span className="compare-cell" key={i}>
                {value ? (
                  <>
                    <span className="compare-component-bar" aria-hidden="true">
                      <span style={{ width: `${value.pct}%` }} />
                    </span>
                    <span className="compare-component-num">
                      {Math.round(value.score)}/{value.max}
                    </span>
                    {(value.notes || []).length > 0 && (
                      <span className="compare-component-note">{value.notes[0]}</span>
                    )}
                  </>
                ) : "—"}
              </span>
            ))}
          </Row>
        ))}
      </div>

      {/* --------------------------------------------------------- actives */}
      {(actives?.shared?.length > 0 || actives?.unique?.some((u) => u.length > 0)) && (
        <section className="compare-block" data-testid="compare-actives">
          <h3 className="compare-block-head">What is actually in them</h3>

          {actives.shared.length > 0 && (
            <div className="compare-actives-shared">
              <h4>In all of them</h4>
              <ul>
                {actives.shared.map((a) => (
                  <li key={a.name}>
                    <strong>{a.name}</strong>
                    {a.evidence && <span className="compare-evidence"> · {a.evidence}</span>}
                    <span className="compare-levels">
                      {a.levels.map((lvl, i) => (
                        <span key={i}>
                          {names[i]}: {lvl.concentration_pct
                            ? `${lvl.concentration_pct}%`
                            : (lvl.position ? `position ${lvl.position}` : "present")}
                        </span>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="compare-actives-unique">
            {actives.unique.map((list, i) => (
              <div key={i}>
                <h4>Only in {names[i]}</h4>
                {list.length > 0 ? (
                  <ul>
                    {list.map((a) => (
                      <li key={a.name}>
                        <strong>{a.name}</strong>
                        {a.targets?.length > 0 && (
                          <span className="compare-evidence"> · for {a.targets.join(", ").toLowerCase()}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="compare-muted">Nothing the others do not also have.</p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* -------------------------------------------------------- concerns */}
      {concerns?.length > 0 && (
        <section className="compare-block" data-testid="compare-concerns">
          <h3 className="compare-block-head">Against what you are treating</h3>
          <p className="compare-muted">
            Each number belongs to the product named above it. This is how well
            that product treats the concern. It is not the formulation score.
            A product can be well made and still be the weaker treatment.
          </p>
          <div className="compare-grid">
            {concerns.map((entry) => (
              <Row key={entry.concern} label={entry.concern} cols={cols}>
                {entry.scores.map((score, i) => (
                  <span className={`compare-cell${entry.best_index === i ? " compare-cell-best" : ""}`}
                        key={i}>
                    <span className="compare-col-name">{names[i]}</span>
                    <strong>{score ?? "—"}</strong>
                    <span className="compare-component-num">/ 100</span>
                    {entry.best_index === i && (
                      <span className="compare-component-note">Better for this concern</span>
                    )}
                  </span>
                ))}
              </Row>
            ))}
          </div>
          {concerns.some((c) => c.note) && (
            <p className="compare-muted">
              Where no product is highlighted, the gap is inside what the method
              can resolve.
            </p>
          )}
        </section>
      )}

      {/* ---------------------------------------------------- tolerability */}
      {/* Two measures, deliberately on separate rows. Together in one cell
          they produced "Tolerability 100% - High Risk", which reads as a
          contradiction and is not one: the first is formulation-level and the
          same for everybody, the second is specific to the skin type being
          analysed for. A product can be free of irritants and still be a poor
          idea for oily skin. */}
      {tolerability?.length > 0 && (
        <section className="compare-block" data-testid="compare-tolerability">
          <h3 className="compare-block-head">Irritation and congestion risk</h3>
          <div className="compare-grid">
            <Row label="Formula tolerability" cols={cols}>
              {tolerability.map((t, i) => (
                <span className="compare-cell" key={i}>
                  <span className="compare-col-name">{names[i]}</span>
                  <strong>
                    {t.formulation_pct !== null && t.formulation_pct !== undefined
                      ? `${Math.round(t.formulation_pct)}/100`
                      : "—"}
                  </strong>
                  {(t.formulation_notes || []).length > 0 && (
                    <span className="compare-component-note">{t.formulation_notes[0]}</span>
                  )}
                </span>
              ))}
            </Row>
            <Row label={`For ${String(skinType || "this").toLowerCase()} skin`} cols={cols}>
              {tolerability.map((t, i) => (
                <span className="compare-cell" key={i}>
                  <span className="compare-col-name">{names[i]}</span>
                  {t.skin_type_risk ? (
                    <span className={`compare-risk compare-risk-${String(t.skin_type_risk).split(" ")[0].toLowerCase()}`}>
                      {t.skin_type_risk} risk
                    </span>
                  ) : <span>&mdash;</span>}
                  {(t.skin_type_notes || []).length > 0 && (
                    <span className="compare-component-note">
                      {t.skin_type_notes.length === 1
                        ? t.skin_type_notes[0]
                        : `${t.skin_type_notes.length} ingredients this skin type often reacts to`}
                    </span>
                  )}
                </span>
              ))}
            </Row>
          </div>
          <p className="compare-muted">
            Formula tolerability is the same for everyone. The row under it
            counts ingredients that often bother this skin type. Both can say
            low risk and still list a different number of ingredients.
          </p>
        </section>
      )}

      {/* --------------------------------------------------- using them both */}
      {together?.checked && (
        <section className="compare-block" data-testid="compare-together">
          <h3 className="compare-block-head">Could you use both?</h3>
          {together.clear && (
            <p className="compare-together-clear">
              <i className="fa-solid fa-circle-check"></i> No layering conflict
              found between these two, and neither duplicates the other's job.
            </p>
          )}
          {together.conflicts.map((c, i) => (
            <p className="compare-together-warn" key={`c${i}`}>
              <i className="fa-solid fa-triangle-exclamation"></i>
              <span><strong>{c.families.join(" + ")}.</strong> {c.message}</span>
            </p>
          ))}
          {together.redundant.map((r, i) => (
            <p className="compare-together-warn" key={`r${i}`}>
              <i className="fa-solid fa-copy"></i>
              <span>{r.message}</span>
            </p>
          ))}
        </section>
      )}
      {together && together.checked === false && (
        <p className="compare-muted" data-testid="compare-together-skipped">
          {together.reason}
        </p>
      )}

      {/* --------------------------------------------------------- verdict */}
      <div className="compare-verdict" data-testid="compare-verdict">
        {verdict.best_formulation && (
          <p className="compare-verdict-line">
            <i className="fa-solid fa-flask" aria-hidden="true"></i>
            <span>Better made: <strong>{verdict.best_formulation}</strong></span>
          </p>
        )}
        {verdict.best_value && (
          <p className="compare-verdict-line">
            <i className="fa-solid fa-tag" aria-hidden="true"></i>
            <span>Better value per ml: <strong>{verdict.best_value}</strong></span>
          </p>
        )}
        {verdict.note && <p className="compare-note">{verdict.note}</p>}

        {verdict.choose_if?.length > 0 && (
          <div className="compare-choose">
            {verdict.choose_if.map((c) => (
              <div className="compare-choose-item" key={c.product_name}>
                <h4>Choose {c.product_name} if…</h4>
                <ul>{c.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </div>
            ))}
          </div>
        )}

        <p className="compare-method">{result.method_note}</p>
      </div>
      <div className="export-row no-print">
        <button type="button" className="export-btn" data-testid="compare-pdf"
                onClick={() => {
                  document.body.classList.add("print-compare");
                  window.print();
                  document.body.classList.remove("print-compare");
                }}>
          <i className="fa-solid fa-file-arrow-down"></i> Save as PDF
        </button>
      </div>
      <ComparePrint result={result} currency={currency} skinType={skinType} />
    </div>
  );
}

function ComparePrint({ result, currency, skinType }) {
  const { products, concerns, tolerability, verdict } = result;
  return createPortal(
    <article className="print-compare">
      <h1>Comparison</h1>
      <table>
        <thead>
          <tr>
            <th />
            {products.map((p) => <th key={p.product_name}>{p.product_name}</th>)}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th>Formulation</th>
            {products.map((p) => (
              <td key={p.product_name}>{p.formulation_score ?? "—"} {p.formulation_tier || ""}</td>
            ))}
          </tr>
          <tr>
            <th>Price per ml</th>
            {products.map((p) => (
              <td key={p.product_name}>
                {p.price_per_ml ? money(p.currency || currency, p.price_per_ml) : "—"}
              </td>
            ))}
          </tr>
          {(concerns || []).map((entry) => (
            <tr key={entry.concern}>
              <th>{entry.concern}</th>
              {entry.scores.map((score, i) => (
                <td key={products[i].product_name}>{score ?? "—"} / 100</td>
              ))}
            </tr>
          ))}
          <tr>
            <th>Formula tolerability</th>
            {(tolerability || []).map((t, i) => (
              <td key={products[i].product_name}>
                {t.formulation_pct != null ? `${Math.round(t.formulation_pct)}/100` : "—"}
                {t.formulation_notes?.[0] ? `. ${t.formulation_notes[0]}` : ""}
              </td>
            ))}
          </tr>
          <tr>
            <th>For {String(skinType || "this skin").toLowerCase()}</th>
            {(tolerability || []).map((t, i) => (
              <td key={products[i].product_name}>
                {t.skin_type_risk ? `${t.skin_type_risk} risk` : "—"}
                {t.skin_type_notes?.length > 1
                  ? `. ${t.skin_type_notes.length} ingredients this skin type often reacts to`
                  : (t.skin_type_notes?.[0] ? `. ${t.skin_type_notes[0]}` : "")}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
      {verdict?.note && <p>{verdict.note}</p>}
      {result.method_note && <p>{result.method_note}</p>}
    </article>,
    document.body
  );
}

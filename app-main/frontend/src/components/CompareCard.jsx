import React, { useState } from "react";

import { money } from "../constants";
import { API, api, describeError } from "../api";

const MAX_PRODUCTS = 4;

const EMPTY = {
  product_name: "", brand: "", category: "Serum",
  price: "", size_ml: "", ingredients: "",
};

/**
 * Two to four products side by side.
 *
 * Free, and the card says so: it compares formulation scores, and formulation
 * analysis is the free tier. Charging to put two free numbers next to each
 * other would be charging for arithmetic.
 *
 * The verdict is shown as two separate answers - better made, better value -
 * because they are different questions and the right product depends on which
 * one the reader is asking. The server refuses to rank across categories and
 * refuses to call a winner on a gap smaller than the method can resolve; this
 * component renders those refusals as plainly as it renders a result, since a
 * stated limit is more useful than a confident guess.
 */
export default function CompareCard({ seed, currency }) {
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
            Put two to four products side by side and see where the difference
            actually comes from. Free — it compares formulation scores, and
            those are free.
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
                  {["Serum", "Moisturizer", "Cleanser", "Toner", "Sunscreen",
                    "Eye Cream", "Mask", "Treatment", "Facial Oil"].map((c) => (
                      <option key={c} value={c}>{c}</option>))}
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

      {result && <CompareResult result={result} currency={currency} />}
    </div>
  );
}

function CompareResult({ result, currency }) {
  const { products, components, verdict } = result;

  return (
    <div className="compare-result" data-testid="compare-result">
      <div className="compare-grid" style={{ "--cols": products.length }}>
        <div className="compare-head-row">
          <span />
          {products.map((p, i) => (
            <span className="compare-col-head" key={i}>
              <span className="compare-col-name">{p.product_name}</span>
              {p.brand && <span className="compare-col-brand">{p.brand}</span>}
            </span>
          ))}
        </div>

        <div className="compare-row compare-score-row">
          <span className="compare-row-label">Formulation</span>
          {products.map((p, i) => (
            <span className="compare-cell" key={i}>
              <strong className="compare-score">{p.formulation_score ?? "—"}</strong>
              <span className="compare-tier">{p.formulation_tier}</span>
            </span>
          ))}
        </div>

        <div className="compare-row">
          <span className="compare-row-label">Price per ml</span>
          {products.map((p, i) => (
            <span className="compare-cell" key={i}>
              {p.price_per_ml ? money(p.currency || currency, p.price_per_ml) : "—"}
            </span>
          ))}
        </div>

        {components.map((component) => (
          <div className="compare-row" key={component.key}>
            <span className="compare-row-label">{component.label}</span>
            {component.values.map((value, i) => (
              <span className="compare-cell" key={i}>
                {value
                  ? <>
                      <span className="compare-component-bar" aria-hidden="true">
                        <span style={{ width: `${value.pct}%` }} />
                      </span>
                      <span className="compare-component-num">
                        {Math.round(value.score)}/{value.max}
                      </span>
                    </>
                  : "—"}
              </span>
            ))}
          </div>
        ))}
      </div>

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
        <p className="compare-method">{result.method_note}</p>
      </div>
    </div>
  );
}

import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  CircleCheck, Copy, FileDown, FlaskConical, GitCompare, Lock, Plus, Tag, TriangleAlert, X,
} from "lucide-react";

import { money, categoryLabel, SIZE_UNITS, toMl } from "../constants";
import { API, api, describeError } from "../api";
import { track } from "../track";
import { Badge, Button, Callout, Card, ScoreRing, Select, cx } from "./ds";

const MAX_PRODUCTS = 4;

const EMPTY = {
  product_name: "", brand: "", category: "Serum",
  price: "", size: "", size_unit: "ml", ingredients: "",
};

const CATEGORIES = ["Serum", "Moisturizer", "Cleanser", "Toner", "Sunscreen",
  "Eye Cream", "Mask", "Treatment", "Facial Oil"];

/**
 * Two to four products side by side.
 *
 * Paid. One credit per product compared (two for a pair), up to four, and it
 * needs an account. Opening the same set of products again does not
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
export default function CompareCard({ seed, preset, currency, skinType, concerns, onUnlock, onSignIn, autoOpen, signedIn }) {
  const initialRows = () => [seed ? { ...EMPTY, ...seed } : { ...EMPTY }, { ...EMPTY }];
  const [open, setOpen] = useState(Boolean(autoOpen));
  const [rows, setRows] = useState(autoOpen ? initialRows : null);
  const count = rows ? rows.length : 2;
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!preset?.products?.length) return;
    setOpen(true);
    setResult(null);
    setError("");
    setRows(preset.products.map((product) => ({
      product_name: product.product_name || "",
      brand: product.brand || "",
      category: product.category || "Serum",
      price: product.price ? String(product.price) : "",
      // Saved comparisons store the size already converted to ml.
      size: product.size_ml ? String(Math.round(product.size_ml * 100) / 100) : "",
      size_unit: "ml",
      ingredients: product.ingredients || "",
    })));
  }, [preset]);

  function start() {
    setOpen(true);
    setRows(rows || initialRows());
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

  // Check the form before asking anyone to sign in or spend a credit.
  function checkAndRun() {
    const missing = (rows || []).findIndex((r) => !String(r.ingredients || "").trim());
    if (missing >= 0) {
      setError(`Add the ingredient list for product ${missing + 1} — every product needs one.`);
      return;
    }
    setError("");
    if (signedIn) run();
    else onSignIn?.(() => run());
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
          size_ml: toMl(r.size, r.size_unit),
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
      <Card eyebrow="Compare" title="Compare with another product" className="no-print" data-testid="compare-prompt"
            sub="Two to four products side by side. Comparing starts at 2 credits — 2 for two products, 3 for three, 4 for four. Opening the same products again is free."
            aside={<Button variant="secondary" icon={<GitCompare />} onClick={start} data-testid="compare-start">Compare</Button>} />
    );
  }

  return (
    <div className="stack" style={{ "--stack-gap": "24px" }} data-testid="compare-card">
      <div className="stack no-print" style={{ "--stack-gap": "16px" }}>
        {(rows || []).map((row, i) => (
          <section className="card compare-product" key={i} aria-label={`Product ${i + 1}`}>
            <header className="row-between" style={{ marginBottom: 20 }}>
              <p className="t-heading-m">Product {i + 1}</p>
              {rows.length > 2 && (
                <Button variant="ghost" size="sm" className="btn--icon" icon={<X />} onClick={() => removeRow(i)}
                        aria-label={`Remove product ${i + 1}`} />
              )}
            </header>
            <div className="form-grid">
              <div className="field-row">
                <label className="field"><span className="field__label">Name</span>
                  <span className="field__control"><input value={row.product_name} onChange={(e) => update(i, "product_name", e.target.value)} placeholder="e.g. Niacinamide 10%" /></span>
                </label>
                <label className="field"><span className="field__label">Brand</span>
                  <span className="field__control"><input value={row.brand} onChange={(e) => update(i, "brand", e.target.value)} placeholder="e.g. Minimalist" data-testid={`compare-brand-${i}`} /></span>
                </label>
              </div>
              <div className="field-row field-row--3">
                <div className="field"><span className="field__label" id={`cmp-${i}-category-label`}>Category</span>
                  <Select id={`cmp-${i}-category`} labelledBy={`cmp-${i}-category-label`} value={row.category}
                          onChange={(v) => update(i, "category", v)}
                          options={CATEGORIES.map((c) => ({ value: c, label: categoryLabel(c) }))} />
                </div>
                <label className="field"><span className="field__label">Price</span>
                  <span className="field__control"><input type="number" min="0" inputMode="decimal" value={row.price} onChange={(e) => update(i, "price", e.target.value)} placeholder="549" /></span>
                </label>
                <div className="field"><label className="field__label" htmlFor={`cmp-${i}-size`}>Size</label>
                  <div className="field-inline">
                    <span className="field__control">
                      <input id={`cmp-${i}-size`} type="number" min="0" inputMode="decimal" value={row.size}
                             onChange={(e) => update(i, "size", e.target.value)} placeholder="30" />
                    </span>
                    <Select className="field__unit" value={row.size_unit} onChange={(v) => update(i, "size_unit", v)}
                            options={SIZE_UNITS} ariaLabel={`Size unit for product ${i + 1}`} />
                  </div>
                </div>
              </div>
              <label className="field"><span className="field__label">Ingredients (INCI list)</span>
                <span className="field__control field__control--textarea">
                  <textarea rows={3} value={row.ingredients} onChange={(e) => update(i, "ingredients", e.target.value)} placeholder="Aqua, Niacinamide, Zinc PCA…" spellCheck={false} />
                </span>
              </label>
            </div>
          </section>
        ))}

        <div className="compare-actions">
          {rows && rows.length < MAX_PRODUCTS && (
            <Button variant="ghost" icon={<Plus />} onClick={addRow} data-testid="compare-add">Add another product</Button>
          )}
          <Button variant="primary" size="lg" arrow loading={busy} loadingText="Comparing…" data-testid="compare-run"
                  onClick={checkAndRun}>
            {signedIn ? `Compare ${count} products` : "Sign in to compare"}
          </Button>
        </div>
        <p className="t-caption c-tertiary" style={{ textAlign: "center" }}>
          {signedIn
            ? `Comparing ${count} products uses ${count} credits. Opening the same products again is free.`
            : `Comparing ${count} products uses ${count} credits. Your first 4 credits are free when you sign in.`}
        </p>
        {error && <Callout tone="negative" role="alert" data-testid="compare-error"><p className="callout__text">{error}</p></Callout>}
      </div>

      {result && <CompareResult result={result} currency={currency} skinType={skinType} onUnlock={onUnlock} signedIn={signedIn} productCount={count} />}
    </div>
  );
}

/* ------------------------------------------------------------------------- */

function Row({ label, children, cols, className }) {
  return (
    <div className={cx("cmp-row", className)} style={{ "--cols": cols }}>
      <span className="cmp-row__label">{label}</span>
      {children}
    </div>
  );
}

function toneFor(pct) {
  if (pct >= 80) return "excellent";
  if (pct >= 65) return "good";
  if (pct >= 45) return "fair";
  if (pct >= 30) return "weak";
  return "poor";
}

function CompareResult({ result, currency, skinType, onUnlock, signedIn, productCount = 2 }) {
  // The server omits the table until the comparison is paid for.
  if (result.access?.tier === "free") {
    return (
      <Card eyebrow="Comparison" title="Unlock this comparison"
            aside={<Badge><Lock aria-hidden="true" style={{ width: 12, height: 12 }} />Locked</Badge>}
            data-testid="compare-locked">
        {result.access?.message && <p className="t-body-m c-secondary">{result.access.message}</p>}
        <ul className="need-list">
          <li><span>Formulation and price per ml</span>side by side</li>
          <li><span>What each has</span>that the others don’t</li>
          <li><span>Your concerns</span>which one treats them better</li>
          <li><span>Your skin type</span>irritation and congestion risk</li>
          <li><span>Using both</span>clashes and doubling up</li>
        </ul>
        <Button variant="accent" size="lg" block icon={<Lock />} onClick={onUnlock} data-testid="compare-unlock">
          {signedIn ? `Unlock with ${productCount} credits` : "Sign in — get 4 free credits"}
        </Button>
        <p className="t-caption c-tertiary" style={{ textAlign: "center", marginTop: 10 }}>Once unlocked, these products stay covered — opening them again is free.</p>
      </Card>
    );
  }
  const { products, components, actives, concerns, tolerability, together, verdict } = result;
  const cols = products.length;
  const names = products.map((p) => p.product_name);

  return (
    <div className="stack" style={{ "--stack-gap": "24px" }} data-testid="compare-result">
      <Card eyebrow="Comparison" title="Side by side">
        <div className="cmp-scroll">
          <div className="cmp-grid">
            <div className="cmp-row cmp-row--head" style={{ "--cols": cols }}>
              <span />
              {products.map((p, i) => (
                <span className="cmp-head" key={i}>
                  {p.formulation_score != null && (
                    <ScoreRing score={p.formulation_score} size="sm" animate={false} label={`${p.product_name} score`} />
                  )}
                  <span className="t-label-s">{p.product_name}</span>
                  {p.brand && <span className="t-caption c-accent">{p.brand}</span>}
                  {p.formulation_tier && <span className="t-caption c-tertiary">{p.formulation_tier}</span>}
                </span>
              ))}
            </div>
            <Row label="Price per ml" cols={cols}>
              {products.map((p, i) => (
                <span className="cmp-cell t-mono" key={i}>{p.price_per_ml ? money(p.currency || currency, p.price_per_ml) : "—"}</span>
              ))}
            </Row>
            <Row label="Price per active" cols={cols}>
              {products.map((p, i) => (
                <span className="cmp-cell t-mono" key={i}>{p.price_per_active ? money(p.currency || currency, p.price_per_active) : "—"}</span>
              ))}
            </Row>
            {components.map((component) => (
              <Row key={component.key} label={component.label} cols={cols}>
                {component.values.map((value, i) => (
                  <span className="cmp-cell" key={i}>
                    {value ? (
                      <>
                        <span className="meter__track" aria-hidden="true">
                          <span className="meter__fill" style={{ display: "block", width: `${value.pct}%`, "--meter-color": `var(--score-${toneFor(value.pct)})` }} />
                        </span>
                        <span className="t-mono-s c-secondary">{Math.round(value.score)}/{value.max}</span>
                        {(value.notes || []).length > 0 && <span className="t-caption c-tertiary">{value.notes[0]}</span>}
                      </>
                    ) : "—"}
                  </span>
                ))}
              </Row>
            ))}
          </div>
        </div>
      </Card>

      {(actives?.shared?.length > 0 || actives?.unique?.some((u) => u.length > 0)) && (
        <Card eyebrow="Actives" title="What’s actually in them" data-testid="compare-actives">
          {actives.shared.length > 0 && (
            <div className="cmp-block">
              <p className="t-heading-s">In all of them</p>
              <ul className="cmp-list">
                {actives.shared.map((a) => (
                  <li key={a.name}>
                    <strong>{a.name}</strong>{a.evidence && <span className="c-tertiary"> · {a.evidence}</span>}
                    <span className="t-caption c-secondary" style={{ display: "block" }}>
                      {a.levels.map((lvl, i) => `${names[i]}: ${lvl.concentration_pct ? `${lvl.concentration_pct}%` : (lvl.position ? `position ${lvl.position}` : "present")}`).join(" · ")}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="cmp-unique">
            {actives.unique.map((list, i) => (
              <div key={i} className="cmp-block">
                <p className="t-heading-s">Only in {names[i]}</p>
                {list.length > 0 ? (
                  <ul className="cmp-list">
                    {list.map((a) => (
                      <li key={a.name}>
                        <strong>{a.name}</strong>
                        {a.targets?.length > 0 && <span className="c-tertiary"> · for {a.targets.join(", ").toLowerCase()}</span>}
                      </li>
                    ))}
                  </ul>
                ) : <p className="t-body-s c-tertiary">Nothing the others don’t also have.</p>}
              </div>
            ))}
          </div>
        </Card>
      )}

      {concerns?.length > 0 && (
        <Card eyebrow="Your concerns" title="Against what you’re treating"
              sub="How well each product treats the concern — not its formulation score. A product can be well made and still be the weaker treatment."
              data-testid="compare-concerns">
          <div className="cmp-scroll">
            <div className="cmp-grid">
              {concerns.map((entry) => (
                <Row key={entry.concern} label={entry.concern} cols={cols}>
                  {entry.scores.map((score, i) => (
                    <span className={cx("cmp-cell", entry.best_index === i && "cmp-cell--best")} key={i}>
                      <span className="t-caption c-tertiary">{names[i]}</span>
                      <span className="t-heading-s">{score ?? "—"}<span className="t-mono-s c-tertiary"> / 100</span></span>
                      {entry.best_index === i && <span className="badge badge--positive">Better here</span>}
                    </span>
                  ))}
                </Row>
              ))}
            </div>
          </div>
          {concerns.some((c) => c.note) && (
            <p className="t-caption c-tertiary" style={{ marginTop: 12 }}>Where nothing is highlighted, the gap is inside what the method can resolve.</p>
          )}
        </Card>
      )}

      {tolerability?.length > 0 && (
        <Card eyebrow="Tolerability" title="Irritation and congestion risk" data-testid="compare-tolerability"
              sub="Formula tolerability is the same for everyone. The second row counts ingredients that often bother your skin type.">
          <div className="cmp-scroll">
            <div className="cmp-grid">
              <Row label="Formula tolerability" cols={cols}>
                {tolerability.map((t, i) => (
                  <span className="cmp-cell" key={i}>
                    <span className="t-caption c-tertiary">{names[i]}</span>
                    <span className="t-heading-s">{t.formulation_pct != null ? `${Math.round(t.formulation_pct)}/100` : "—"}</span>
                    {(t.formulation_notes || []).length > 0 && <span className="t-caption c-tertiary">{t.formulation_notes[0]}</span>}
                  </span>
                ))}
              </Row>
              <Row label={`For ${String(skinType || "this").toLowerCase()} skin`} cols={cols}>
                {tolerability.map((t, i) => {
                  const level = String(t.skin_type_risk || "").split(" ")[0].toLowerCase();
                  const tone = level === "low" ? "positive" : level === "moderate" ? "caution" : level === "high" ? "negative" : "neutral";
                  return (
                    <span className="cmp-cell" key={i}>
                      <span className="t-caption c-tertiary">{names[i]}</span>
                      {t.skin_type_risk ? <Badge tone={tone}>{t.skin_type_risk} risk</Badge> : <span>—</span>}
                      {(t.skin_type_notes || []).length > 0 && (
                        <span className="t-caption c-tertiary">
                          {t.skin_type_notes.length === 1 ? t.skin_type_notes[0] : `${t.skin_type_notes.length} ingredients this skin type often reacts to`}
                        </span>
                      )}
                    </span>
                  );
                })}
              </Row>
            </div>
          </div>
        </Card>
      )}

      {together?.checked && (
        <Card eyebrow="Routine" title="Could you use both?" data-testid="compare-together">
          <div className="stack" style={{ "--stack-gap": "10px" }}>
            {together.clear && (
              <Callout tone="positive" icon={CircleCheck} title="No layering conflict">
                <p className="callout__text">Nothing clashes between these, and neither duplicates the other’s job.</p>
              </Callout>
            )}
            {together.conflicts.map((c, i) => (
              <Callout key={`c${i}`} tone="caution" icon={TriangleAlert} title={c.families.join(" + ")}>
                <p className="callout__text">{c.message}</p>
              </Callout>
            ))}
            {together.redundant.map((r, i) => (
              <Callout key={`r${i}`} tone="neutral" icon={Copy} title="Doing the same job">
                <p className="callout__text">{r.message}</p>
              </Callout>
            ))}
          </div>
        </Card>
      )}
      {together && together.checked === false && (
        <p className="t-body-s c-tertiary" data-testid="compare-together-skipped">{together.reason}</p>
      )}

      <Card eyebrow="Verdict" title="So which one?" raised data-testid="compare-verdict">
        <div className="stack" style={{ "--stack-gap": "10px" }}>
          {verdict.best_formulation && (
            <p className="verdict-line"><FlaskConical aria-hidden="true" />Better made: <strong>{verdict.best_formulation}</strong></p>
          )}
          {verdict.best_value && (
            <p className="verdict-line"><Tag aria-hidden="true" />Better value per ml: <strong>{verdict.best_value}</strong></p>
          )}
          {verdict.note && <p className="t-body-m c-secondary">{verdict.note}</p>}
        </div>
        {verdict.choose_if?.length > 0 && (
          <div className="cmp-choose">
            {verdict.choose_if.map((c) => (
              <div key={c.product_name} className="cmp-block">
                <p className="t-heading-s c-accent">Choose {c.product_name}</p>
                <ul className="cmp-list">{c.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </div>
            ))}
          </div>
        )}
        {result.method_note && <p className="t-caption c-tertiary" style={{ marginTop: 16 }}>{result.method_note}</p>}
        <div className="row wrap no-print" style={{ marginTop: 20 }}>
          <Button variant="secondary" icon={<FileDown />} data-testid="compare-pdf"
                  onClick={() => {
                    document.body.classList.add("print-compare");
                    const done = () => {
                      document.body.classList.remove("print-compare");
                      window.removeEventListener("afterprint", done);
                    };
                    window.addEventListener("afterprint", done);
                    window.requestAnimationFrame(() => window.print());
                  }}>
            Save comparison as PDF
          </Button>
          <span className="t-caption c-tertiary">Separate from the product report.</span>
        </div>
      </Card>
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
      {(verdict?.choose_if || []).map((c) => (
        <div key={c.product_name}>
          <h2>Choose {c.product_name}</h2>
          <ul>{(c.reasons || []).map((r, i) => <li key={i}>{r}</li>)}</ul>
        </div>
      ))}
      {result.method_note && <p>{result.method_note}</p>}
    </article>,
    document.body
  );
}

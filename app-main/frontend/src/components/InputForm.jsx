import React, { useMemo, useState } from "react";
import { ArrowLeft, Check, ChevronDown, CircleCheck } from "lucide-react";

import {
  CONCERNS_LIST, SKIN_TYPES, CATEGORIES, COUNTRIES, SIZE_UNITS, CURRENCY_MAP,
  currencyAffix, categoryLabel,
} from "../constants";
import { ConcernBadge } from "../lib/concernIcons";
import SmartInput, { detectInput } from "./SmartInput";
import { Button, Callout, Select, cx } from "./ds";

const FIRST_CONCERNS = 8;

// Keyboard support for the radio chips: arrow keys move, space/enter select.
function handleRadioKey(e, options, current, onSelect) {
  const i = options.indexOf(current);
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(current); return; }
  const forward = e.key === "ArrowRight" || e.key === "ArrowDown";
  const back = e.key === "ArrowLeft" || e.key === "ArrowUp";
  if (!forward && !back) return;
  e.preventDefault();
  const next = options[(i + (forward ? 1 : -1) + options.length) % options.length];
  onSelect(next);
  const el = e.currentTarget.parentElement?.children[options.indexOf(next)];
  if (el) el.focus();
}

export function countIngredients(text) {
  return String(text || "").split(/[,;\n]/).map((s) => s.trim()).filter(Boolean).length;
}

function Fetched({ show, children }) {
  if (show) return <p className="field__help field__help--fetched"><CircleCheck aria-hidden="true" />Fetched{children ? ` · ${children}` : ""}</p>;
  return children ? <p className="field__help">{children}</p> : null;
}

/**
 * The analyser form: one card for the product, one for the person.
 */
export default function InputForm({
  smartValue, setSmartValue, onSmartSubmit, fetchLoading, fetchStatus, fetchMsg, fetchTitle, fetchError, fetchHost,
  fetched, productName, setProductName, brand, setBrand, price, setPrice, size, setSize,
  sizeUnit, setSizeUnit, category, setCategory, country, setCountry, ingredients, setIngredients,
  skinType, setSkinType, concerns, toggleConcern, handleAnalyze, handleClear, loading, error,
  hasResult, onBackToResult, account, pricePerMl,
}) {
  const currency = CURRENCY_MAP[country] || "INR";
  const kind = detectInput(smartValue);
  // Every concern is visible unless the person chooses to see fewer.
  const [showAllConcerns, setShowAllConcerns] = useState(true);
  const ingredientCount = useMemo(() => countIngredients(ingredients), [ingredients]);
  const chosenBeyond = concerns.some((c) => CONCERNS_LIST.findIndex((x) => x.key === c) >= FIRST_CONCERNS);
  const visibleConcerns = showAllConcerns || chosenBeyond ? CONCERNS_LIST : CONCERNS_LIST.slice(0, FIRST_CONCERNS);
  const atLimit = concerns.length >= 3;
  const smartLabel = kind === "list" ? "Use this list" : kind === "name" ? "Add name" : "Fetch details";

  return (
    <div className="analyse-form" data-testid="product-details-card">
      <div className="analyse-head">
        {hasResult && (
          <button type="button" className="link" onClick={onBackToResult} style={{ marginBottom: 12 }}>
            <ArrowLeft aria-hidden="true" /> Back to the result
          </button>
        )}
        <p className="t-eyebrow c-accent">{hasResult ? "Edit details" : "New analysis"}</p>
        <h1 className="t-display-m">What are you thinking of buying?</h1>
      </div>

      {/* ---------------------------------------------------------- step 1 */}
      <section className="card step-card" aria-labelledby="step-product">
        <StepHead n="1" id="step-product" title="The product"
                  sub="Paste a link or barcode to fill this in, or type it yourself." />

        <SmartInput value={smartValue} onChange={setSmartValue} onSubmit={onSmartSubmit}
                    buttonLabel={smartLabel} buttonArrow={false} loading={fetchLoading} loadingText="Fetching…"
                    id="fetch-input" testId="fetch-input" />

        {fetchStatus === "success" && (
          <Callout tone="positive" title={fetchHost ? `Fetched from ${fetchHost}` : "Details fetched"} data-testid="fetch-message">
            <p className="callout__text">Give them a quick look before analysing — product pages are sometimes wrong about size or price.</p>
          </Callout>
        )}
        {fetchStatus === "partial" && (
          <Callout tone="caution" title="Some details need checking" data-testid="fetch-message">
            <p className="callout__text">{fetchMsg}</p>
          </Callout>
        )}
        {fetchStatus === "failed" && (
          <Callout tone="negative" title="We couldn’t read that page" data-testid="fetch-error">
            <p className="callout__text">{fetchError}</p>
          </Callout>
        )}
        {fetchStatus === "local" && (
          <Callout tone="positive" title={fetchTitle}>
            <p className="callout__text">{fetchMsg}</p>
          </Callout>
        )}

        <div className="form-grid">
          <div className="field-row">
            <Field label="Product name" htmlFor="f-name">
              <div className="field__control">
                <input id="f-name" value={productName} onChange={(e) => setProductName(e.target.value)}
                       placeholder="e.g. Niacinamide 10% + Zinc 1%" data-testid="product-name-input" />
              </div>
              <Fetched show={fetched.has("product_name")} />
            </Field>
            <Field label="Brand" htmlFor="f-brand">
              <div className="field__control">
                <input id="f-brand" value={brand} onChange={(e) => setBrand(e.target.value)}
                       placeholder="e.g. Minimalist" data-testid="brand-input" />
              </div>
              <Fetched show={fetched.has("brand")} />
            </Field>
          </div>

          <div className="field-row">
            <Field label="Price" htmlFor="f-price">
              <div className="field__control">
                <input id="f-price" type="number" inputMode="decimal" min="0" value={price}
                       onChange={(e) => setPrice(e.target.value)} placeholder="599" data-testid="price-input" />
                <span className="field__affix" aria-label={currency}>{currencyAffix(currency)}</span>
              </div>
              <Fetched show={fetched.has("price")}>
                {pricePerMl ? `${pricePerMl} per ${sizeUnit === "g" ? "g" : "ml"}` : "Used to work out price per ml."}
              </Fetched>
            </Field>
            <Field label="Size" htmlFor="f-size">
              <div className="field-inline">
                <div className="field__control">
                  <input id="f-size" type="number" inputMode="decimal" min="0" value={size}
                         onChange={(e) => setSize(e.target.value)} placeholder="30" data-testid="size-input" />
                </div>
                <Select className="field__unit" value={sizeUnit} onChange={setSizeUnit} options={SIZE_UNITS}
                        ariaLabel="Size unit" testId="size-unit-select" />
              </div>
              <Fetched show={fetched.has("size")}>{fetched.has("size") ? null : "As printed on the pack."}</Fetched>
            </Field>
          </div>

          <div className="field-row">
            <Field label="Category" htmlFor="f-category">
              <Select id="f-category" labelledBy="f-category-label" value={category} onChange={setCategory}
                      options={CATEGORIES.map((c) => ({ value: c, label: categoryLabel(c) }))} testId="category-select" />
              <Fetched show={fetched.has("category")}>{fetched.has("category") ? null : "Each category is scored on what it is for."}</Fetched>
            </Field>
            <Field label="Country" htmlFor="f-country">
              <Select id="f-country" labelledBy="f-country-label" value={country} onChange={setCountry}
                      options={COUNTRIES.map((c) => ({ value: c, label: c, meta: currencyAffix(CURRENCY_MAP[c]) }))}
                      testId="country-select" />
              <p className="field__help">Prices are compared within this country.</p>
            </Field>
          </div>

          <Field label="Ingredients (INCI list)" htmlFor="f-inci"
                 meta={ingredientCount ? `${ingredientCount} ingredient${ingredientCount === 1 ? "" : "s"}` : null}>
            <div className="field__control field__control--textarea">
              <textarea id="f-inci" value={ingredients} onChange={(e) => setIngredients(e.target.value)} rows={4}
                        placeholder="Aqua, Niacinamide, Pentylene Glycol, Zinc PCA, Sodium Hyaluronate…"
                        data-testid="ingredients-input" spellCheck={false} />
            </div>
            <Fetched show={fetched.has("ingredients")}>
              {fetched.has("ingredients") ? "check it matches the pack" : "Copy it from the pack or the product page, in the order printed."}
            </Fetched>
          </Field>
        </div>
      </section>

      {/* ---------------------------------------------------------- step 2 */}
      <section className="card step-card" aria-labelledby="step-skin" data-testid="skin-profile-card">
        <StepHead n="2" id="step-skin" title="Your skin"
                  sub="Used for the personal fit. The formulation score doesn’t change." />

        <div className="stack" style={{ "--stack-gap": "12px" }}>
          <p className="field__label" id="skin-type-label">Skin type</p>
          <div className="chip-group" role="radiogroup" aria-labelledby="skin-type-label">
            {SKIN_TYPES.map((t) => {
              const on = skinType === t;
              return (
                <button key={t} type="button" role="radio" aria-checked={on} className="chip"
                        tabIndex={on || (!skinType && t === SKIN_TYPES[0]) ? 0 : -1}
                        onKeyDown={(e) => handleRadioKey(e, SKIN_TYPES, t, setSkinType)}
                        onClick={() => setSkinType(t)} data-testid={`skin-type-${t.toLowerCase()}`}>
                  {on && <Check aria-hidden="true" />}{t}
                </button>
              );
            })}
          </div>
        </div>

        <div className="stack" style={{ "--stack-gap": "12px" }}>
          <div className="field__label" id="concerns-label">
            <span>Concerns</span>
            <span className="field__label-meta">{concerns.length} of 3 chosen</span>
          </div>
          <div className="tile-grid" role="group" aria-labelledby="concerns-label" data-testid="skin-concerns-grid">
            {visibleConcerns.map((c) => {
              const on = concerns.includes(c.key);
              const disabled = !on && atLimit;
              return (
                <button key={c.key} type="button" className="tile" aria-pressed={on}
                        aria-disabled={disabled || undefined}
                        onClick={() => { if (!disabled) toggleConcern(c.key); }}
                        data-testid={`concern-${c.key.replace(/\s+/g, "-").toLowerCase()}`}>
                  <span className="tile__top">
                    <ConcernBadge name={c.key} />
                    <span className="tile__check" aria-hidden="true"><Check /></span>
                  </span>
                  <span>
                    <span className="tile__name">{c.key}</span>
                    <span className="tile__desc" style={{ display: "block" }}>{c.desc}</span>
                  </span>
                </button>
              );
            })}
          </div>
          {!chosenBeyond && (
            <button type="button" className="link" onClick={() => setShowAllConcerns((v) => !v)} aria-expanded={showAllConcerns}>
              {showAllConcerns ? "Show fewer concerns" : `Show all ${CONCERNS_LIST.length} concerns`}
              <ChevronDown aria-hidden="true" style={{ transform: showAllConcerns ? "rotate(180deg)" : "none" }} />
            </button>
          )}
          {atLimit && <p className="field__help">Three is the most we score at once — tap one to swap it out.</p>}
        </div>
      </section>

      {/* ---------------------------------------------------------- action */}
      <div className="analyse-action">
        {error && (
          <Callout tone="negative" title="Before we can analyse" role="alert" data-testid="error-message">
            <p className="callout__text">{error}</p>
          </Callout>
        )}
        <Button variant="primary" size="lg" block arrow loading={loading} loadingText="Analysing…"
                onClick={handleAnalyze} data-testid="analyze-btn">
          Analyse product
        </Button>
        <p className="t-caption c-tertiary analyse-action__note">
          {account?.signedIn
            ? (account.owner
              ? "Your formulation score and personal fit, together."
              : `Your formulation score is free. The personal fit uses 1 of your ${account.balance} credits.`)
            : "Your formulation score is free. Sign in for a personal fit — your first 4 credits are on us."}
        </p>
        <button type="button" className={cx("link", "analyse-action__clear")} onClick={handleClear} data-testid="clear-btn">
          Clear everything
        </button>
      </div>
    </div>
  );
}

function StepHead({ n, id, title, sub }) {
  return (
    <header className="step-head">
      <span className="step-head__num" aria-hidden="true">{n}</span>
      <div>
        <h2 className="t-heading-l" id={id}>{title}</h2>
        {sub && <p className="t-body-s c-secondary">{sub}</p>}
      </div>
    </header>
  );
}

function Field({ label, htmlFor, meta, children }) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={htmlFor} id={htmlFor ? `${htmlFor}-label` : undefined}>
        <span>{label}</span>
        {meta && <span className="field__label-meta">{meta}</span>}
      </label>
      {children}
    </div>
  );
}

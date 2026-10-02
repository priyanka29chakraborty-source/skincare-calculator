import { CONCERNS_LIST, SKIN_TYPES, CATEGORIES, COUNTRIES, SIZE_UNITS, CURRENCY_MAP, currencyAffix } from "../constants";


// Keyboard support for the custom radio chips. They carry role="radio", which
// promises arrow-key navigation and space/enter selection to assistive tech;
// without this they were announced as radios but could not be operated at all.
function handleRadioKey(e, options, current, onSelect) {
  const i = options.indexOf(current);
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    onSelect(current);
    return;
  }
  const forward = e.key === "ArrowRight" || e.key === "ArrowDown";
  const back = e.key === "ArrowLeft" || e.key === "ArrowUp";
  if (!forward && !back) return;
  e.preventDefault();
  const next = options[(i + (forward ? 1 : -1) + options.length) % options.length];
  onSelect(next);
  const el = e.currentTarget.parentElement?.children[options.indexOf(next)];
  if (el) el.focus();
}

export default function InputForm({
  fetchInput, setFetchInput, fetchLoading, fetchMsg, fetchStatus, fetchError, handleFetch,
  fetchVerifyPending, onFetchVerifyDismiss,
  productName, setProductName, brand, setBrand, price, setPrice,
  size, setSize, sizeUnit, setSizeUnit, category, setCategory, country, setCountry,
  ingredients, setIngredients, skinType, setSkinType, concerns, toggleConcern,
  handleAnalyze, handleClear, loading, error,
}) {
  const currency = CURRENCY_MAP[country] || "INR";

  return (
    <>
      {/* Fetch verification popup */}
      {fetchVerifyPending && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)",
          zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: "16px"
        }}>
          <div style={{
            background: "#fff", borderRadius: "14px", padding: "28px 24px", maxWidth: "420px",
            width: "100%", boxShadow: "0 8px 32px rgba(0,0,0,0.18)", textAlign: "center"
          }}>
            <i className="fa-solid fa-circle-exclamation" style={{ color: "#C9A96E", fontSize: "2rem", marginBottom: "12px", display: "block" }}></i>
            <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "10px", color: "#2C2420" }}>
              Please verify the auto-filled details
            </h3>
            <p style={{ fontSize: "0.82rem", color: "#7A7168", lineHeight: 1.6, marginBottom: "18px" }}>
              We fetched details from the product page. Please cross-check the <strong>Product Name</strong>,
              <strong> Brand</strong>, <strong>Price</strong>, <strong>Size</strong>, and especially the
              <strong> Ingredients (INCI) list</strong> before analysing — scraped data can sometimes be
              incomplete or incorrect.
            </p>
            <button
              onClick={onFetchVerifyDismiss}
              style={{
                background: "linear-gradient(135deg, #C9A96E, #b8904a)", color: "#fff",
                border: "none", borderRadius: "8px", padding: "10px 28px",
                fontSize: "0.88rem", fontWeight: 700, cursor: "pointer", width: "100%"
              }}
            >
              Got it — I'll verify the details
            </button>
          </div>
        </div>
      )}
      <div className="card" data-testid="product-details-card">
        <div className="card-label">Product Details</div>
        <div className="url-row">
          <input className="url-input" data-testid="fetch-input" value={fetchInput} onChange={e => setFetchInput(e.target.value)}
            placeholder="Paste product link or barcode to auto-fill..."
            onKeyDown={e => e.key === "Enter" && handleFetch()} />
          <button className="fetch-btn" data-testid="fetch-details-btn" onClick={handleFetch} disabled={fetchLoading}>
            {fetchLoading ? <><i className="fa-solid fa-spinner fa-spin"></i> Fetching...</> : <><i className="fa-solid fa-download"></i> Fetch Details</>}
          </button>
        </div>
        {fetchStatus === "success" && fetchMsg && (
          <div style={{ marginTop: "6px", padding: "7px 12px", borderRadius: "6px", background: "#E8F5E9", border: "1px solid #66BB6A", fontSize: "0.78rem", color: "#1B5E20", display: "flex", alignItems: "center", gap: "7px" }}>
            <i className="fa-solid fa-circle-check" style={{ flexShrink: 0 }}></i>
            <span>{fetchMsg}</span>
          </div>
        )}
        {fetchStatus === "partial" && fetchMsg && (
          <div style={{ marginTop: "6px", padding: "7px 12px", borderRadius: "6px", background: "#FFF8E1", border: "1px solid #FFD54F", fontSize: "0.78rem", color: "#7A5C00", display: "flex", alignItems: "center", gap: "7px" }}>
            <i className="fa-solid fa-triangle-exclamation" style={{ flexShrink: 0 }}></i>
            <span>{fetchMsg}</span>
          </div>
        )}
        {fetchStatus === "failed" && fetchError && (
          <div style={{ marginTop: "6px", padding: "7px 12px", borderRadius: "6px", background: "#FFEBEE", border: "1px solid #EF9A9A", fontSize: "0.78rem", color: "#B71C1C", display: "flex", alignItems: "center", gap: "7px" }}>
            <i className="fa-solid fa-circle-xmark" style={{ flexShrink: 0 }}></i>
            <span>{fetchError}</span>
          </div>
        )}
        {!fetchStatus && fetchMsg && <div className="fetch-msg" data-testid="fetch-message">{fetchMsg}</div>}
        {!fetchStatus && fetchError && <div className="fetch-error-msg" data-testid="fetch-error"><i className="fa-solid fa-triangle-exclamation"></i> {fetchError}</div>}
        <div className="or-divider">or enter manually</div>
        <div className="form-grid">
          <div className="field-group">
            <label className="field-label">Product Name</label>
            <input className="field-input" data-testid="product-name-input" value={productName} onChange={e => setProductName(e.target.value)} placeholder="e.g. 10% Niacinamide Serum" />
          </div>
          <div className="field-group">
            <label className="field-label">Brand</label>
            <input className="field-input" data-testid="brand-input" value={brand} onChange={e => setBrand(e.target.value)} placeholder="e.g. Minimalist" />
          </div>
          <div className="field-group">
            <label className="field-label">Price</label>
            <div className="inline-row">
              <input className="field-input" data-testid="price-input" type="number" value={price} onChange={e => setPrice(e.target.value)} placeholder="599" min="0" />
              <div className="currency-tag" aria-label={currency}>{currencyAffix(currency)}</div>
            </div>
          </div>
          <div className="field-group">
            <label className="field-label">Size</label>
            <div className="inline-row">
              <input className="field-input" data-testid="size-input" type="number" value={size} onChange={e => setSize(e.target.value)} placeholder="30" min="0" />
              <select className="field-select" data-testid="size-unit-select" value={sizeUnit} onChange={e => setSizeUnit(e.target.value)} aria-label="Size unit">
                {SIZE_UNITS.map(u => <option key={u} value={u}>{u}</option>)}
              </select>
            </div>
          </div>
          <div className="field-group">
            <label className="field-label">Category</label>
            <select className="field-select full-w" data-testid="category-select" value={category} onChange={e => setCategory(e.target.value)} aria-label="Category">
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="field-group">
            <label className="field-label">Country</label>
            <select className="field-select full-w" data-testid="country-select" value={country} onChange={e => setCountry(e.target.value)} aria-label="Country">
              {COUNTRIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="field-group full">
            <label className="field-label">Ingredients (INCI List)</label>
            <textarea className="field-textarea" data-testid="ingredients-input" value={ingredients} onChange={e => setIngredients(e.target.value)}
              placeholder="Aqua, Niacinamide, Pentylene Glycol, Zinc PCA, Sodium Hyaluronate..." />
          </div>
        </div>
      </div>

      <div className="card" data-testid="skin-profile-card">
        <div className="card-label">Your Skin Profile</div>
        <div className="field-sublabel">Skin Type</div>
        <div className="skin-type-row" role="radiogroup" aria-label="Skin type">
          {SKIN_TYPES.map(t => (
            <div key={t} role="radio" aria-checked={skinType === t} data-testid={`skin-type-${t.toLowerCase()}`}
              tabIndex={skinType === t || (!skinType && t === SKIN_TYPES[0]) ? 0 : -1}
              onKeyDown={e => handleRadioKey(e, SKIN_TYPES, t, setSkinType)}
              className={`skin-chip ${skinType === t ? "active" : ""}`} onClick={() => setSkinType(t)}>{t}</div>
          ))}
        </div>
        <div className="field-sublabel">
          Skin Concerns <span className="field-hint">choose up to 3</span>
        </div>
        <div className="concerns-grid" role="group" aria-label="Skin concerns">
          {CONCERNS_LIST.map(c => (
            <div key={c.key} data-testid={`concern-${c.key.replace(/\s+/g, "-").toLowerCase()}`}
              role="button" tabIndex={0}
              onKeyDown={e => {
                if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleConcern(c.key); }
              }}
              className={`concern-card ${concerns.includes(c.key) ? "selected" : ""}`}
              onClick={() => toggleConcern(c.key)} aria-pressed={concerns.includes(c.key)}>
              <span className="concern-icon"><i className={c.icon}></i></span>
              <span className="concern-name">{c.key}</span>
              <span className="concern-desc">{c.desc}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="action-row">
        <button className="analyze-btn" data-testid="analyze-btn" onClick={handleAnalyze} disabled={loading}>
          {loading ? <><i className="fa-solid fa-spinner fa-spin"></i> Analysing...</> : <>Analyze Product &#10022;</>}
        </button>
      </div>
      <button className="clear-btn-solo" data-testid="clear-btn" onClick={handleClear}><i className="fa-solid fa-eraser"></i> Clear All</button>
      {error && <div className="error-banner" data-testid="error-message" role="alert"><i className="fa-solid fa-triangle-exclamation"></i> {error}</div>}
    </>
  );
}

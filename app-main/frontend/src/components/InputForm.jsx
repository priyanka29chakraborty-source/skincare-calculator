import { CONCERNS_LIST, SKIN_TYPES, CATEGORIES, COUNTRIES, SIZE_UNITS, CURRENCY_MAP } from "../constants";

export default function InputForm({
  fetchInput, setFetchInput, fetchLoading, fetchMsg, fetchError, handleFetch,
  productName, setProductName, brand, setBrand, price, setPrice,
  size, setSize, sizeUnit, setSizeUnit, category, setCategory, country, setCountry,
  ingredients, setIngredients, skinType, setSkinType, concerns, toggleConcern,
  handleAnalyze, handleClear, loading, error,
}) {
  const currency = CURRENCY_MAP[country] || "INR";

  return (
    <>
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
        {fetchMsg && <div className="fetch-msg" data-testid="fetch-message">{fetchMsg}</div>}
        {fetchError && <div className="fetch-error-msg" data-testid="fetch-error"><i className="fa-solid fa-triangle-exclamation"></i> {fetchError}</div>}
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
              <div className="currency-tag">{currency}</div>
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
        <div className="field-label" style={{ marginBottom: 12 }}>Skin Type</div>
        <div className="skin-type-row" role="radiogroup" aria-label="Skin type">
          {SKIN_TYPES.map(t => (
            <div key={t} role="radio" aria-checked={skinType === t} data-testid={`skin-type-${t.toLowerCase()}`}
              className={`skin-chip ${skinType === t ? "active" : ""}`} onClick={() => setSkinType(t)}>{t}</div>
          ))}
        </div>
        <div className="field-label" style={{ marginBottom: 12 }}>Select up to 3 Skin Concerns</div>
        <div className="concerns-grid" role="group" aria-label="Skin concerns">
          {CONCERNS_LIST.map(c => (
            <div key={c.key} data-testid={`concern-${c.key.replace(/\s+/g, "-").toLowerCase()}`}
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
          {loading ? <><i className="fa-solid fa-spinner fa-spin"></i> Analysing...</> : <>Analyse Worth &#10022;</>}
        </button>
      </div>
      <button className="clear-btn-solo" data-testid="clear-btn" onClick={handleClear}><i className="fa-solid fa-eraser"></i> Clear All</button>
      {error && <div className="error-banner" data-testid="error-message" role="alert"><i className="fa-solid fa-triangle-exclamation"></i> {error}</div>}
    </>
  );
}

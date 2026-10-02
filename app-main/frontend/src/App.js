import { useState, useCallback, useRef, useEffect } from "react";
import "@/App.css";
import { api, describeError } from "./api";
import { API, CURRENCY_MAP } from "./constants";
import InputForm from "./components/InputForm";
import ResultCards from "./components/ResultCards";
import PersonaliseCard from "./components/PersonaliseCard";
import AccountBar from "./components/AccountBar";
import UnlockModal from "./components/UnlockModal";
import HistoryCard from "./components/HistoryCard";
import CompareCard from "./components/CompareCard";
import PrintReport from "./components/PrintReport";
import useAccount from "./hooks/useAccount";

function App() {
  const [ingredients, setIngredients] = useState("");
  const [price, setPrice] = useState("");
  const [size, setSize] = useState("");
  const [sizeUnit, setSizeUnit] = useState("ml");
  const [category, setCategory] = useState("Serum");
  const [skinType, setSkinType] = useState("");
  const [concerns, setConcerns] = useState([]);
  const [country, setCountry] = useState("India");
  const [productName, setProductName] = useState("");
  const [brand, setBrand] = useState("");
  const [activeConcentrations, setActiveConcentrations] = useState({});
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  // Personal context, gathered AFTER a first result rather than before it.
  const [userProfile, setUserProfile] = useState({});
  const [personalising, setPersonalising] = useState(false);
  const [error, setError] = useState("");
  const [fetchInput, setFetchInput] = useState("");
  const [fetchLoading, setFetchLoading] = useState(false);
  const [fetchError, setFetchError] = useState("");
  const [fetchMsg, setFetchMsg] = useState("");
  const [fetchStatus, setFetchStatus] = useState(""); // "success" | "partial" | "failed"
  const [alternatives, setAlternatives] = useState(null);
  const account = useAccount();
  const [unlockOpen, setUnlockOpen] = useState(false);
  const [pendingReopen, setPendingReopen] = useState(false);
  // Read through a ref inside handleAnalyze: adding `account` to its dependency
  // list would rebuild the callback on every balance change and re-trigger the
  // effects that depend on it.
  const accountRef = useRef(account);
  accountRef.current = account;
  const [altLoading, setAltLoading] = useState(false);
  const [bestPrice, setBestPrice] = useState(null);
  const [bestPriceLoading, setBestPriceLoading] = useState(false);
  const resultRef = useRef(null);
  const analyzeTimerRef = useRef(null);
  const [fetchVerifyPending, setFetchVerifyPending] = useState(false);

  const currency = CURRENCY_MAP[country] || "INR";

  const toggleConcern = (c) => {
    setConcerns(prev => prev.includes(c) ? prev.filter(x => x !== c) : prev.length >= 3 ? prev : [...prev, c]);
  };

  const fetchAlts = useCallback(async (res) => {
    setAltLoading(true);
    try {
      const concernFit = res.skin_concern_fit || {};
      const concernScores = {};
      for (const [k, v] of Object.entries(concernFit)) {
        concernScores[k] = typeof v === 'object' ? v.score : v;
      }
      const { data } = await api.post(`${API}/find-alternatives`, {
        product_category: category,
        key_actives: (res.identified_actives || []).map(a => a.name),
        country, currency,
        upgrade_targets: res.upgrade_suggestions || [],
        user_score: res.main_worth_score,
        user_concern_fit: concernScores,
        user_safety_score: res.component_scores?.D || 0,
        user_skin_type_score: res.skin_type_compatibility || 0,
        user_skin_type: skinType.toLowerCase(),
        user_concerns: concerns,
        user_price: parseFloat(price) || 0,
        user_size_ml: parseFloat(size) || 30,
        user_product_name: productName || '',
      });
      setAlternatives(data);
    } catch { setAlternatives(null); }
    finally { setAltLoading(false); }
  }, [category, country, currency, skinType, concerns, price, size, productName]);

  const fetchBestPrice = useCallback(async () => {
    const isUrl = fetchInput.trim().startsWith('http');
    const isBarcode = /^\d{8,14}$/.test(fetchInput.trim());
    // Build best search name: prefer productName/brand, else use fetchInput if plain text
    const pName = (productName || brand || (!isUrl && !isBarcode ? fetchInput : '') || '').trim();
    if (!pName) { setBestPriceLoading(false); return; }
    setBestPriceLoading(true);
    try {
      const userUrl = isUrl ? fetchInput.trim() : null;
      const { data } = await api.post(`${API}/best-price`, {
        product_name: pName,
        brand: brand || null,
        size_ml: parseFloat(size) || null,
        country, currency,
        user_price: parseFloat(price) || 0,
        user_url: userUrl,
      });
      setBestPrice(data);
    } catch { setBestPrice(null); }
    finally { setBestPriceLoading(false); }
  }, [productName, brand, fetchInput, size, country, currency, price]);

  // Re-score with newly supplied personal context. Only the Fit score and
  // advisories can change - the formulation score is computed from the product
  // alone and will come back identical.
  const applyPersonalisation = useCallback(async (profile) => {
    setUserProfile(profile);
    if (!result) return;
    setPersonalising(true);
    try {
      let sizeMl = parseFloat(size) || 30;
      if (sizeUnit === "oz" || sizeUnit === "fl oz") sizeMl = sizeMl * 29.5735;
      const { data } = await api.post(`${API}/analyze`, {
        ingredients, price: parseFloat(price) || 0, size_ml: sizeMl,
        category, skin_concerns: concerns, skin_type: skinType.toLowerCase(),
        country, currency,
        product_name: productName || '', brand: brand || '',
        active_concentrations: activeConcentrations || {},
        size_defaulted: !size.trim(),
        user_profile: profile,
      });
      setResult(data);
    } catch (e) { setError(describeError(e)); }
    finally { setPersonalising(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, ingredients, price, size, sizeUnit, category, concerns, skinType,
      country, currency, productName, brand, activeConcentrations]);

  const handleAnalyze = useCallback(async () => {
    if (!ingredients.trim()) { setError("Please enter ingredients"); return; }
    if (!skinType) { setError("Please select a skin type"); return; }
    setError(""); setLoading(true); setResult(null); setAlternatives(null);
    try {
      let sizeMl = parseFloat(size) || 30;
      if (sizeUnit === "oz" || sizeUnit === "fl oz") sizeMl = sizeMl * 29.5735;
      const isUrlFetch = fetchInput.trim().startsWith('http');
      const isBarcodeInput = /^\d{8,14}$/.test(fetchInput.trim());
      const fetchTypeValue = isUrlFetch ? 'url' : isBarcodeInput ? 'barcode' : 'manual';
      const { data } = await api.post(`${API}/analyze`, {
        ingredients, price: parseFloat(price) || 0, size_ml: sizeMl,
        category, skin_concerns: concerns, skin_type: skinType.toLowerCase(), country, currency,
        url_provided: isUrlFetch,
        fetch_type: fetchTypeValue,
        product_name: productName || '',
        brand: brand || '',
        active_concentrations: activeConcentrations || {},
        size_defaulted: !size.trim(),
        user_profile: userProfile,
      });
      setResult(data);
      // An analysis may have spent a credit, so the counter in the header is
      // now stale. Leaving it stale means someone watches their balance sit
      // still while it is quietly going down, which is exactly the kind of
      // thing that makes a paid product feel untrustworthy.
      if (accountRef.current.signedIn) accountRef.current.refresh();
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth" }), 200);
      const concernFit = data.skin_concern_fit || {};
      const weakConcerns = Object.entries(concernFit).filter(([, v]) => typeof v === 'object' ? v.score < 75 : v < 75);
      // Only search for alternatives if score < 75 AND there are weak concern fits
      if (data.main_worth_score < 75 && weakConcerns.length > 0 && concerns.length > 0) fetchAlts(data);
      fetchBestPrice();
    } catch (e) { setError(describeError(e)); }
    finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
 }, [ingredients, price, size, sizeUnit, category, skinType, concerns, country, currency, fetchInput, productName, brand, activeConcentrations, fetchAlts, fetchBestPrice]);

  /**
   * Re-open a saved analysis.
   *
   * Restores the inputs and re-runs the engine rather than replaying a stored
   * result: the score depends on the engine, and the engine changes. Showing a
   * saved 91 beside a freshly computed 87 is how a tool loses a reader, so
   * there is only ever one number - today's.
   *
   * The analysis is scheduled on the next tick because handleAnalyze reads
   * these values from the closure it was built with, which has not yet seen
   * the state we just set.
   */
  const reopenSaved = useCallback((entry) => {
    setProductName(entry.product_name || "");
    setBrand(entry.brand || "");
    setCategory(entry.category || "Serum");
    setPrice(entry.price ? String(entry.price) : "");
    setSize(entry.size_ml ? String(entry.size_ml) : "");
    setIngredients(entry.ingredients || "");
    setSkinType(entry.skin_type ? entry.skin_type.charAt(0).toUpperCase()
                                  + entry.skin_type.slice(1) : "");
    setConcerns(entry.concerns || []);
    setResult(null);
    setPendingReopen(true);
  }, []);

  // Runs once the restored inputs have been committed, so handleAnalyze sees
  // them. Re-running costs no credit: the ledger is keyed on the product.
  useEffect(() => {
    if (!pendingReopen) return;
    setPendingReopen(false);
    handleAnalyze();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingReopen]);

  // Input debouncing - clear error after typing
  useEffect(() => {
    if (error && ingredients.trim()) {
      if (analyzeTimerRef.current) clearTimeout(analyzeTimerRef.current);
      analyzeTimerRef.current = setTimeout(() => setError(""), 2000);
    }
    return () => { if (analyzeTimerRef.current) clearTimeout(analyzeTimerRef.current); };
  }, [ingredients, error]);

  const handleFetch = useCallback(async () => {
    if (!fetchInput.trim()) return;
    setFetchLoading(true); setFetchError(""); setFetchMsg(""); setFetchStatus("");
    const isBarcode = /^\d{8,14}$/.test(fetchInput.trim());
    const isUrl = fetchInput.trim().startsWith("http");
    if (!isBarcode && !isUrl) { setFetchError("Enter a valid barcode or product URL"); setFetchLoading(false); return; }
    
    // Reset form fields before fetching new product
    setIngredients(""); setPrice(""); setSize(""); setSizeUnit("ml");
    setProductName(""); setBrand(""); setActiveConcentrations({});
    setResult(null); setAlternatives(null); setBestPrice(null);

    try {
      const body = isBarcode ? { barcode: fetchInput.trim() } : { url: fetchInput.trim() };
      const { data } = await api.post(`${API}/fetch-product`, body);
      if (data.ingredients) {
        // Strip emojis, section headings (e.g. "Key Ingredients:"), and normalize separators
        const cleaned = data.ingredients
          // Remove emojis (surrogate pairs used by JS for supplementary planes)
          .replace(/\uD83C[\uDF00-\uDFFF]|\uD83D[\uDC00-\uDE4F\uDE80-\uDEFF]|\uD83E[\uDD00-\uDDFF]/g, '')
          .replace(/[\u2600-\u26FF\u2700-\u27BF\uFE00-\uFEFF]/g, '')
          // Remove section headings: "Key Ingredients:", "Active Ingredients:", etc.
          .replace(/\s*[^\n,;]*ingredients?\s*[:：]\s*/gi, '')
          // After emoji removal, items may be separated by 2+ spaces — convert to comma
          .replace(/[ \t]{2,}/g, ', ')
          // Remove leading comma/semicolon per line
          .replace(/^\s*[,;]+\s*/gm, '')
          // Normalize inline separators
          .replace(/[ \t]*[,;][ \t]*/g, ', ')
          // Newlines → comma
          .replace(/\n+/g, ', ')
          // Collapse duplicate commas
          .replace(/,\s*,+/g, ', ')
          // Trim leading/trailing junk
          .replace(/^[,\s]+|[,\s]+$/g, '')
          .trim();
        setIngredients(cleaned);
      }
      if (data.price) setPrice(String(data.price));
      if (data.size) { setSize(String(data.size)); if (data.unit) setSizeUnit(data.unit); }
      if (data.country) setCountry(data.country);
      if (data.brand) setBrand(data.brand);
      if (data.product_name) setProductName(data.product_name);
      if (data.category) setCategory(data.category);
      if (data.active_concentrations) setActiveConcentrations(data.active_concentrations);
      if (data.bundle_warning) {
        setFetchStatus("partial");
        setFetchMsg("⚠️ This URL looks like a bundle/pack listing. Size and price may reflect the pack, not a single product. Please verify all fields manually.");
        setFetchVerifyPending(true);
      } else if (data.scrape_failed) {
        setFetchStatus("failed");
        setFetchError("⚠️ Could not fetch product details from this URL. Please fill in the fields manually.");
      } else if (data.message || data.partial) {
        setFetchStatus("partial");
        setFetchMsg(data.message || "Some fields could not be fetched. Please fill in the missing fields manually.");
        setFetchVerifyPending(true);
      } else if (data.price_note && !data.partial) {
        setFetchStatus("partial");
        setFetchMsg(data.price_note);
      } else if (!data.partial && data.ingredients) {
        setFetchStatus("success");
        setFetchMsg("Product details fetched successfully!");
        setFetchVerifyPending(true);
      }
    } catch (e) { setFetchError(describeError(e) + " You can paste the ingredient list manually instead."); }
    finally { setFetchLoading(false); }
  }, [fetchInput]);

  const handleClear = () => {
    setIngredients(""); setPrice(""); setSize(""); setSizeUnit("ml"); setCategory("Serum");
    setSkinType(""); setConcerns([]); setCountry("India"); setProductName(""); setBrand("");
    setResult(null); setError(""); setFetchInput(""); setFetchError(""); setFetchMsg(""); setFetchStatus("");
    setAlternatives(null); setBestPrice(null); setActiveConcentrations({});
  };

  return (
    <div className="sc-app" data-testid="skincare-app">
      <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" />

      <AccountBar account={account} onOpenUnlock={() => setUnlockOpen(true)} />

      <UnlockModal
        open={unlockOpen}
        onClose={() => setUnlockOpen(false)}
        account={account}
        /* Re-run the analysis straight after a purchase. The user pressed
           unlock on a result that is already on screen; making them press
           Analyze again to see what they just paid for would be a poor joke. */
        onPurchased={() => { setUnlockOpen(false); handleAnalyze(); }}
      />

      <header className="sc-header" data-testid="app-header">
        <div className="eyebrow">Skincare Analysis Tool</div>
        <h1 className="sc-title"><i className="fa-solid fa-flask-vial"></i> Analyze Your Skincare Product</h1>
        <p className="sc-subtitle">Science-backed ingredient analysis. Transparent scoring.</p>
      </header>

      <main className="sc-main">
        <HistoryCard account={account} onReopen={reopenSaved} />

        <InputForm
          fetchInput={fetchInput} setFetchInput={setFetchInput}
          fetchLoading={fetchLoading} fetchMsg={fetchMsg} fetchStatus={fetchStatus} fetchError={fetchError} handleFetch={handleFetch}
          fetchVerifyPending={fetchVerifyPending} onFetchVerifyDismiss={() => setFetchVerifyPending(false)}
          productName={productName} setProductName={setProductName}
          brand={brand} setBrand={setBrand}
          price={price} setPrice={setPrice}
          size={size} setSize={setSize}
          sizeUnit={sizeUnit} setSizeUnit={setSizeUnit}
          category={category} setCategory={setCategory}
          country={country} setCountry={setCountry}
          ingredients={ingredients} setIngredients={setIngredients}
          skinType={skinType} setSkinType={setSkinType}
          concerns={concerns} toggleConcern={toggleConcern}
          handleAnalyze={handleAnalyze} handleClear={handleClear}
          loading={loading} error={error}
        />

        {result && (
          <section className="sc-results" ref={resultRef} data-testid="results-section">
            {/* Shown after the result, never before it. Three questions to
                sharpen the fit assessment is a fair trade once someone can see
                what they are sharpening. Eight questions before any answer is
                a wall in front of the thing they came for. */}
            {/* Skin tone, climate, sensitivities and current routine are the
                paid product. When locked the card collects nothing at all -
                see PersonaliseCard. `access.tier` is the server's answer, not
                a client guess. */}
            <PersonaliseCard
              profile={userProfile}
              onApply={applyPersonalisation}
              loading={personalising}
              level={result.personalisation?.level || "none"}
              locked={result.access?.tier === "free"}
              onUnlock={() => setUnlockOpen(true)}
            />
            <ResultCards
              result={result} concerns={concerns} skinType={skinType} currency={currency}
              productName={productName} brand={brand} price={price} size={size} sizeUnit={sizeUnit}
              alternatives={alternatives} altLoading={altLoading}
              bestPrice={bestPrice} bestPriceLoading={bestPriceLoading}
              fetchInput={fetchInput}
              category={category}
              onUnlock={() => setUnlockOpen(true)}
            />

            <div className="export-row no-print">
              <button className="export-btn" onClick={() => window.print()}
                      data-testid="export-btn">
                <i className="fa-solid fa-file-arrow-down"></i> Save as PDF
              </button>
            </div>

            {/* The document that actually prints. Hidden on screen; @media
                print hides the app and shows only this. It is a standalone
                report rather than a picture of the page, because a saved PDF
                is read weeks later by someone who was not here when it was
                made. */}
            <PrintReport
              result={result}
              productName={productName} brand={brand} category={category}
              price={price} size={size} sizeUnit={sizeUnit}
              currency={currency} skinType={skinType} concerns={concerns}
            />

            {/* Seeded with the product just analysed, so comparing it against
                something else does not mean typing it in again. */}
            <CompareCard
              currency={currency}
              skinType={skinType}
              concerns={concerns}
              seed={{
                product_name: productName, brand, category,
                price: price || "", size_ml: size || "", ingredients,
              }}
            />
          </section>
        )}
      </main>
    </div>
  );
}

export default App;

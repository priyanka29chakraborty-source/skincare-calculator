import { useState, useCallback, useRef, useEffect } from "react";
import "@/App.css";
import axios from "axios";
import { API, CURRENCY_MAP } from "./constants";
import InputForm from "./components/InputForm";
import ResultCards from "./components/ResultCards";

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
  const [error, setError] = useState("");
  const [fetchInput, setFetchInput] = useState("");
  const [fetchLoading, setFetchLoading] = useState(false);
  const [fetchError, setFetchError] = useState("");
  const [fetchMsg, setFetchMsg] = useState("");
  const [alternatives, setAlternatives] = useState(null);
  const [altLoading, setAltLoading] = useState(false);
  const [bestPrice, setBestPrice] = useState(null);
  const [bestPriceLoading, setBestPriceLoading] = useState(false);
  const resultRef = useRef(null);
  const analyzeTimerRef = useRef(null);

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
      const { data } = await axios.post(`${API}/find-alternatives`, {
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
      const { data } = await axios.post(`${API}/best-price`, {
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

  const handleAnalyze = useCallback(async () => {
    if (!ingredients.trim()) { setError("Please enter ingredients"); return; }
    if (!skinType) { setError("Please select a skin type"); return; }
    setError(""); setLoading(true); setResult(null); setAlternatives(null);
    try {
      let sizeMl = parseFloat(size) || 30;
      if (sizeUnit === "oz" || sizeUnit === "fl oz") sizeMl = sizeMl * 29.5735;
      const { data } = await axios.post(`${API}/analyze`, {
        ingredients, price: parseFloat(price) || 0, size_ml: sizeMl,
        category, skin_concerns: concerns, skin_type: skinType.toLowerCase(), country, currency,
        url_provided: fetchInput.trim().startsWith('http'),
        product_name: productName || '',
        active_concentrations: activeConcentrations || {}
      });
      setResult(data);
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth" }), 200);
      const concernFit = data.skin_concern_fit || {};
      const weakConcerns = Object.entries(concernFit).filter(([, v]) => typeof v === 'object' ? v.score < 75 : v < 75);
      // Only search for alternatives if score < 75 AND there are weak concern fits
      if (data.main_worth_score < 75 && weakConcerns.length > 0 && concerns.length > 0) fetchAlts(data);
      fetchBestPrice();
    } catch (e) { setError(e.response?.data?.error || "Analysis failed"); }
    finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
 }, [ingredients, price, size, sizeUnit, category, skinType, concerns, country, currency, fetchInput, productName, activeConcentrations, fetchAlts, fetchBestPrice]);

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
    setFetchLoading(true); setFetchError(""); setFetchMsg("");
    const isBarcode = /^\d{8,14}$/.test(fetchInput.trim());
    const isUrl = fetchInput.trim().startsWith("http");
    if (!isBarcode && !isUrl) { setFetchError("Enter a valid barcode or product URL"); setFetchLoading(false); return; }
    
    // Reset form fields before fetching new product
    setIngredients(""); setPrice(""); setSize(""); setSizeUnit("ml");
    setProductName(""); setBrand(""); setActiveConcentrations({});
    setResult(null); setAlternatives(null); setBestPrice(null);

    try {
      const body = isBarcode ? { barcode: fetchInput.trim() } : { url: fetchInput.trim() };
      const { data } = await axios.post(`${API}/fetch-product`, body);
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
      if (data.scrape_failed) {
        setFetchError("⚠️ Could not fetch product details from this URL. Please fill in the fields manually.");
      } else if (data.message) setFetchMsg(data.message);
      else if (data.price_note) setFetchMsg(data.price_note);
      else if (data.partial) setFetchMsg("Some fields not found — please check and fill in manually.");
      else if (!data.partial && data.ingredients) setFetchMsg("Product details fetched successfully!");
    } catch (e) { setFetchError(e.response?.data?.error || "Failed to fetch. Please fill in manually."); }
    finally { setFetchLoading(false); }
  }, [fetchInput]);

  const handleClear = () => {
    setIngredients(""); setPrice(""); setSize(""); setSizeUnit("ml"); setCategory("Serum");
    setSkinType(""); setConcerns([]); setCountry("India"); setProductName(""); setBrand("");
    setResult(null); setError(""); setFetchInput(""); setFetchError(""); setFetchMsg("");
    setAlternatives(null); setBestPrice(null); setActiveConcentrations({});
  };

  return (
    <div className="sc-app" data-testid="skincare-app">
      <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" />

      <header className="sc-header" data-testid="app-header">
        <div className="eyebrow">Skincare Analysis Tool</div>
        <h1 className="sc-title"><i className="fa-solid fa-flask-vial"></i> Analyze Your Skincare Product</h1>
        <p className="sc-subtitle">Science-backed ingredient analysis. Transparent scoring.</p>
      </header>

      <main className="sc-main">
        <InputForm
          fetchInput={fetchInput} setFetchInput={setFetchInput}
          fetchLoading={fetchLoading} fetchMsg={fetchMsg} fetchError={fetchError} handleFetch={handleFetch}
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
            <ResultCards
              result={result} concerns={concerns} skinType={skinType} currency={currency}
              alternatives={alternatives} altLoading={altLoading}
              bestPrice={bestPrice} bestPriceLoading={bestPriceLoading}
              fetchInput={fetchInput}
            />
          </section>
        )}
      </main>
    </div>
  );
}

export default App;

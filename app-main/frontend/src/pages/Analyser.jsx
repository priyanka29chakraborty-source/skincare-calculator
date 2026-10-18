import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check } from "lucide-react";

import { api, describeError } from "../api";
import { API, CURRENCY_MAP, money, toMl } from "../constants";
import AppBar from "../components/AppBar";
import InputForm, { countIngredients } from "../components/InputForm";
import ResultView from "../components/ResultView";
import AnalysingState from "../components/AnalysingState";
import SavedSheet from "../components/HistoryCard";
import CompareCard from "../components/CompareCard";
import PrintReport from "../components/PrintReport";
import { SiteFooter } from "../components/SiteChrome";
import { detectInput } from "../components/SmartInput";
import { ANALYSE_PATH, navigate } from "../lib/router";
import { track } from "../track";

/** Strip emoji, section headings and stray separators from a scraped INCI list. */
function cleanInci(raw) {
  return String(raw || "")
    .replace(/\uD83C[\uDF00-\uDFFF]|\uD83D[\uDC00-\uDE4F\uDE80-\uDEFF]|\uD83E[\uDD00-\uDDFF]/g, "")
    .replace(/[☀-⛿✀-➿︀-﻿]/g, "")
    .replace(/\s*[^\n,;]*ingredients?\s*[:：]\s*/gi, "")
    .replace(/[ \t]{2,}/g, ", ")
    .replace(/^\s*[,;]+\s*/gm, "")
    .replace(/[ \t]*[,;][ \t]*/g, ", ")
    .replace(/\n+/g, ", ")
    .replace(/,\s*,+/g, ", ")
    .replace(/^[,\s]+|[,\s]+$/g, "")
    .trim();
}

function hostOf(url) {
  try { return new URL(url.startsWith("http") ? url : `https://${url}`).hostname.replace(/^www\./, ""); }
  catch { return ""; }
}

export default function Analyser({ route, account, openUnlock, onPurchasedRef }) {
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
  // Personal context, gathered AFTER a first result rather than before it.
  const [userProfile, setUserProfile] = useState({});
  const [personalising, setPersonalising] = useState(false);
  const [personaliseOpen, setPersonaliseOpen] = useState(false);

  const [fetchInput, setFetchInput] = useState("");
  const [fetchLoading, setFetchLoading] = useState(false);
  const [fetchError, setFetchError] = useState("");
  const [fetchMsg, setFetchMsg] = useState("");
  const [fetchTitle, setFetchTitle] = useState("");
  const [fetchStatus, setFetchStatus] = useState(""); // success | partial | failed | local
  const [fetched, setFetched] = useState(() => new Set());
  const [productUrl, setProductUrl] = useState("");

  const [alternatives, setAlternatives] = useState(null);
  const [altLoading, setAltLoading] = useState(false);
  const [bestPrice, setBestPrice] = useState(null);
  const [bestPriceLoading, setBestPriceLoading] = useState(false);
  const [bestPriceError, setBestPriceError] = useState("");

  const [editing, setEditing] = useState(false);
  const [savedOpen, setSavedOpen] = useState(false);
  // A saved comparison to load into the compare form ("Compare again").
  const [comparePreset, setComparePreset] = useState(null);
  const [pendingReopen, setPendingReopen] = useState(false);
  const [pendingFetch, setPendingFetch] = useState(false);
  const [toast, setToast] = useState("");

  const accountRef = useRef(account);
  accountRef.current = account;

  const currency = CURRENCY_MAP[country] || "INR";
  const view = new URLSearchParams(route.search).get("view") === "compare" ? "compare" : "analyse";

  const pricePerMl = useMemo(() => {
    const p = parseFloat(price); const s = parseFloat(size);
    if (!p || !s) return "";
    const ml = toMl(s, sizeUnit);
    return money(currency, (p / ml).toFixed(2));
  }, [price, size, sizeUnit, currency]);

  const toggleConcern = (c) => {
    setConcerns((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : prev.length >= 3 ? prev : [...prev, c]));
  };

  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(""), 2600);
    return () => clearTimeout(t);
  }, [toast]);

  const fetchAlts = useCallback(async (res) => {
    setAltLoading(true);
    try {
      const concernScores = {};
      for (const [k, v] of Object.entries(res.skin_concern_fit || {})) {
        concernScores[k] = typeof v === "object" ? v.score : v;
      }
      const { data } = await api.post(`${API}/find-alternatives`, {
        product_category: category,
        key_actives: (res.identified_actives || []).map((a) => a.name),
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
        user_product_name: productName || "",
      });
      setAlternatives(data);
    } catch { setAlternatives(null); }
    finally { setAltLoading(false); }
  }, [category, country, currency, skinType, concerns, price, size, productName]);

  const fetchBestPrice = useCallback(async () => {
    const isUrl = productUrl.startsWith("http");
    const pName = (productName || brand || "").trim();
    if (!pName) { setBestPriceLoading(false); setBestPrice(null); return; }
    setBestPriceLoading(true);
    setBestPriceError("");
    try {
      const { data } = await api.post(`${API}/best-price`, {
        product_name: pName,
        brand: brand || null,
        size_ml: parseFloat(size) || null,
        country, currency,
        user_price: parseFloat(price) || 0,
        user_url: isUrl ? productUrl : null,
      });
      setBestPrice(data);
    } catch (e) {
      setBestPrice(null);
      setBestPriceError(`${describeError(e)} Price search did not finish.`);
    } finally { setBestPriceLoading(false); }
  }, [productName, brand, productUrl, size, country, currency, price]);

  // Re-score with personal context. Only the fit and advisories can change -
  // the formulation score is computed from the product alone.
  const applyPersonalisation = useCallback(async (profile) => {
    setUserProfile(profile);
    if (!result) return;
    setPersonalising(true);
    try {
      const sizeMl = toMl(size, sizeUnit) || 30;
      const { data } = await api.post(`${API}/analyze`, {
        ingredients, price: parseFloat(price) || 0, size_ml: sizeMl,
        category, skin_concerns: concerns, skin_type: skinType.toLowerCase(),
        country, currency,
        product_name: productName || "", brand: brand || "",
        active_concentrations: activeConcentrations || {},
        size_defaulted: !String(size).trim(),
        user_profile: profile,
      });
      setResult(data);
    } catch (e) { setError(describeError(e)); }
    finally { setPersonalising(false); }
  }, [result, ingredients, price, size, sizeUnit, category, concerns, skinType,
      country, currency, productName, brand, activeConcentrations]);

  const handleAnalyze = useCallback(async () => {
    if (!ingredients.trim()) { setError("Add the ingredient list — paste it from the pack or the product page."); return; }
    if (!skinType) { setError("Choose your skin type so we can match the product to you."); return; }
    setError(""); setLoading(true); setAlternatives(null); setBestPrice(null); setBestPriceError("");
    setPersonaliseOpen(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
    try {
      const sizeMl = toMl(size, sizeUnit) || 30;
      const isUrlFetch = productUrl.startsWith("http");
      const isBarcode = /^\d{8,14}$/.test(fetchInput.trim());
      const { data } = await api.post(`${API}/analyze`, {
        ingredients, price: parseFloat(price) || 0, size_ml: sizeMl,
        category, skin_concerns: concerns, skin_type: skinType.toLowerCase(), country, currency,
        url_provided: isUrlFetch,
        fetch_type: isUrlFetch ? "url" : isBarcode ? "barcode" : "manual",
        product_name: productName || "",
        brand: brand || "",
        active_concentrations: activeConcentrations || {},
        size_defaulted: !String(size).trim(),
        user_profile: userProfile,
      });
      setResult(data);
      setEditing(false);
      track("analysis_completed");
      // A credit may have been spent; never leave the balance stale.
      if (accountRef.current.signedIn) accountRef.current.refresh();
      const weak = Object.values(data.skin_concern_fit || {})
        .filter((v) => (typeof v === "object" ? v.score : v) < 75);
      if (data.main_worth_score < 75 && weak.length > 0 && concerns.length > 0) fetchAlts(data);
      fetchBestPrice();
    } catch (e) { setError(describeError(e)); }
    finally { setLoading(false); }
  }, [ingredients, price, size, sizeUnit, category, skinType, concerns, country, currency, fetchInput,
      productUrl, productName, brand, activeConcentrations, userProfile, fetchAlts, fetchBestPrice]);

  // After a purchase, re-run so the person sees what they paid for.
  useEffect(() => {
    onPurchasedRef.current = () => { if (result) handleAnalyze(); };
    return () => { onPurchasedRef.current = null; };
  }, [onPurchasedRef, result, handleAnalyze]);

  /** Re-open a saved analysis: restore inputs, re-run on today's engine. */
  const reopenSaved = useCallback((entry) => {
    setProductName(entry.product_name || "");
    setBrand(entry.brand || "");
    setCategory(entry.category || "Serum");
    setPrice(entry.price ? String(entry.price) : "");
    setSize(entry.size_ml ? String(entry.size_ml) : "");
    setIngredients(entry.ingredients || "");
    setSkinType(entry.skin_type ? entry.skin_type.charAt(0).toUpperCase() + entry.skin_type.slice(1) : "");
    setConcerns(entry.concerns || []);
    setResult(null);
    setFetched(new Set());
    setFetchStatus("");
    if (view === "compare") navigate(ANALYSE_PATH);
    setPendingReopen(true);
  }, [view]);

  useEffect(() => {
    if (!pendingReopen) return;
    setPendingReopen(false);
    handleAnalyze();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingReopen]);

  useEffect(() => {
    if (!personaliseOpen) return;
    requestAnimationFrame(() => document.querySelector('[data-testid="personalise-card"]')
      ?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }, [personaliseOpen]);

  const handleFetch = useCallback(async () => {
    const raw = fetchInput.trim();
    const kind = detectInput(raw);
    setFetchError(""); setFetchMsg(""); setFetchTitle(""); setFetchStatus("");
    if (kind === "empty") return;
    if (kind === "list") {
      setIngredients(cleanInci(raw));
      setFetchInput("");
      setFetchStatus("local");
      setFetchTitle("Ingredient list added");
      setFetchMsg("It’s in the ingredients box below. Add the price and size to see price per ml.");
      return;
    }
    if (kind === "name") {
      setProductName(raw);
      setFetchInput("");
      setFetchStatus("local");
      setFetchTitle("Name added");
      setFetchMsg("Now paste the ingredient list from the pack or the product page — or paste a product link above to fill everything in.");
      return;
    }

    setFetchLoading(true);
    const url = kind === "url" ? (raw.startsWith("http") ? raw : `https://${raw}`) : "";
    // Reset the product before filling it from a new page.
    setIngredients(""); setPrice(""); setSize(""); setSizeUnit("ml");
    setProductName(""); setBrand(""); setActiveConcentrations({});
    setResult(null); setAlternatives(null); setBestPrice(null);
    setProductUrl(url);
    try {
      const body = kind === "barcode" ? { barcode: raw } : { url };
      const { data } = await api.post(`${API}/fetch-product`, body);
      const got = new Set();
      if (data.ingredients) { setIngredients(cleanInci(data.ingredients)); got.add("ingredients"); }
      if (data.price) { setPrice(String(data.price)); got.add("price"); }
      if (data.size) { setSize(String(data.size)); got.add("size"); if (data.unit) setSizeUnit(data.unit); }
      if (data.country) setCountry(data.country);
      if (data.brand) { setBrand(data.brand); got.add("brand"); }
      if (data.product_name) { setProductName(data.product_name); got.add("product_name"); }
      if (data.category) { setCategory(data.category); got.add("category"); }
      if (data.active_concentrations) setActiveConcentrations(data.active_concentrations);
      setFetched(got);

      if (data.bundle_warning) {
        setFetchStatus("partial");
        setFetchMsg("This looks like a bundle or pack listing, so the size and price may be for the whole pack. Please check them.");
      } else if (data.scrape_failed) {
        setFetchStatus("failed");
        setFetchError("Fill in the details below instead — the ingredient list is the only part we need to score it.");
      } else if (data.message || data.partial) {
        setFetchStatus("partial");
        setFetchMsg(data.message || "Some details could not be read. Please fill in what’s missing below.");
      } else if (data.price_note) {
        setFetchStatus("partial");
        setFetchMsg(data.price_note);
      } else if (data.ingredients) {
        setFetchStatus("success");
      } else {
        setFetchStatus("partial");
        setFetchMsg("We found the product but not its ingredient list. Paste it from the pack below.");
      }
    } catch (e) {
      setFetchStatus("failed");
      setFetchError(`${describeError(e)} You can paste the ingredient list below instead.`);
    } finally { setFetchLoading(false); }
  }, [fetchInput]);

  useEffect(() => {
    if (!pendingFetch) return;
    setPendingFetch(false);
    handleFetch();
  }, [pendingFetch, handleFetch]);

  // Arrived from the landing page with something already pasted.
  useEffect(() => {
    const prefill = window.history.state?.prefill;
    if (!prefill?.value) return;
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    setFetchInput(prefill.value);
    setPendingFetch(true);
  }, []);

  // A shared link opens the product and its result.
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("share");
    if (!id) return;
    setLoading(true);
    api.get(`${API}/share/${id}`).then(({ data }) => {
      const product = data.product || {};
      setProductName(product.product_name || "");
      setBrand(product.brand || "");
      setCategory(product.category || "Serum");
      setPrice(product.price ? String(product.price) : "");
      setSize(product.size_ml ? String(product.size_ml) : "");
      setIngredients(product.ingredients || "");
      setCountry(product.country || "India");
      setResult(data.result || null);
    }).catch((e) => setError(describeError(e)))
      .finally(() => setLoading(false));
  }, []);

  function savePdf() {
    document.body.classList.remove("print-compare");
    track("pdf_saved");
    window.print();
  }

  async function copyShareLink() {
    try {
      const { data } = await api.post(`${API}/share`, {
        product_name: productName, brand, category,
        price: parseFloat(price) || 0, size_ml: parseFloat(size) || 0,
        ingredients, country, currency,
      });
      const link = `${window.location.origin}${ANALYSE_PATH}?share=${data.share_id}`;
      await navigator.clipboard.writeText(link);
      setToast("Link copied — anyone with it sees this product’s score");
    } catch (e) {
      setToast(describeError(e));
    }
  }

  const handleClear = () => {
    setIngredients(""); setPrice(""); setSize(""); setSizeUnit("ml"); setCategory("Serum");
    setSkinType(""); setConcerns([]); setCountry("India"); setProductName(""); setBrand("");
    setResult(null); setError(""); setFetchInput(""); setFetchError(""); setFetchMsg(""); setFetchStatus("");
    setFetchTitle(""); setFetched(new Set()); setProductUrl("");
    setAlternatives(null); setBestPrice(null); setBestPriceError(""); setActiveConcentrations({});
    setEditing(false);
  };

  const startNew = () => { handleClear(); window.scrollTo({ top: 0, behavior: "smooth" }); };
  // Signed out: sign in first. Signed in but out of credits: straight to the packs.
  const unlock = () => openUnlock(account.signedIn ? "credits" : "signin", () => handleAnalyze(), "fit");

  let body;
  if (view === "compare") {
    body = (
      <main className="container app-main app-main--narrow" data-testid="compare-view">
        <div className="analyse-head">
          <p className="t-eyebrow c-accent">Compare</p>
          <h1 className="t-display-m">Which one is worth it?</h1>
          <p className="t-body-l c-secondary">Two to six products, scored on the same scale, with what each has that the others don’t.</p>
        </div>
        <CompareCard autoOpen preset={comparePreset} signedIn={account.signedIn} currency={currency} skinType={skinType} concerns={concerns}
                     onUnlock={() => openUnlock(account.signedIn ? "credits" : "signin", null, "compare")}
                     onSignIn={(after) => openUnlock("signin", after, "compare")}
                     seed={ingredients ? { product_name: productName, brand, category, price: price || "", size: size || "", size_unit: sizeUnit, ingredients } : null} />
      </main>
    );
  } else if (loading) {
    body = (
      <main className="container app-main app-main--narrow">
        <AnalysingState ingredientCount={countIngredients(ingredients)} category={category} productName={productName} />
      </main>
    );
  } else if (result && !editing) {
    body = (
      <ResultView
        result={result} account={account}
        productName={productName} brand={brand} category={category} price={price} size={size} sizeUnit={sizeUnit}
        currency={currency} country={country} skinType={skinType} concerns={concerns}
        alternatives={alternatives} altLoading={altLoading}
        bestPrice={bestPrice} bestPriceLoading={bestPriceLoading} bestPriceError={bestPriceError}
        onRetryBestPrice={fetchBestPrice} productUrl={productUrl}
        onUnlock={unlock} onBuyPack={() => openUnlock("credits")} onPdfSignIn={() => openUnlock("signin", null, "pdf")} onSavePdf={savePdf} pdfLocked={!account.pdfUnlocked}
        onEdit={() => { setEditing(true); window.scrollTo({ top: 0 }); }}
        onNew={startNew}
        onCompare={() => navigate(`${ANALYSE_PATH}?view=compare`)}
        onShare={copyShareLink}
        userProfile={userProfile} onApplyPersonalisation={applyPersonalisation} personalising={personalising}
        personaliseOpen={personaliseOpen} onOpenPersonalise={() => setPersonaliseOpen(true)}
        error={error}
      />
    );
  } else {
    body = (
      <main className="container app-main">
        <div className="app-grid">
          <InputForm
            smartValue={fetchInput} setSmartValue={setFetchInput} onSmartSubmit={handleFetch}
            fetchLoading={fetchLoading} fetchStatus={fetchStatus} fetchMsg={fetchMsg} fetchTitle={fetchTitle}
            fetchError={fetchError} fetchHost={hostOf(productUrl)} fetched={fetched}
            productName={productName} setProductName={setProductName}
            brand={brand} setBrand={setBrand} price={price} setPrice={setPrice}
            size={size} setSize={setSize} sizeUnit={sizeUnit} setSizeUnit={setSizeUnit}
            category={category} setCategory={setCategory} country={country} setCountry={setCountry}
            ingredients={ingredients} setIngredients={setIngredients}
            skinType={skinType} setSkinType={setSkinType} concerns={concerns} toggleConcern={toggleConcern}
            handleAnalyze={handleAnalyze} handleClear={handleClear} loading={loading} error={error}
            hasResult={Boolean(result)} onBackToResult={() => setEditing(false)}
            account={account} pricePerMl={pricePerMl}
          />
          <AnalyseRail
            productName={productName} brand={brand} category={category} price={price} size={size}
            sizeUnit={sizeUnit} currency={currency} skinType={skinType} concerns={concerns}
            ingredientCount={countIngredients(ingredients)} account={account}
            onOpenSaved={() => setSavedOpen(true)}
          />
        </div>
      </main>
    );
  }

  return (
    <div className="page app" data-testid="skincare-app">
      <AppBar account={account} view={view}
              onOpenSaved={() => setSavedOpen(true)}
              onSignIn={() => openUnlock("signin")}
              onTopUp={() => openUnlock("credits")} />
      {body}
      {result && account.pdfUnlocked && (
        <PrintReport result={result} productName={productName} brand={brand} category={category}
                     price={price} size={size} sizeUnit={sizeUnit} currency={currency}
                     skinType={skinType} concerns={concerns} />
      )}
      <SavedSheet open={savedOpen} onClose={() => setSavedOpen(false)} account={account}
                  onReopen={reopenSaved} onSignIn={() => openUnlock("signin")}
                  onCompareAgain={(products) => {
                    setComparePreset({ at: Date.now(), products });
                    navigate(`${ANALYSE_PATH}?view=compare`);
                  }} />
      {toast && <div className="toast" role="status"><Check aria-hidden="true" />{toast}</div>}
      <SiteFooter compact />
    </div>
  );
}

/** Live summary of what will be analysed. Desktop only. */
function AnalyseRail({ productName, brand, category, price, size, sizeUnit, currency, skinType, concerns,
  ingredientCount, account, onOpenSaved }) {
  const has = productName || brand || ingredientCount;
  return (
    <aside className="app-rail" aria-label="Summary">
      <div className="card rail-card">
        <p className="t-eyebrow c-tertiary">Summary</p>
        <div className="stack" style={{ "--stack-gap": "4px" }}>
          {brand && <p className="t-caption c-accent">{brand}</p>}
          <p className="t-heading-m">{productName || (has ? "Unnamed product" : "No product yet")}</p>
          <p className="t-mono-s c-secondary">
            {[category, price && money(currency, price), size && `${size} ${sizeUnit}`, ingredientCount && `${ingredientCount} ingredients`]
              .filter(Boolean).join(" · ") || "Paste a link or fill in the form"}
          </p>
        </div>
        <hr className="divider" />
        <div className="stack" style={{ "--stack-gap": "8px" }}>
          <p className="t-label-s">{skinType ? `${skinType} skin` : "Skin type not chosen"}</p>
          {concerns.length > 0 ? (
            <div className="row wrap">{concerns.map((c) => <span key={c} className="badge badge--accent">{c}</span>)}</div>
          ) : <p className="t-caption c-tertiary">Choose up to three concerns.</p>}
        </div>
        <hr className="divider" />
        <ul className="cost-rows">
          <li><span>Formulation score</span><span className="badge">Free</span></li>
          <li><span>How it suits you</span><span className="badge badge--accent">1 credit</span></li>
        </ul>
        {account.signedIn && !account.owner && (
          <p className="rail-balance">You have {account.balance} {account.balance === 1 ? "credit" : "credits"}</p>
        )}
      </div>
      {account.signedIn && (
        <button type="button" className="card card--subtle rail-tip" onClick={onOpenSaved}>
          <p className="t-label-s">Saved products and comparisons</p>
          <p className="t-body-s c-secondary">Reopen any past product or comparison — it re-runs on today’s engine, so you never see two different scores for the same bottle.</p>
        </button>
      )}
    </aside>
  );
}

// Production calls the same-origin Pages Function, which proxies to Render.
// Keeping the browser on urancal.com makes the HttpOnly session a first-party
// cookie. Local development still talks directly to the configured backend.
const API_ORIGIN = process.env.NODE_ENV === "production"
  ? ""
  : (process.env.REACT_APP_BACKEND_URL || "");
export const API = `${API_ORIGIN}/api`;
// Credits: when they lapse (shown beside the balance and in the FAQ), and the
// whole rule (the account menu's "how credits work").
export const CREDIT_EXPIRY_HINT = "Credits last one year from the day they are added, including the 4 from your first sign-in. If you buy more while some are still left, those remaining credits last until the new credits expire. Credits that have already expired are not restored.";
export const CREDIT_RULE = "A personal analysis costs 1 credit. A comparison starts at 2 credits: 2 for two products, 3 for three, 4 for four. Opening the same product or the same comparison again costs nothing. " + CREDIT_EXPIRY_HINT;

// Google AdSense ad unit ids, one per placement. Nothing renders in production
// until REACT_APP_ADSENSE_CLIENT and the matching slot id are set.
export const AD_SLOTS = {
  landingTop: process.env.REACT_APP_ADSENSE_SLOT_LANDING_TOP,
  landingBottom: process.env.REACT_APP_ADSENSE_SLOT_LANDING_BOTTOM,
  resultInArticle: process.env.REACT_APP_ADSENSE_SLOT_RESULT_INARTICLE,
  resultBottom: process.env.REACT_APP_ADSENSE_SLOT_RESULT_BOTTOM,
};
// Set REACT_APP_BACKEND_URL in Render environment to your backend URL e.g. https://your-backend.onrender.com

export const CONCERNS_LIST = [
  { key: "Acne & Oily Skin", desc: "Breakouts, oiliness" },
  { key: "Pigmentation", desc: "Dark spots, tone" },
  { key: "Aging & Fine Lines", desc: "Wrinkles, firmness" },
  { key: "Barrier Repair", desc: "Dryness, flakiness" },
  { key: "Dry Skin", desc: "Tight, rough, flaky" },
  { key: "Sensitive Skin", desc: "Redness, reactive" },
  { key: "Hydration", desc: "Tightness, dull" },
  { key: "Large Pores", desc: "Visible, texture" },
  { key: "Dullness", desc: "Lack of glow" },
  { key: "Uneven Texture", desc: "Rough, bumpy" },
  { key: "Dark Circles", desc: "Under-eye" },
  { key: "Sun Protection", desc: "SPF, UV filters" },
  { key: "UV Damage", desc: "Photoaging repair" },
  { key: "Tanning", desc: "Anti-tan, brightening" },
  { key: "Puffiness", desc: "Swelling, de-puff" },
];

export const SKIN_TYPES = ["Oily", "Dry", "Combination", "Sensitive", "Normal"];
export const CATEGORIES = ["Serum", "Moisturizer", "Cleanser", "Toner", "Sunscreen", "Eye Cream", "Mask", "Treatment", "Facial Oil"];

/** Visible spelling. The stored value stays "Moisturizer" so saved results still match. */
export function categoryLabel(value) {
  const raw = String(value || "").trim();
  if (/^moisturi[sz]er$/i.test(raw)) return "Moisturiser";
  // Sentence case everywhere: "Eye cream", "Facial oil".
  return raw ? raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase() : raw;
}
export const COUNTRIES = ["India", "USA", "UK", "UAE", "Singapore", "Australia", "Canada", "South Korea", "Japan", "France", "Germany", "Brazil"];
export const CURRENCY_MAP = { India:"INR", USA:"USD", UK:"GBP", UAE:"AED", Singapore:"SGD", Australia:"AUD", Canada:"CAD", "South Korea":"KRW", Japan:"JPY", France:"EUR", Germany:"EUR", Brazil:"BRL" };
export const SIZE_UNITS = ["ml", "g", "oz", "fl oz"];

/** Pack size in ml for the API. Ounces are read as fluid ounces; grams count as ml. */
export function toMl(size, unit) {
  const n = parseFloat(size);
  if (!n) return 0;
  return unit === "oz" || unit === "fl oz" ? n * 29.5735 : n;
}

// Display glyphs for the codes in CURRENCY_MAP. CURRENCY_MAP itself must
// keep returning ISO codes - that value is sent to the API as `currency`,
// and the backend matches on "INR", not on a symbol.
export const CURRENCY_SYMBOL = {
  INR: "\u20B9", USD: "$", GBP: "\u00A3", EUR: "\u20AC", JPY: "\u00A5",
  KRW: "\u20A9", BRL: "R$", AUD: "A$", CAD: "C$", SGD: "S$",
};

/**
 * Format an amount for display: "\u20B9549", "$12.5", or "AED 45" where no
 * single-glyph symbol is in common use. Returns "" for a missing amount so
 * callers can test it directly instead of printing a bare symbol.
 */
export function money(currency, amount) {
  if (amount === null || amount === undefined || amount === "") return "";
  // A fractional amount always shows two decimals: "₹20.50", never "₹20.5".
  const n = Number(amount);
  const shown = Number.isFinite(n) && !Number.isInteger(n) ? n.toFixed(2) : amount;
  const sym = CURRENCY_SYMBOL[currency];
  return sym ? `${sym}${shown}` : `${currency} ${shown}`;
}

/** Just the affix, for the price field's unit tag. */
export function currencyAffix(currency) {
  return CURRENCY_SYMBOL[currency] || currency;
}

/** Price per ml, compared with the usual price per ml for this type of product. */
export function pricePlain(value, currency) {
  if (!value?.available) return value?.headline || "";
  const yours = `${money(currency, value.price_per_ml)} per ml`;
  if (!value.category_avg) return `This costs ${yours}.`;
  const typical = `${money(currency, value.category_avg)} per ml`;
  const ratio = Number(value.ratio);
  let compare = "far more per ml";
  if (ratio <= 1) compare = "the same or less per ml";
  else if (ratio <= 1.8) compare = "a bit more per ml";
  else if (ratio <= 3.5) compare = "much more per ml";
  return `This costs ${yours}. Most products of this type cost about ${typical}, so this costs ${compare}.`;
}

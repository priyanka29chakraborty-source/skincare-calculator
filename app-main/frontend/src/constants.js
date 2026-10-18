export const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;
export const CREDIT_EXPIRY_HINT = "A personal analysis costs 1 credit. A comparison always includes at least two products, so it starts at 2 credits. Three products cost 3, four cost 4, five cost 5, and six cost 6. Opening the same product or the same comparison again costs nothing. Credits last one year from the day they are added. If you buy more while some are still left, those remaining credits last until the new credits expire. Credits that have already expired are not restored.";
// Set REACT_APP_BACKEND_URL in Render environment to your backend URL e.g. https://your-backend.onrender.com

export const CONCERNS_LIST = [
  { key: "Acne & Oily Skin", desc: "Breakouts, oiliness", icon: "fa-solid fa-droplet" },
  { key: "Pigmentation", desc: "Dark spots, tone", icon: "fa-solid fa-circle-half-stroke" },
  { key: "Aging & Fine Lines", desc: "Wrinkles, firmness", icon: "fa-solid fa-hourglass-half" },
  { key: "Barrier Repair", desc: "Dryness, flakiness", icon: "fa-solid fa-shield-halved" },
  { key: "Dry Skin", desc: "Tight, rough, flaky", icon: "fa-solid fa-droplet-slash" },
  { key: "Sensitive Skin", desc: "Redness, reactive", icon: "fa-solid fa-hand-holding-heart" },
  { key: "Hydration", desc: "Tightness, dull", icon: "fa-solid fa-tint" },
  { key: "Large Pores", desc: "Visible, texture", icon: "fa-solid fa-magnifying-glass" },
  { key: "Dullness", desc: "Lack of glow", icon: "fa-solid fa-sun" },
  { key: "Uneven Texture", desc: "Rough, bumpy", icon: "fa-solid fa-layer-group" },
  { key: "Dark Circles", desc: "Under-eye", icon: "fa-solid fa-eye" },
  { key: "Sun Protection", desc: "SPF, UV filters", icon: "fa-solid fa-umbrella-beach" },
  { key: "UV Damage", desc: "Photoaging repair", icon: "fa-solid fa-bolt" },
  { key: "Tanning", desc: "Anti-tan, brightening", icon: "fa-solid fa-star" },
  { key: "Puffiness", desc: "Swelling, de-puff", icon: "fa-solid fa-face-smile" },
];

export const SKIN_TYPES = ["Oily", "Dry", "Combination", "Sensitive", "Normal"];
export const CATEGORIES = ["Serum", "Moisturizer", "Cleanser", "Toner", "Sunscreen", "Eye Cream", "Mask", "Treatment", "Facial Oil"];

/** Visible spelling. The stored value stays "Moisturizer" so saved results still match. */
export function categoryLabel(value) {
  const raw = String(value || "").trim();
  if (/^moisturi[sz]er$/i.test(raw)) return "Moisturiser";
  return raw;
}
export const COUNTRIES = ["India", "USA", "UK", "UAE", "Singapore", "Australia", "Canada", "South Korea", "Japan", "France", "Germany", "Brazil"];
export const CURRENCY_MAP = { India:"INR", USA:"USD", UK:"GBP", UAE:"AED", Singapore:"SGD", Australia:"AUD", Canada:"CAD", "South Korea":"KRW", Japan:"JPY", France:"EUR", Germany:"EUR", Brazil:"BRL" };
export const SIZE_UNITS = ["ml", "g", "oz", "fl oz"];

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
  const sym = CURRENCY_SYMBOL[currency];
  return sym ? `${sym}${amount}` : `${currency} ${amount}`;
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

export function getScoreColor(s) {
  if (s >= 75) return "#22c55e";
  if (s >= 60) return "#eab308";
  if (s >= 40) return "#f97316";
  return "#ef4444";
}

export function getBarColor(p) {
  // Steps widened for scannability. The previous green (#22c55e) and lime
  // (#84cc16) were close enough that a component at 74% looked identical to
  // one at 100%, so the breakdown could not be read at a glance - which is the
  // whole job of a bar chart. Each step is now visibly distinct, using the
  // existing palette (--sage, --green, --gold, --orange, --red).
  if (p >= 85) return "#267C36";   // sage - excellent
  if (p >= 70) return "#22c55e";   // green - good
  if (p >= 50) return "#C9A96E";   // gold - middling
  if (p >= 30) return "#f97316";   // orange - weak
  return "#ef4444";                // red - poor
}

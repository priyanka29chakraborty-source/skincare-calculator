export const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;
// Set REACT_APP_BACKEND_URL in Render environment to your backend URL e.g. https://your-backend.onrender.com

export const CONCERNS_LIST = [
  { key: "Acne & Oily Skin", desc: "Breakouts, oiliness", icon: "fa-solid fa-droplet" },
  { key: "Pigmentation", desc: "Dark spots, tone", icon: "fa-solid fa-circle-half-stroke" },
  { key: "Aging & Fine Lines", desc: "Wrinkles, firmness", icon: "fa-solid fa-hourglass-half" },
  { key: "Barrier Repair", desc: "Dryness, flakiness", icon: "fa-solid fa-shield-halved" },
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
export const COUNTRIES = ["India", "USA", "UK", "UAE", "Singapore", "Australia", "Canada", "South Korea", "Japan", "France", "Germany", "Brazil"];
export const CURRENCY_MAP = { India:"INR", USA:"USD", UK:"GBP", UAE:"AED", Singapore:"SGD", Australia:"AUD", Canada:"CAD", "South Korea":"KRW", Japan:"JPY", France:"EUR", Germany:"EUR", Brazil:"BRL" };
export const SIZE_UNITS = ["ml", "g", "oz", "fl oz"];

export function getScoreColor(s) {
  if (s >= 75) return "#22c55e";
  if (s >= 60) return "#eab308";
  if (s >= 40) return "#f97316";
  return "#ef4444";
}

export function getBarColor(p) {
  if (p >= 80) return "#22c55e";
  if (p >= 60) return "#84cc16";
  if (p >= 40) return "#eab308";
  if (p >= 20) return "#f97316";
  return "#ef4444";
}

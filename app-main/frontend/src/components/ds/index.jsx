import React, { useEffect, useRef, useState } from "react";
import {
  ArrowRight, CircleCheck, Info, LoaderCircle, TriangleAlert,
} from "lucide-react";

/*
 * Design-system primitives. Each one mirrors a component set in the Figma
 * library and only uses the tokens in styles/tokens.css.
 */

/* ------------------------------------------------------------------ util */

export function cx(...parts) {
  return parts.filter(Boolean).join(" ");
}

export function prefersReducedMotion() {
  return typeof window !== "undefined"
    && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** Score → tone name used by --score-* tokens. One scale everywhere. */
export function scoreTone(score) {
  const s = Number(score) || 0;
  if (s >= 80) return "excellent";
  if (s >= 65) return "good";
  if (s >= 45) return "fair";
  if (s >= 30) return "weak";
  return "poor";
}

/** Score → badge tone for text labels. */
export function scoreBadgeTone(score) {
  const t = scoreTone(score);
  if (t === "excellent" || t === "good") return "positive";
  if (t === "fair") return "caution";
  return "negative";
}

/* ---------------------------------------------------------------- Button */

export function Button({
  variant = "primary", size, block, icon, arrow, loading, loadingText,
  as: Tag = "button", className, children, type, ...rest
}) {
  const content = loading ? (
    <>
      <LoaderCircle className="spin" aria-hidden="true" />
      <span>{loadingText || children}</span>
    </>
  ) : (
    <>
      {icon}
      {children != null && <span>{children}</span>}
      {arrow && <ArrowRight className="btn__arrow" aria-hidden="true" />}
    </>
  );
  const props = {
    className: cx("btn", `btn--${variant}`, size && `btn--${size}`, block && "btn--block", className),
    ...rest,
  };
  if (Tag === "button") {
    props.type = type || "button";
    if (loading) props["aria-busy"] = true;
  }
  return <Tag {...props}>{content}</Tag>;
}

/* ----------------------------------------------------------------- Badge */

export function Badge({ tone = "neutral", plain, className, children, ...rest }) {
  return (
    <span className={cx("badge", tone !== "neutral" && `badge--${tone}`, plain && "badge--plain", className)} {...rest}>
      {children}
    </span>
  );
}

/* ---------------------------------------------------------------- Callout */

const CALLOUT_ICON = {
  info: Info, positive: CircleCheck, caution: TriangleAlert, negative: TriangleAlert,
  neutral: Info, accent: Info,
};

export function Callout({ tone = "info", icon, title, aside, children, className, ...rest }) {
  const Icon = icon || CALLOUT_ICON[tone] || Info;
  return (
    <div className={cx("callout", tone !== "info" && `callout--${tone}`, className)} {...rest}>
      <Icon aria-hidden="true" />
      <div className="callout__body">
        {(title || aside) && (
          <div className="row-between" style={{ alignItems: "baseline" }}>
            {title && <p className="callout__title">{title}</p>}
            {aside && <span className="callout__aside">{aside}</span>}
          </div>
        )}
        {children}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ Card */

export function Card({ eyebrow, title, sub, aside, raised, subtle, className, children, headId, ...rest }) {
  return (
    <section className={cx("card", raised && "card--raised", subtle && "card--subtle", className)} {...rest}>
      {(eyebrow || title || aside) && (
        <header className="card__head">
          <div className="card__titles">
            {eyebrow && <p className="card__eyebrow">{eyebrow}</p>}
            {title && <h2 className="card__title" id={headId}>{title}</h2>}
            {sub && <p className="card__sub">{sub}</p>}
          </div>
          {aside}
        </header>
      )}
      {children}
    </section>
  );
}

/* ------------------------------------------------------------- Wordmark */

export function Wordmark({ inverse, small, href = "/", onClick, label = "Urancal home" }) {
  return (
    <a href={href} onClick={onClick} aria-label={label}
       className={cx("wordmark", inverse && "wordmark--inverse", small && "wordmark--sm")}>
      <span aria-hidden="true">urancal</span>
      <span className="wordmark__dot" aria-hidden="true" />
    </a>
  );
}

/* ----------------------------------------------------------- Count-up */

export function useCountUp(target, { duration = 900, enabled = true } = {}) {
  const value = Number(target) || 0;
  const [shown, setShown] = useState(enabled && !prefersReducedMotion() ? 0 : value);
  const fromRef = useRef(0);

  useEffect(() => {
    if (!enabled || prefersReducedMotion()) { setShown(value); return undefined; }
    const from = fromRef.current;
    let raf = 0;
    const start = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(from + (value - from) * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
      else fromRef.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration, enabled]);

  return shown;
}

/* ----------------------------------------------------------- ScoreRing */

const RING = { lg: { d: 200, w: 12 }, md: { d: 132, w: 9 }, sm: { d: 56, w: 5 } };

export function ScoreRing({ score, size = "lg", label = "Formulation score", animate = true, className, ...rest }) {
  const value = Math.max(0, Math.min(100, Number(score) || 0));
  const shown = useCountUp(value, { enabled: animate });
  const { d, w } = RING[size] || RING.lg;
  const r = (d - w) / 2;
  const c = 2 * Math.PI * r;
  const tone = scoreTone(value);
  return (
    <div className={cx("score-ring", `score-ring--${size}`, className)}
         style={{ "--ring-color": `var(--score-${tone})` }}
         role="img" aria-label={`${label}: ${value} out of 100`} {...rest}>
      <svg viewBox={`0 0 ${d} ${d}`} aria-hidden="true">
        <circle className="score-ring__track" cx={d / 2} cy={d / 2} r={r} fill="none" strokeWidth={w} />
        <circle className="score-ring__arc" cx={d / 2} cy={d / 2} r={r} fill="none" strokeWidth={w}
                strokeLinecap="round" strokeDasharray={c}
                strokeDashoffset={c * (1 - shown / 100)} />
      </svg>
      <div className="score-ring__center" aria-hidden="true">
        <span className="score-ring__num">{Math.round(shown)}</span>
        <span className="score-ring__of">out of 100</span>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- Meter */

export function Meter({ label, value, pct, tone, icon, note, unknown, className }) {
  const p = Math.max(0, Math.min(100, Number(pct) || 0));
  const [width, setWidth] = useState(prefersReducedMotion() ? p : 0);
  useEffect(() => {
    if (prefersReducedMotion()) { setWidth(p); return undefined; }
    const id = requestAnimationFrame(() => setWidth(p));
    return () => cancelAnimationFrame(id);
  }, [p]);
  const color = tone === "accent" ? "var(--bg-accent)"
    : tone === "neutral" ? "var(--border-strong)"
    : `var(--score-${tone || scoreTone(p)})`;
  return (
    <div className={cx("meter", className)}>
      {(label || value != null) && (
        <div className="meter__top">
          <span className="meter__label">{icon}{label}</span>
          {value != null && <span className="meter__value">{value}</span>}
        </div>
      )}
      {unknown ? (
        <div className="meter__track meter__track--unknown" aria-hidden="true" />
      ) : (
        <div className="meter__track" role="meter" aria-valuemin={0} aria-valuemax={100}
             aria-valuenow={Math.round(p)} aria-label={typeof label === "string" ? label : undefined}>
          <div className="meter__fill" style={{ width: `${width}%`, "--meter-color": color }} />
        </div>
      )}
      {note && <p className="meter__note">{note}</p>}
    </div>
  );
}

/* ------------------------------------------------------------ StatTile */

export function StatTile({ label, value, note, textValue, className }) {
  return (
    <div className={cx("stat", className)}>
      <span className="stat__label">{label}</span>
      <span className={cx("stat__value", textValue && "stat__value--text")}>{value ?? "—"}</span>
      {note && <span className="stat__note">{note}</span>}
    </div>
  );
}

/* --------------------------------------------------------------- AdSlot */

/*
 * Google AdSense placement.
 *
 * Production renders nothing until REACT_APP_ADSENSE_CLIENT (ca-pub-…) and a
 * slot id are configured, so no empty boxes ever ship. In development, or with
 * ?ads=preview on the URL, a labelled placeholder of the reserved size is drawn
 * so placements can be reviewed. Heights are reserved up front so an ad
 * arriving never shifts the page.
 */
const AD_CLIENT = process.env.REACT_APP_ADSENSE_CLIENT || "";

const AD_SIZES = {
  leaderboard: { w: 728, h: 90, spec: "728 × 90" },
  rectangle: { w: 300, h: 250, spec: "300 × 250" },
  halfpage: { w: 300, h: 600, spec: "300 × 600" },
  mobile: { w: 320, h: 100, spec: "320 × 100" },
  inarticle: { w: null, h: 280, spec: "in-article · fluid" },
};

function adsPreview() {
  if (typeof window === "undefined") return false;
  if (process.env.NODE_ENV === "development") return true;
  return new URLSearchParams(window.location.search).get("ads") === "preview";
}

let adScriptRequested = false;
function ensureAdScript() {
  if (adScriptRequested || !AD_CLIENT) return;
  adScriptRequested = true;
  const s = document.createElement("script");
  s.async = true;
  s.crossOrigin = "anonymous";
  s.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${AD_CLIENT}`;
  document.head.appendChild(s);
}

function LiveAd({ slot, size }) {
  const ref = useRef(null);
  useEffect(() => {
    ensureAdScript();
    try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch { /* blocked */ }
  }, []);
  const s = AD_SIZES[size];
  return (
    <ins ref={ref} className="adsbygoogle"
         style={{ display: "block", width: s.w ? `${s.w}px` : "100%", height: `${s.h}px` }}
         data-ad-client={AD_CLIENT} data-ad-slot={slot}
         {...(size === "inarticle" ? { "data-ad-format": "fluid", "data-ad-layout": "in-article" } : {})} />
  );
}

export function AdSlot({ size = "rectangle", slot, className }) {
  const s = AD_SIZES[size] || AD_SIZES.rectangle;
  const live = Boolean(AD_CLIENT && slot);
  if (!live && !adsPreview()) return null;
  return (
    <aside className={cx("ad-slot", live && "ad-slot--live", className)}
           style={{ maxWidth: s.w ? `${s.w}px` : "100%", "--ad-h": `${s.h}px` }}
           aria-label="Advertisement">
      <span className="ad-slot__label">Advertisement</span>
      <div className="ad-slot__box">
        {live ? <LiveAd slot={slot} size={size} /> : <span className="ad-slot__spec">AdSense · {s.spec}</span>}
      </div>
    </aside>
  );
}

export { default as Select } from "./Select";

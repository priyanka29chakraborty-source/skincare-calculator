import React, { useRef, useState } from "react";
import {
  ArrowRight, Check, CircleCheck, Droplet, FlaskConical, GitCompare, Link as LinkIcon,
  Lock, Plus, Tag, TriangleAlert, User,
} from "lucide-react";

import {
  AdSlot, Badge, Button, Callout, Meter, ScoreRing,
} from "../components/ds";
import SmartInput, { detectInput } from "../components/SmartInput";
import { MarketingNav, SiteFooter } from "../components/SiteChrome";
import { ANALYSE_PATH, linkTo, navigate } from "../lib/router";
import useMedia from "../lib/useMedia";
import { AD_SLOTS, CREDIT_EXPIRY_HINT } from "../constants";

/*
 * Every number on this page is either a fact about the database or the real
 * output of the engine for the example formula below. Nothing is a mock score
 * attached to a real brand.
 */
const EXAMPLE = {
  name: "Niacinamide 10% + Zinc 1%",
  inci: "Aqua, Niacinamide, Pentylene Glycol, Zinc PCA, Dimethyl Isosorbide, Sodium Hyaluronate, Tamarindus Indica Seed Gum, Xanthan Gum, Acacia Senegal Gum, Sodium PCA, Glycerin, Panthenol, Allantoin, Phenoxyethanol, Ethylhexylglycerin, Disodium EDTA, Lactic Acid",
  score: 97,
  parts: [
    ["Active efficacy", 40, 40],
    ["Evidence quality", 17.4, 20],
    ["Formulation integrity", 25, 25],
    ["Tolerability", 15, 15],
  ],
  pricePerMl: "₹19.97",
  categoryAvg: "₹20.50",
};

const RUBRICS = {
  Serum: [["Active efficacy", 40], ["Formulation integrity", 25], ["Evidence quality", 20], ["Tolerability", 15]],
  Moisturiser: [["Barrier & occlusives", 30], ["Humectant system", 25], ["Formulation integrity", 20], ["Tolerability", 15], ["Added actives", 10]],
  Cleanser: [["Surfactant mildness", 40], ["pH suitability", 20], ["Post-cleanse support", 15], ["Formulation integrity", 15], ["Tolerability", 10]],
  Sunscreen: [["UVA protection", 30], ["Filter photostability", 25], ["UVB protection", 20], ["Formulation integrity", 15], ["Tolerability", 10]],
  Toner: [["Humectant system", 35], ["Soothing support", 25], ["Active efficacy", 20], ["Tolerability", 20]],
  Treatment: [["Active efficacy", 40], ["Evidence quality", 20], ["Formulation integrity", 20], ["Tolerability", 20]],
  "Eye cream": [["Suitability for the eye area", 35], ["Hydration & barrier", 30], ["Formulation integrity", 20], ["Targeted actives", 15]],
  Mask: [["Hydration payload", 35], ["Comfort while it’s on", 30], ["Formulation integrity", 20], ["Contact-appropriate actives", 15]],
  "Facial oil": [["Lipid & emollient profile", 35], ["Oxidative stability", 30], ["Tolerability", 20], ["Ingredient evidence", 15]],
};
const RUBRIC_COLORS = ["var(--rose-600)", "var(--rose-400)", "var(--rose-200)", "var(--stone-400)", "var(--stone-600)"];

const EVIDENCE = [
  ["02", "Niacinamide", "Oil control, evens tone, supports the barrier", "Strong", "positive", "10% stated"],
  ["04", "Zinc PCA", "Helps regulate oil", "Strong", "positive", "1% stated"],
  ["06", "Sodium hyaluronate", "Holds water at the surface", "Strong", "positive", "High on the list"],
  ["17", "Lactic acid", "Gentle exfoliant at higher doses", "Limited", "caution", "Under 2%"],
];

const FAQ = [
  ["How is the score worked out?",
    "Each product is scored against a rubric for its category — a serum on its actives, a cleanser on how gently it cleans, a sunscreen on its filters. Every rubric adds up to 100, ingredients are graded on published clinical evidence, and price is never part of the score."],
  ["How accurate are the concentrations?",
    "When a brand states a percentage, we use it. Otherwise we estimate from each ingredient’s place in the list. Ingredients above about 1% must be listed from most to least, but below that line the order says nothing about amount — so every result tells you how confident it is."],
  ["Is this medical advice?",
    "No. It is an assessment of the ingredient list, not a diagnosis or a prescription. If you are pregnant, breastfeeding or using a prescription treatment, check with your doctor before changing what you use."],
  ["Which products can I analyse?",
    "Face products in nine categories — serums, moisturisers, cleansers, toners, sunscreens, eye creams, masks, treatments and facial oils. Paste a product link or barcode, or enter the details yourself."],
  ["What do credits pay for?",
    "The formulation score is free. A personal analysis — how a product suits your skin — uses 1 credit, and comparing starts at 2 credits — 2 for two products, 3 for three, and so on up to six. Opening something you’ve already paid for again costs nothing."],
  ["Do credits expire?", CREDIT_EXPIRY_HINT],
];

export default function Landing({ account, openUnlock }) {
  const [value, setValue] = useState("");
  const [ctaValue, setCtaValue] = useState("");
  const heroInput = useRef(null);
  const wide = useMedia("(min-width: 768px)");

  function start(raw) {
    const v = String(raw || "").trim();
    // Nothing typed yet: open the analyser, where the details can be entered by hand.
    if (!v) { navigate(ANALYSE_PATH); return; }
    navigate(ANALYSE_PATH, { state: { prefill: { kind: detectInput(v), value: v } } });
  }

  return (
    <div className="page landing" data-testid="landing">
      <MarketingNav account={account} onSignIn={() => openUnlock("signin")} />

      {/* ------------------------------------------------------------ Hero */}
      <section className="hero">
        <div className="container hero__grid">
          <div className="hero__copy">
            <h1 className="t-display-xl reveal">
              Know what’s <em>really</em> in the bottle.
            </h1>
            <p className="t-body-l c-secondary hero__lede reveal" style={{ "--i": 2 }}>
              Paste any skincare product link, or enter the details yourself. Urancal reads the whole
              formula — actives, likely strengths, clashes and price per ml — and tells you, plainly,
              whether it’s worth it for your skin.
            </p>
            <div className="reveal" style={{ "--i": 3 }}>
              <SmartInput value={value} onChange={setValue} onSubmit={() => start(value)} onEmpty={() => start("")} inputRef={heroInput}
                          id="hero-input" testId="hero-input" />
            </div>
            <ul className="trust reveal" style={{ "--i": 4 }}>
              {["Free formulation score", "4 free credits when you sign in", "Matched to your skin type"].map((t) => (
                <li key={t}><Check aria-hidden="true" />{t}</li>
              ))}
            </ul>
          </div>

          <div className="hero__stage reveal" style={{ "--i": 2 }} aria-label="Example analysis">
            <div className="preview">
              <div className="preview__head">
                <div className="stack" style={{ "--stack-gap": "6px" }}>
                  <span className="t-eyebrow c-accent">Example · Serum</span>
                  <h2 className="t-display-xs">{EXAMPLE.name}</h2>
                  <Badge tone="positive">Excellent formulation</Badge>
                </div>
                <ScoreRing score={EXAMPLE.score} size="md" label="Example formulation score" />
              </div>
              <div className="preview__meters">
                {EXAMPLE.parts.map(([label, s, max]) => (
                  <Meter key={label} label={label} value={`${s} / ${max}`} pct={(s / max) * 100} />
                ))}
              </div>
              <div className="preview__foot">
                <Tag aria-hidden="true" />
                <span>{EXAMPLE.pricePerMl} per ml · just under the usual serum price</span>
              </div>
            </div>
            <span className="float-chip float-chip--a"><CircleCheck aria-hidden="true" className="c-positive" />No ingredient clashes</span>
            <span className="float-chip float-chip--b"><Droplet aria-hidden="true" style={{ color: "var(--status-info)" }} />Estimated pH 3.5–5.0</span>
          </div>
        </div>
      </section>

      {/* ----------------------------------------------------------- Facts */}
      <section className="facts" aria-label="What the analysis draws on">
        <div className="container facts__grid">
          {[["920+", "ingredients graded by clinical evidence"], ["850", "ingredient pairings checked for clashes"],
            ["15", "skin concerns scored individually"], ["12", "countries’ prices for per-ml value"]].map(([n, l]) => (
            <div className="fact" key={n}>
              <span className="t-display-s">{n}</span>
              <span className="t-body-s c-secondary">{l}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ---------------------------------------------------- How it works */}
      <section className="section" id="how">
        <div className="container">
          <SectionHead eyebrow="How it works" title="Add a product. Tell us your skin. Get your answer."
                       lede="An honest, ingredient-by-ingredient answer to the one question that matters — is it worth buying?" />
          <div className="steps">
            <Step n="01" title="Paste a link, or enter it yourself"
                  body="Paste a product link and we fill in the name, price, size and full ingredient list — or type the details in yourself.">
              <div className="mini-input"><LinkIcon aria-hidden="true" /><span>shop.example.com/niacinamide-10…</span></div>
              <p className="mini-ok"><CircleCheck aria-hidden="true" />₹599 · 30 ml · 17 ingredients found</p>
            </Step>
            <Step n="02" title="Tell us about your skin"
                  body="Skin type and up to three concerns. Four more questions sharpen it further: tone, climate, sensitivities and routine.">
              <div className="row wrap">
                <span className="chip" aria-checked="true" role="presentation"><Check aria-hidden="true" />Oily</span>
                <span className="chip" role="presentation">Combination</span>
                <span className="chip" role="presentation">Dry</span>
              </div>
              <div className="row wrap"><Badge tone="accent">Acne &amp; oily</Badge><Badge tone="accent">Pigmentation</Badge></div>
            </Step>
            <Step n="03" title="Read the verdict"
                  body="A formulation score out of 100, how it suits you, price per ml against similar products, and anything to watch.">
              <div className="row" style={{ "--row-gap": "12px" }}>
                <ScoreRing score={EXAMPLE.score} size="sm" animate={false} />
                <div>
                  <p className="t-label-s">Excellent formulation</p>
                  <p className="t-caption c-secondary">Good price · suits oily skin</p>
                </div>
              </div>
            </Step>
          </div>
        </div>
      </section>

      <div className="ad-band">
        <AdSlot size={wide ? "leaderboard" : "rectangle"} slot={AD_SLOTS.landingTop} />
      </div>

      {/* ---------------------------------------------------- What you get */}
      <section className="section section--subtle" id="features">
        <div className="container">
          <SectionHead eyebrow="What you get" title={<>How well will the ingredients work on <em>your</em> skin?</>}
                       lede="We check every active, how much of it is likely there, what clashes, and what you’re paying per ml — so you don’t have to." />
          <div className="bento">
            <Feature className="bento__a" icon={<FlaskConical />} title="Formulation score"
                     body="One number for how well the product is made for its category, built from weighted parts that always add up to the total.">
              <div className="bento__score">
                <ScoreRing score={EXAMPLE.score} size="md" animate={false} />
                <div className="stack grow" style={{ "--stack-gap": "14px" }}>
                  {EXAMPLE.parts.map(([label, s, max]) => (
                    <Meter key={label} label={label} value={`${s} / ${max}`} pct={(s / max) * 100} />
                  ))}
                </div>
              </div>
            </Feature>
            <Feature className="bento__b" icon={<User />} title="How it suits you"
                     body="Fit for each concern you chose and for your skin type — explained in plain sentences, not just a percentage.">
              <div className="stack" style={{ "--stack-gap": "14px" }}>
                <Meter label="Acne & oily skin" value="77 · good fit" pct={77} />
                <Meter label="Pigmentation" value="50 · moderate fit" pct={50} />
                <Meter label="Oily skin compatibility" value="97%" pct={97} />
              </div>
            </Feature>
            <Feature icon={<Tag />} title="Price per ml, in context"
                     body="What you actually pay per ml, next to the usual price for that product type in your country. Never mixed into the score.">
              <div className="stack" style={{ "--stack-gap": "14px" }}>
                <Meter label="This product" value={`${EXAMPLE.pricePerMl} / ml`} pct={62} tone="accent" />
                <Meter label="Typical serum, India" value={`${EXAMPLE.categoryAvg} / ml`} pct={64} tone="neutral" />
              </div>
            </Feature>
            <Feature icon={<TriangleAlert />} title="Clashes & pH"
                     body="Actives that work against each other in the same formula, and the likely pH from its buffers.">
              <div className="stack" style={{ "--stack-gap": "10px" }}>
                <Callout tone="positive" title="No clashes found">None of the actives work against each other.</Callout>
                <Callout tone="info" title="Estimated pH 3.5–5.0">In range for lactic acid.</Callout>
              </div>
            </Feature>
            <Feature icon={<GitCompare />} title="Compare side by side"
                     body="Up to six products on the same scale, with what each has that the others don’t.">
              <div className="vs">
                <div className="vs__item"><ScoreRing score={97} size="sm" animate={false} /><span className="t-caption c-secondary">Product A</span></div>
                <span className="t-display-xs c-tertiary">vs</span>
                <div className="vs__item"><ScoreRing score={71} size="sm" animate={false} /><span className="t-caption c-secondary">Product B</span></div>
              </div>
            </Feature>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------- Method */}
      <section className="method" id="method">
        <div className="container method__grid">
          <MethodCopy />
          <div className="evidence" aria-label="Sample ingredient evidence">
            <div className="evidence__head">
              <span className="t-label-s">Ingredient evidence · {EXAMPLE.name}</span>
              <span className="t-mono-s" style={{ color: "var(--text-inverse-secondary)" }}>17 ingredients · 4 actives</span>
            </div>
            <table className="evidence__table">
              <thead>
                <tr><th>#</th><th>Ingredient</th><th>Evidence</th><th>Amount</th></tr>
              </thead>
              <tbody>
                {EVIDENCE.map(([n, name, what, ev, tone, amt]) => (
                  <tr key={name}>
                    <td className="t-mono" style={{ color: "var(--text-inverse-secondary)" }}>{n}</td>
                    <td>
                      <span className="t-label-s">{name}</span>
                      <span className="t-caption" style={{ display: "block", color: "var(--text-inverse-secondary)" }}>{what}</span>
                    </td>
                    <td><span className={`ev ev--${tone}`}>{ev}</span></td>
                    <td className="t-mono">{amt}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="evidence__foot t-caption">Stated amounts come from the product page. Everything else is estimated from list position.</p>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------- Pricing */}
      <section className="section" id="pricing">
        <div className="container">
          <SectionHead eyebrow="Pricing" title="The score is free. Always."
                       lede="Pay only when you want a product matched to your own skin. Credits last a year." />
          <div className="plans">
            <Plan name="Score" price="Free" unit="for every product"
                  desc="A formulation score for every product you check."
                  features={[["Formulation score out of 100"], ["Ingredient evidence table"], ["Clashes and estimated pH"], ["Price per ml vs similar products"]]}
                  cta={<Button as="a" href={ANALYSE_PATH} onClick={linkTo(ANALYSE_PATH)} variant="secondary" block arrow>Analyse a product</Button>} />
            <Plan featured name="Sign in" price="4 credits" unit="free, first sign-in"
                  desc="Match products to your skin — your first 4 credits are on us."
                  features={[["How it suits you", "1 credit"], ["Compare products", "from 2 credits"], ["Saved products and comparisons"], ["Four extra questions for a sharper fit"]]}
                  cta={<Button variant="primary" block arrow onClick={() => openUnlock("signin")}>Sign in with email</Button>} />
            <Plan name="Credit packs" price="₹99" unit="from · 5 credits"
                  desc="Top up when you need to. Every pack includes the PDF report, and credits last a year."
                  features={[["5 credits — ₹99"], ["8 credits — ₹149"], ["12 credits — ₹199"], ["PDF report included"]]}
                  cta={<Button variant="secondary" block arrow onClick={() => openUnlock("credits")}>See packs</Button>} />
          </div>
          <p className="plans__note"><Lock aria-hidden="true" />UPI and cards via Razorpay.</p>
        </div>
      </section>

      {/* ------------------------------------------------------------- FAQ */}
      <section className="section section--surface" id="faq">
        <div className="container faq">
          <div className="faq__head">
            <span className="t-eyebrow c-accent">FAQ</span>
            <h2 className="t-display-m">Questions, answered plainly.</h2>
            <p className="t-body-m c-secondary">
              Something else? <a className="link" href="#feedback">Write to us</a> — a person reads every note.
            </p>
          </div>
          <Accordion items={FAQ} />
        </div>
      </section>

      <div className="ad-band">
        <AdSlot size={wide ? "leaderboard" : "rectangle"} slot={AD_SLOTS.landingBottom} />
      </div>

      {/* ------------------------------------------------------- Final CTA */}
      <section className="cta-band">
        <div className="container cta-band__inner">
          <h2 className="t-display-l">Know it’s worth it<br /><em>before</em> you buy it.</h2>
          <p className="t-body-l c-secondary">Paste the product you’re about to buy. If it isn’t worth it, we’ll tell you why — and what to look for instead.</p>
          <div className="cta-band__input">
            <SmartInput value={ctaValue} onChange={setCtaValue} onSubmit={() => start(ctaValue)} onEmpty={() => start("")}
                        id="cta-input" testId="cta-input" />
          </div>
        </div>
      </section>

      <SiteFooter />
    </div>
  );
}

/* ------------------------------------------------------------------ parts */

function SectionHead({ eyebrow, title, lede }) {
  return (
    <div className="section-head">
      <span className="t-eyebrow c-accent">{eyebrow}</span>
      <h2 className="t-display-m">{title}</h2>
      {lede && <p className="t-body-l c-secondary">{lede}</p>}
    </div>
  );
}

function Step({ n, title, body, children }) {
  return (
    <article className="step">
      <span className="t-display-s c-accent">{n}</span>
      <h3 className="t-heading-m">{title}</h3>
      <p className="t-body-m c-secondary">{body}</p>
      <div className="step__visual" aria-hidden="true">{children}</div>
    </article>
  );
}

function Feature({ icon, title, body, children, className }) {
  return (
    <article className={`feature ${className || ""}`}>
      <div className="feature__head">
        <span className="feature__icon" aria-hidden="true">{icon}</span>
        <h3 className="t-heading-m">{title}</h3>
      </div>
      <p className="t-body-m c-secondary">{body}</p>
      <div className="feature__visual" aria-hidden="true">{children}</div>
    </article>
  );
}

function MethodCopy() {
  const [cat, setCat] = useState("Serum");
  const parts = RUBRICS[cat];
  return (
    <div className="method__copy">
      <span className="t-eyebrow" style={{ color: "var(--text-inverse-accent)" }}>Method</span>
      <h2 className="t-display-m method__title">Scored on <em>evidence</em>, not on marketing.</h2>
      <p className="t-body-l" style={{ color: "var(--text-inverse-secondary)" }}>
        Each product is judged on what its category is for — a serum on its actives, a cleanser on how gently it
        cleans, a sunscreen on its filters. Every rubric adds up to 100, and price is never part of it.
      </p>
      <div className="seg" role="tablist" aria-label="Category rubric">
        {Object.keys(RUBRICS).map((k) => (
          <button key={k} role="tab" aria-selected={k === cat} className="seg__btn" onClick={() => setCat(k)}>{k}</button>
        ))}
      </div>
      <div className="compbar" aria-hidden="true">
        {parts.map(([label, w], i) => (
          <span key={label} style={{ flexGrow: w, background: RUBRIC_COLORS[i] }} />
        ))}
      </div>
      <ul className="legend">
        {parts.map(([label, w], i) => (
          <li key={label}>
            <span className="legend__dot" style={{ background: RUBRIC_COLORS[i] }} />
            <span className="grow">{label}</span>
            <span className="t-mono">{w} pts</span>
          </li>
        ))}
      </ul>
      <a className="method__link" href={ANALYSE_PATH} onClick={linkTo(ANALYSE_PATH)}>
        See it on your own product <ArrowRight aria-hidden="true" />
      </a>
    </div>
  );
}

function Plan({ name, price, unit, desc, features, cta, featured }) {
  return (
    <article className={`plan${featured ? " plan--featured" : ""}`}>
      <div className="row-between">
        <span className={`t-eyebrow ${featured ? "c-accent" : "c-tertiary"}`}>{name}</span>
        {featured && <Badge tone="accent">Most people start here</Badge>}
      </div>
      <p className="plan__price"><span className="t-display-m">{price}</span><span className="t-body-s c-tertiary">{unit}</span></p>
      <p className="t-body-m c-secondary">{desc}</p>
      <ul className="plan__features">
        {features.map(([f, meta]) => (
          <li key={f}><Check aria-hidden="true" /><span className="grow">{f}</span>{meta && <span className="t-mono-s c-tertiary">{meta}</span>}</li>
        ))}
      </ul>
      <div className="plan__cta">{cta}</div>
    </article>
  );
}

function Accordion({ items }) {
  const [open, setOpen] = useState(0);
  return (
    <div className="accordion">
      {items.map(([q, a], i) => {
        const isOpen = open === i;
        return (
          <div className="accordion__item" key={q}>
            <h3 style={{ margin: 0 }}>
              <button className="accordion__trigger" aria-expanded={isOpen} aria-controls={`faq-${i}`}
                      id={`faq-q-${i}`} onClick={() => setOpen(isOpen ? -1 : i)}>
                {q}<Plus aria-hidden="true" />
              </button>
            </h3>
            <div className="accordion__panel" data-open={isOpen} id={`faq-${i}`} role="region" aria-labelledby={`faq-q-${i}`}>
              <div><p>{a}</p></div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

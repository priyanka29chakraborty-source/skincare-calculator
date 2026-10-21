import React, { useEffect, useMemo, useState } from "react";
import { FileDown, GitCompare, Link as LinkIcon, Lock, PenLine, Plus } from "lucide-react";

import { AD_SLOTS } from "../constants";
import useMedia from "../lib/useMedia";
import { AdSlot, Badge, Button } from "./ds";
import {
  VerdictCard, StatsRow, Advisories, BreakdownCard, IngredientsCard, SunscreenCard, MethodNote,
} from "./ResultCards";
import { ValueCard } from "./FormulationCards";
import PersonaliseCard from "./PersonaliseCard";
import LockedCard from "./LockedCard";
import SuitabilityCard, { SuitabilityWaiting } from "./SuitabilityCard";
import PairingsCard from "./PairingsCard";
import AlternativesCard from "./AlternativesCard";
import BestPriceCard from "./BestPriceCard";

/**
 * The result page: one reading order, top to bottom.
 *
 *   Overview      verdict, supporting numbers, anything that must not be missed
 *   Ingredients   what is in it and how strong the evidence is
 *   Your fit      how it suits this person (paid; asks four questions)
 *   [ad]          between complete sections, never beside an action
 *   Routine       what to pair it with
 *   Value         price on its own, then where to buy it for less
 *   Alternatives  what would cover the gaps
 */
export default function ResultView(props) {
  const {
    result, account, productName, brand, category, price, size, sizeUnit, currency, skinType, concerns,
    alternatives, altLoading, bestPrice, bestPriceLoading, bestPriceError, onRetryBestPrice, productUrl,
    onUnlock, onBuyPack, onPdfSignIn, onSavePdf, pdfLocked, onEdit, onNew, onCompare, onShare,
    userProfile, onApplyPersonalisation, personalising, personaliseOpen, onOpenPersonalise, error,
  } = props;

  const wide = useMedia("(min-width: 1101px)");
  const tablet = useMedia("(min-width: 800px)");
  // The personal half of a result (fit, sunscreen detail, alternatives) uses a
  // credit, so it needs an account: locked when the server says so, and always
  // locked for someone who has not signed in.
  const signedIn = Boolean(account.signedIn);
  const personalLocked = result?.access?.tier === "free" || !signedIn;
  const hasAnswers = (result?.personalisation?.level || "none") !== "none";
  const sunscreen = result.skin_concern_fit?.["Sun Protection"]?.sunscreen_analysis;
  const lockedNote = signedIn ? "Locked means unknown — not bad. One credit covers this product for good."
    : "Your first 4 credits are free when you sign in.";

  const sections = useMemo(() => [
    ["overview", "Overview"],
    ["ingredients", "Ingredients"],
    ["fit", "Your fit"],
    ["value", "Value"],
    ["alternatives", "Alternatives"],
  ], []);

  const active = useScrollSpy(sections.map(([id]) => id));
  const unlockLabel = signedIn ? "Unlock with 1 credit" : "Sign in — get 4 free credits";
  const lockedConcerns = result.access?.preview?.concern_names || (concerns.length ? concerns : ["your chosen concerns"]);

  const actions = (
    <ResultActions pdfLocked={pdfLocked} signedIn={signedIn} onSavePdf={onSavePdf}
                   onPdfLocked={signedIn ? onBuyPack : onPdfSignIn}
                   onCompare={onCompare} onShare={onShare} compact={!wide} />
  );

  return (
    <>
      <nav className="result-tabs no-print" aria-label="Result sections">
        <div className="container result-tabs__inner">
          <div className="tabs">
            {sections.map(([id, label]) => (
              <button key={id} type="button" className="tab" aria-current={active === id ? "true" : undefined}
                      onClick={() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })}>
                {label}
              </button>
            ))}
          </div>
          <Button variant="secondary" size="sm" icon={<Plus />} onClick={onNew} className="hide-mobile">New analysis</Button>
        </div>
      </nav>

      <main className="container app-main" data-testid="results-section">
        <div className="result-grid">
          <div className="result-main">
            <section id="overview" className="result-section" aria-label="Overview">
              <VerdictCard result={result} productName={productName} brand={brand} category={category}
                           price={price} size={size} sizeUnit={sizeUnit} currency={currency} skinType={skinType} />
              {!wide && <div className="mobile-actions no-print">{actions}</div>}
              <StatsRow result={result} category={category} currency={currency} />
              <Advisories result={result} category={category} concerns={concerns} />
              <BreakdownCard result={result} />
            </section>

            <section id="ingredients" className="result-section" aria-label="Ingredients">
              <IngredientsCard result={result} category={category} />
              {!personalLocked && sunscreen && <SunscreenCard data={sunscreen} />}
            </section>

            <section id="fit" className="result-section" aria-label="Your fit">
              {personalLocked ? (
                <LockedCard
                  title="How this suits you" access={result.access} onUnlock={onUnlock} ctaLabel={unlockLabel}
                  message={result.access?.message || (signedIn ? null
                    : "Sign in to see how well this product treats your concerns, whether it suits your skin type, and what to watch out for.")}
                  note={lockedNote}
                  lines={[
                    ...lockedConcerns.map((c) => `How well it treats ${c}`),
                    `Whether it suits ${String(skinType || "your").toLowerCase()} skin`,
                    "Irritation and pore-clogging risk",
                  ]}
                />
              ) : (
                <>
                  <PersonaliseCard
                    profile={userProfile} onApply={onApplyPersonalisation} loading={personalising}
                    level={result.personalisation?.level || "none"} skinType={skinType}
                    personalisation={result.personalisation} locked={false}
                    opened={personaliseOpen} onUnlock={onUnlock} ctaLabel={unlockLabel}
                  />
                  {!hasAnswers && !personaliseOpen && (
                    <SuitabilityWaiting skinType={skinType} onAnswer={onOpenPersonalise} />
                  )}
                  {hasAnswers && <SuitabilityCard result={result} skinType={skinType} />}
                </>
              )}
              {error && <p className="t-body-s c-negative" role="alert">{error}</p>}
            </section>

            <div className="ad-gap">
              <AdSlot size="inarticle" slot={AD_SLOTS.resultInArticle} />
            </div>

            <PairingsCard pairings={result.pairs_well_with} />

            <section id="value" className="result-section" aria-label="Value">
              <ValueCard value={result.value_assessment} priceAnalysis={result.price_analysis}
                         currency={currency} category={category} />
              {personalLocked ? (
                <LockedCard
                  eyebrow="Where to buy" title="Best price we could find" testId="locked-best-price"
                  onUnlock={onUnlock} ctaLabel={unlockLabel} note={lockedNote}
                  message={signedIn
                    ? "The shop search is part of the personal analysis for this product."
                    : "Sign in to search other shops for this exact product, same brand and same size."}
                  lines={["Other shops selling this exact product", "The cheapest price we could find"]}
                />
              ) : (
                <BestPriceCard bestPrice={bestPrice} bestPriceLoading={bestPriceLoading}
                               bestPriceError={bestPriceError} onRetry={onRetryBestPrice}
                               currency={currency} productUrl={productUrl} />
              )}
            </section>

            <section id="alternatives" className="result-section" aria-label="Alternatives">
              {personalLocked ? (
                <LockedCard
                  eyebrow="Alternatives" title="Products that may suit you better" testId="locked-alternatives"
                  onUnlock={onUnlock} ctaLabel={unlockLabel} note={lockedNote}
                  message={signedIn
                    ? "Alternatives are part of the personal analysis for this product."
                    : "Sign in to see products that may cover your concerns better."}
                  lines={["Products scored on the same scale", "What each covers that this one doesn’t"]}
                />
              ) : (
                <AlternativesCard result={result} concerns={concerns} alternatives={alternatives}
                                  altLoading={altLoading} currency={currency} category={category} />
              )}
            </section>

            <MethodNote />

            {/* End of the result, after the method note - never next to a buy link. */}
            <div className="ad-gap">
              <AdSlot size={tablet ? "leaderboard" : "rectangle"} slot={AD_SLOTS.resultBottom} />
            </div>
          </div>

          {wide && (
            <aside className="result-rail no-print" aria-label="Actions">
              <div className="card rail-card">
                <div className="row-between">
                  <p className="t-eyebrow c-tertiary">Analysed for</p>
                  <button type="button" className="link" onClick={onEdit}><PenLine aria-hidden="true" />Edit</button>
                </div>
                <p className="t-heading-m">{skinType ? `${skinType} skin` : "No skin type"}</p>
                {concerns.length > 0 && (
                  <div className="row wrap">{concerns.map((c) => <Badge key={c} tone="accent">{c}</Badge>)}</div>
                )}
              </div>
              <div className="card rail-card">
                {actions}
                {signedIn && !account.owner && (
                  <p className="rail-balance">{account.balance} {account.balance === 1 ? "credit" : "credits"} left</p>
                )}
              </div>
            </aside>
          )}
        </div>
      </main>
    </>
  );
}

function ResultActions({ pdfLocked, signedIn, onSavePdf, onPdfLocked, onCompare, onShare, compact }) {
  if (compact) {
    return (
      <div className="result-actions result-actions--compact">
        <Button variant="primary" className="grow" icon={pdfLocked ? <Lock /> : <FileDown />}
                onClick={pdfLocked ? onPdfLocked : onSavePdf} data-testid="export-btn">
          Save as PDF
        </Button>
        <Button variant="secondary" className="btn--icon" icon={<GitCompare />} onClick={onCompare} aria-label="Compare with another product" />
        <Button variant="secondary" className="btn--icon" icon={<LinkIcon />} onClick={onShare} aria-label="Copy share link" />
      </div>
    );
  }
  return (
    <div className="result-actions">
      <Button variant="primary" block icon={pdfLocked ? <Lock /> : <FileDown />}
              onClick={pdfLocked ? onPdfLocked : onSavePdf} data-testid="export-btn">
        Save as PDF
      </Button>
      <Button variant="secondary" block icon={<GitCompare />} onClick={onCompare}>Compare with another</Button>
      <Button variant="ghost" block icon={<LinkIcon />} onClick={onShare}>Copy share link</Button>
      {pdfLocked && (
        <p className="t-caption c-tertiary result-actions__note">
          {signedIn
            ? "The PDF report comes with any credit pack. The 4 sign-in credits don’t include it."
            : "Sign in, then any credit pack includes the PDF report."}
        </p>
      )}
    </div>
  );
}

/** Which section is in view, for the sticky tabs. */
function useScrollSpy(ids) {
  const [active, setActive] = useState(ids[0]);
  useEffect(() => {
    const els = ids.map((id) => document.getElementById(id)).filter(Boolean);
    if (!els.length || !("IntersectionObserver" in window)) return undefined;
    const visible = new Map();
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => visible.set(e.target.id, e.isIntersecting ? e.intersectionRatio : 0));
      const top = ids.find((id) => (visible.get(id) || 0) > 0);
      if (top) setActive(top);
    }, { rootMargin: "-120px 0px -55% 0px", threshold: [0, 0.01] });
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids.join("|")]);
  return active;
}

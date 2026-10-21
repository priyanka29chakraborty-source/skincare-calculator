import React from "react";
import { ArrowUpRight, CircleCheck, Info, LoaderCircle, Plus } from "lucide-react";

import { money } from "../constants";
import AffiliateNotice from "./AffiliateNotice";
import { Badge, Callout, Card } from "./ds";

/**
 * What would cover the concerns this product leaves weak.
 *
 * It needs concern fit, which is paid and absent from a free response - so it
 * does not render without it, rather than claim "nothing to add" unseen.
 */
export default function AlternativesCard({ result, concerns, alternatives, altLoading, currency, category }) {
  if (result?.access?.tier === "free") return null;

  const concernFit = result.skin_concern_fit || {};
  const cat = (category || result.price_analysis?.category || "").toLowerCase();
  const isFacialOil = cat === "facial oil" || cat === "oil";
  const scoreOf = (v) => (typeof v === "object" ? v.score : v);

  const weak = Object.entries(concernFit).filter(([, v]) => scoreOf(v) < 75)
    .map(([k, v]) => `${k} (${scoreOf(v)}/100)`);
  const hasWeak = weak.length > 0 && concerns.length > 0;
  const allFit = concerns.length > 0 && concerns.every((c) => {
    const v = concernFit[c];
    return typeof v === "object" ? v.score >= 75 : typeof v === "number" && v >= 75;
  });
  const excellent = allFit && result.main_worth_score >= 75;

  const head = { eyebrow: "Alternatives", title: "Worth adding to your routine" };

  if (!hasWeak) {
    return (
      <Card {...head} data-testid="card-alternatives-great">
        {concerns.length === 0 ? (
          <Callout tone="neutral" title="No skin concerns chosen" data-testid="no-concerns-message">
            <p className="callout__text">Choose your concerns and we’ll suggest what would help alongside this.</p>
          </Callout>
        ) : (
          <Callout tone="positive" icon={CircleCheck} title="Nothing worth adding for these concerns"
                   data-testid={excellent ? "excellent-message" : "great-value-message"}>
            <p className="callout__text">
              {excellent
                ? `This ${isFacialOil ? "oil" : "product"} already covers everything you chose — ${result.main_worth_score}/100 overall, and every concern scores 75 or better.`
                : "Every concern you chose already scores 75 or better here."}
            </p>
          </Callout>
        )}
      </Card>
    );
  }

  const scored = alternatives?.scored_alternatives || [];
  const basic = alternatives?.basic_alternatives || [];

  return (
    <Card {...head} sub={`For ${weak.join(", ")}, a separate step can do more of that job. Use it with this product, not instead of it.`}
          data-testid="card-alternatives">
      {result.upgrade_suggestions?.length > 0 && (
        <div className="stack" style={{ "--stack-gap": "12px" }}>
          {result.upgrade_suggestions.map((sug, i) => (
            <div key={i} className="upgrade" data-testid={`upgrade-suggestion-${i}`}>
              <div className="row-between">
                <p className="t-heading-s row" style={{ "--row-gap": "8px" }}><Plus aria-hidden="true" className="c-accent" style={{ width: 16, height: 16 }} />Add: {sug.upgrade}</p>
                <Badge tone="accent">{sug.concern}</Badge>
              </div>
              <p className="t-body-s c-secondary">{sug.reason}</p>
              {sug.suggested_active && <p className="t-body-s c-secondary">Active to look for: <strong className="c-primary">{sug.suggested_active}</strong></p>}
              {sug.builds_on && <p className="t-body-s c-secondary">Steps up from the <strong className="c-primary">{sug.builds_on}</strong> already in your product.</p>}
              <p className="t-caption c-tertiary row" style={{ "--row-gap": "6px" }}><Info aria-hidden="true" style={{ width: 14, height: 14 }} />
                {isFacialOil ? `Use this alongside your oil for ${sug.concern} — not a replacement.` : `An addition for ${sug.concern}, not a replacement for what you have.`}
              </p>
            </div>
          ))}
        </div>
      )}

      {altLoading && (
        <p className="loading-line" data-testid="alt-loading"><LoaderCircle className="spin" aria-hidden="true" />Looking for products that cover these concerns…</p>
      )}

      {!altLoading && scored.length > 0 && (
        <>
          <p className="t-eyebrow c-tertiary list-label">Products to consider</p>
          <ul className="alt-list" data-testid="scored-alternatives-list">
            {scored.slice(0, 3).map((alt, i) => (
              <li key={i} className="alt" data-testid={`scored-alt-${i}`}>
                <div className="alt__main">
                  <p className="t-heading-s">{alt.name}</p>
                  <div className="row wrap" style={{ "--row-gap": "6px" }}>
                    <Badge>Score {alt.score}/100</Badge>
                    {alt.score_delta > 0 && <Badge tone="positive">+{alt.score_delta} pts</Badge>}
                    {alt.safety_score != null && <Badge>Safety {Math.round(alt.safety_score)}/10</Badge>}
                    {alt.concern_fit && Object.entries(alt.concern_fit).map(([c, pct]) => <Badge key={c} tone="accent">{c} {pct}%</Badge>)}
                  </div>
                  {alt.why_better?.length > 0 && <ul className="alt__why">{alt.why_better.map((r, j) => <li key={j}>{r}</li>)}</ul>}
                </div>
                <div className="alt__side">
                  {alt.price && <p className="t-display-xs">{money(currency, alt.price)}</p>}
                  {alt.link && (
                    <a href={alt.link} target="_blank" rel="noopener noreferrer sponsored" className="btn btn--secondary btn--sm"
                       data-testid={`scored-alt-link-${i}`}>
                      <span>{alt.source ? `View on ${alt.source}` : "View"}</span><ArrowUpRight aria-hidden="true" />
                    </a>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      {!altLoading && !scored.length && !basic.length && alternatives?.search_message && (
        <Callout tone="neutral" data-testid="alt-search-message"><p className="callout__text">{alternatives.search_message}</p></Callout>
      )}

      {!altLoading && basic.length > 0 && !scored.length && (
        <>
          <p className="t-eyebrow c-tertiary list-label">Products to consider</p>
          <div className="alt-grid" data-testid="basic-alternatives-list">
            {basic.map((alt, i) => (
              <a key={i} href={alt.link} target="_blank" rel="noopener noreferrer sponsored" className="alt-tile" data-testid={`alt-card-${i}`}>
                {alt.thumbnail && <img src={alt.thumbnail} alt="" className="alt-tile__img" loading="lazy" />}
                <span className="alt-tile__text">
                  <span className="t-label-s alt-tile__name">{alt.name}</span>
                  <span className="t-mono c-accent">{typeof alt.price === "number" ? money(currency, alt.price) : alt.price}</span>
                  <span className="t-caption c-tertiary row" style={{ "--row-gap": "4px" }}>{alt.source}<ArrowUpRight aria-hidden="true" style={{ width: 12, height: 12 }} /></span>
                </span>
              </a>
            ))}
          </div>
        </>
      )}
      <AffiliateNotice disclosure={alternatives?.affiliate_disclosure} />
    </Card>
  );
}

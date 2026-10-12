import { money } from "../constants";
import AffiliateNotice from "./AffiliateNotice";
export default function AlternativesCard({ result, concerns, alternatives, altLoading, currency, category }) {
  // Everything this card decides rests on concern fit, which is paid and is
  // absent from a free response. With it missing, weakConcerns came out empty
  // and the card fell through to its "nothing worth adding - every concern
  // already scores 75% or better" state: a confident positive claim made
  // without sight of a single score. Same shape as the locked compatibility
  // card that once rendered a red bar for an unknown value.
  //
  // So it does not render at all without the data. Free readers still get the
  // pairings card, which works from the product's own actives.
  if (result?.access?.tier === "free") return null;

  const concernFit = result.skin_concern_fit || {};
  const cat = (category || result.price_analysis?.category || '').toLowerCase();
  const isFacialOil = cat === 'facial oil' || cat === 'oil';

  const weakConcerns = Object.entries(concernFit)
    .filter(([, v]) => (typeof v === 'object' ? v.score : v) < 75)
    .map(([k, v]) => {
      const score = typeof v === 'object' ? v.score : v;
      return `${k} (${score}/100)`;
    });
  const hasWeakConcerns = weakConcerns.length > 0 && concerns.length > 0;

  const allConcernsFit = concerns.length > 0 && concerns.every(c => {
    const v = concernFit[c];
    return typeof v === 'object' ? (v.score >= 75) : (typeof v === 'number' && v >= 75);
  });
  const isExcellent = allConcernsFit && (result.main_worth_score >= 75);

  // ── Card title changes for facial oils ──────────────────────────────────────
  // One title for both. The search is not category-locked, so what comes
  // back is a mix of formats to add alongside this product - which is what
  // the card body always said, while the old title ("Better Alternatives")
  // promised a replacement.
  const cardTitle = 'Worth adding to your routine';
  const cardIcon = 'fa-solid fa-layer-group';

  // ── Upgrade suggestion label: oils get "Complement" not "Add-On" ────────────
  const upgradeLabel = 'Add:';
  if (!hasWeakConcerns) return (
    <div className="sc-card result-card card-4" data-testid="card-alternatives-great" style={{ "--anim-delay": "0.45s" }}>
      <h2 className="card-title"><i className={cardIcon}></i> {cardTitle}</h2>
      {concerns.length === 0 ? (
        <div className="great-value-badge" data-testid="no-concerns-message" style={{ background: '#f8f8f4', borderColor: '#d4cfc8' }}>
          <i className="fa-solid fa-info-circle" style={{ color: '#8B7E74' }}></i>
          <div>
            <strong style={{ color: '#2C2420' }}>No skin concerns selected</strong>
            <p style={{ color: '#8B7E74' }}>Select your skin concerns above to see what would help alongside this.</p>
          </div>
        </div>
      ) : isExcellent ? (
        <div className="great-value-badge" data-testid="excellent-message">
          <i className="fa-solid fa-trophy" style={{ color: '#C9A84C' }}></i>
          <div>
            <strong>Nothing worth adding for these concerns</strong>
            <p>
              This {isFacialOil ? 'oil' : 'product'} already covers everything
              you selected &mdash; {result.main_worth_score}/100 overall, and
              every concern scores 75% or better.
            </p>
          </div>
        </div>
      ) : (
        <div className="great-value-badge" data-testid="great-value-message">
          <i className="fa-solid fa-circle-check"></i>
          <div>
            <strong>Nothing worth adding for these concerns</strong>
            <p>Every concern you selected already scores 75% or better here.</p>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="sc-card result-card card-4" data-testid="card-alternatives" style={{ "--anim-delay": "0.45s" }}>
      <h2 className="card-title"><i className={cardIcon}></i> {cardTitle}</h2>
      <div className="alt-concern-msg" data-testid="weak-concerns-msg">
        For <strong>{weakConcerns.join(', ')}</strong>, a separate step can do
        more of that job. Use it with this product, not instead of it.
      </div>

      {result.upgrade_suggestions?.map((sug, i) => (
        <div key={i} className="upgrade-box" data-testid={`upgrade-suggestion-${i}`}>
          <div className="upgrade-header">
            <i className="fa-solid fa-plus-circle"></i>
            <span className="upgrade-name">{upgradeLabel} {sug.upgrade}</span>
            <span className="upgrade-concern-tag">{sug.concern}</span>
          </div>
          <div className="upgrade-body">
            <p className="upgrade-why-title">Why It Helps:</p>
            <ul className="upgrade-reasons">
              <li>{sug.reason}</li>
              {/* Two different ingredients, and the card used to print the
                  wrong one under "Key active ingredient": the CSV's `active`
                  was what your product already has, not what is being
                  suggested, so "Add-On: Adapalene / Key active ingredient:
                  Niacinamide" was the result. */}
              {sug.suggested_active && (
                <li>Active to look for: <strong>{sug.suggested_active}</strong></li>
              )}
              {sug.builds_on && (
                <li>
                  Steps up from the <strong>{sug.builds_on}</strong> already in
                  your product
                </li>
              )}
            </ul>
            <p style={{ fontSize: "0.74rem", color: "var(--text-sub)", marginTop: "6px", fontStyle: "italic" }}>
              <i className="fa-solid fa-circle-info" style={{ marginRight: "4px" }}></i>
              {isFacialOil
                ? `Use this alongside your oil for ${sug.concern} — not a replacement.`
                : `An addition for ${sug.concern}, not a replacement for what you have.`}
            </p>
          </div>
        </div>
      ))}

      {altLoading && (
        <div className="alt-loading" data-testid="alt-loading"><i className="fa-solid fa-spinner fa-spin"></i> Searching for products that cover these concerns...</div>
      )}

      {!altLoading && alternatives?.scored_alternatives?.length > 0 && (
        <>
          <div className="alt-section-label">Products to consider</div>
          <div className="scored-alt-list" data-testid="scored-alternatives-list">
            {alternatives.scored_alternatives.slice(0, 3).map((alt, i) => (
              <div key={i} className="scored-alt-card" data-testid={`scored-alt-${i}`}>
                <div className="scored-alt-header">
                  <span className="scored-alt-name">{alt.name}</span>
                  {alt.score_delta > 0 && (
                    <span className="scored-alt-badge" style={{ fontSize: "0.72rem", padding: "2px 8px" }}>+{alt.score_delta} pts</span>
                  )}
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", margin: "8px 0" }}>
                  <span style={{ fontSize: "0.75rem", background: "#F9F6FE", border: "1px solid #e2d9f3", borderRadius: "8px", padding: "3px 8px", color: "#5a4478" }}>
                    Worth: {alt.score}/100
                  </span>
                  {alt.safety_score != null && (
                    <span style={{ fontSize: "0.75rem", background: "#F0FAF0", border: "1px solid #b6ddb6", borderRadius: "8px", padding: "3px 8px", color: "#2d6e2d" }}>
                      Safety: {Math.round(alt.safety_score)}/10
                    </span>
                  )}
                  {alt.concern_fit && Object.entries(alt.concern_fit).map(([c, pct]) => (
                    <span key={c} style={{ fontSize: "0.75rem", background: "#FFF8F0", border: "1px solid #f0d8b0", borderRadius: "8px", padding: "3px 8px", color: "#7a5c2e" }}>
                      {c}: {pct}%
                    </span>
                  ))}
                </div>
                {alt.why_better?.length > 0 && (
                  <ul className="scored-alt-reasons" style={{ margin: "6px 0", paddingLeft: "16px" }}>
                    {alt.why_better.map((r, j) => <li key={j} style={{ fontSize: "0.78rem", marginBottom: "3px" }}>{r}</li>)}
                  </ul>
                )}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "8px", flexWrap: "wrap", gap: "8px" }}>
                  {alt.price && <div className="scored-alt-price" style={{ fontSize: "0.85rem", fontWeight: 600 }}>{money(currency, alt.price)}</div>}
                  {alt.link && (
                    <a href={alt.link} target="_blank" rel="noopener noreferrer" className="scored-alt-link buy-here-link" data-testid={`scored-alt-link-${i}`} style={{ fontSize: "0.78rem" }}>
                      <i className="fa-solid fa-store" style={{ marginRight: "4px" }}></i>
                      Shop on {alt.source || 'Retailer'} <i className="fa-solid fa-arrow-up-right-from-square" style={{ fontSize: "0.65rem" }}></i>
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {!altLoading && !alternatives?.scored_alternatives?.length && !alternatives?.basic_alternatives?.length && alternatives?.search_message && (
        <p className="alt-empty" data-testid="alt-search-message">{alternatives.search_message}</p>
      )}

      {!altLoading && alternatives?.basic_alternatives?.length > 0 && !alternatives?.scored_alternatives?.length && (
        <>
          <div className="alt-section-label">Products to consider</div>
          <div className="alt-grid" data-testid="basic-alternatives-list">
            {alternatives.basic_alternatives.map((alt, i) => (
              <a key={i} href={alt.link} target="_blank" rel="noopener noreferrer" className="alt-card" data-testid={`alt-card-${i}`}>
                {alt.thumbnail && <img src={alt.thumbnail} alt="" className="alt-thumb" />}
                <div className="alt-info">
                  <span className="alt-name">{alt.name}</span>
                  <span className="alt-price">{typeof alt.price === 'number' ? money(currency, alt.price) : alt.price}</span>
                  <span className="alt-source">{alt.source} <i className="fa-solid fa-arrow-up-right-from-square" style={{ fontSize: "0.6rem" }}></i></span>
                </div>
              </a>
            ))}
          </div>
        </>
      )}
      <AffiliateNotice disclosure={alternatives?.affiliate_disclosure} />
    </div>
  );
}

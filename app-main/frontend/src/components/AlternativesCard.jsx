export default function AlternativesCard({ result, concerns, alternatives, altLoading, currency }) {
  const concernFit = result.skin_concern_fit || {};
  const weakConcerns = Object.entries(concernFit)
    .filter(([, v]) => (typeof v === 'object' ? v.score : v) < 75)
    .map(([k]) => k);
  const hasWeakConcerns = weakConcerns.length > 0 && concerns.length > 0;

  // "Excellent" = worth score >= 75 AND all concern fits >= 75
  const allConcernsFit = concerns.length > 0 && concerns.every(c => {
    const v = concernFit[c];
    return typeof v === 'object' ? (v.score >= 75) : (typeof v === 'number' && v >= 75);
  });
  const isExcellent = allConcernsFit && (result.main_worth_score >= 75);

  if (!hasWeakConcerns) return (
    <div className="sc-card result-card card-4" data-testid="card-alternatives-great" style={{ "--anim-delay": "0.45s" }}>
      <h2 className="card-title"><i className="fa-solid fa-arrow-up-right-dots"></i> Better Alternatives</h2>
      {concerns.length === 0 ? (
        <div className="great-value-badge" data-testid="no-concerns-message" style={{ background: '#f8f8f4', borderColor: '#d4cfc8' }}>
          <i className="fa-solid fa-info-circle" style={{ color: '#8B7E74' }}></i>
          <div>
            <strong style={{ color: '#2C2420' }}>No skin concerns selected</strong>
            <p style={{ color: '#8B7E74' }}>Select your skin concerns above to see personalized alternatives.</p>
          </div>
        </div>
      ) : isExcellent ? (
        <div className="great-value-badge" data-testid="excellent-message">
          <i className="fa-solid fa-trophy" style={{ color: '#C9A84C' }}></i>
          <div>
            <strong>Your product is already excellent for your concerns!</strong>
            <p>Worth score {result.main_worth_score}/100 and all concern fits are 75%+. No better alternative needed.</p>
          </div>
        </div>
      ) : (
        <div className="great-value-badge" data-testid="great-value-message">
          <i className="fa-solid fa-circle-check"></i>
          <div>
            <strong>Your product targets your concerns effectively!</strong>
            <p>All concern fit scores are 75% or above. No need to look for alternatives.</p>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="sc-card result-card card-4" data-testid="card-alternatives" style={{ "--anim-delay": "0.45s" }}>
      <h2 className="card-title"><i className="fa-solid fa-arrow-up-right-dots"></i> Better Alternatives</h2>
      <div className="alt-concern-msg" data-testid="weak-concerns-msg">
        Better options found for <strong>{weakConcerns.join(', ')}</strong> — products that target {weakConcerns.length === 1 ? 'this concern' : 'these concerns'} more effectively
      </div>

      {result.upgrade_suggestions?.map((sug, i) => (
        <div key={i} className="upgrade-box" data-testid={`upgrade-suggestion-${i}`}>
          <div className="upgrade-header">
            <i className="fa-solid fa-arrow-trend-up"></i>
            <span className="upgrade-name">Add-On: {sug.upgrade}</span>
            <span className="upgrade-concern-tag">{sug.concern}</span>
          </div>
          <div className="upgrade-body">
            <p className="upgrade-why-title">Why It Helps:</p>
            <ul className="upgrade-reasons">
              <li>{sug.reason}</li>
              {sug.active && <li>Key active ingredient: <strong>{sug.active}</strong></li>}
            </ul>
            <p style={{ fontSize: "0.74rem", color: "var(--text-sub)", marginTop: "6px", fontStyle: "italic" }}>
              <i className="fa-solid fa-circle-info" style={{ marginRight: "4px" }}></i>
              Consider as an add-on serum for {sug.concern}, not a replacement for your current product.
            </p>
          </div>
        </div>
      ))}

      {altLoading && (
        <div className="alt-loading" data-testid="alt-loading"><i className="fa-solid fa-spinner fa-spin"></i> Searching &amp; analyzing alternatives...</div>
      )}

      {!altLoading && alternatives?.scored_alternatives?.length > 0 && (
        <>
          <div className="alt-section-label">Alternatives</div>
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
                  {alt.skin_type_score != null && (
                    <span style={{ fontSize: "0.75rem", background: "#FFF4F4", border: "1px solid #f0c8c8", borderRadius: "8px", padding: "3px 8px", color: "#8b4444" }}>
                      Skin Compat: {Math.round(alt.skin_type_score)}%
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
                  {alt.price && <div className="scored-alt-price" style={{ fontSize: "0.85rem", fontWeight: 600 }}>{currency} {alt.price}</div>}
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

      {!altLoading && alternatives?.basic_alternatives?.length > 0 && !alternatives?.scored_alternatives?.length && (
        <>
          <div className="alt-section-label">Found Alternatives:</div>
          <div className="alt-grid" data-testid="basic-alternatives-list">
            {alternatives.basic_alternatives.map((alt, i) => (
              <a key={i} href={alt.link} target="_blank" rel="noopener noreferrer" className="alt-card" data-testid={`alt-card-${i}`}>
                {alt.thumbnail && <img src={alt.thumbnail} alt="" className="alt-thumb" />}
                <div className="alt-info">
                  <span className="alt-name">{alt.name}</span>
                  <span className="alt-price">{typeof alt.price === 'number' ? `${currency} ${alt.price}` : alt.price}</span>
                  <span className="alt-source">{alt.source} <i className="fa-solid fa-arrow-up-right-from-square" style={{ fontSize: "0.6rem" }}></i></span>
                </div>
              </a>
            ))}
          </div>
        </>
      )}


    </div>
  );
}

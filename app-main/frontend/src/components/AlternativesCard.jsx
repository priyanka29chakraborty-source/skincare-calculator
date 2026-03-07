export default function AlternativesCard({ result, concerns, alternatives, altLoading, currency }) {
  const concernFit = result.skin_concern_fit || {};
  const weakConcerns = Object.entries(concernFit)
    .filter(([, v]) => (typeof v === 'object' ? v.score : v) < 75)
    .map(([k]) => k);
  const hasWeakConcerns = weakConcerns.length > 0 && concerns.length > 0;

  if (!hasWeakConcerns) return (
    <div className="sc-card result-card card-4" data-testid="card-alternatives-great" style={{ "--anim-delay": "0.45s" }}>
      <h2 className="card-title"><i className="fa-solid fa-arrow-up-right-dots"></i> Better Alternatives</h2>
      {concerns.length > 0 ? (
        <div className="great-value-badge" data-testid="great-value-message">
          <i className="fa-solid fa-circle-check"></i>
          <div>
            <strong>Your product targets your concerns effectively!</strong>
            <p>All concern fit scores are 75% or above. No need to look for alternatives.</p>
          </div>
        </div>
      ) : (
        <div className="great-value-badge" data-testid="no-concerns-message" style={{ background: '#f8f8f4', borderColor: '#d4cfc8' }}>
          <i className="fa-solid fa-info-circle" style={{ color: '#8B7E74' }}></i>
          <div>
            <strong style={{ color: '#2C2420' }}>No skin concerns selected</strong>
            <p style={{ color: '#8B7E74' }}>Select your skin concerns above to see personalized alternatives.</p>
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
            <span className="upgrade-name">Upgrade Option: {sug.upgrade}</span>
            <span className="upgrade-concern-tag">{sug.concern}</span>
          </div>
          <div className="upgrade-body">
            <p className="upgrade-why-title">Why Better:</p>
            <ul className="upgrade-reasons">
              <li>{sug.reason}</li>
              {sug.active && <li>Key active: {sug.active}</li>}
            </ul>
          </div>
        </div>
      ))}

      {altLoading && (
        <div className="alt-loading" data-testid="alt-loading"><i className="fa-solid fa-spinner fa-spin"></i> Searching &amp; analyzing alternatives...</div>
      )}

      {!altLoading && alternatives?.scored_alternatives?.length > 0 && (
        <>
          <div className="alt-section-label">Verified Alternatives (Fully Analyzed):</div>
          <div className="scored-alt-list" data-testid="scored-alternatives-list">
            {alternatives.scored_alternatives.map((alt, i) => (
              <div key={i} className="scored-alt-card" data-testid={`scored-alt-${i}`}>
                <div className="scored-alt-header">
                  <span className="scored-alt-name">{alt.name}</span>
                  {alt.score_delta > 0 && <span className="scored-alt-badge">+{alt.score_delta} pts</span>}
                </div>
                <div className="scored-alt-scores">
                  <div className="scored-alt-metric">
                    <span className="scored-alt-label">Worth</span>
                    <span className="scored-alt-value">{alt.worth_score}/100</span>
                  </div>
                  {alt.concern_scores && Object.entries(alt.concern_scores).map(([concern, score]) => (
                    <div key={concern} className="scored-alt-metric">
                      <span className="scored-alt-label">{concern}</span>
                      <span className="scored-alt-value">{score}%</span>
                    </div>
                  ))}
                  {alt.skin_type_score && (
                    <div className="scored-alt-metric">
                      <span className="scored-alt-label">Skin Fit</span>
                      <span className="scored-alt-value">{alt.skin_type_score}%</span>
                    </div>
                  )}
                </div>
                {alt.why_better?.length > 0 && (
                  <ul className="scored-alt-reasons">{alt.why_better.map((r, j) => <li key={j}>{r}</li>)}</ul>
                )}
                {alt.price && <div className="scored-alt-price">{currency} {alt.price}</div>}
                {alt.link && !alt.link.includes('google.com') && (
                  <div className="scored-alt-links">
                    <a href={alt.link} target="_blank" rel="noopener noreferrer" className="scored-alt-link" data-testid={`scored-alt-link-${i}-0`}>
                      <i className="fa-solid fa-store"></i> Buy on {alt.source || new URL(alt.link).hostname.replace('www.', '')} <i className="fa-solid fa-arrow-up-right-from-square"></i>
                    </a>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {!altLoading && alternatives?.basic_alternatives?.length > 0 && !alternatives?.scored_alternatives?.length && (
        <>
          <div className="alt-section-label">Found Alternatives:</div>
          <div className="alt-grid" data-testid="basic-alternatives-list">
            {alternatives.basic_alternatives
              .filter(alt => alt.link && !alt.link.includes('google.com'))
              .map((alt, i) => (
              <a key={i} href={alt.link} target="_blank" rel="noopener noreferrer" className="alt-card" data-testid={`alt-card-${i}`}>
                {alt.thumbnail && <img src={alt.thumbnail} alt="" className="alt-thumb" />}
                <div className="alt-info">
                  <span className="alt-name">{alt.name}</span>
                  <span className="alt-price">{typeof alt.price === 'number' ? `${currency} ${alt.price}` : alt.price}</span>
                  <span className="alt-source"><i className="fa-solid fa-store"></i> {alt.source} <i className="fa-solid fa-arrow-up-right-from-square" style={{ fontSize: "0.6rem" }}></i></span>
                </div>
              </a>
            ))}
          </div>
        </>
      )}

      {!altLoading && !alternatives?.scored_alternatives?.length && !alternatives?.basic_alternatives?.length && result.upgrade_suggestions?.length > 0 && (
        <p className="alt-empty">Search for the upgrade ingredients above on your preferred shopping site for best results.</p>
      )}
    </div>
  );
}

export default function BestPriceCard({ bestPrice, bestPriceLoading, currency, fetchInput }) {
  const allPrices = (bestPrice?.all_prices || []).slice(0, 2);

  return (
    <div className="sc-card result-card card-best-price" data-testid="card-best-price" style={{ "--anim-delay": "0.6s" }}>
      <h2 className="card-title"><i className="fa-solid fa-tags"></i> Best Price Available</h2>
      <p className="best-price-subtitle">
        <i className="fa-solid fa-circle-info"></i> Searching for the same product (same brand, size &amp; category) across shopping sites in your country
      </p>

      {bestPriceLoading && (
        <div className="alt-loading"><i className="fa-solid fa-spinner fa-spin"></i> Searching for best prices...</div>
      )}

      {!bestPriceLoading && bestPrice?.is_user_cheapest && (
        <div className="best-price-badge user-cheapest" data-testid="user-cheapest-badge">
          <i className="fa-solid fa-check-circle"></i>
          <div>
            <strong>Best Price!</strong> You are already looking at the cheapest available option for this product.
            {(bestPrice.user_url || (fetchInput?.trim().startsWith('http') && fetchInput?.trim())) && (
              <a href={bestPrice.user_url || fetchInput?.trim()} target="_blank" rel="noopener noreferrer" className="buy-here-link" data-testid="buy-here-link">
                Buy Here <i className="fa-solid fa-arrow-up-right-from-square"></i>
              </a>
            )}
          </div>
        </div>
      )}

      {!bestPriceLoading && !bestPrice?.is_user_cheapest && bestPrice?.best_price && (
        <div className="best-price-badge better-found" data-testid="better-price-badge">
          <i className="fa-solid fa-piggy-bank"></i>
          <div>
            <strong>Better Price Found on {bestPrice.best_price.source}!</strong>
            {' '}{currency} {bestPrice.best_price.price}
            {bestPrice.savings > 0 && <span className="savings-tag"> (Save {currency} {bestPrice.savings})</span>}
            {bestPrice.best_price.link && (
              <a href={bestPrice.best_price.link} target="_blank" rel="noopener noreferrer" className="buy-here-link">
                View &amp; Buy <i className="fa-solid fa-arrow-up-right-from-square"></i>
              </a>
            )}
          </div>
        </div>
      )}

      {!bestPriceLoading && allPrices.length > 0 && (
        <div className="price-comparison-list" data-testid="price-comparison-list">
          <div className="alt-section-label">Price Comparison (up to 2 sources):</div>
          {allPrices.map((item, i) => (
            item.link ? (
              <a key={i} href={item.link} target="_blank" rel="noopener noreferrer"
                className={`best-price-row ${i === 0 && !bestPrice.is_user_cheapest ? "cheapest" : ""}`}
                data-testid={`best-price-${i}`}>
                {item.thumbnail && <img src={item.thumbnail} alt="" className="bp-thumb" />}
                <div className="bp-info">
                  <span className="bp-name">{item.name}</span>
                  <span className="bp-source"><i className="fa-solid fa-store"></i> {item.source}</span>
                </div>
                <div className="bp-price-col">
                  <span className="bp-price">{currency} {item.price}</span>
                  {i === 0 && !bestPrice.is_user_cheapest && <span className="bp-cheapest-tag">Cheapest</span>}
                </div>
                <i className="fa-solid fa-arrow-up-right-from-square bp-link-icon"></i>
              </a>
            ) : (
              <div key={i} className={`best-price-row no-link ${i === 0 && !bestPrice.is_user_cheapest ? "cheapest" : ""}`} data-testid={`best-price-${i}`}>
                {item.thumbnail && <img src={item.thumbnail} alt="" className="bp-thumb" />}
                <div className="bp-info">
                  <span className="bp-name">{item.name}</span>
                  <span className="bp-source"><i className="fa-solid fa-store"></i> {item.source}</span>
                </div>
                <div className="bp-price-col">
                  <span className="bp-price">{currency} {item.price}</span>
                  {i === 0 && !bestPrice.is_user_cheapest && <span className="bp-cheapest-tag">Cheapest</span>}
                </div>
              </div>
            )
          ))}
        </div>
      )}

      {!bestPriceLoading && !allPrices.length && !bestPrice?.is_user_cheapest && (
        <p className="alt-empty">No other verified listings found for this exact product.</p>
      )}
    </div>
  );
}

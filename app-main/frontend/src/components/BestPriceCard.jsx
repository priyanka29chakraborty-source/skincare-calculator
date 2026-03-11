export default function BestPriceCard({ bestPrice, bestPriceLoading, currency, fetchInput }) {
  return (
    <div className="sc-card result-card card-best-price" data-testid="card-best-price" style={{ "--anim-delay": "0.6s" }}>
      <h2 className="card-title"><i className="fa-solid fa-tags"></i> Best Price Available</h2>

      {bestPriceLoading && (
        <div className="alt-loading"><i className="fa-solid fa-spinner fa-spin"></i> Searching for the best price...</div>
      )}

      {!bestPriceLoading && bestPrice?.is_user_cheapest && (
        <div className="best-price-badge user-cheapest" data-testid="user-cheapest-badge">
          <i className="fa-solid fa-check-circle"></i>
          <div>
            <strong>You're already at the best price!</strong> No cheaper listing found for this exact product.
            {(bestPrice.user_url || (fetchInput?.trim().startsWith('http') && fetchInput?.trim())) && (
              <div style={{ marginTop: "8px" }}>
                <a href={bestPrice.user_url || fetchInput.trim()} target="_blank" rel="noopener noreferrer" className="buy-here-link" data-testid="buy-here-link">
                  <i className="fa-solid fa-store" style={{ marginRight: "5px" }}></i>
                  Buy Here <i className="fa-solid fa-arrow-up-right-from-square"></i>
                </a>
              </div>
            )}
          </div>
        </div>
      )}

      {!bestPriceLoading && !bestPrice?.is_user_cheapest && bestPrice?.best_price && (
        <div className="best-price-badge better-found" data-testid="better-price-badge">
          <i className="fa-solid fa-piggy-bank"></i>
          <div>
            <strong>Better price found on {bestPrice.best_price.source}!</strong>
            {" "}{currency} {bestPrice.best_price.price}
            {bestPrice.savings > 0 && (
              <span className="savings-tag"> (Save {currency} {bestPrice.savings})</span>
            )}
            {bestPrice.best_price.link && (
              <div style={{ marginTop: "8px" }}>
                <a href={bestPrice.best_price.link} target="_blank" rel="noopener noreferrer" className="buy-here-link">
                  <i className="fa-solid fa-store" style={{ marginRight: "5px" }}></i>
                  View &amp; Buy on {bestPrice.best_price.source} <i className="fa-solid fa-arrow-up-right-from-square"></i>
                </a>
              </div>
            )}
          </div>
        </div>
      )}

      {!bestPriceLoading && !bestPrice?.best_price && !bestPrice?.is_user_cheapest && (
        <p className="alt-empty">No other verified listings found for this product.</p>
      )}
    </div>
  );
}

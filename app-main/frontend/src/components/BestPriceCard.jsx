export default function BestPriceCard({ bestPrice, bestPriceLoading, currency, fetchInput }) {
  const userUrl = bestPrice?.user_url || (fetchInput?.trim().startsWith('http') ? fetchInput.trim() : null);

  function displaySource(source) {
    if (!source) return "Unknown";
    return source
      .replace(/^www\./, "")
      .replace(/\.(com\.au|co\.uk|co\.kr|co\.jp|com\.br|com\.sg|ae|sg|fr|de|ca|in|com)$/, "")
      .split(".")[0]
      .replace(/^\w/, c => c.toUpperCase());
  }

  const allPrices = bestPrice?.all_prices || [];
  const cheapestPrice = allPrices.length > 0 ? parseFloat(allPrices[0].price) : null;

  return (
    <div className="sc-card result-card card-best-price" data-testid="card-best-price" style={{ "--anim-delay": "0.6s" }}>
      <h2 className="card-title">
        <i className="fa-solid fa-tags"></i> Best Price Available
      </h2>

      {bestPriceLoading && (
        <div className="alt-loading">
          <i className="fa-solid fa-spinner fa-spin"></i> Searching for the best price...
        </div>
      )}

      {/* ── Case 1: User already has cheapest ── */}
      {!bestPriceLoading && bestPrice?.is_user_cheapest && (
        <div style={{ marginBottom: allPrices.length > 0 ? "1rem" : 0 }}>
          <div className="best-price-badge user-cheapest" data-testid="user-cheapest-badge">
            <i className="fa-solid fa-circle-check" style={{ color: "#267C36", fontSize: "1.1rem" }}></i>
            <div>
              <strong style={{ color: "#267C36" }}>✅ Best price available</strong>
              <p style={{ fontSize: "0.8rem", color: "var(--text-sub)", margin: "2px 0 8px" }}>
                No cheaper listing found for this exact product.
              </p>
              {userUrl && (
                <a href={userUrl} target="_blank" rel="noopener noreferrer" className="buy-here-link" data-testid="buy-here-link">
                  <i className="fa-solid fa-store" style={{ marginRight: "5px" }}></i>
                  Buy Here <i className="fa-solid fa-arrow-up-right-from-square"></i>
                </a>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Case 2: Cheaper found — saving banner ── */}
      {!bestPriceLoading && !bestPrice?.is_user_cheapest && bestPrice?.best_price && (
        <div className="best-price-badge better-found" style={{ marginBottom: "1rem" }} data-testid="better-price-badge">
          <i className="fa-solid fa-piggy-bank" style={{ color: "#267C36", fontSize: "1.1rem" }}></i>
          <div>
            <strong>Better price found on {displaySource(bestPrice.best_price.source)}!</strong>
            {" "}{currency} {bestPrice.best_price.price}
            {bestPrice.savings > 0 && (
              <span className="savings-tag"> — Save {currency} {bestPrice.savings}</span>
            )}
            {bestPrice.best_price.link && (
              <div style={{ marginTop: "8px" }}>
                <a href={bestPrice.best_price.link} target="_blank" rel="noopener noreferrer" className="buy-here-link">
                  <i className="fa-solid fa-store" style={{ marginRight: "5px" }}></i>
                  View &amp; Buy on {displaySource(bestPrice.best_price.source)}{" "}
                  <i className="fa-solid fa-arrow-up-right-from-square"></i>
                </a>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Case 3: Not found anywhere ── */}
      {!bestPriceLoading && bestPrice?.not_found && (
        <div style={{ marginBottom: "0.5rem" }}>
          {userUrl ? (
            <div className="best-price-badge user-cheapest" data-testid="not-found-with-url">
              <i className="fa-solid fa-circle-info" style={{ color: "var(--text-sub)", fontSize: "1rem" }}></i>
              <div>
                <strong style={{ color: "var(--charcoal)" }}>No other listings found for this product</strong>
                <p style={{ fontSize: "0.8rem", color: "var(--text-sub)", margin: "2px 0 8px" }}>
                  Use the original source to purchase.
                </p>
                <a href={userUrl} target="_blank" rel="noopener noreferrer" className="buy-here-link">
                  <i className="fa-solid fa-store" style={{ marginRight: "5px" }}></i>
                  Buy Here <i className="fa-solid fa-arrow-up-right-from-square"></i>
                </a>
              </div>
            </div>
          ) : (
            <p className="alt-empty" data-testid="not-found-message">
              No other listings found for this product.
            </p>
          )}
        </div>
      )}

      {/* ── Fallback: no data at all ── */}
      {!bestPriceLoading && !bestPrice && (
        <p className="alt-empty">No other listings found for this product.</p>
      )}

      {/* ── Price Table: Platform | Price | Action (up to 3 rows) ── */}
      {!bestPriceLoading && allPrices.length > 0 && (
        <div style={{ marginTop: "0.5rem", overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
            <thead>
              <tr style={{ background: "var(--bg-deep)", borderBottom: "2px solid var(--border)" }}>
                <th style={{ padding: "7px 10px", textAlign: "left", fontWeight: 700, color: "var(--text-sub)", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.4px" }}>
                  Platform
                </th>
                <th style={{ padding: "7px 10px", textAlign: "right", fontWeight: 700, color: "var(--text-sub)", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.4px" }}>
                  Price ({currency})
                </th>
                <th style={{ padding: "7px 10px", textAlign: "center", fontWeight: 700, color: "var(--text-sub)", fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.4px" }}>
                  Action
                </th>
              </tr>
            </thead>
            <tbody>
              {allPrices.map((item, idx) => {
                const isCheapest = cheapestPrice !== null && parseFloat(item.price) === cheapestPrice;
                const saving = item.savings > 0 ? item.savings : null;
                return (
                  <tr
                    key={idx}
                    style={{
                      background: isCheapest ? "rgba(38, 124, 54, 0.07)" : idx % 2 === 0 ? "transparent" : "rgba(0,0,0,0.015)",
                      borderBottom: "1px solid var(--border)",
                    }}
                  >
                    <td style={{ padding: "8px 10px" }}>
                      <span style={{ fontWeight: isCheapest ? 700 : 500, color: isCheapest ? "#267C36" : "var(--charcoal)" }}>
                        {isCheapest && (
                          <i className="fa-solid fa-star" style={{ fontSize: "0.65rem", marginRight: "5px", color: "#267C36" }}></i>
                        )}
                        {displaySource(item.source)}
                      </span>
                      {saving && (
                        <span style={{ fontSize: "0.7rem", color: "#267C36", marginLeft: "6px", fontWeight: 600 }}>
                          Save {currency} {saving}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 700, color: isCheapest ? "#267C36" : "var(--charcoal)" }}>
                      {item.price}
                    </td>
                    <td style={{ padding: "8px 10px", textAlign: "center" }}>
                      {item.link ? (
                        <a
                          href={item.link}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{
                            display: "inline-block",
                            padding: "4px 14px",
                            borderRadius: "6px",
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            textDecoration: "none",
                            background: isCheapest
                              ? "linear-gradient(135deg, #267C36, #1a5c28)"
                              : "var(--bg-deep)",
                            color: isCheapest ? "#fff" : "var(--charcoal)",
                            border: isCheapest ? "none" : "1px solid var(--border)",
                            transition: "opacity 0.15s",
                          }}
                        >
                          Buy <i className="fa-solid fa-arrow-up-right-from-square" style={{ fontSize: "0.65rem" }}></i>
                        </a>
                      ) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p style={{ fontSize: "0.7rem", color: "var(--text-sub)", marginTop: "6px", fontStyle: "italic" }}>
            ⭐ Cheapest verified listing highlighted in green. Same product, same brand, same size only.
          </p>
        </div>
      )}
    </div>
  );
}

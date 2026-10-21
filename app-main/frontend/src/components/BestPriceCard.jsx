import React from "react";
import { ArrowUpRight, CircleCheck, LoaderCircle, PiggyBank, RotateCcw, Store } from "lucide-react";

import { money, currencyAffix } from "../constants";
import AffiliateNotice from "./AffiliateNotice";
import { Button, Callout, Card, cx } from "./ds";

function displaySource(source) {
  if (!source) return "Unknown";
  return source
    .replace(/^www\./, "")
    .replace(/\.(com\.au|co\.uk|co\.kr|co\.jp|com\.br|com\.sg|ae|sg|fr|de|ca|in|com)$/, "")
    .split(".")[0]
    .replace(/^\w/, (c) => c.toUpperCase());
}

/** Where to buy this exact product - same brand, same size - for less. */
export default function BestPriceCard({ bestPrice, bestPriceLoading, bestPriceError, onRetry, currency, productUrl }) {
  const userUrl = bestPrice?.user_url || (productUrl?.startsWith("http") ? productUrl : null);
  const all = bestPrice?.all_prices || [];
  const cheapest = all.length > 0 ? parseFloat(all[0].price) : null;
  const retry = onRetry && (
    <Button variant="ghost" size="sm" icon={<RotateCcw />} onClick={onRetry} data-testid="best-price-retry">Search again</Button>
  );

  return (
    <Card eyebrow="Where to buy" title="Best price we could find"
          sub="Same product, same brand, same size only." data-testid="card-best-price">
      {bestPriceLoading && <p className="loading-line"><LoaderCircle className="spin" aria-hidden="true" />Searching shops for this exact product…</p>}

      {!bestPriceLoading && bestPrice?.is_user_cheapest && (
        <Callout tone="positive" icon={CircleCheck} title="You’ve found the best price" data-testid="user-cheapest-badge">
          <p className="callout__text">No cheaper listing turned up for this exact product.</p>
          {userUrl && (
            <a href={userUrl} target="_blank" rel="noopener noreferrer" className="link" data-testid="buy-here-link" style={{ marginTop: 8 }}>
              Open your listing<ArrowUpRight aria-hidden="true" />
            </a>
          )}
        </Callout>
      )}

      {!bestPriceLoading && !bestPrice?.is_user_cheapest && bestPrice?.best_price && (
        <Callout tone="positive" icon={PiggyBank} data-testid="better-price-badge"
                 title={`Cheaper on ${displaySource(bestPrice.best_price.source)}: ${money(currency, bestPrice.best_price.price)}`}
                 aside={bestPrice.savings > 0 ? `Save ${money(currency, bestPrice.savings)}` : null}>
          {bestPrice.best_price.link && (
            <a href={bestPrice.best_price.link} target="_blank" rel="noopener noreferrer sponsored" className="link" style={{ marginTop: 6 }}>
              View on {displaySource(bestPrice.best_price.source)}<ArrowUpRight aria-hidden="true" />
            </a>
          )}
        </Callout>
      )}

      {!bestPriceLoading && bestPrice?.search_unavailable && (
        <Callout tone="neutral" data-testid="best-price-unavailable"><p className="callout__text">{bestPrice.message}</p></Callout>
      )}

      {!bestPriceLoading && bestPriceError && (
        <div className="stack" style={{ "--stack-gap": "10px" }}>
          <Callout tone="caution" data-testid="best-price-error"><p className="callout__text">{bestPriceError}</p></Callout>
          {retry}
        </div>
      )}

      {!bestPriceLoading && !bestPriceError && !bestPrice?.search_unavailable && bestPrice?.not_found && (
        <div className="stack" style={{ "--stack-gap": "10px" }}>
          <Callout tone="neutral" icon={Store} title={userUrl ? "Your listing" : "No other listings found"} data-testid="not-found-message">
            <p className="callout__text">
              {userUrl
                ? `${bestPrice.user_price > 0 ? `${money(currency, bestPrice.user_price)}. ` : ""}A wider search didn’t return another price for this exact product and size.`
                : "We couldn’t find another shop selling this exact product."}
            </p>
            {userUrl && <a href={userUrl} target="_blank" rel="noopener noreferrer" className="link" data-testid="buy-here-link" style={{ marginTop: 6 }}>Open your listing<ArrowUpRight aria-hidden="true" /></a>}
          </Callout>
          {retry}
        </div>
      )}

      {!bestPriceLoading && !bestPrice && !bestPriceError && (
        <Callout tone="neutral"><p className="callout__text">Add the product name to search other shops for it.</p></Callout>
      )}

      {!bestPriceLoading && all.length > 0 && (
        <table className="dtable price-table">
          <thead><tr><th>Shop</th><th style={{ textAlign: "right" }}>Price ({currencyAffix(currency)})</th><th /></tr></thead>
          <tbody>
            {all.map((item, idx) => {
              const best = cheapest !== null && parseFloat(item.price) === cheapest;
              return (
                <tr key={idx} className={cx(best && "price-table__best")}>
                  <td>
                    <span className="t-label-s">{displaySource(item.source)}</span>
                    {best && <span className="badge badge--positive" style={{ marginLeft: 8 }}>Cheapest</span>}
                    {item.savings > 0 && <span className="t-caption c-positive" style={{ display: "block" }}>Save {money(currency, item.savings)}</span>}
                  </td>
                  <td className="num" style={{ textAlign: "right" }}>{item.price}</td>
                  <td style={{ textAlign: "right" }}>
                    {item.link ? (
                      <a href={item.link} target="_blank" rel="noopener noreferrer sponsored" className={cx("btn btn--sm", best ? "btn--primary" : "btn--secondary")}>
                        <span>View</span><ArrowUpRight aria-hidden="true" />
                      </a>
                    ) : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <AffiliateNotice disclosure={bestPrice?.affiliate_disclosure} />
    </Card>
  );
}

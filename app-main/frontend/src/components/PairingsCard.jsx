import React from "react";

/**
 * What to use alongside this product.
 *
 * Free, because it is derived from the product's own actives and says nothing
 * about the person. Concern fit only changes the order.
 *
 * The suggestions are deliberately few. The database holds synergy partners
 * for 815 ingredients, and almost none of it survives the question "could
 * somebody actually buy this?" - niacinamide alone pairs with entries like
 * aegle marmelos fruit extract. The server only returns partners it can name
 * a format for, so every line here ends in something you could put in a
 * search box.
 */
export default function PairingsCard({ pairings }) {
  if (!pairings || pairings.length === 0) return null;

  return (
    <div className="sc-card result-card pairings-card" data-testid="pairings-card">
      <h2 className="card-title">
        <i className="fa-solid fa-link"></i> What to pair this with
      </h2>
      <p className="pairings-lede">
        These work <em>with</em> what is already in this product rather than
        repeating it. Nothing here is required &mdash; the product stands on
        its own.
      </p>

      <ul className="pairings-list">
        {pairings.map((p, i) => (
          <li className="pairing" key={i} data-testid={`pairing-${i}`}>
            <div className="pairing-head">
              <strong className="pairing-name">{p.ingredient}</strong>
              {p.addresses_concern && (
                <span className="pairing-gap">
                  fills a gap on {p.addresses_concern.toLowerCase()}
                </span>
              )}
            </div>

            <p className="pairing-why">
              Works with the <strong>{p.works_with}</strong> already here
              {p.adds ? ` — adds ${String(p.adds).toLowerCase()}` : ""}.
            </p>

            {p.look_for && (
              <p className="pairing-where">
                <i className="fa-solid fa-magnifying-glass" aria-hidden="true"></i>
                Look for {p.look_for}.
              </p>
            )}

            {p.caution && (
              <p className="pairing-caution">
                <i className="fa-solid fa-triangle-exclamation" aria-hidden="true"></i>
                {p.caution}
              </p>
            )}
          </li>
        ))}
      </ul>

      <p className="pairings-foot">
        Based on documented interactions between these ingredients, not on who
        sells them. We earn nothing from these suggestions.
      </p>
    </div>
  );
}

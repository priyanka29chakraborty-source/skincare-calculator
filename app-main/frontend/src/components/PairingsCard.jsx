import React from "react";
import { Search, TriangleAlert } from "lucide-react";

import { Badge, Card } from "./ds";

/**
 * What to use alongside this product. Free: it is derived from the product's
 * own actives. The server only returns partners it can name a format for, so
 * every line ends in something you could actually search for.
 */
export default function PairingsCard({ pairings }) {
  if (!pairings || pairings.length === 0) return null;
  return (
    <Card eyebrow="Routine" title="Pairs well with"
          sub="These work with what’s already in this product and with your skin type. The product stands on its own — these are additions, not requirements."
          data-testid="pairings-card">
      <ul className="pairings">
        {pairings.map((p, i) => (
          <li className="pairing" key={i} data-testid={`pairing-${i}`}>
            <p className="t-heading-s">{p.ingredient}</p>
            {p.addresses_concern && <Badge tone="positive">Fills a gap · {p.addresses_concern.toLowerCase()}</Badge>}
            <p className="t-body-s c-secondary">
              Works with the <strong className="c-primary">{p.works_with}</strong> already here{p.adds ? ` — adds ${String(p.adds).toLowerCase()}` : ""}.
            </p>
            {p.look_for && <p className="pairing__meta"><Search aria-hidden="true" />Look for {p.look_for}.</p>}
            {p.caution && <p className="pairing__meta pairing__meta--caution"><TriangleAlert aria-hidden="true" />{p.caution}</p>}
          </li>
        ))}
      </ul>
      <p className="t-caption c-tertiary" style={{ marginTop: 16 }}>Pairings come from how these ingredients are documented to work together.</p>
    </Card>
  );
}

import React from "react";
import { Info } from "lucide-react";

/**
 * The affiliate disclosure, shown only when the server actually tagged a link
 * (it sets `affiliate_disclosure` in the same pass that rewrites links). Plain
 * and legible, as Amazon Associates and FTC guidance require.
 */
export default function AffiliateNotice({ disclosure }) {
  if (!disclosure) return null;
  return (
    <p className="affiliate-notice" data-testid="affiliate-disclosure">
      <Info aria-hidden="true" />
      <span>{disclosure}</span>
    </p>
  );
}

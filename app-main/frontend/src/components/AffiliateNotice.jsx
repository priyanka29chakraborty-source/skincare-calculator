import React from "react";

/**
 * The affiliate disclosure, shown wherever tagged links appear.
 *
 * It renders only when the server actually tagged something: the backend sets
 * `affiliate_disclosure` in the same pass that rewrites the links, so the
 * notice and the links it describes cannot drift apart. Claiming a commercial
 * relationship we do not have would be its own kind of dishonesty, so an
 * untagged response shows nothing.
 *
 * Deliberately plain and legible rather than tucked into a footnote. The
 * Amazon Associates agreement and the FTC endorsement guides both require the
 * disclosure to be clear and conspicuous, and a reader deciding whether to
 * trust a price comparison is entitled to know how it is paid for.
 */
export default function AffiliateNotice({ disclosure }) {
  if (!disclosure) return null;
  return (
    <p className="affiliate-notice" data-testid="affiliate-disclosure">
      <i className="fa-solid fa-circle-info" aria-hidden="true"></i>
      <span>{disclosure}</span>
    </p>
  );
}

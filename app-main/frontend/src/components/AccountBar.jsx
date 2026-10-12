import React from "react";
import { CREDIT_EXPIRY_HINT } from "../constants";

/**
 * Balance and sign-out, above the header.
 *
 * Shown only once there is something to say. A signed-out visitor who has not
 * hit the paywall does not need an account control in front of the thing they
 * came for - the unlock prompt appears in context, on the card that is locked.
 */
export default function AccountBar({ account, onOpenUnlock }) {
  if (account.loading || !account.signedIn) return null;

  const { balance, owner } = account;

  return (
    <div className="account-bar" data-testid="account-bar">
      {owner ? (
        <span className="account-balance">Signed in</span>
      ) : (
        <span className="account-balance" title={CREDIT_EXPIRY_HINT}>
          <i className="fa-solid fa-circle-check" aria-hidden="true"></i>
          <strong data-testid="account-balance">{balance}</strong>
          {balance === 1 ? " credit" : " credits"}
        </span>
      )}
      <span className="account-actions">
        {!owner && (
          <button className="account-link" onClick={onOpenUnlock} data-testid="top-up">
            {balance === 0 ? "Get credits" : "Top up"}
          </button>
        )}
        <button className="account-link" onClick={account.signOut} data-testid="sign-out">
          Sign out
        </button>
      </span>
    </div>
  );
}

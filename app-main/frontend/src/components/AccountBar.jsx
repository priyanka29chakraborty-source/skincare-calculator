import React from "react";

/**
 * Balance and sign-out, above the header.
 *
 * Shown only once there is something to say. A signed-out visitor who has not
 * hit the paywall does not need an account control in front of the thing they
 * came for - the unlock prompt appears in context, on the card that is locked.
 */
export default function AccountBar({ account, onOpenUnlock }) {
  if (account.loading || !account.signedIn) return null;

  const { balance } = account;

  return (
    <div className="account-bar" data-testid="account-bar">
      <span className="account-balance">
        <i className="fa-solid fa-circle-check" aria-hidden="true"></i>
        <strong data-testid="account-balance">{balance}</strong>
        {balance === 1 ? " analysis left" : " analyses left"}
      </span>
      <span className="account-actions">
        <button className="account-link" onClick={onOpenUnlock} data-testid="top-up">
          {balance === 0 ? "Get credits" : "Top up"}
        </button>
        <button className="account-link" onClick={account.signOut} data-testid="sign-out">
          Sign out
        </button>
      </span>
    </div>
  );
}

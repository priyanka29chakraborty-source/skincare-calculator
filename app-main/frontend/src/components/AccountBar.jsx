import React from "react";
import { CREDIT_EXPIRY_HINT } from "../constants";

/**
 * Sign-in, balance, and sign-out, above the header.
 *
 * Sign in stays visible while signed out. The credit count appears only
 * after an account exists.
 */
export default function AccountBar({ account, onOpenUnlock }) {
  if (account.loading) return null;

  if (!account.signedIn) {
    return (
      <div className="account-bar" data-testid="account-bar">
        <button className="sign-in-btn" onClick={() => onOpenUnlock("signin")} data-testid="sign-in">
          Sign-in
        </button>
      </div>
    );
  }

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
          <button className="account-link" onClick={() => onOpenUnlock("credits")} data-testid="top-up">
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

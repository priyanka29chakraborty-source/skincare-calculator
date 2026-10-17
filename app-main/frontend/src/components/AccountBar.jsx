import React, { useEffect, useRef, useState } from "react";

import { CREDIT_EXPIRY_HINT } from "../constants";
import { API, api } from "../api";

function when(ts) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleDateString("en-IN", {
    day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata",
  });
}

function activityLine(row) {
  if (row.reason === "grant" && row.delta > 0) return `${row.delta} trial credits`;
  if (row.reason === "purchase" && row.delta > 0) return `${row.delta} purchased credits`;
  return "";
}

/**
 * Signed-out: the Sign-in button.
 * Signed-in: a letter avatar and the credit count. The menu holds the balance,
 * the credit rule, expiry, top up, credit activity, and both histories.
 */
export default function AccountBar({ account, onOpenUnlock, onReopen, onCompareAgain }) {
  const [open, setOpen] = useState(false);
  const [ruleOpen, setRuleOpen] = useState(false);
  const [analyses, setAnalyses] = useState([]);
  const [comparisons, setComparisons] = useState([]);
  const [activity, setActivity] = useState([]);
  const [busy, setBusy] = useState(false);
  const root = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    function onPointer(event) {
      if (root.current && !root.current.contains(event.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onPointer);
    return () => document.removeEventListener("mousedown", onPointer);
  }, [open]);

  useEffect(() => {
    if (!open || !account.signedIn) return undefined;
    let cancelled = false;
    api.get(`${API}/history`).then(({ data }) => {
      if (!cancelled) setAnalyses(data.entries || []);
    }).catch(() => { if (!cancelled) setAnalyses([]); });
    api.get(`${API}/history/comparisons`).then(({ data }) => {
      if (!cancelled) setComparisons(data.entries || []);
    }).catch(() => { if (!cancelled) setComparisons([]); });
    api.get(`${API}/credits/history`).then(({ data }) => {
      if (!cancelled) {
        setActivity((data.entries || []).filter((row) => activityLine(row)));
      }
    }).catch(() => { if (!cancelled) setActivity([]); });
    return () => { cancelled = true; };
  }, [open, account.signedIn, account.balance]);

  if (account.loading || !account.signedIn) {
    return (
      <div className="account-bar" data-testid="account-bar">
        <button className="sign-in-btn" onClick={() => onOpenUnlock("signin")} data-testid="sign-in">
          Sign-in
        </button>
      </div>
    );
  }

  const { balance, owner, email, creditsExpireAt, paymentsEnabled } = account;
  const letter = (email || "?").trim().charAt(0).toUpperCase() || "?";

  async function openAnalysis(entry) {
    setBusy(true);
    try {
      const { data } = await api.get(`${API}/history/${entry.entry_id}`);
      onReopen(data);
      setOpen(false);
    } catch {
      setAnalyses((rows) => rows.filter((row) => row.entry_id !== entry.entry_id));
    } finally { setBusy(false); }
  }

  async function removeAnalysis(entry) {
    setBusy(true);
    try {
      await api.post(`${API}/history/${entry.entry_id}/forget`, {});
      setAnalyses((rows) => rows.filter((row) => row.entry_id !== entry.entry_id));
    } finally { setBusy(false); }
  }

  async function openComparison(entry) {
    setBusy(true);
    try {
      const { data } = await api.get(`${API}/history/comparisons/${entry.entry_id}`);
      onCompareAgain(data.products || []);
      setOpen(false);
    } catch {
      setComparisons((rows) => rows.filter((row) => row.entry_id !== entry.entry_id));
    } finally { setBusy(false); }
  }

  async function removeComparison(entry) {
    setBusy(true);
    try {
      await api.post(`${API}/history/comparisons/${entry.entry_id}/forget`, {});
      setComparisons((rows) => rows.filter((row) => row.entry_id !== entry.entry_id));
    } finally { setBusy(false); }
  }

  return (
    <div className="account-bar" data-testid="account-bar" ref={root}>
      <button
        className="account-menu-btn"
        type="button"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((value) => !value)}
        data-testid="account-menu"
      >
        <span className="account-avatar" aria-hidden="true">{letter}</span>
        {!owner && (
          <span className="account-menu-credits">
            <strong data-testid="account-balance">{balance}</strong>
            {balance === 1 ? " credit" : " credits"}
          </span>
        )}
      </button>

      {open && (
        <div className="account-menu" role="menu" data-testid="account-dropdown">
          <p className="account-menu-email">{email}</p>

          {!owner && (
            <div className="account-menu-credits-block">
              <p className="account-menu-balance">
                {balance} {balance === 1 ? "credit" : "credits"} remaining
                <button
                  type="button"
                  className="account-info"
                  aria-expanded={ruleOpen}
                  aria-label="How credits work"
                  onClick={() => setRuleOpen((value) => !value)}
                  data-testid="credit-info"
                >
                  i
                </button>
              </p>
              {ruleOpen && (
                <p className="account-rule" data-testid="credit-rule">{CREDIT_EXPIRY_HINT}</p>
              )}
              <p className="account-expiry" data-testid="credit-expiry">
                {balance > 0 && creditsExpireAt
                  ? `Valid until ${when(creditsExpireAt)}`
                  : "No credits left"}
              </p>
              {paymentsEnabled && (
                <button
                  className="account-topup"
                  type="button"
                  onClick={() => { setOpen(false); onOpenUnlock("credits"); }}
                  data-testid="top-up"
                >
                  Top up
                </button>
              )}
              {activity.length > 0 && (
                <ul className="account-activity">
                  {activity.map((row) => (
                    <li key={row.entry_id}>
                      <span>{activityLine(row)}</span>
                      <span>{when(row.created_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="account-history">
            <p className="account-history-head">Product analyses</p>
            {analyses.length === 0 && <p className="account-empty">No analyses yet.</p>}
            <ul>
              {analyses.map((entry) => (
                <li key={entry.entry_id}>
                  <div>
                    <strong>{entry.product_name || "Unnamed product"}</strong>
                    <span>
                      {[entry.brand, entry.category].filter(Boolean).join(" · ")}
                      {entry.score != null ? ` · Score ${entry.score}` : ""}
                      {entry.created_at ? ` · ${when(entry.created_at)}` : ""}
                    </span>
                  </div>
                  <span className="account-history-actions">
                    <button type="button" disabled={busy} onClick={() => openAnalysis(entry)}>Open again</button>
                    <button type="button" disabled={busy} onClick={() => removeAnalysis(entry)}>Remove</button>
                  </span>
                </li>
              ))}
            </ul>

            <p className="account-history-head">Comparisons</p>
            {comparisons.length === 0 && <p className="account-empty">No comparisons yet.</p>}
            <ul>
              {comparisons.map((entry) => (
                <li key={entry.entry_id}>
                  <div>
                    <strong>
                      {(entry.products || []).map((product) => (
                        [product.brand, product.product_name].filter(Boolean).join(" ")
                        || "Unnamed product"
                      )).join(" vs ")}
                    </strong>
                    <span>
                      {(entry.products || []).map((product) => (
                        `${product.category || "Product"} · Score ${product.score == null ? "—" : product.score}`
                      )).join(" vs ")}
                      {entry.created_at ? ` · ${when(entry.created_at)}` : ""}
                    </span>
                  </div>
                  <span className="account-history-actions">
                    <button type="button" disabled={busy} onClick={() => openComparison(entry)}>Compare again</button>
                    <button type="button" disabled={busy} onClick={() => removeComparison(entry)}>Remove</button>
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <button className="account-signout" type="button" onClick={account.signOut} data-testid="sign-out">
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

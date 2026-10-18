import React, { useCallback, useEffect, useState } from "react";
import { History, X } from "lucide-react";

import { money, categoryLabel } from "../constants";
import { API, api } from "../api";
import { track } from "../track";
import { Button, ScoreRing } from "./ds";

/**
 * Saved analyses, in a side panel.
 *
 * Re-opening a saved product reloads its inputs and re-runs the analysis
 * rather than replaying a stored result: the score depends on the engine, and
 * the engine changes. Showing a saved 91 next to a freshly computed 87 is how
 * a tool loses a reader's trust, so there is only ever one number - today's.
 *
 * Re-running also costs nothing: the credit was already spent on this product
 * and the ledger is keyed on the product, not the request.
 */
export default function SavedSheet({ open, onClose, account, onReopen, onSignIn }) {
  const [entries, setEntries] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!account.signedIn) { setEntries(null); return; }
    try {
      const { data } = await api.get(`${API}/history`);
      setEntries(data.entries || []);
    } catch {
      setEntries([]);
    }
  }, [account.signedIn]);

  useEffect(() => { if (open) load(); }, [open, load, account.balance]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  async function reopen(entry) {
    setBusy(true);
    try {
      const { data } = await api.get(`${API}/history/${entry.entry_id}`);
      onReopen(data);
      track("result_reopened");
      onClose();
    } catch {
      load();
    } finally { setBusy(false); }
  }

  async function forget(entry) {
    setBusy(true);
    try {
      await api.post(`${API}/history/${entry.entry_id}/forget`, {});
      setEntries((rows) => (rows || []).filter((r) => r.entry_id !== entry.entry_id));
    } finally { setBusy(false); }
  }

  return (
    <div className="overlay sheet-overlay" role="presentation" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby="saved-title"
           onClick={(e) => e.stopPropagation()} data-testid="history-card">
        <div className="sheet__head">
          <div>
            <p className="t-eyebrow c-accent">Saved</p>
            <h2 className="t-heading-m" id="saved-title">Your analyses</h2>
          </div>
          <button className="modal__close" style={{ position: "static" }} onClick={onClose} aria-label="Close">
            <X />
          </button>
        </div>
        <div className="sheet__body">
          {!account.signedIn ? (
            <div className="empty">
              <span className="empty__icon"><History aria-hidden="true" /></span>
              <p className="t-heading-s">Keep every product you check</p>
              <p className="t-body-s c-secondary">Sign in with your email and each analysis is saved here, ready to reopen on today’s engine.</p>
              <Button variant="primary" onClick={() => { onClose(); onSignIn(); }}>Sign in</Button>
            </div>
          ) : entries === null ? (
            <div className="stack" style={{ "--stack-gap": "12px" }} aria-busy="true">
              {[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 72, borderRadius: 14 }} />)}
            </div>
          ) : entries.length === 0 ? (
            <div className="empty">
              <span className="empty__icon"><History aria-hidden="true" /></span>
              <p className="t-heading-s">Nothing saved yet</p>
              <p className="t-body-s c-secondary">Products you analyse while signed in appear here.</p>
            </div>
          ) : (
            <>
              <ul className="saved-list">
                {entries.map((entry) => (
                  <li key={entry.entry_id} className="saved-row">
                    <button className="saved-row__main" disabled={busy} onClick={() => reopen(entry)}
                            data-testid={`history-row-${entry.entry_id}`}>
                      <ScoreRing score={entry.score} size="sm" animate={false} label="Score" />
                      <span className="saved-row__text">
                        <span className="t-label-s saved-row__name">{entry.product_name || "Unnamed product"}</span>
                        <span className="t-caption c-tertiary">
                          {[entry.brand, entry.category && categoryLabel(entry.category),
                            entry.price ? money(entry.currency, entry.price) : null].filter(Boolean).join(" · ")}
                        </span>
                      </span>
                    </button>
                    <button className="btn btn--ghost btn--icon btn--sm" disabled={busy} type="button"
                            onClick={() => forget(entry)} aria-label={`Remove ${entry.product_name || "this product"}`}>
                      <X />
                    </button>
                  </li>
                ))}
              </ul>
              <p className="t-caption c-tertiary">
                Opening one re-runs it with today’s data, so the score is always current. It costs no credit —
                a product is charged once per account, however often you come back to it.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

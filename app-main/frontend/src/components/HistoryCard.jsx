import React, { useCallback, useEffect, useState } from "react";
import { GitCompare, History, X } from "lucide-react";

import { money, categoryLabel } from "../constants";
import { API, api, describeError } from "../api";
import { track } from "../track";
import { Button, ScoreRing } from "./ds";

function when(ts) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

/**
 * Saved products and saved comparisons, in a side panel.
 *
 * Re-opening a saved product reloads its inputs and re-runs the analysis
 * rather than replaying a stored result: the score depends on the engine, and
 * the engine changes. Showing a saved 91 next to a freshly computed 87 is how
 * a tool loses a reader's trust, so there is only ever one number - today's.
 * A saved comparison works the same way: it fills the compare form again.
 *
 * Re-running also costs nothing: the credit was already spent on this product
 * (or this set of products) and the ledger is keyed on that, not the request.
 */
export default function SavedSheet({ open, onClose, account, onReopen, onCompareAgain, onSignIn }) {
  const [tab, setTab] = useState("products");
  const [entries, setEntries] = useState(null);
  const [comparisons, setComparisons] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    if (!account.signedIn) { setEntries(null); setComparisons(null); return; }
    const [products, compared] = await Promise.allSettled([
      api.get(`${API}/history`),
      api.get(`${API}/history/comparisons`),
    ]);
    setEntries(products.status === "fulfilled" ? products.value.data.entries || [] : []);
    setComparisons(compared.status === "fulfilled" ? compared.value.data.entries || [] : []);
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
    setBusy(true); setError("");
    try {
      const { data } = await api.post(`${API}/history/${entry.entry_id}/forget`, {});
      if (!data.forgotten) {
        setError("That saved product could not be removed. Please refresh and try again.");
        return;
      }
      setEntries((rows) => (rows || []).filter((r) => r.entry_id !== entry.entry_id));
    } catch (e) {
      setError(describeError(e));
    } finally { setBusy(false); }
  }

  async function compareAgain(entry) {
    setBusy(true);
    try {
      const { data } = await api.get(`${API}/history/comparisons/${entry.entry_id}`);
      onCompareAgain(data.products || []);
      onClose();
    } catch {
      load();
    } finally { setBusy(false); }
  }

  async function forgetComparison(entry) {
    setBusy(true); setError("");
    try {
      const { data } = await api.post(`${API}/history/comparisons/${entry.entry_id}/forget`, {});
      if (!data.forgotten) {
        setError("That saved comparison could not be removed. Please refresh and try again.");
        return;
      }
      setComparisons((rows) => (rows || []).filter((r) => r.entry_id !== entry.entry_id));
    } catch (e) {
      setError(describeError(e));
    } finally { setBusy(false); }
  }

  const list = tab === "products" ? entries : comparisons;

  return (
    <div className="overlay sheet-overlay" role="presentation" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby="saved-title"
           onClick={(e) => e.stopPropagation()} data-testid="history-card">
        <div className="sheet__head">
          <div>
            <p className="t-eyebrow c-accent">Saved</p>
            <h2 className="t-heading-m" id="saved-title">Your saved work</h2>
          </div>
          <button className="modal__close" style={{ position: "static" }} onClick={onClose} aria-label="Close">
            <X />
          </button>
        </div>

        {account.signedIn && (
          <div className="tabs saved-tabs" role="tablist" aria-label="Saved">
            {[["products", "Products", entries], ["comparisons", "Comparisons", comparisons]].map(([key, label, rows]) => (
              <button key={key} type="button" role="tab" className="tab" aria-selected={tab === key}
                      aria-current={tab === key ? "true" : undefined} onClick={() => setTab(key)}
                      data-testid={`saved-tab-${key}`}>
                {label}{rows && rows.length > 0 ? <span className="saved-tabs__count">{rows.length}</span> : null}
              </button>
            ))}
          </div>
        )}

        <div className="sheet__body">
          {error && <p className="t-body-s c-negative" role="alert">{error}</p>}
          {!account.signedIn ? (
            <div className="empty">
              <span className="empty__icon"><History aria-hidden="true" /></span>
              <p className="t-heading-s">Keep every product you check</p>
              <p className="t-body-s c-secondary">Sign in with your email and each analysis and comparison is saved here, ready to reopen on today’s engine.</p>
              <Button variant="primary" onClick={() => { onClose(); onSignIn(); }}>Sign in</Button>
            </div>
          ) : list === null ? (
            <div className="stack" style={{ "--stack-gap": "12px" }} aria-busy="true">
              {[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 72, borderRadius: 14 }} />)}
            </div>
          ) : list.length === 0 ? (
            <div className="empty">
              <span className="empty__icon">{tab === "products" ? <History aria-hidden="true" /> : <GitCompare aria-hidden="true" />}</span>
              <p className="t-heading-s">Nothing saved yet</p>
              <p className="t-body-s c-secondary">
                {tab === "products"
                  ? "Products you analyse while signed in appear here."
                  : "Comparisons you run while signed in appear here."}
              </p>
            </div>
          ) : tab === "products" ? (
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
          ) : (
            <>
              <ul className="saved-list">
                {comparisons.map((entry) => {
                  const products = entry.products || [];
                  const names = products.map((p) => [p.brand, p.product_name].filter(Boolean).join(" ") || "Unnamed product");
                  const scores = products.map((p) => (p.score == null ? "—" : p.score)).join(" · ");
                  return (
                    <li key={entry.entry_id} className="saved-row">
                      <button className="saved-row__main" disabled={busy} onClick={() => compareAgain(entry)}
                              data-testid={`comparison-row-${entry.entry_id}`}>
                        <span className="saved-row__icon" aria-hidden="true"><GitCompare /></span>
                        <span className="saved-row__text">
                          <span className="t-label-s saved-row__name">{names.join(" vs ")}</span>
                          <span className="t-caption c-tertiary">
                            {[`${products.length} products`, scores && `Scores ${scores}`, when(entry.created_at)]
                              .filter(Boolean).join(" · ")}
                          </span>
                        </span>
                      </button>
                      <button className="btn btn--ghost btn--icon btn--sm" disabled={busy} type="button"
                              onClick={() => forgetComparison(entry)} aria-label={`Remove ${names.join(" vs ")}`}>
                        <X />
                      </button>
                    </li>
                  );
                })}
              </ul>
              <p className="t-caption c-tertiary">
                Opening one fills the compare form again with the same products. Running the same set again costs no credit.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

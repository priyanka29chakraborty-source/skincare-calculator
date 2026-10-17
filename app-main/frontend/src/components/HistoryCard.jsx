import React, { useCallback, useEffect, useState } from "react";

import { money } from "../constants";
import { API, api } from "../api";
import { track } from "../track";

/**
 * Previously analysed products, for signed-in accounts.
 *
 * Re-opening a saved product reloads its inputs and re-runs the analysis
 * rather than replaying a stored result. That is the honest choice: the score
 * depends on the engine, and the engine changes. Showing a saved 91 next to a
 * freshly computed 87 is how a tool loses a reader's trust, so there is only
 * ever one number - today's.
 *
 * Re-running also costs nothing, because the credit was already spent on this
 * product and the ledger is keyed on the product, not the request.
 */
export default function HistoryCard({ account, onReopen }) {
  const [entries, setEntries] = useState(null);
  const [open, setOpen] = useState(false);
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

  useEffect(() => { load(); }, [load, account.balance]);

  if (!account.signedIn || !entries || entries.length === 0) return null;

  async function reopen(entry) {
    setBusy(true);
    try {
      const { data } = await api.get(`${API}/history/${entry.entry_id}`);
      onReopen(data);
      track("result_reopened");
      setOpen(false);
    } catch {
      // Nothing useful to say: the entry is gone or the network failed, and
      // the list refresh below makes the state honest either way.
      load();
    } finally { setBusy(false); }
  }

  async function forget(entry, e) {
    e.stopPropagation();
    setBusy(true);
    try {
      await api.post(`${API}/history/${entry.entry_id}/forget`, {});
      setEntries((rows) => rows.filter((r) => r.entry_id !== entry.entry_id));
    } finally { setBusy(false); }
  }

  return (
    <div className="card history-card no-print" data-testid="history-card">
      <button className="history-toggle" onClick={() => setOpen((v) => !v)}
              aria-expanded={open} data-testid="history-toggle">
        <span className="card-label history-label">
          Previously analysed
          <span className="history-count">{entries.length}</span>
        </span>
        <i className={`fa-solid fa-chevron-${open ? "up" : "down"}`} aria-hidden="true"></i>
      </button>

      {open && (
        <>
          <ul className="history-list">
            {entries.map((entry) => (
              <li key={entry.entry_id}>
                <button className="history-row" disabled={busy}
                        onClick={() => reopen(entry)}
                        data-testid={`history-row-${entry.entry_id}`}>
                  <span className="history-ident">
                    <span className="history-name">
                      {entry.product_name || "Unnamed product"}
                    </span>
                    <span className="history-meta">
                      {[entry.brand, entry.category,
                        entry.price ? money(entry.currency, entry.price) : null]
                        .filter(Boolean).join(" · ")}
                    </span>
                  </span>
                  <span className="history-score">Score {entry.score}</span>
                </button>
                <button className="history-forget" disabled={busy}
                        onClick={(e) => forget(entry, e)}
                        aria-label={`Remove ${entry.product_name || "this product"}`}>
                  <i className="fa-solid fa-xmark"></i>
                </button>
              </li>
            ))}
          </ul>
          <p className="history-note">
            Opening one of these re-runs the analysis with today's data, so the
            score is always current. It costs no credit — a product is charged
            once per account, however often you come back to it.
          </p>
        </>
      )}
    </div>
  );
}

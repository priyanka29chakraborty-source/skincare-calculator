import React, { useEffect, useState } from "react";

import { API, api, describeError } from "../api";
import { CREDIT_EXPIRY_HINT } from "../constants";
import { openCheckout } from "../lib/razorpay";
import { track } from "../track";

/**
 * Sign in, then buy credits.
 *
 * Two deliberate choices about how this reads:
 *
 * It never implies the locked result is bad. The analysis has already run and
 * the user can see its free half; manufacturing suspense about the rest would
 * be using their worry about their own skin as a sales lever.
 *
 * It says plainly what a credit buys and that re-analysing the same product is
 * free, because that is true and because the alternative is someone
 * discovering it only after they feel double-charged.
 */
export default function UnlockModal({ open, onClose, account, onPurchased }) {
  const [step, setStep] = useState("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [packs, setPacks] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!open) return;
    setError("");
    setNotice("");
    setStep(account.signedIn ? "packs" : "email");
    track("personal_opened");
  }, [open, account.signedIn]);

  useEffect(() => {
    if (!open || packs) return;
    let cancelled = false;
    api.get(`${API}/credits/packs`)
      .then(({ data }) => { if (!cancelled) setPacks(data); })
      .catch(() => { if (!cancelled) setPacks({ packs: [], payments_enabled: false }); });
    return () => { cancelled = true; };
  }, [open, packs]);

  // Escape closes, and focus does not escape to the page behind.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  async function sendCode(e) {
    e.preventDefault();
    setBusy(true); setError(""); setNotice("");
    try {
      await account.requestCode(email);
      setStep("code");
      setNotice(`We sent a 6-digit code to ${email}. It expires in 10 minutes.`);
    } catch (err) {
      setError(describeError(err));
    } finally { setBusy(false); }
  }

  async function confirmCode(e) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      await account.verifyCode(email, code);
      setStep("packs");
      setNotice("");
    } catch (err) {
      setError(describeError(err));
    } finally { setBusy(false); }
  }

  async function buy(pack) {
    setBusy(true); setError(""); setNotice("");
    try {
      track("checkout_started");
      const { data: order } = await api.post(
        `${API}/credits/order`, { pack_id: pack.pack_id }, { withCredentials: true });

      const result = await openCheckout({
        order,
        description: `${pack.credits} personalised analyses`,
        prefillEmail: email || undefined,
      });

      await api.post(`${API}/credits/confirm`, {
        razorpay_order_id: result.razorpay_order_id,
        razorpay_payment_id: result.razorpay_payment_id,
        razorpay_signature: result.razorpay_signature,
      }, { withCredentials: true });

      await account.refresh();
      track("checkout_completed");
      setNotice(`${pack.credits} analyses added.`);
      if (onPurchased) onPurchased();
    } catch (err) {
      if (err?.dismissed) {
        // Closing the payment window is not a failure and needs no message.
      } else if (err?.failed) {
        setError(err.message);
      } else {
        // The webhook is the authoritative delivery path, so a failure here
        // does not necessarily mean the payment was lost. Say so rather than
        // implying the money vanished.
        setError(
          `${describeError(err)} If you were charged, your credits will appear ` +
          `within a minute - reload the page to check.`);
        await account.refresh();
      }
    } finally { setBusy(false); }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true"
         aria-label="Unlock personal analysis" data-testid="unlock-modal">
      <div className="modal-card">
        <button className="modal-close" onClick={onClose} aria-label="Close">
          <i className="fa-solid fa-xmark"></i>
        </button>

        <div className="card-label">Personal analysis</div>

        {step === "email" && (
          <form onSubmit={sendCode}>
            <p className="modal-lede">
              The formulation score is free and always will be &mdash; how well
              this product is <em>made</em> is the same for everyone. What costs
              a credit is the part that is about <em>you</em>: whether it treats
              the concerns you picked, whether it suits your skin type, and what
              in it is likely to cause you trouble.
            </p>
            <div className="field-group">
              <label className="field-label" htmlFor="unlock-email">Email</label>
              <input id="unlock-email" className="field-input" type="email" required
                     value={email} onChange={(e) => setEmail(e.target.value)}
                     placeholder="you@example.com" autoFocus
                     data-testid="unlock-email" />
            </div>
            <button className="analyze-btn modal-cta" disabled={busy} type="submit">
              {busy ? "Sending..." : "Send me a sign-in code"}
            </button>
          </form>
        )}

        {step === "code" && (
          <form onSubmit={confirmCode}>
            <p className="modal-lede">{notice}</p>
            <div className="field-group">
              <label className="field-label" htmlFor="unlock-code">6-digit code</label>
              <input id="unlock-code" className="field-input" inputMode="numeric"
                     autoComplete="one-time-code" maxLength={6} required
                     value={code} onChange={(e) => setCode(e.target.value)}
                     placeholder="123456" autoFocus data-testid="unlock-code" />
            </div>
            <button className="analyze-btn modal-cta" disabled={busy} type="submit">
              {busy ? "Checking..." : "Sign in"}
            </button>
            <p className="modal-fineprint">
              Not arrived after a minute? Check your spam folder, then request a
              fresh one &mdash; each code lasts ten minutes and works once.
            </p>
            <button type="button" className="clear-btn-solo"
                    onClick={() => { setStep("email"); setError(""); }}>
              Use a different email
            </button>
          </form>
        )}

        {step === "packs" && (
          <>
            <p className="modal-lede">
              <strong>One credit per product, once.</strong> Re-opening it,
              answering the personalisation questions, exporting the report or
              correcting a price all cost nothing &mdash; you have already paid
              for that product, and that does not expire.
            </p>

            {packs && !packs.payments_enabled && (
              <p className="modal-fineprint" data-testid="payments-off">
                Card and UPI payments are not connected yet, so these packs
                cannot be bought today. Your account and any credits on it are
                saved.
              </p>
            )}

            <div className="pack-grid">
              {(packs?.packs || []).map((pack) => (
                <button key={pack.pack_id} className="pack-card" disabled={busy}
                        onClick={() => buy(pack)}
                        data-testid={`pack-${pack.pack_id}`}>
                  <span className="pack-credits">{pack.credits}</span>
                  <span className="pack-unit">analyses</span>
                  <span className="pack-price">&#8377;{pack.amount_display}</span>
                  <span className="pack-each">
                    &#8377;{(pack.amount_paise / 100 / pack.credits).toFixed(1)} each
                  </span>
                </button>
              ))}
            </div>

            <p className="modal-fineprint">
              Signed in{email ? ` as ${email}` : ""}.{" "}
              <span title={CREDIT_EXPIRY_HINT}>
                <strong data-testid="modal-balance">{account.balance}</strong>
                {" "}
                {account.balance === 1 ? "credit" : "credits"}
              </span>
            </p>
            {notice && <p className="modal-notice" data-testid="unlock-notice">{notice}</p>}
          </>
        )}

        {error && <p className="modal-error" role="alert" data-testid="unlock-error">{error}</p>}
      </div>
    </div>
  );
}

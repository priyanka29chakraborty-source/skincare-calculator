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
export default function UnlockModal({ open, onClose, account, onPurchased, onSignedIn, purpose = "signin" }) {
  const [step, setStep] = useState("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [packs, setPacks] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [signedBalance, setSignedBalance] = useState(0);

  useEffect(() => {
    if (!open) return;
    setError("");
    setNotice("");
    setStep(account.signedIn && purpose === "credits" ? "packs" : "email");
    track("personal_opened");
    // Opening the dialog chooses the first step. A successful code must not
    // flip it back to the email form just because the account is now signed in.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, purpose]);

  useEffect(() => {
    if (!open || packs) return;
    let cancelled = false;
    api.get(`${API}/credits/packs`)
      .then(({ data }) => { if (!cancelled) setPacks(data); })
      .catch(() => { if (!cancelled) setPacks({ packs: [], payments_enabled: false }); });
    return () => { cancelled = true; };
  }, [open, packs]);

  // The sign-in card stays up until its close mark is used. Escape still
  // closes the credit packs card.
  useEffect(() => {
    if (!open || step !== "packs") return undefined;
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose, step]);

  if (!open) return null;

  async function sendCode(e) {
    e.preventDefault();
    setBusy(true); setError(""); setNotice("");
    try {
      await account.requestCode(email);
      setStep("code");
      setCode("");
    } catch (err) {
      setError(describeError(err));
    } finally { setBusy(false); }
  }

  async function confirmCode(e) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const data = await account.verifyCode(email, code);
      setSignedBalance(data.balance || 0);
      if (purpose === "credits") {
        setStep("packs");
        setNotice("");
        return;
      }
      setStep("done");
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

  function finishSignIn() {
    onClose();
    if (onSignedIn) onSignedIn();
  }

  if (step !== "packs") {
    return (
      <div className="signin-overlay" role="presentation" data-testid="unlock-modal">
        <div className="signin-modal" role="dialog" aria-modal="true" aria-labelledby="signin-title">
          <button className="signin-close" onClick={onClose} aria-label="Close" type="button">&times;</button>
          <Bottle />

          {step === "email" && (
            <section className="signin-step">
              <p className="signin-hi">Hello, gorgeous</p>
              <h2 id="signin-title">Is this product <em>right for you?</em></h2>
              <p className="signin-lede">Your formulation score is always free. Sign in and we'll tell you how this product matches your skin.</p>
              <ul className="signin-chips" aria-label="What each feature costs">
                <li className="free">Score <span>Free</span></li>
                <li>Personal analysis <span>1 credit</span></li>
                <li>Comparison <span>2 credits</span></li>
                <li>Product PDF report <span>Unlocks with a credit pack</span></li>
              </ul>
              <div className="signin-gift">
                <div className="signin-num" aria-hidden="true">4</div>
                <p>Free credits are added to your account the first time you sign in.</p>
              </div>
              <form onSubmit={sendCode}>
                <label htmlFor="unlock-email">Your email</label>
                <input id="unlock-email" type="email" autoComplete="email" required
                       value={email} onChange={(e) => setEmail(e.target.value)}
                       placeholder="you@example.com" autoFocus data-testid="unlock-email" />
                {error && <p className="signin-error" role="alert" data-testid="unlock-error">{error}</p>}
                <button className="signin-btn" disabled={busy} type="submit">
                  {busy ? "Sending your code…" : "Sign-in"}
                </button>
              </form>
              <p className="signin-fine">We'll email you a one-time code to sign in.</p>
            </section>
          )}

          {step === "code" && (
            <section className="signin-step">
              <p className="signin-hi">Almost there</p>
              <h2 id="signin-title">Check your <em>inbox</em></h2>
              <p className="signin-lede">We sent a sign-in code to <strong>{email}</strong>. Can't see it? Peek in your spam folder.</p>
              <form onSubmit={confirmCode}>
                <label htmlFor="unlock-code">Sign-in code</label>
                <input id="unlock-code" className="signin-code" inputMode="numeric"
                       autoComplete="one-time-code" maxLength={6} required
                       value={code} onChange={(e) => setCode(e.target.value)}
                       placeholder="Enter code" autoFocus data-testid="unlock-code" />
                {error && <p className="signin-error" role="alert" data-testid="unlock-error">{error}</p>}
                <button className="signin-btn" disabled={busy} type="submit">
                  {busy ? "Signing you in…" : "Sign-in"}
                </button>
              </form>
              <p className="signin-fine">
                Wrong email?{" "}
                <button className="signin-link" type="button" onClick={() => { setStep("email"); setError(""); }}>
                  Change it
                </button>
              </p>
            </section>
          )}

          {step === "done" && (
            <section className="signin-step">
              <p className="signin-hi">You're in</p>
              <h2 id="signin-title">
                {account.owner ? "Signed in" : <>Your <em>{signedBalance} credits</em> are ready</>}
              </h2>
              <p className="signin-lede">A personal analysis uses 1 credit. A comparison uses 2. Let's see what your skin thinks.</p>
              <button className="signin-btn" type="button" onClick={finishSignIn}>
                Start my personal analysis
              </button>
            </section>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true"
         aria-label="Credits" data-testid="unlock-modal">
      <div className="modal-card">
        <button className="modal-close" onClick={onClose} aria-label="Close">
          <i className="fa-solid fa-xmark"></i>
        </button>
        <div className="card-label">Personal analysis</div>
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

        {error && <p className="modal-error" role="alert" data-testid="unlock-error">{error}</p>}
      </div>
    </div>
  );
}

function Spark() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path fill="currentColor" d="M10 0c.6 5.2 4.8 9.4 10 10-5.2.6-9.4 4.8-10 10-.6-5.2-4.8-9.4-10-10C5.2 9.4 9.4 5.2 10 0z" />
    </svg>
  );
}

function Bottle() {
  return (
    <div className="signin-hero">
      <div className="signin-halo" aria-hidden="true"></div>
      <span className="signin-spark s1"><Spark /></span>
      <span className="signin-spark s2"><Spark /></span>
      <span className="signin-spark s3"><Spark /></span>
      <svg className="signin-product" viewBox="0 0 140 230" role="img" aria-label="Serum dropper bottle">
        <defs>
          <linearGradient id="signin-glass" x1="0" x2="1">
            <stop offset="0" stopColor="#c98f8c" /><stop offset=".45" stopColor="#e9c2bf" /><stop offset="1" stopColor="#a86f6f" />
          </linearGradient>
          <linearGradient id="signin-liquid" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#f3d6c9" /><stop offset="1" stopColor="#d99a8e" />
          </linearGradient>
          <linearGradient id="signin-bulb" x1="0" x2="1">
            <stop offset="0" stopColor="#232a40" /><stop offset=".5" stopColor="#46507020" /><stop offset=".5" stopColor="#3a4462" /><stop offset="1" stopColor="#1e2438" />
          </linearGradient>
          <linearGradient id="signin-collar" x1="0" x2="1">
            <stop offset="0" stopColor="#b98a6a" /><stop offset=".4" stopColor="#f1d4b3" /><stop offset="1" stopColor="#9c6f52" />
          </linearGradient>
        </defs>
        <rect x="52" y="2" width="36" height="52" rx="18" fill="url(#signin-bulb)" />
        <rect x="58" y="10" width="6" height="34" rx="3" fill="#ffffff" opacity=".22" />
        <rect x="44" y="50" width="52" height="28" rx="6" fill="url(#signin-collar)" />
        <rect x="44" y="60" width="52" height="2" fill="#000" opacity=".12" />
        <rect x="54" y="76" width="32" height="12" fill="#c58c89" />
        <path d="M30 98c0-6 4-10 10-10h60c6 0 10 4 10 10v108c0 12-8 20-20 20H50c-12 0-20-8-20-20z" fill="url(#signin-glass)" />
        <path d="M34 128h72v76c0 10-6 17-16 17H50c-10 0-16-7-16-17z" fill="url(#signin-liquid)" opacity=".85" />
        <rect x="66" y="88" width="8" height="112" rx="4" fill="#ffffff" opacity=".35" />
        <rect x="42" y="140" width="56" height="54" rx="6" fill="#fffaf8" />
        <text x="70" y="162" textAnchor="middle" fontFamily="Georgia, serif" fontSize="13" fontStyle="italic" fill="#9b6b6c">serum</text>
        <rect x="56" y="169" width="28" height="1.5" fill="#d8aaa8" />
        <text x="70" y="184" textAnchor="middle" fontFamily="Arial, sans-serif" fontSize="7" letterSpacing="1.5" fill="#2c3550">30 ML</text>
        <rect x="36" y="96" width="6" height="104" rx="3" fill="#ffffff" opacity=".45" />
      </svg>
    </div>
  );
}

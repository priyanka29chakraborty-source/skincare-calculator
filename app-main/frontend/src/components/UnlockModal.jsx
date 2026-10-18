import React, { useEffect, useState } from "react";

import { API, api, describeError } from "../api";
import { CREDIT_EXPIRY_HINT } from "../constants";
import { openCheckout } from "../lib/razorpay";
import { track } from "../track";
import { Check, CircleCheck, Lock, X } from "lucide-react";
import { Button, Callout, Meter, ScoreRing, cx } from "./ds";

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
// The sign-in heading follows what the person was trying to do.
const SIGN_IN_HEADS = {
  account: {
    eyebrow: "Sign in",
    title: <>Welcome to Urancal</>,
    body: "See how products suit your skin, compare them side by side, and keep everything you analyse in one place.",
  },
  fit: {
    eyebrow: "Personal fit",
    title: <>Is this product <em>right for you?</em></>,
    body: "Sign in to see how well it treats your concerns and whether it suits your skin type.",
  },
  compare: {
    eyebrow: "Compare",
    title: <>Find the one that’s <em>worth it</em></>,
    body: "Sign in to put products side by side — formulation, fit for your skin and price per ml.",
  },
  pdf: {
    eyebrow: "PDF report",
    title: <>Keep this report <em>for later</em></>,
    body: "Sign in, then any credit pack adds the PDF report to your analyses.",
  },
};

export default function UnlockModal({ open, onClose, account, onPurchased, onSignedIn, purpose = "signin", topic = "account" }) {
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
        description: `${pack.credits} Urancal credits`,
        prefillEmail: email || undefined,
      });

      await api.post(`${API}/credits/confirm`, {
        razorpay_order_id: result.razorpay_order_id,
        razorpay_payment_id: result.razorpay_payment_id,
        razorpay_signature: result.razorpay_signature,
      }, { withCredentials: true });

      await account.refresh();
      track("checkout_completed");
      setNotice(`${pack.credits} credits added.`);
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

  const close = (
    <button className="modal__close" onClick={onClose} aria-label="Close" type="button"><X /></button>
  );

  if (step !== "packs") {
    const head = SIGN_IN_HEADS[topic] || SIGN_IN_HEADS.account;
    return (
      <div className="overlay" role="presentation" data-testid="unlock-modal"
           onMouseDown={(e) => { if (e.target === e.currentTarget && step === "done") onClose(); }}>
        <div className="modal modal--auth" role="dialog" aria-modal="true" aria-labelledby="signin-title">
          {close}
          <AuthAside />

          <div className="auth__main">
            <span className="wordmark wordmark--sm auth__brand" aria-hidden="true">
              <span>urancal</span><span className="wordmark__dot" />
            </span>

            {step === "email" && (
              <>
                <div className="auth__head">
                  <p className="t-eyebrow c-accent">{head.eyebrow}</p>
                  <h2 id="signin-title" className="t-display-s">{head.title}</h2>
                  <p className="t-body-m c-secondary">{head.body}</p>
                </div>
                <p className="auth__gift-pill"><span aria-hidden="true">4</span>Free credits on your first sign-in</p>
                <form onSubmit={sendCode} className="stack" style={{ "--stack-gap": "14px" }}>
                  <div className="field">
                    <label className="field__label" htmlFor="unlock-email">Email address</label>
                    <div className="field__control">
                      <input id="unlock-email" type="email" autoComplete="email" required value={email}
                             onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" autoFocus
                             data-testid="unlock-email" />
                    </div>
                  </div>
                  {error && <Callout tone="negative" role="alert" data-testid="unlock-error"><p className="callout__text">{error}</p></Callout>}
                  <Button type="submit" variant="primary" size="lg" block arrow loading={busy} loadingText="Sending your code…">
                    Continue with email
                  </Button>
                  <p className="field__help auth__help">We’ll email you a 6-digit code to sign in.</p>
                </form>
                <p className="t-caption c-tertiary auth__legal">
                  By continuing you agree to the <a className="link" href="#terms" onClick={onClose}>Terms</a> and <a className="link" href="#privacy" onClick={onClose}>Privacy policy</a>.
                </p>
              </>
            )}

            {step === "code" && (
              <>
                <div className="auth__head">
                  <p className="t-eyebrow c-accent">Almost there</p>
                  <h2 id="signin-title" className="t-display-s">Check your <em>inbox</em></h2>
                  <p className="t-body-m c-secondary">We sent a 6-digit code to <strong className="c-primary">{email}</strong>. Can’t see it? Look in spam or promotions.</p>
                </div>
                <form onSubmit={confirmCode} className="stack" style={{ "--stack-gap": "14px" }}>
                  <div className="field">
                    <label className="field__label" htmlFor="unlock-code">Sign-in code</label>
                    <div className="field__control">
                      <input id="unlock-code" className="code-input" inputMode="numeric" autoComplete="one-time-code"
                             maxLength={6} required value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                             placeholder="••••••" autoFocus data-testid="unlock-code" />
                    </div>
                  </div>
                  {error && <Callout tone="negative" role="alert" data-testid="unlock-error"><p className="callout__text">{error}</p></Callout>}
                  <Button type="submit" variant="primary" size="lg" block arrow loading={busy} loadingText="Signing you in…">
                    Sign in
                  </Button>
                  <p className="t-caption c-tertiary auth__legal">
                    Wrong email? <button className="link" type="button" onClick={() => { setStep("email"); setError(""); }}>Change it</button>
                  </p>
                </form>
              </>
            )}

            {step === "done" && (
              <>
                <div className="auth__head">
                  <span className="auth__done" aria-hidden="true"><CircleCheck /></span>
                  <p className="t-eyebrow c-accent">You’re in</p>
                  <h2 id="signin-title" className="t-display-s">
                    {account.owner || signedBalance < 1 ? <>You’re <em>signed in</em></>
                      : signedBalance === 1 ? <>Your <em>1 credit</em> is ready</>
                      : <>Your <em>{signedBalance} credits</em> are ready</>}
                  </h2>
                  <p className="t-body-m c-secondary">
                    {!account.owner && signedBalance < 1
                      ? "Top up whenever you want a personal analysis or a comparison. Opening something you’ve already paid for is always free."
                      : "A personal analysis uses 1 credit, and comparing starts at 2. Opening something you’ve already paid for is always free."}
                  </p>
                </div>
                <Button variant="primary" size="lg" block arrow onClick={finishSignIn}>Continue</Button>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="overlay" role="presentation" data-testid="unlock-modal"
         onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal modal--wide" role="dialog" aria-modal="true" aria-labelledby="packs-title">
        {close}
        <div className="modal__head">
          <span className="mark" aria-hidden="true">u</span>
          <p className="t-eyebrow c-accent">Credits</p>
          <h2 id="packs-title" className="t-display-s">Top up your <em>credits</em></h2>
          <p className="t-body-m c-secondary">
            A personal analysis uses 1 credit, and comparing starts at 2. Reopening something you’ve paid for, answering the four questions or correcting a price costs nothing more.
          </p>
        </div>

        {packs && !packs.payments_enabled && (
          <Callout tone="info" title="Payments open soon" data-testid="payments-off">
            <p className="callout__text">Card and UPI payments aren’t switched on yet, so packs can’t be bought today. Your account and any credits on it are saved.</p>
          </Callout>
        )}

        <div className="packs">
          {(packs?.packs || []).map((pack, i) => (
            <button key={pack.pack_id} type="button" className={cx("pack", i === 1 && "pack--featured")} disabled={busy || (packs && !packs.payments_enabled)}
                    onClick={() => buy(pack)} data-testid={`pack-${pack.pack_id}`}>
              {i === 1 && <span className="pack__tag">Popular</span>}
              <span className="pack__credits">{pack.credits}</span>
              <span className="t-eyebrow c-tertiary">credits</span>
              <span className="pack__price">₹{pack.amount_display}</span>
            </button>
          ))}
          {!packs && [0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 156, borderRadius: 14 }} />)}
        </div>

        <ul className="pack-perks">
          <li><Check aria-hidden="true" />PDF report included with every pack</li>
          <li><Check aria-hidden="true" />Credits last a year</li>
          <li><Lock aria-hidden="true" />UPI and cards via Razorpay</li>
        </ul>

        <p className="t-caption c-tertiary" style={{ textAlign: "center" }}>
          Signed in{email ? ` as ${email}` : ""} ·{" "}
          <span title={CREDIT_EXPIRY_HINT}><strong className="c-primary" data-testid="modal-balance">{account.balance}</strong> {account.balance === 1 ? "credit" : "credits"}</span>
        </p>
        {notice && <Callout tone="positive" data-testid="unlock-notice"><p className="callout__text">{notice}</p></Callout>}
        {error && <Callout tone="negative" role="alert" data-testid="unlock-error"><p className="callout__text">{error}</p></Callout>}
      </div>
    </div>
  );
}

/*
 * The left half of the sign-in card: what signing in gets you, shown rather
 * than listed. Every number is the engine's real output for this formula on
 * oily skin, with acne and pigmentation chosen as concerns.
 */
function AuthAside() {
  return (
    <aside className="auth__aside" aria-hidden="true">
      <span className="wordmark wordmark--sm"><span>urancal</span><span className="wordmark__dot" /></span>
      <div className="auth__card">
        <p className="t-eyebrow c-tertiary">Example · your fit</p>
        <p className="auth__product">Niacinamide 10% + Zinc 1%</p>
        <div className="auth__fit">
          <ScoreRing score={97} size="sm" animate={false} label="Oily skin match" />
          <div>
            <p className="t-label-s">Suits oily skin</p>
            <p className="t-caption c-secondary">Low irritation risk</p>
          </div>
        </div>
        <Meter label="Acne & oily skin" value="77" pct={77} />
        <Meter label="Pigmentation" value="50" pct={50} />
      </div>
      <div className="auth__gift">
        <span className="auth__gift-num">4</span>
        <p className="t-body-s">free credits on your<br />first sign-in</p>
      </div>
    </aside>
  );
}

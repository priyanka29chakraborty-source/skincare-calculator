import { useLayoutEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";

import { API, api, describeError } from "../api";
import { Button, Callout } from "./ds";
import { MarketingNav, SiteFooter } from "./SiteChrome";

const NON_REFUNDABLE = "Payments for personalised analysis are non-refundable.";

const PAGES = {
  terms: {
    eyebrow: "Legal",
    title: "Terms of Service",
    body: [
      "The first time you sign in with your email, the account includes 4 credits. Signing in again with the same email does not add another 4. A personal analysis costs 1 credit. A comparison always includes at least two products, so it starts at 2 credits. Three products cost 3 and four cost 4, the most that can be compared at once. Opening the same product or the same comparison again does not spend another credit. After those credits are used, further analyses and comparisons need a credit pack.",
      "The product PDF is included once you buy any credit pack. The 4 sign-in credits do not include it. The comparison PDF is a separate document, and it is available only after that comparison has been run.",
      "The formulation score, the ingredient list, and safety warnings for a single product stay free.",
      "Unused credits expire one year after they are added. If you buy more while some are still left, those remaining credits last until the new credits expire. Credits that have already expired are not restored.",
      NON_REFUNDABLE,
      "This is an ingredient assessment from the label you entered. It is not a diagnosis or a prescription. If you are pregnant, breastfeeding, or on a prescription treatment, check with your doctor before changing what you use.",
    ],
  },
  privacy: {
    eyebrow: "Legal",
    title: "Privacy Policy",
    body: [
      "We store the email you sign in with, the products you choose to save, and the credit balance on that account. After you sign in, a saved product shows under Saved, and you can remove it from that list.",
      "If you send feedback and include an email for a reply, that note and address are stored so we can read them. They are not shown on the public site.",
      NON_REFUNDABLE,
    ],
  },
  feedback: {
    eyebrow: "Feedback",
    title: "Tell us what to fix",
    body: ["Tell us what was unclear or wrong on a result. A short note is enough — a person reads every one."],
  },
};

export function legalPageName() {
  return (window.location.hash || "").replace("#", "");
}

export function isLegalPage(page) {
  return Boolean(PAGES[page]);
}

function goBack() {
  if (window.history.length > 1) window.history.back();
  else window.location.hash = "";
}

export default function LegalPages({ page, account, openUnlock }) {
  const item = PAGES[page];
  // A hash link keeps the scroll position of the page it came from (often the
  // footer), so start every legal page at the top.
  useLayoutEffect(() => { window.scrollTo(0, 0); }, [page]);
  if (!item) return null;
  return (
    <div className="page" data-testid="skincare-app">
      <MarketingNav account={account} onSignIn={() => openUnlock("signin")} />
      <main className="container legal">
        <button type="button" className="link" onClick={goBack}><ArrowLeft aria-hidden="true" />Back</button>
        <p className="t-eyebrow c-accent">{item.eyebrow}</p>
        <h1 className="t-display-m">{item.title}</h1>
        <div className="legal__body">
          {item.body.map((paragraph) => <p key={paragraph} className="t-body-l c-secondary">{paragraph}</p>)}
        </div>
        {page === "feedback" && <FeedbackForm />}
      </main>
      <SiteFooter />
    </div>
  );
}

function FeedbackForm() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setErr(""); setMsg(""); setBusy(true);
    try {
      await api.post(`${API}/feedback`, { email, message });
      setMessage("");
      setEmail("");
      setMsg("Received — thank you.");
    } catch (error) {
      setErr(describeError(error));
    } finally { setBusy(false); }
  }

  return (
    <form onSubmit={submit} className="card legal__form">
      <div className="field">
        <label className="field__label" htmlFor="feedback-message">What should we look at?</label>
        <div className="field__control field__control--textarea">
          <textarea id="feedback-message" required minLength={3} rows={5} value={message}
                    onChange={(e) => setMessage(e.target.value)} style={{ fontFamily: "var(--font-sans)", fontSize: 15 }} />
        </div>
      </div>
      <div className="field">
        <label className="field__label" htmlFor="feedback-email">Your email</label>
        <div className="field__control">
          <input id="feedback-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
        </div>
        <p className="field__help">So we can reply. We never share it.</p>
      </div>
      <Button type="submit" variant="primary" arrow loading={busy} loadingText="Sending…">Send feedback</Button>
      {msg && <Callout tone="positive"><p className="callout__text">{msg}</p></Callout>}
      {err && <Callout tone="negative" role="alert"><p className="callout__text">{err}</p></Callout>}
    </form>
  );
}

import { useState } from "react";
import { API, api, describeError } from "../api";

const NON_REFUNDABLE =
  "Payments for personalised analysis are non-refundable.";

const PAGES = {
  terms: {
    title: "Terms of Service",
    body: [
      "The first time you sign in with your email, the account includes 4 credits. A personal analysis costs 1 credit. A comparison costs 2 credits. Opening the same product or the same pair again does not spend another credit. After those credits are used, further analyses and comparisons need a credit pack.",
      "The product PDF is included once you buy any credit pack. The 4 sign-in credits do not include it. The comparison PDF is a separate document, and it is available only after that comparison has been run.",
      "The formulation score, the ingredient list, and safety warnings for a single product stay free.",
      "Unused credits expire one year after they are added.",
      NON_REFUNDABLE,
      "This is an ingredient assessment from the label you entered. It is not a diagnosis or a prescription. If you are pregnant, breastfeeding, or on a prescription treatment, check with your doctor before changing what you use.",
    ],
  },
  privacy: {
    title: "Privacy Policy",
    body: [
      "We store the email you sign in with, the products you choose to save, and the credit balance on that account. After you sign in, a saved product shows under Previously analysed, and you can remove it from that list.",
      "If you send feedback and include an email for a reply, that note and address are stored so we can read them. They are not shown on the public site.",
      NON_REFUNDABLE,
    ],
  },
  feedback: {
    title: "Feedback",
    body: ["Tell us what was unclear or wrong on a result. A short note is enough."],
  },
};

export function legalPageName() {
  return (window.location.hash || "").replace("#", "");
}

export function isLegalPage(page) {
  return Boolean(PAGES[page]);
}

export default function LegalPages({ page, header = null }) {
  const item = PAGES[page];
  if (!item) return null;
  return (
    <main className="sc-app legal-page" data-testid="skincare-app">
      {header}
      <h1>{item.title}</h1>
      {item.body.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
      {page === "feedback" && <FeedbackForm />}
      <a className="legal-back" href="#app">Back</a>
    </main>
  );
}

function FeedbackForm() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  async function submit(e) {
    e.preventDefault();
    setErr(""); setMsg("");
    try {
      await api.post(`${API}/feedback`, { email, message });
      setMessage("");
      setEmail("");
      setMsg("Received. Thank you.");
    } catch (error) {
      setErr(describeError(error));
    }
  }

  return (
    <form onSubmit={submit} className="legal-form">
      <label className="field-label" htmlFor="feedback-message">What should we look at?</label>
      <textarea id="feedback-message" className="field-input" required minLength={3}
                value={message} onChange={(e) => setMessage(e.target.value)} />
      <label className="field-label" htmlFor="feedback-email">Email, if you want a reply</label>
      <input id="feedback-email" className="field-input" type="email" value={email}
             onChange={(e) => setEmail(e.target.value)} />
      <button className="personalise-update" type="submit">Send</button>
      {msg && <p>{msg}</p>}
      {err && <p role="alert">{err}</p>}
    </form>
  );
}

export function LegalFooter() {
  return (
    <footer className="no-print legal-footer">
      <a href="#terms">Terms of Service</a>
      <a href="#privacy">Privacy Policy</a>
      <a href="#feedback">Feedback</a>
    </footer>
  );
}

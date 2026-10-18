import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowRight, Menu, X } from "lucide-react";

import { Button, Wordmark } from "./ds";
import { ANALYSE_PATH, linkTo, navigate } from "../lib/router";

const LINKS = [
  ["How it works", "/#how"],
  ["What you get", "/#features"],
  ["Method", "/#method"],
  ["Pricing", "/#pricing"],
  ["FAQ", "/#faq"],
];

/** Sticky marketing navigation. Gains a hairline once the page scrolls. */
export function MarketingNav({ account, onSignIn }) {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; };
  }, [open]);

  const signedIn = account && !account.loading && account.signedIn;

  return (
    <header className="mnav" data-scrolled={scrolled} data-testid="marketing-nav">
      <div className="container mnav__inner">
        <Wordmark onClick={linkTo("/")} />
        <nav className="mnav__links" aria-label="Main">
          {LINKS.map(([label, href]) => (
            <a key={href} href={href} onClick={linkTo(href)}>{label}</a>
          ))}
        </nav>
        <div className="mnav__actions">
          {!signedIn && (
            <Button variant="ghost" className="hide-mobile" onClick={onSignIn} data-testid="sign-in">
              Sign in
            </Button>
          )}
          <Button as="a" href={ANALYSE_PATH} onClick={linkTo(ANALYSE_PATH)} variant="primary" arrow
                  className="hide-mobile">
            {signedIn ? "Open the analyser" : "Analyse a product"}
          </Button>
          <Button variant="ghost" className="mnav__menu btn--icon" aria-label="Open menu"
                  aria-expanded={open} onClick={() => setOpen(true)} icon={<Menu />} />
        </div>
      </div>

      {/* Portalled: the header's blur would otherwise trap a fixed sheet inside it. */}
      {open && createPortal(
        <div className="overlay sheet-overlay" role="presentation" onClick={() => setOpen(false)}>
          <div className="sheet" role="dialog" aria-modal="true" aria-label="Menu" onClick={(e) => e.stopPropagation()}>
            <div className="sheet__head">
              <span className="t-eyebrow c-tertiary">Menu</span>
              <button className="modal__close" style={{ position: "static" }} onClick={() => setOpen(false)} aria-label="Close menu">
                <X />
              </button>
            </div>
            <div className="sheet__body">
              <nav className="mobile-links" aria-label="Main">
                {LINKS.map(([label, href]) => (
                  <a key={href} href={href} onClick={linkTo(href, () => setOpen(false))}>
                    <span>{label}</span><ArrowRight aria-hidden="true" />
                  </a>
                ))}
              </nav>
              <div className="stack" style={{ "--stack-gap": "10px", marginTop: "auto" }}>
                <Button variant="primary" size="lg" block arrow
                        onClick={() => { setOpen(false); navigate(ANALYSE_PATH); }}>
                  Analyse a product
                </Button>
                {!signedIn && (
                  <Button variant="secondary" size="lg" block onClick={() => { setOpen(false); onSignIn(); }}>
                    Sign in
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </header>
  );
}

/** Dark footer shared by the landing page, legal pages and the app. */
export function SiteFooter({ compact }) {
  const year = new Date().getFullYear();
  return (
    <footer className="footer no-print" data-testid="site-footer">
      <div className="container">
        {!compact && (
          <div className="footer__top">
            <div className="footer__brand">
              <Wordmark inverse onClick={linkTo("/")} />
              <p className="t-body-s" style={{ color: "var(--text-inverse-secondary)" }}>
                Clear, ingredient-by-ingredient verdicts on skincare — so you know what you’re paying for before you buy.
              </p>
            </div>
            <div className="footer__cols">
              <FooterCol title="Product" links={[
                ["Analyse a product", ANALYSE_PATH],
                ["Compare products", `${ANALYSE_PATH}?view=compare`],
                ["Pricing", "/#pricing"],
              ]} />
              <FooterCol title="Learn" links={[
                ["How scoring works", "/#method"],
                ["What you get", "/#features"],
                ["FAQ", "/#faq"],
              ]} />
              <FooterCol title="Company" links={[
                ["Privacy", "#privacy"],
                ["Terms", "#terms"],
                ["Feedback", "#feedback"],
              ]} />
            </div>
          </div>
        )}
        <div className="footer__bottom" style={compact ? { borderTop: 0 } : undefined}>
          <span>Educational use only — not medical advice. Some links are affiliate links; we may earn a commission at no cost to you.</span>
          <span>© {year} Urancal</span>
        </div>
      </div>
    </footer>
  );
}

function FooterCol({ title, links }) {
  return (
    <div className="footer__col">
      <span className="t-eyebrow" style={{ color: "var(--text-inverse-accent)" }}>{title}</span>
      {links.map(([label, href]) => (
        href.startsWith("#")
          ? <a key={label} href={href}>{label}</a>
          : <a key={label} href={href} onClick={linkTo(href)}>{label}</a>
      ))}
    </div>
  );
}

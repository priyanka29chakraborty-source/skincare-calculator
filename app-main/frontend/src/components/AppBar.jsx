import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowRight, Coins, History, LogOut, Menu, Plus, User, X } from "lucide-react";

import { Button, Wordmark, cx } from "./ds";
import { ANALYSE_PATH, linkTo } from "../lib/router";
import { CREDIT_EXPIRY_HINT } from "../constants";

/**
 * The signed-in tool's top bar. The credit balance is always visible: a paid
 * product should never hide what is being spent.
 */
export default function AppBar({ account, view, onOpenSaved, onSignIn, onTopUp }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!navOpen) return undefined;
    const onKey = (e) => { if (e.key === "Escape") setNavOpen(false); };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; };
  }, [navOpen]);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const onDown = (e) => { if (!menuRef.current?.contains(e.target)) setMenuOpen(false); };
    const onKey = (e) => { if (e.key === "Escape") setMenuOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [menuOpen]);

  const signedIn = !account.loading && account.signedIn;

  return (
    <header className="appbar no-print" data-testid="account-bar">
      <div className="container appbar__inner">
        <div className="appbar__left">
          <Wordmark small />
          <nav className="appbar__nav" aria-label="Analyser">
            <a className="appbar__item" href={ANALYSE_PATH} onClick={linkTo(ANALYSE_PATH)}
               aria-current={view === "analyse" ? "page" : undefined}>Analyse</a>
            <button className="appbar__item" type="button" onClick={onOpenSaved}>Saved</button>
            <a className="appbar__item" href={`${ANALYSE_PATH}?view=compare`} onClick={linkTo(`${ANALYSE_PATH}?view=compare`)}
               aria-current={view === "compare" ? "page" : undefined}>Compare</a>
          </nav>
        </div>

        <div className="appbar__right">
          {signedIn ? (
            <>
              {account.owner ? (
                <span className="credits-pill">Signed in</span>
              ) : (
                <span className="credits-pill" title={CREDIT_EXPIRY_HINT}>
                  <Coins aria-hidden="true" />
                  <span data-testid="account-balance">{account.balance}</span>
                  <span>{account.balance === 1 ? "credit" : "credits"}</span>
                </span>
              )}
              {!account.owner && (
                <button className="link hide-mobile" type="button" onClick={onTopUp} data-testid="top-up">
                  {account.balance === 0 ? "Get credits" : "Top up"}
                </button>
              )}
              <div className="menu-wrap" ref={menuRef}>
                <button className="avatar" type="button" aria-haspopup="menu" aria-expanded={menuOpen}
                        aria-label="Account menu" onClick={() => setMenuOpen((v) => !v)}>
                  <User aria-hidden="true" />
                </button>
                {menuOpen && (
                  <div className="menu" role="menu">
                    <div className="menu__meta">
                      <p className="t-label-s">Your account</p>
                      <p className="t-caption c-tertiary">{account.owner ? "Owner access" : `${account.balance} ${account.balance === 1 ? "credit" : "credits"} left`}</p>
                    </div>
                    <button className="menu__item" role="menuitem" type="button" onClick={() => { setMenuOpen(false); onOpenSaved(); }}>
                      <History /> Saved analyses
                    </button>
                    {!account.owner && (
                      <button className="menu__item" role="menuitem" type="button" onClick={() => { setMenuOpen(false); onTopUp(); }}>
                        <Plus /> Top up credits
                      </button>
                    )}
                    <button className="menu__item" role="menuitem" type="button" data-testid="sign-out"
                            onClick={() => { setMenuOpen(false); account.signOut(); }}>
                      <LogOut /> Sign out
                    </button>
                  </div>
                )}
              </div>
            </>
          ) : (
            <Button variant={account.loading ? "ghost" : "secondary"} size="sm" onClick={onSignIn}
                    className={cx(account.loading && "is-loading")} data-testid="sign-in">
              Sign in
            </Button>
          )}
          <Button variant="ghost" className="appbar__menu btn--icon" aria-label="Open menu" aria-expanded={navOpen}
                  onClick={() => setNavOpen(true)} icon={<Menu />} />
        </div>
      </div>

      {/* Portalled so no ancestor style (blur, transform) can clip the sheet. */}
      {navOpen && createPortal(
        <div className="overlay sheet-overlay" role="presentation" onClick={() => setNavOpen(false)}>
          <div className="sheet" role="dialog" aria-modal="true" aria-label="Menu" onClick={(e) => e.stopPropagation()}>
            <div className="sheet__head">
              <span className="t-eyebrow c-tertiary">Menu</span>
              <button className="modal__close" style={{ position: "static" }} onClick={() => setNavOpen(false)} aria-label="Close menu"><X /></button>
            </div>
            <div className="sheet__body">
              <nav className="mobile-links" aria-label="Analyser">
                <a href={ANALYSE_PATH} onClick={linkTo(ANALYSE_PATH, () => setNavOpen(false))}><span>Analyse a product</span><ArrowRight aria-hidden="true" /></a>
                <a href="#saved" onClick={(e) => { e.preventDefault(); setNavOpen(false); onOpenSaved(); }}><span>Saved analyses</span><ArrowRight aria-hidden="true" /></a>
                <a href={`${ANALYSE_PATH}?view=compare`} onClick={linkTo(`${ANALYSE_PATH}?view=compare`, () => setNavOpen(false))}><span>Compare products</span><ArrowRight aria-hidden="true" /></a>
                <a href="/" onClick={linkTo("/", () => setNavOpen(false))}><span>Home</span><ArrowRight aria-hidden="true" /></a>
              </nav>
              <div className="stack" style={{ "--stack-gap": "10px", marginTop: "auto" }}>
                {signedIn ? (
                  <>
                    {!account.owner && <p className="t-body-s c-secondary">You have {account.balance} {account.balance === 1 ? "credit" : "credits"}.</p>}
                    {!account.owner && <Button variant="secondary" size="lg" block icon={<Plus />} onClick={() => { setNavOpen(false); onTopUp(); }}>Top up credits</Button>}
                    <Button variant="ghost" size="lg" block icon={<LogOut />} onClick={() => { setNavOpen(false); account.signOut(); }}>Sign out</Button>
                  </>
                ) : (
                  <Button variant="primary" size="lg" block onClick={() => { setNavOpen(false); onSignIn(); }}>Sign in — 4 free credits</Button>
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

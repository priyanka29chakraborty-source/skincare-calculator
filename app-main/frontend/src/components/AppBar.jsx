import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowRight, Coins, History, Info, LogOut, Menu, Plus, User, X } from "lucide-react";

import { Button, Wordmark, cx } from "./ds";
import { API, api } from "../api";
import { ANALYSE_PATH, linkTo } from "../lib/router";
import { CREDIT_EXPIRY_HINT, CREDIT_RULE } from "../constants";

function when(ts) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

// Credit activity worth showing: what was added, and when.
function activityLine(row) {
  if (row.reason === "grant" && row.delta > 0) return `${row.delta} free credits`;
  if (row.reason === "purchase" && row.delta > 0) return `${row.delta} credits bought`;
  return "";
}

/**
 * The signed-in tool's top bar. The credit balance is always visible: a paid
 * product should never hide what is being spent.
 */
export default function AppBar({ account, view, onOpenSaved, onSignIn, onTopUp }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [ruleOpen, setRuleOpen] = useState(false);
  const [activity, setActivity] = useState([]);
  const menuRef = useRef(null);

  // The menu shows recent credit activity; fetch it when it opens.
  useEffect(() => {
    if (!menuOpen || !account.signedIn || account.owner) return undefined;
    let cancelled = false;
    api.get(`${API}/credits/history`)
      .then(({ data }) => { if (!cancelled) setActivity((data.entries || []).filter((row) => activityLine(row))); })
      .catch(() => { if (!cancelled) setActivity([]); });
    return () => { cancelled = true; };
  }, [menuOpen, account.signedIn, account.owner, account.balance]);

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
  // Top up only once payments are switched on; until then there is nothing to buy.
  const canTopUp = signedIn && !account.owner && account.paymentsEnabled;
  const letter = (account.email || "").trim().charAt(0).toUpperCase();

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
              {canTopUp && (
                <button className="link hide-mobile" type="button" onClick={onTopUp} data-testid="top-up">
                  {account.balance === 0 ? "Get credits" : "Top up"}
                </button>
              )}
              <div className="menu-wrap" ref={menuRef}>
                <button className="avatar" type="button" aria-haspopup="menu" aria-expanded={menuOpen}
                        aria-label="Account menu" onClick={() => setMenuOpen((v) => !v)} data-testid="account-menu">
                  {letter || <User aria-hidden="true" />}
                </button>
                {menuOpen && (
                  <div className="menu menu--account" role="menu" data-testid="account-dropdown">
                    <div className="menu__account">
                      <span className="avatar avatar--lg" aria-hidden="true">{letter || <User />}</span>
                      <div className="menu__who">
                        <p className="t-label-s">{account.owner ? "Owner access" : "Your account"}</p>
                        {account.email && <p className="t-caption c-tertiary menu__email">{account.email}</p>}
                      </div>
                    </div>

                    {!account.owner && (
                      <div className="menu__credits">
                        <div className="menu__balance-row">
                          <p className="menu__balance">
                            <span className="menu__balance-num">{account.balance}</span>
                            {account.balance === 1 ? "credit" : "credits"} remaining
                          </p>
                          <button type="button" className="menu__info" aria-expanded={ruleOpen}
                                  aria-label="How credits work" onClick={() => setRuleOpen((v) => !v)} data-testid="credit-info">
                            <Info aria-hidden="true" />
                          </button>
                        </div>
                        <p className="t-caption c-tertiary" data-testid="credit-expiry">
                          {account.balance > 0 && account.creditsExpireAt
                            ? `Valid until ${when(account.creditsExpireAt)}`
                            : "No credits left"}
                        </p>
                        {ruleOpen && <p className="menu__rule" data-testid="credit-rule">{CREDIT_RULE}</p>}
                        {activity.length > 0 && (
                          <ul className="menu__activity" aria-label="Recent credit activity">
                            {activity.slice(0, 3).map((row) => (
                              <li key={row.entry_id || `${row.reason}-${row.created_at}`}>
                                <span>{activityLine(row)}</span>
                                <span>{when(row.created_at)}</span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}

                    <button className="menu__item" role="menuitem" type="button" onClick={() => { setMenuOpen(false); onOpenSaved(); }}>
                      <History /> Saved products and comparisons
                    </button>
                    {canTopUp && (
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
                <a href="#saved" onClick={(e) => { e.preventDefault(); setNavOpen(false); onOpenSaved(); }}><span>Saved products and comparisons</span><ArrowRight aria-hidden="true" /></a>
                <a href={`${ANALYSE_PATH}?view=compare`} onClick={linkTo(`${ANALYSE_PATH}?view=compare`, () => setNavOpen(false))}><span>Compare products</span><ArrowRight aria-hidden="true" /></a>
                <a href="/" onClick={linkTo("/", () => setNavOpen(false))}><span>Home</span><ArrowRight aria-hidden="true" /></a>
              </nav>
              <div className="stack" style={{ "--stack-gap": "10px", marginTop: "auto" }}>
                {signedIn ? (
                  <>
                    {!account.owner && <p className="t-body-s c-secondary">You have {account.balance} {account.balance === 1 ? "credit" : "credits"}.</p>}
                    {canTopUp && <Button variant="secondary" size="lg" block icon={<Plus />} onClick={() => { setNavOpen(false); onTopUp(); }}>Top up credits</Button>}
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

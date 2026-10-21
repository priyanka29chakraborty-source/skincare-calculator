import { useCallback, useEffect, useRef, useState } from "react";

import Landing from "./pages/Landing";
import Analyser from "./pages/Analyser";
import LegalPages, { isLegalPage } from "./components/LegalPages";
import UnlockModal from "./components/UnlockModal";
import useAccount from "./hooks/useAccount";
import { ANALYSE_PATH, useRoute } from "./lib/router";

/**
 * Root: one account, one sign-in dialog, three kinds of page.
 *
 *   /            landing page
 *   /analyse     the analyser (also opened by a ?share= link on any path)
 *   #terms etc.  legal pages, over whichever page is underneath
 */
function App() {
  const route = useRoute();
  const account = useAccount();

  const [unlockOpen, setUnlockOpen] = useState(false);
  const [unlockPurpose, setUnlockPurpose] = useState("signin");
  // What the person was doing when sign-in opened, so the heading matches it.
  const [unlockTopic, setUnlockTopic] = useState("account");
  const afterSignIn = useRef(null);
  // The analyser registers what to do after a purchase (re-run the analysis,
  // so the person sees what they just paid for without pressing anything).
  const onPurchasedRef = useRef(null);

  const openUnlock = useCallback((purpose = "signin", after = null, topic = "account") => {
    afterSignIn.current = after;
    setUnlockPurpose(purpose);
    setUnlockTopic(topic);
    setUnlockOpen(true);
  }, []);

  // Copying result text is blocked outside form fields - kept from the
  // original app, where scraped copies of results were a problem.
  useEffect(() => {
    const block = (e) => {
      const el = e.target;
      if (el && el.closest && el.closest("input, textarea, select")) return;
      e.preventDefault();
    };
    document.addEventListener("copy", block);
    document.addEventListener("cut", block);
    return () => {
      document.removeEventListener("copy", block);
      document.removeEventListener("cut", block);
    };
  }, []);

  const hasShare = new URLSearchParams(route.search).has("share");
  const onAnalyser = route.path === ANALYSE_PATH || hasShare;

  useEffect(() => {
    document.title = isLegalPage(route.hash)
      ? "Urancal"
      : onAnalyser
        ? "Analyse a product | Urancal"
        : "Skincare Product Worth Calculator | Urancal";
  }, [onAnalyser, route.hash]);

  let page;
  if (isLegalPage(route.hash)) {
    page = <LegalPages page={route.hash} account={account} openUnlock={openUnlock} />;
  } else if (onAnalyser) {
    page = <Analyser route={route} account={account} openUnlock={openUnlock} onPurchasedRef={onPurchasedRef} />;
  } else {
    page = <Landing account={account} openUnlock={openUnlock} />;
  }

  return (
    <>
      {page}
      <UnlockModal
        open={unlockOpen}
        purpose={unlockPurpose}
        topic={unlockTopic}
        account={account}
        onClose={() => setUnlockOpen(false)}
        onSignedIn={() => {
          const next = afterSignIn.current;
          afterSignIn.current = null;
          if (next) next();
        }}
        onPurchased={() => {
          setUnlockOpen(false);
          if (onPurchasedRef.current) onPurchasedRef.current();
        }}
      />
    </>
  );
}

export default App;

import { useEffect, useState } from "react";

/*
 * A deliberately tiny router: the site has two real pages (the landing page at
 * "/" and the analyser at "/analyse") plus hash-addressed legal pages. That
 * does not justify a routing dependency. The host already rewrites every path
 * to index.html (public/_redirects).
 */

const EVENT = "urancal:navigate";

export const ANALYSE_PATH = "/analyse";

function current() {
  return {
    path: window.location.pathname.replace(/\/+$/, "") || "/",
    hash: (window.location.hash || "").replace("#", ""),
    search: window.location.search,
  };
}

export function navigate(to, { replace = false, state = null } = {}) {
  const url = new URL(to, window.location.origin);
  const samePath = url.pathname === window.location.pathname;
  if (replace) window.history.replaceState(state, "", url);
  else window.history.pushState(state, "", url);
  window.dispatchEvent(new Event(EVENT));
  if (url.hash) {
    // The target may be on a page that has not rendered yet, so try now and
    // again once React has committed the new route.
    const id = url.hash.slice(1);
    const go = () => {
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({ behavior: samePath ? "smooth" : "auto", block: "start" });
      return Boolean(el);
    };
    requestAnimationFrame(() => { if (!go()) setTimeout(go, 120); });
  } else if (!samePath) {
    window.scrollTo({ top: 0 });
  }
}

/** onClick helper for <a href> so links keep working with cmd/ctrl-click. */
export function linkTo(to, extra) {
  return (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    if (extra) extra();
    navigate(to);
  };
}

export function useRoute() {
  const [route, setRoute] = useState(current);
  useEffect(() => {
    const update = () => setRoute(current());
    window.addEventListener("popstate", update);
    window.addEventListener("hashchange", update);
    window.addEventListener(EVENT, update);
    return () => {
      window.removeEventListener("popstate", update);
      window.removeEventListener("hashchange", update);
      window.removeEventListener(EVENT, update);
    };
  }, []);
  return route;
}

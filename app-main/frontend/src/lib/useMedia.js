import { useEffect, useState } from "react";

/** True while the media query matches. Used where a CSS-only switch is not
 *  enough - for example to render exactly one ad unit rather than hiding one. */
export default function useMedia(query) {
  const get = () => (typeof window !== "undefined" && window.matchMedia
    ? window.matchMedia(query).matches : false);
  const [matches, setMatches] = useState(get);
  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

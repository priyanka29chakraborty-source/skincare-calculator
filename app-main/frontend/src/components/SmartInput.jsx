import React from "react";
import { ClipboardList, Link as LinkIcon, ScanBarcode, Search } from "lucide-react";

import { Button } from "./ds";

/** What someone pasted: a product page, a barcode, an INCI list, or a name. */
export function detectInput(raw) {
  const v = String(raw || "").trim();
  if (!v) return "empty";
  if (/^https?:\/\//i.test(v) || /^www\./i.test(v)) return "url";
  if (/^\d{8,14}$/.test(v)) return "barcode";
  if ((v.match(/,/g) || []).length >= 2) return "list";
  return "name";
}

const ICONS = { url: LinkIcon, barcode: ScanBarcode, list: ClipboardList, name: Search, empty: LinkIcon };

/**
 * The hero interaction: one field that takes a link, a barcode or a pasted
 * ingredient list, and shows which it recognised.
 */
export default function SmartInput({
  value, onChange, onSubmit, buttonLabel = "Analyse product", loading, loadingText,
  placeholder = "Paste a product link or barcode", inputRef, id = "smart-input",
  buttonArrow = true, disabled, testId, onEmpty,
}) {
  const kind = detectInput(value);
  const Icon = ICONS[kind] || LinkIcon;
  const localRef = React.useRef(null);
  const ref = inputRef || localRef;
  return (
    <form className="smart" role="search"
          onSubmit={(e) => {
            e.preventDefault();
            // An empty submit is not an error. Where there is somewhere to go
            // (the landing page opens the analyser) go there; otherwise put the
            // cursor where it is needed.
            if (kind === "empty") {
              if (onEmpty) onEmpty(); else ref.current?.focus();
              return;
            }
            onSubmit?.();
          }}>
      <div className="smart__field">
        <Icon className="smart__icon" aria-hidden="true" />
        <label htmlFor={id} className="sr-only">Product link or barcode</label>
        <input id={id} ref={ref} value={value} onChange={(e) => onChange(e.target.value)}
               placeholder={placeholder} autoComplete="off" spellCheck={false}
               data-testid={testId || "fetch-input"} />
      </div>
      <Button type="submit" variant="primary" arrow={buttonArrow && !loading} loading={loading}
              loadingText={loadingText} disabled={disabled}
              data-testid="smart-submit">
        {buttonLabel}
      </Button>
    </form>
  );
}

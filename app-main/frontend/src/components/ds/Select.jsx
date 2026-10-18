import React, { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";

const cx = (...c) => c.filter(Boolean).join(" ");

/*
 * A dropdown that looks like the rest of the form. The browser's own <select>
 * list cannot be styled - on Windows it draws options flush against the edge
 * in the system font - so this replaces it with a listbox that follows the
 * ARIA select-only combobox pattern: arrow keys, Home/End, Enter or Space to
 * choose, Escape to close, and typing a few letters jumps to a match.
 *
 * options: strings, or { value, label, meta } where meta is a short muted
 * note on the right (a currency symbol, say).
 */
export default function Select({
  id, value, onChange, options, labelledBy, ariaLabel, placeholder = "Choose…", className, testId,
}) {
  const opts = options.map((o) => (typeof o === "string" ? { value: o, label: o } : o));
  const reactId = useId().replace(/:/g, "");
  const baseId = id || `select-${reactId}`;
  const listId = `${baseId}-list`;
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [pos, setPos] = useState(null);
  const triggerRef = useRef(null);
  const listRef = useRef(null);
  const typed = useRef({ text: "", at: 0 });

  const selectedIndex = opts.findIndex((o) => o.value === value);
  const selected = opts[selectedIndex];

  // Open below the field, or above it when there is not enough room below.
  const place = useCallback(() => {
    const r = triggerRef.current?.getBoundingClientRect();
    if (!r) return;
    const gap = 6;
    const margin = 12;
    const vh = window.innerHeight;
    const wanted = Math.min(420, opts.length * 42 + 14);
    const below = vh - r.bottom - gap - margin;
    const above = r.top - gap - margin;
    const up = below < Math.min(wanted, 220) && above > below;
    setPos({
      left: r.left,
      width: r.width,
      top: up ? undefined : r.bottom + gap,
      bottom: up ? vh - r.top + gap : undefined,
      maxHeight: Math.max(132, Math.min(wanted, up ? above : below)),
      up,
    });
  }, [opts.length]);

  const openMenu = (start) => {
    place();
    setActive(start ?? (selectedIndex >= 0 ? selectedIndex : 0));
    setOpen(true);
  };

  const close = useCallback((returnFocus = true) => {
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  }, []);

  const choose = (i) => {
    const o = opts[i];
    if (!o) return;
    if (o.value !== value) onChange(o.value);
    close();
  };

  useLayoutEffect(() => {
    if (open) listRef.current?.focus({ preventScroll: true });
  }, [open]);

  // Keep the highlighted option in view while moving with the keyboard. This
  // scrolls the list only - scrollIntoView would also move the page.
  useEffect(() => {
    const list = listRef.current;
    const el = open && active >= 0 ? list?.querySelector(`[data-index="${active}"]`) : null;
    if (!el) return;
    const pad = 6;
    if (el.offsetTop - pad < list.scrollTop) list.scrollTop = el.offsetTop - pad;
    else if (el.offsetTop + el.offsetHeight + pad > list.scrollTop + list.clientHeight) {
      list.scrollTop = el.offsetTop + el.offsetHeight + pad - list.clientHeight;
    }
  }, [open, active]);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (listRef.current?.contains(e.target) || triggerRef.current?.contains(e.target)) return;
      close(false);
    };
    const onScroll = (e) => {
      // Scrolling the list itself must not move it; scrolling the page does.
      if (listRef.current && e.target instanceof Node && listRef.current.contains(e.target)) return;
      place();
    };
    document.addEventListener("mousedown", onDown);
    window.addEventListener("resize", place);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open, place, close]);

  function typeAhead(key) {
    const now = Date.now();
    const t = typed.current;
    t.text = now - t.at < 600 ? t.text + key.toLowerCase() : key.toLowerCase();
    t.at = now;
    const i = opts.findIndex((o) => String(o.label).toLowerCase().startsWith(t.text));
    if (i >= 0) setActive(i);
  }

  function onTriggerKey(e) {
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
      e.preventDefault();
      if (e.key === "ArrowUp") openMenu(Math.max(0, selectedIndex - 1));
      else openMenu();
    }
  }

  function onListKey(e) {
    const last = opts.length - 1;
    const keys = {
      ArrowDown: () => setActive((a) => Math.min(last, a + 1)),
      ArrowUp: () => setActive((a) => Math.max(0, a - 1)),
      Home: () => setActive(0),
      End: () => setActive(last),
      PageDown: () => setActive((a) => Math.min(last, a + 5)),
      PageUp: () => setActive((a) => Math.max(0, a - 5)),
      Enter: () => choose(active),
      " ": () => choose(active),
      Escape: () => close(),
      Tab: () => close(),
    };
    if (keys[e.key]) {
      e.preventDefault();
      e.stopPropagation();
      keys[e.key]();
    } else if (e.key.length === 1 && !e.metaKey && !e.ctrlKey && !e.altKey) {
      typeAhead(e.key);
    }
  }

  return (
    <>
      <button type="button" id={baseId} ref={triggerRef}
              className={cx("field__control", "select", open && "is-open", className)}
              aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? listId : undefined}
              aria-labelledby={labelledBy ? `${labelledBy} ${baseId}` : undefined}
              aria-label={labelledBy ? undefined : ariaLabel}
              onClick={() => (open ? close() : openMenu())} onKeyDown={onTriggerKey}
              data-testid={testId} data-value={value}>
        <span className={cx("select__value", !selected && "select__value--empty")}>{selected ? selected.label : placeholder}</span>
        {selected?.meta && <span className="select__meta">{selected.meta}</span>}
        <ChevronDown className="select__chevron" aria-hidden="true" />
      </button>

      {open && pos && createPortal(
        <ul id={listId} ref={listRef} role="listbox" tabIndex={-1}
            className={cx("select__menu", pos.up && "select__menu--up")}
            aria-labelledby={labelledBy} aria-label={labelledBy ? undefined : ariaLabel}
            aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
            style={{ left: pos.left, top: pos.top, bottom: pos.bottom, minWidth: pos.width, maxHeight: pos.maxHeight }}
            onKeyDown={onListKey} data-testid={testId ? `${testId}-menu` : undefined}>
          {opts.map((o, i) => (
            <li key={o.value} id={`${listId}-${i}`} role="option" aria-selected={o.value === value} data-index={i}
                className={cx("select__option", i === active && "is-active")}
                onMouseEnter={() => setActive(i)} onMouseDown={(e) => e.preventDefault()} onClick={() => choose(i)}>
              <span className="select__label">{o.label}</span>
              {o.meta && <span className="select__meta">{o.meta}</span>}
              <Check className="select__check" aria-hidden="true" />
            </li>
          ))}
        </ul>,
        document.body,
      )}
    </>
  );
}

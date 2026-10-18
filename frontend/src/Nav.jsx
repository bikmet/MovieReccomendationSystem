import { useEffect, useRef, useState } from "react";

export function Logo() {
  return (
    <a
      className="logo"
      href="#top"
      aria-label="NextWatch home"
      onClick={(e) => {
        e.preventDefault();
        window.scrollTo({ top: 0, behavior: "smooth" });
      }}
    >
      <svg viewBox="0 0 32 32" aria-hidden="true">
        <defs>
          <linearGradient id="nw-g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#7a8aff" />
            <stop offset="1" stopColor="#3a4ad8" />
          </linearGradient>
        </defs>
        <rect width="32" height="32" rx="9" fill="url(#nw-g)" />
        <path d="M12.5 9.5v13l10.5-6.5z" fill="#fff" />
        <circle cx="25.5" cy="6.5" r="2.6" fill="#ffc15e" />
      </svg>
      <span className="wordmark">
        Next<b>Watch</b>
      </span>
    </a>
  );
}

export default function Nav({ query, setQuery, pickCount, onPicks }) {
  const input = useRef(null);
  const [scrolled, setScrolled] = useState(false);

  // The bar gets a frosted background once the page scrolls under it.
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Press "/" anywhere to jump to the search box.
  useEffect(() => {
    const onKey = (e) => {
      const tag = document.activeElement?.tagName;
      if (e.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA") {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <header className={`nav${scrolled ? " scrolled" : ""}`}>
      <div className="nav-inner">
        <Logo />
        <div className="searchbox">
          <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="11" cy="11" r="6.5" />
            <path d="M16 16l4.5 4.5" />
          </svg>
          <input
            ref={input}
            type="search"
            aria-label="Search for a movie"
            placeholder="Search movies you like"
            autoComplete="off"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                setQuery("");
                e.currentTarget.blur();
              }
            }}
          />
          {query ? (
            <button className="clear" aria-label="Clear search" onClick={() => { setQuery(""); input.current?.focus(); }}>
              <svg className="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
            </button>
          ) : (
            <kbd aria-hidden="true">/</kbd>
          )}
        </div>
        {pickCount > 0 && (
          <button className="picks-btn" onClick={onPicks}>
            <span className="label">My picks</span>
            <span key={pickCount} className="badge">{pickCount}</span>
          </button>
        )}
      </div>
    </header>
  );
}

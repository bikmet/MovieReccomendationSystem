import { useRef } from "react";

// A titled horizontal row that scrolls sideways (children must be <li> elements).
export default function Rail({ title, action, children }) {
  const track = useRef(null);

  function scroll(direction) {
    const el = track.current;
    if (!el) return;
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollBy({ left: direction * el.clientWidth * 0.85, behavior: calm ? "auto" : "smooth" });
  }

  return (
    <section className="rail">
      <div className="rail-head">
        <h2>{title}</h2>
        {action}
      </div>
      <div className="rail-wrap">
        <button className="arrow left" aria-label="Scroll left" onClick={() => scroll(-1)}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7" /></svg>
        </button>
        <ul className="rail-track" ref={track}>
          {children}
        </ul>
        <button className="arrow right" aria-label="Scroll right" onClick={() => scroll(1)}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5l7 7-7 7" /></svg>
        </button>
      </div>
    </section>
  );
}

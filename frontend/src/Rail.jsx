import { useCallback, useEffect, useRef, useState } from "react";

const calmMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
const GLIDE_MS = 450; // how long one arrow click takes to move the row
const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

// Becomes true the first time the element scrolls into view (used to fade rows in).
function useReveal() {
  const ref = useRef(null);
  const [shown, setShown] = useState(typeof IntersectionObserver === "undefined");
  useEffect(() => {
    if (shown || !ref.current) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShown(true);
          io.disconnect();
        }
      },
      { rootMargin: "0px 0px -6% 0px", threshold: 0.05 }
    );
    io.observe(ref.current);
    return () => io.disconnect();
  }, [shown]);
  return [ref, shown];
}

// A titled horizontal row that scrolls sideways (children must be <li> elements).
export default function Rail({ id, title, action, children }) {
  const track = useRef(null);
  const [ref, shown] = useReveal();

  const glide = useRef(null); // { target, frame } while a scroll animation is running

  const stop = useCallback(() => {
    if (glide.current) cancelAnimationFrame(glide.current.frame);
    glide.current = null;
  }, []);
  useEffect(() => stop, [stop]); // stop animating if the row is removed

  // Arrow click: ease the row sideways by ~85% of its visible width.
  // Clicking again mid-glide extends the same movement instead of restarting it.
  function scroll(direction) {
    const el = track.current;
    if (!el) return;
    const from = el.scrollLeft;
    const base = glide.current ? glide.current.target : from;
    const max = el.scrollWidth - el.clientWidth;
    const target = Math.max(0, Math.min(max, base + direction * el.clientWidth * 0.85));
    stop();
    if (calmMotion() || target === from) {
      el.scrollLeft = target;
      return;
    }
    const start = performance.now();
    const state = { target, frame: 0 };
    glide.current = state;
    const step = (now) => {
      const t = Math.max(0, Math.min(1, (now - start) / GLIDE_MS));
      el.scrollLeft = from + (target - from) * easeInOutCubic(t);
      if (t < 1) state.frame = requestAnimationFrame(step);
      else glide.current = null;
    };
    state.frame = requestAnimationFrame(step);
  }

  return (
    <section id={id} ref={ref} className={`rail reveal${shown ? " in" : ""}`}>
      <div className="rail-head">
        <h2>{title}</h2>
        {action}
      </div>
      <div className="rail-wrap">
        <button className="arrow left" aria-label="Scroll left" onClick={() => scroll(-1)}>
          <svg className="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7" /></svg>
        </button>
        <ul className="rail-track" ref={track} onWheel={stop} onTouchStart={stop} onPointerDown={stop}>
          {children}
        </ul>
        <button className="arrow right" aria-label="Scroll right" onClick={() => scroll(1)}>
          <svg className="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5l7 7-7 7" /></svg>
        </button>
      </div>
    </section>
  );
}

// Shimmering placeholder row shown while the home page loads.
export function SkeletonRail() {
  return (
    <section className="rail" role="status" aria-label="Loading movies">
      <div className="rail-head">
        <div className="skeleton sk-title" />
      </div>
      <ul className="rail-track">
        {Array.from({ length: 9 }, (_, i) => (
          <li className="card" key={i}>
            <div className="art skeleton" />
            <div className="skeleton sk-cap" />
          </li>
        ))}
      </ul>
    </section>
  );
}

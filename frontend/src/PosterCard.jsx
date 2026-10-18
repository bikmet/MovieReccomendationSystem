import { useState } from "react";
import { formatTitle } from "./format";

export default function PosterCard({ movie, poster, picked, onToggle, rank, disabled }) {
  const { name, year } = formatTitle(movie.title);
  const [broken, setBroken] = useState(false); // poster URL failed to load -> use the placeholder

  return (
    <li className="card">
      <div className="art">
        {poster && !broken ? (
          <img src={poster} alt={`${name} poster`} loading="lazy" onError={() => setBroken(true)} />
        ) : (
          // No poster (no TMDB key, or none found): a colour derived from the id + the title
          <div className="fallback" style={{ "--h": movie.movieId % 360 }}>
            <span>{name}</span>
          </div>
        )}
        {rank && <span className="rank">{rank}</span>}
        <button
          className="add"
          aria-pressed={picked}
          aria-label={picked ? `Remove ${name} from your picks` : `Add ${name} to your picks`}
          onClick={() => onToggle(movie)}
          disabled={disabled && !picked}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d={picked ? "M5 13l4 4L19 7" : "M12 5v14M5 12h14"} />
          </svg>
        </button>
      </div>
      <p className="cap" title={movie.title}>
        <span className="name">{name}</span>
        <span className="year">{year}</span>
      </p>
    </li>
  );
}

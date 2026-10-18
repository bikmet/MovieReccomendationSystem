import { useCallback, useEffect, useRef, useState } from "react";
import { getHome, getPosters, recommendForNewUser, recommendForUser, searchMovies } from "./api";
import PosterCard from "./PosterCard";
import Rail from "./Rail";

const MAX_PICKS = 10;

export default function App() {
  const [home, setHome] = useState(null); // { rows: [{ title, movies }] }
  const [homeError, setHomeError] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [picked, setPicked] = useState([]);
  const [recs, setRecs] = useState(null); // movies recommended from the picks
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [userId, setUserId] = useState("");
  const [userRecs, setUserRecs] = useState(null); // { movies, note }
  const [userLoading, setUserLoading] = useState(false);
  const [userError, setUserError] = useState("");
  const [posters, setPosters] = useState({}); // movieId -> poster url | null
  const [postersOn, setPostersOn] = useState(true);
  const asked = useRef(new Set()); // movieIds whose poster we've already requested

  // Home page rows load once on startup.
  const loadHome = useCallback(async () => {
    setHomeError("");
    try {
      setHome(await getHome());
    } catch (e) {
      setHomeError(e.message);
    }
  }, []);
  useEffect(() => {
    loadHome();
  }, [loadHome]);

  // Any movie that appears anywhere on screen gets its poster fetched (once, in batches).
  useEffect(() => {
    if (!postersOn) return;
    const all = [
      ...(home?.rows.flatMap((r) => r.movies) ?? []),
      ...results,
      ...picked,
      ...(recs ?? []),
      ...(userRecs?.movies ?? []),
    ];
    const ids = [...new Set(all.map((m) => m.movieId))].filter((id) => !asked.current.has(id));
    if (!ids.length) return;
    ids.forEach((id) => asked.current.add(id));
    (async () => {
      for (let i = 0; i < ids.length; i += 50) {
        try {
          const data = await getPosters(ids.slice(i, i + 50));
          setPostersOn(data.enabled);
          setPosters((p) => ({ ...p, ...data.posters }));
        } catch {
          /* posters are optional: cards fall back to a placeholder */
        }
      }
    })();
  }, [home, results, picked, recs, userRecs, postersOn]);

  // Search as you type: wait 300 ms after the last keystroke, cancel stale requests.
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      setSearching(false);
      return;
    }
    const ctrl = new AbortController();
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        setResults(await searchMovies(q, 12, ctrl.signal));
        setError("");
      } catch (e) {
        if (e.name !== "AbortError") setError(e.message);
      } finally {
        if (!ctrl.signal.aborted) setSearching(false);
      }
    }, 300);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [query]);

  const isPicked = (movie) => picked.some((p) => p.movieId === movie.movieId);

  function togglePick(movie) {
    setPicked((prev) =>
      prev.some((p) => p.movieId === movie.movieId)
        ? prev.filter((p) => p.movieId !== movie.movieId)
        : prev.length < MAX_PICKS
        ? [...prev, movie]
        : prev
    );
  }

  async function getRecommendations() {
    setLoading(true);
    setError("");
    try {
      const data = await recommendForNewUser(picked.map((m) => m.movieId));
      setRecs(data.recommendations);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function getUserRecommendations() {
    setUserLoading(true);
    setUserError("");
    try {
      const data = await recommendForUser(Number(userId));
      setUserRecs({
        movies: data.recommendations,
        note: data.personalized
          ? ""
          : `User ${userId} isn't in the data, so these are the most popular movies instead.`,
      });
    } catch (e) {
      setUserError(e.message);
    } finally {
      setUserLoading(false);
    }
  }

  const card = (movie, extra = {}) => (
    <PosterCard
      key={movie.movieId}
      movie={movie}
      poster={posters[movie.movieId]}
      picked={isPicked(movie)}
      onToggle={togglePick}
      disabled={picked.length >= MAX_PICKS}
      {...extra}
    />
  );

  const q = query.trim();

  return (
    <div className="app">
      <section className="hero">
        <h1>Next watch</h1>
        <p>Add movies you love with the + button, then get recommendations picked for your taste.</p>
        <input
          className="search"
          type="search"
          aria-label="Search for a movie"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search for a movie you like, like “matrix” or “toy story”"
          autoComplete="off"
        />
        {!postersOn && (
          <p className="status">Posters are off. Add TMDB_API_KEY to your .env file to show them.</p>
        )}
      </section>

      {q &&
        (searching && results.length === 0 ? (
          <p className="status">Searching…</p>
        ) : results.length === 0 ? (
          <p className="status">No movies match “{q}”.</p>
        ) : (
          <Rail title={`Results for “${q}”`}>{results.map((m) => card(m))}</Rail>
        ))}

      {picked.length > 0 ? (
        <Rail
          title={
            <>
              Your picks{" "}
              <span className="count">
                {picked.length} of {MAX_PICKS}
              </span>
            </>
          }
          action={
            <button className="go" onClick={getRecommendations} disabled={loading}>
              {loading ? "Finding movies…" : "Get recommendations"}
            </button>
          }
        >
          {picked.map((m) => card(m))}
        </Rail>
      ) : (
        !q && <p className="status">Your picks will show up here. Add 3 to 5 movies for the best results.</p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {recs && <Rail title="Recommended for you">{recs.map((m, i) => card(m, { rank: i + 1 }))}</Rail>}

      <div className="browse">
        {homeError ? (
          <p className="error" role="alert">
            {homeError} <button className="link" onClick={loadHome}>Try again</button>
          </p>
        ) : !home ? (
          <p className="status">Loading movies…</p>
        ) : (
          home.rows.map((row) => (
            <Rail key={row.title} title={row.title}>
              {row.movies.map((m) => card(m))}
            </Rail>
          ))
        )}
      </div>

      <section className="user">
        <h2>Already have a user ID?</h2>
        <p className="status">We'll use what that user rated highly in the dataset. Unknown IDs get popular movies.</p>
        <div className="inline">
          <input
            aria-label="User ID"
            inputMode="numeric"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="User ID, for example 1"
          />
          <button
            className="go"
            onClick={getUserRecommendations}
            disabled={!/^\d+$/.test(userId.trim()) || userLoading}
          >
            {userLoading ? "Finding movies…" : "Show recommendations"}
          </button>
        </div>
        {userError && (
          <p className="error" role="alert">
            {userError}
          </p>
        )}
        {userRecs && (
          <>
            {userRecs.note && <p className="note">{userRecs.note}</p>}
            <Rail title="Picked from your ratings">
              {userRecs.movies.map((m, i) => card(m, { rank: i + 1 }))}
            </Rail>
          </>
        )}
      </section>

      {postersOn && (
        <footer>This product uses the TMDB API but is not endorsed or certified by TMDB.</footer>
      )}
    </div>
  );
}

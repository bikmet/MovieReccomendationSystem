import { useEffect, useState } from "react";
import { recommendForNewUser, recommendForUser, searchMovies } from "./api";

const MAX_PICKS = 10;

// "Matrix, The (1999)" -> { name: "The Matrix", year: "1999" }
function formatTitle(raw) {
  const m = raw.match(/^(.*) \((\d{4})\)$/);
  let name = m ? m[1] : raw;
  const article = name.match(/^(.*), (The|A|An)$/);
  if (article) name = `${article[2]} ${article[1]}`;
  return { name, year: m ? m[2] : "" };
}

export default function App() {
  const [mode, setMode] = useState("new"); // "new" = pick movies, "user" = existing user id
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [picked, setPicked] = useState([]);
  const [userId, setUserId] = useState("");
  const [recs, setRecs] = useState(null); // { movies, note }
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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
        setResults(await searchMovies(q, 8, ctrl.signal));
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

  const canSubmit = mode === "new" ? picked.length > 0 : /^\d+$/.test(userId.trim());

  async function getRecommendations() {
    setLoading(true);
    setError("");
    try {
      if (mode === "new") {
        const data = await recommendForNewUser(picked.map((m) => m.movieId));
        setRecs({ movies: data.recommendations, note: "" });
      } else {
        const data = await recommendForUser(Number(userId));
        setRecs({
          movies: data.recommendations,
          note: data.personalized
            ? ""
            : `User ${userId} isn't in the data, so these are the most popular movies instead.`,
        });
      }
    } catch (e) {
      setError(e.message);
      setRecs(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app">
      <header>
        <h1>Next watch</h1>
        <p>Pick a few movies you love and get a list of what to watch next.</p>
      </header>

      <main>
        <section className="panel" aria-label="Your taste">
          <div className="segmented">
            <button aria-pressed={mode === "new"} onClick={() => setMode("new")}>
              Pick movies
            </button>
            <button aria-pressed={mode === "user"} onClick={() => setMode("user")}>
              I have a user ID
            </button>
          </div>

          {mode === "new" ? (
            <>
              <label htmlFor="search">Search for a movie you like</label>
              <input
                id="search"
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Try “matrix” or “toy story”"
                autoComplete="off"
              />
              {query.trim() && (
                <ul className="results">
                  {searching && <li className="hint">Searching…</li>}
                  {!searching && results.length === 0 && (
                    <li className="hint">No movies match “{query.trim()}”.</li>
                  )}
                  {results.map((m) => {
                    const { name, year } = formatTitle(m.title);
                    return (
                      <li key={m.movieId}>
                        <button
                          aria-pressed={isPicked(m)}
                          onClick={() => togglePick(m)}
                          disabled={!isPicked(m) && picked.length >= MAX_PICKS}
                        >
                          <span>
                            {name} <span className="year">{year}</span>
                          </span>
                          <span className="action">{isPicked(m) ? "Added" : "Add"}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}

              <h2>
                Your picks <span className="count">{picked.length} of {MAX_PICKS}</span>
              </h2>
              {picked.length === 0 ? (
                <p className="hint">Search above and add 3 to 5 movies for the best results.</p>
              ) : (
                <ul className="chips">
                  {picked.map((m) => (
                    <li key={m.movieId}>
                      {formatTitle(m.title).name}
                      <button
                        aria-label={`Remove ${formatTitle(m.title).name}`}
                        onClick={() => togglePick(m)}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <>
              <label htmlFor="uid">User ID</label>
              <input
                id="uid"
                inputMode="numeric"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                placeholder="For example 1"
              />
              <p className="hint">
                Uses what that user rated highly in the dataset. Unknown IDs get popular movies.
              </p>
            </>
          )}

          <button className="go" onClick={getRecommendations} disabled={!canSubmit || loading}>
            {loading ? "Finding movies…" : "Get recommendations"}
          </button>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
        </section>

        <section className="out" aria-live="polite" aria-label="Recommendations">
          {recs ? (
            <>
              {recs.note && <p className="note">{recs.note}</p>}
              <ol className="tickets">
                {recs.movies.map((m, i) => {
                  const { name, year } = formatTitle(m.title);
                  return (
                    <li className="ticket" key={m.movieId}>
                      <span className="stub">{i + 1}</span>
                      <div className="body">
                        <h3>
                          {name} <span className="year">{year}</span>
                        </h3>
                        <p>{m.genres.join(", ")}</p>
                      </div>
                    </li>
                  );
                })}
              </ol>
            </>
          ) : (
            <p className="empty">Your recommendations will appear here.</p>
          )}
        </section>
      </main>
    </div>
  );
}

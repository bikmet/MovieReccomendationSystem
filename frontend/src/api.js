// All talking to the FastAPI backend lives here, so components never build URLs themselves.
const BASE = import.meta.env?.VITE_API_URL ?? "http://127.0.0.1:8000";

async function request(path, options) {
  let res;
  try {
    res = await fetch(`${BASE}${path}`, options);
  } catch (err) {
    if (err.name === "AbortError") throw err; // a cancelled search is not an error
    throw new Error("Can't reach the API. Start it with: uvicorn api:app --reload");
  }
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail; // our own 400/404 messages
    } catch {
      /* body wasn't JSON; keep the generic message */
    }
    throw new Error(message);
  }
  return res.json();
}

export const searchMovies = (q, limit = 8, signal) =>
  request(`/movies/search?q=${encodeURIComponent(q)}&limit=${limit}`, { signal });

export const recommendForNewUser = (movieIds, n = 12) =>
  request("/recommendations/new-user", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ liked_movie_ids: movieIds, n }),
  });

export const recommendForUser = (userId, n = 12) =>
  request(`/recommendations/${userId}?n=${n}`);

export const getHome = () => request("/home");

export const getPosters = (ids) =>
  request(`/posters?${ids.map((id) => `ids=${id}`).join("&")}`);

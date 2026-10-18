"""
Movie poster lookup using the TMDB API (https://www.themoviedb.org/).

- Uses links.csv (movieId -> tmdbId) when it exists: exact match.
- Otherwise searches TMDB by title + year.
- Results are cached in memory; with no API key everything returns None and the
  frontend shows placeholders.
"""
import asyncio
import logging
import os
import re

import httpx
import pandas as pd

log = logging.getLogger("posters")
IMAGE_BASE = "https://image.tmdb.org/t/p/w342"


def load_tmdb_ids(data_dir):
    path = os.path.join(data_dir, "links.csv")
    if not os.path.exists(path):
        return {}
    links = pd.read_csv(path).dropna(subset=["tmdbId"])
    return dict(zip(links["movieId"].astype(int), links["tmdbId"].astype(int)))


def clean_title(raw):
    """'Matrix, The (1999)' -> ('The Matrix', '1999')"""
    m = re.match(r"^(.*) \((\d{4})\)\s*$", raw)
    name, year = (m.group(1), m.group(2)) if m else (raw, None)
    name = name.split(" (")[0]                       # drop alternate titles in brackets
    a = re.match(r"^(.*), (The|A|An)$", name)
    if a:
        name = f"{a.group(2)} {a.group(1)}"
    return name, year


class PosterService:
    def __init__(self, client, api_key, titles, tmdb_ids):
        self.client = client                         # httpx.AsyncClient with TMDB base_url
        self.api_key = api_key or ""
        self.titles = titles                         # DataFrame indexed by movieId
        self.tmdb_ids = tmdb_ids
        self.enabled = bool(self.api_key)
        self.cache = {}                              # movieId -> poster url or None
        self.sem = asyncio.Semaphore(8)              # at most 8 TMDB requests at once

    def _auth(self):
        if self.api_key.startswith("eyJ"):           # v4 "read access token"
            return {"Authorization": f"Bearer {self.api_key}"}, {}
        return {}, {"api_key": self.api_key}         # v3 API key

    async def _json(self, path, **params):
        headers, auth = self._auth()
        r = await self.client.get(path, params={**auth, **params}, headers=headers)
        if r.status_code in (401, 403):
            log.warning("TMDB rejected the API key (HTTP %s); posters disabled", r.status_code)
            self.enabled = False
            return None
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    async def _poster_path(self, movie_id):
        tmdb_id = self.tmdb_ids.get(movie_id)
        if tmdb_id:
            data = await self._json(f"/movie/{tmdb_id}")
            return data.get("poster_path") if data else None
        name, year = clean_title(self.titles.at[movie_id, "title"])
        attempts = ([{"query": name, "year": year}] if year else []) + [{"query": name}]
        for params in attempts:
            if not self.enabled:
                return None
            data = await self._json("/search/movie", **params)
            for hit in (data or {}).get("results", []):
                if hit.get("poster_path"):
                    return hit["poster_path"]
        return None

    async def poster_for(self, movie_id):
        if movie_id in self.cache:
            return self.cache[movie_id]
        if not self.enabled or movie_id not in self.titles.index:
            return None
        try:
            async with self.sem:
                path = await self._poster_path(movie_id)
        except httpx.HTTPError as e:                 # (never log str(e): it contains the URL + API key)
            log.warning("TMDB lookup failed for movie %s (%s)", movie_id, type(e).__name__)
            return None                              # temporary problem: don't cache it
        url = f"{IMAGE_BASE}{path}" if path else None
        if self.enabled:
            self.cache[movie_id] = url
        return url

    async def posters(self, ids):
        unique = list(dict.fromkeys(ids))
        urls = await asyncio.gather(*(self.poster_for(i) for i in unique))
        return dict(zip(unique, urls))

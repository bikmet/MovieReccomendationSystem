"""
FastAPI layer for the movie recommender.

Run:   uvicorn api:app --reload
Docs:  http://127.0.0.1:8000/docs
Posters: put TMDB_API_KEY=... in a .env file next to this file (optional).
"""

import logging
import os
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from posters import PosterService, load_tmdb_ids
from reccomendationsystem import DATA_DIR, MODEL_PATH, load_recommender

load_dotenv()                                        # reads .env into environment variables
HOME_GENRES = ["Action", "Comedy", "Drama", "Sci-Fi", "Animation", "Thriller", "Romance", "Horror"]


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class Movie(BaseModel):
    movieId: int
    title: str
    genres: list[str]
    score: float | None = None


class RecommendationResponse(BaseModel):
    userId: int
    personalized: bool
    recommendations: list[Movie]


class NewUserRequest(BaseModel):
    liked_movie_ids: list[int] = Field(..., min_length=1, max_length=50)
    n: int = Field(10, ge=1, le=50)


class NewUserResponse(BaseModel):
    used_movie_ids: list[int]
    ignored_movie_ids: list[int]
    recommendations: list[Movie]


class LikedResponse(BaseModel):
    userId: int
    liked: list[Movie]


class Row(BaseModel):                                # one horizontal row on the home page
    title: str
    movies: list[Movie]


class HomeResponse(BaseModel):
    rows: list[Row]


class PostersResponse(BaseModel):
    enabled: bool                                    # False = no TMDB key, so no posters
    posters: dict[int, str | None]


class HealthResponse(BaseModel):
    status: str
    users: int
    movies: int


# --------------------------------------------------------------------------- #
# Startup / shutdown
# --------------------------------------------------------------------------- #
def to_movies(df, with_score=True):
    return [
        Movie(movieId=int(r.movieId), title=r.title, genres=r.genres.split("|"),
              score=float(r.score) if with_score else None)
        for r in df.itertuples()
    ]


def build_home(rec):
    """Netflix-style rows, computed once at startup (they don't change per request)."""
    rows = [Row(title="Most loved", movies=to_movies(rec.popular(limit=20), with_score=False))]
    for genre in HOME_GENRES:
        df = rec.popular(genre=genre, limit=20)
        if not df.empty:
            rows.append(Row(title=f"Top in {genre}", movies=to_movies(df, with_score=False)))
    return HomeResponse(rows=rows)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.path.exists(MODEL_PATH):
        raise RuntimeError(f"{MODEL_PATH} not found. Train first: python reccomendationsystem.py")
    rec = load_recommender(MODEL_PATH)
    app.state.recommender = rec
    app.state.home = build_home(rec)

    client = httpx.AsyncClient(base_url="https://api.themoviedb.org/3", timeout=8.0)
    app.state.posters = PosterService(
        client, os.getenv("TMDB_API_KEY"), rec.titles, load_tmdb_ids(DATA_DIR))
    if not app.state.posters.enabled:
        logging.getLogger("uvicorn.error").warning(
            "TMDB_API_KEY is not set: posters are off (placeholders will be shown)")
    yield
    await client.aclose()


app = FastAPI(title="Movie Recommendation API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def get_recommender(request: Request):
    return request.app.state.recommender


def get_posters(request: Request):
    return request.app.state.posters


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health", response_model=HealthResponse)
def health(rec=Depends(get_recommender)):
    return HealthResponse(status="ok", users=len(rec.user_ids), movies=len(rec.movie_ids))


@app.get("/home", response_model=HomeResponse)
def home(request: Request):
    """Rows for the home page: most loved overall, then the top movies in each genre."""
    return request.app.state.home


@app.get("/posters", response_model=PostersResponse)
async def posters(
    ids: list[int] = Query(..., max_length=50),      # /posters?ids=1&ids=2&ids=3
    service: PosterService = Depends(get_posters),
):
    """Poster image URLs from TMDB for a batch of movieIds (null where none found)."""
    return PostersResponse(enabled=service.enabled, posters=await service.posters(ids))


@app.get("/recommendations/{user_id}", response_model=RecommendationResponse)
def recommendations(user_id: int, n: int = Query(10, ge=1, le=50), rec=Depends(get_recommender)):
    df = rec.recommend(user_id, n)
    return RecommendationResponse(
        userId=user_id, personalized=user_id in rec.user_index, recommendations=to_movies(df))


@app.post("/recommendations/new-user", response_model=NewUserResponse)
def recommendations_new_user(body: NewUserRequest, rec=Depends(get_recommender)):
    """Cold start: send a few movies you like, get recommendations."""
    ids = list(dict.fromkeys(body.liked_movie_ids))
    used = [m for m in ids if m in rec.movie_index]
    ignored = [m for m in ids if m not in rec.movie_index]
    if not used:
        raise HTTPException(status_code=400, detail="None of the given movie IDs exist")
    df = rec.recommend_for_new_user(used, body.n)
    return NewUserResponse(used_movie_ids=used, ignored_movie_ids=ignored,
                           recommendations=to_movies(df))


@app.get("/users/{user_id}/liked", response_model=LikedResponse)
def liked_movies(user_id: int, limit: int = Query(20, ge=1, le=100), rec=Depends(get_recommender)):
    if user_id not in rec.user_index:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    idx = rec.L[rec.user_index[user_id]].indices[:limit]
    df = rec.titles.loc[rec.movie_ids[idx]].reset_index()
    return LikedResponse(userId=user_id, liked=to_movies(df, with_score=False))


@app.get("/movies/search", response_model=list[Movie])
def search_movies(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    rec=Depends(get_recommender),
):
    """Find movies by title (case-insensitive), most popular first."""
    return to_movies(rec.search(q, limit), with_score=False)

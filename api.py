"""
FastAPI layer for the movie recommender.

Run:   uvicorn api:app --reload
Docs:  http://127.0.0.1:8000/docs   (interactive, auto-generated)
"""

from contextlib import asynccontextmanager
import os

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Importing from this module is also what lets pickle find the MovieRecommender class
from reccomendationsystem import MODEL_PATH, load_recommender


# --------------------------------------------------------------------------- #
# 1. Schemas (Pydantic): the exact shape of what the API sends back
# --------------------------------------------------------------------------- #
class Movie(BaseModel):
    movieId: int
    title: str
    genres: list[str]
    score: float | None = None      # only recommendations have a score


class RecommendationResponse(BaseModel):
    userId: int
    personalized: bool              # False = unknown user, got popular movies instead
    recommendations: list[Movie]


class LikedResponse(BaseModel):
    userId: int
    liked: list[Movie]


class NewUserRequest(BaseModel):                  # the JSON body the client POSTs
    liked_movie_ids: list[int] = Field(..., min_length=1, max_length=50)
    n: int = Field(10, ge=1, le=50)


class NewUserResponse(BaseModel):
    used_movie_ids: list[int]                     # ids the model recognised
    ignored_movie_ids: list[int]                  # ids not in the dataset
    recommendations: list[Movie]


class HealthResponse(BaseModel):
    status: str
    users: int
    movies: int


# --------------------------------------------------------------------------- #
# 2. Startup: load the model ONCE, not on every request
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.path.exists(MODEL_PATH):
        raise RuntimeError(
            f"{MODEL_PATH} not found. Train first: python reccomendationsystem.py")
    app.state.recommender = load_recommender(MODEL_PATH)
    yield                            # the app serves requests while paused here
    # (anything after yield runs at shutdown)


app = FastAPI(title="Movie Recommendation API", version="0.1.0", lifespan=lifespan)

# Lets a React dev server (different port = different "origin") call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# 3. Dependency: endpoints ask for the loaded model instead of using a global
# --------------------------------------------------------------------------- #
def get_recommender(request: Request):
    return request.app.state.recommender


def to_movies(df, with_score=True):
    return [
        Movie(
            movieId=int(row.movieId),
            title=row.title,
            genres=row.genres.split("|"),
            score=float(row.score) if with_score else None,
        )
        for row in df.itertuples()
    ]


# --------------------------------------------------------------------------- #
# 4. Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health", response_model=HealthResponse)
def health(rec=Depends(get_recommender)):
    """Is the server up and is the model loaded?"""
    return HealthResponse(status="ok", users=len(rec.user_ids), movies=len(rec.movie_ids))


@app.get("/recommendations/{user_id}", response_model=RecommendationResponse)
def recommendations(
    user_id: int,                                   # path parameter, validated as int
    n: int = Query(10, ge=1, le=50),                # query parameter: ?n=10 (1-50)
    rec=Depends(get_recommender),
):
    """Top-n movies for a user, based on the movies they rated highly."""
    df = rec.recommend(user_id, n)
    return RecommendationResponse(
        userId=user_id,
        personalized=user_id in rec.user_index,
        recommendations=to_movies(df),
    )


@app.get("/users/{user_id}/liked", response_model=LikedResponse)
def liked_movies(
    user_id: int,
    limit: int = Query(20, ge=1, le=100),
    rec=Depends(get_recommender),
):
    """Movies this user rated highly (the taste the model learned from)."""
    if user_id not in rec.user_index:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    idx = rec.L[rec.user_index[user_id]].indices[:limit]
    df = rec.titles.loc[rec.movie_ids[idx]].reset_index()
    return LikedResponse(userId=user_id, liked=to_movies(df, with_score=False))


@app.get("/movies/search", response_model=list[Movie])
def search_movies(
    q: str = Query(..., min_length=1),              # required: /movies/search?q=matrix
    limit: int = Query(20, ge=1, le=100),
    rec=Depends(get_recommender),
):
    """Find movies by title (case-insensitive), most popular first."""
    return to_movies(rec.search(q, limit), with_score=False)


@app.post("/recommendations/new-user", response_model=NewUserResponse)
def recommendations_new_user(body: NewUserRequest, rec=Depends(get_recommender)):
    """Cold start: send a few movies you like, get recommendations (3-5+ picks work best)."""
    ids = list(dict.fromkeys(body.liked_movie_ids))          # drop duplicates, keep order
    used = [m for m in ids if m in rec.movie_index]
    ignored = [m for m in ids if m not in rec.movie_index]
    if not used:
        raise HTTPException(status_code=400, detail="None of the given movie IDs exist")
    df = rec.recommend_for_new_user(used, body.n)
    return NewUserResponse(used_movie_ids=used, ignored_movie_ids=ignored,
                           recommendations=to_movies(df))
"""
Movie recommendation backend: hybrid recommender (no LightFM needed).
Dependencies: pandas, numpy, scipy, scikit-learn, implicit.

Pipeline
  1. Load movies / ratings / tags.
  2. Merge all tags that share a movieId into one text field.
  3. Put the merged tags into the ratings dataset (ratings + movies + tags).
  4. Feature engineering: genres (multi-hot) + tags (TF-IDF) -> item feature vectors.
  5. Two models, blended:
       - Collaborative: ALS matrix factorization (implicit library) on users' high ratings
       - Content-based: user taste profile = average feature vector of the
         movies they rated highly, scored by cosine similarity to every movie
  6. recommend(user_id) -> top-N movies the user has not rated yet.

Usage
  python reccomendationsystem.py
  from reccomendationsystem import recommend_movies
  recommend_movies(user_id=1, n=10)
"""

import os
import pickle

# implicit's ALS runs its own threads; keep BLAS single-threaded (recommended by the library)
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import numpy as np
import pandas as pd
from implicit.als import AlternatingLeastSquares
from scipy import sparse
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import MultiLabelBinarizer, normalize

DATA_DIR = "dataset"
MODEL_PATH = "recommender.pkl"
MERGED_CSV = "ratings_with_tags.csv"
LIKE_THRESHOLD = 4.0   # ratings >= this count as "liked"
RANDOM_STATE = 42


# --------------------------------------------------------------------------- #
# 1-3. Load + merge
# --------------------------------------------------------------------------- #
def load_data(data_dir=DATA_DIR):
    # os.path.join: works on Windows/Mac/Linux (no "\m" escape problems)
    movies = pd.read_csv(os.path.join(data_dir, "movies.csv"))
    ratings = pd.read_csv(os.path.join(data_dir, "ratings.csv"))
    tags = pd.read_csv(os.path.join(data_dir, "tags.csv"))
    return movies, ratings, tags


def merge_tags_per_movie(tags):
    """Combine every tag on the same movieId into a single lowercase string."""
    tags = tags.dropna(subset=["tag"]).copy()
    tags["tag"] = tags["tag"].astype(str).str.lower().str.strip()
    return (
        tags.groupby("movieId")["tag"].apply(" ".join)
        .reset_index().rename(columns={"tag": "tags"})
    )


def build_ratings_dataset(movies, ratings, tags):
    """ratings + movie title/genres + merged tags, one row per rating."""
    df = ratings.merge(movies, on="movieId", how="left")
    df = df.merge(merge_tags_per_movie(tags), on="movieId", how="left")
    df["tags"] = df["tags"].fillna("")
    df["genres"] = df["genres"].fillna("(no genres listed)")
    return df


# --------------------------------------------------------------------------- #
# 4. Feature engineering
# --------------------------------------------------------------------------- #
def build_item_features(movies, merged_tags, genre_weight=1.0,
                        tag_weight=1.0, max_tag_features=500):
    """Sparse (n_movies x n_features) matrix: [genres multi-hot | tags TF-IDF]."""
    items = movies.merge(merged_tags, on="movieId", how="left")
    items["tags"] = items["tags"].fillna("")
    items["genres"] = items["genres"].fillna("(no genres listed)")

    mlb = MultiLabelBinarizer(sparse_output=True)
    genre_m = normalize(mlb.fit_transform(items["genres"].str.split("|"))
                        .astype(np.float32)) * genre_weight

    tfidf = TfidfVectorizer(max_features=max_tag_features, ngram_range=(1, 2),
                            min_df=2, stop_words="english", sublinear_tf=True)
    try:
        tag_m = normalize(tfidf.fit_transform(items["tags"]).astype(np.float32)) * tag_weight
    except ValueError:  # no usable tags at all
        tag_m = sparse.csr_matrix((len(items), 0), dtype=np.float32)

    F = sparse.hstack([genre_m, tag_m]).tocsr()
    return normalize(F), items["movieId"].to_numpy(), mlb, tfidf


def _zscore_rows(x):
    return (x - x.mean(axis=1, keepdims=True)) / (x.std(axis=1, keepdims=True) + 1e-9)


# --------------------------------------------------------------------------- #
# 5. Model
# --------------------------------------------------------------------------- #
class MovieRecommender:
    def __init__(self, factors=16, reg=0.05, confidence=10.0, iterations=15, alpha=0.9):
        """ALS settings: factors / reg / confidence / iterations.
        alpha = weight of collaborative score (1-alpha goes to content score).
        (factors=16 beat 32 and 64 across several random splits on MovieLens-small.)"""
        self.factors = factors
        self.reg = reg
        self.confidence = confidence
        self.iterations = iterations
        self.alpha = alpha

    # ---- training ---------------------------------------------------------
    def fit(self, movies, ratings, tags, evaluate=True):
        merged_tags = merge_tags_per_movie(tags)
        self.F, self.movie_ids, self.mlb, self.tfidf = build_item_features(movies, merged_tags)
        self.movie_index = {m: i for i, m in enumerate(self.movie_ids)}
        self.user_ids = np.sort(ratings["userId"].unique())
        self.user_index = {u: i for i, u in enumerate(self.user_ids)}
        self.titles = movies.set_index("movieId")[["title", "genres"]]

        df = ratings[ratings["movieId"].isin(self.movie_index)]
        shape = (len(self.user_ids), len(self.movie_ids))
        r = df["userId"].map(self.user_index).to_numpy()
        c = df["movieId"].map(self.movie_index).to_numpy()
        # A = every rated movie (used to hide "already seen"); L = liked only
        self.A = sparse.csr_matrix((np.ones(len(df), np.float32), (r, c)), shape=shape)
        liked = df["rating"].to_numpy() >= LIKE_THRESHOLD
        self.L = sparse.csr_matrix((np.ones(liked.sum(), np.float32), (r[liked], c[liked])), shape=shape)

        self.metrics = self._evaluate() if evaluate else {}
        self._train(self.L)          # final model uses ALL liked ratings
        return self

    def _train(self, L):
        als = AlternatingLeastSquares(
            factors=self.factors, regularization=self.reg, alpha=self.confidence,
            iterations=self.iterations, random_state=RANDOM_STATE, use_gpu=False)
        als.fit(L, show_progress=False)                    # L: users x movies
        self.U = np.asarray(als.user_factors)              # user factors
        self.V = np.asarray(als.item_factors).T            # movie factors
        self.P = normalize(L @ self.F)                     # user taste profiles
        self.pop = np.asarray(L.sum(axis=0)).ravel()       # popularity
        self._L, self._A = L, None

    # ---- scoring ----------------------------------------------------------
    def _scores(self, rows, alpha=None, mode="hybrid"):
        alpha = self.alpha if alpha is None else alpha
        if mode == "popularity":
            return np.tile(self.pop, (len(rows), 1)).astype(np.float64)
        if mode == "svd":                                   # comparison baseline (eval only)
            return _zscore_rows(self._svd_U[rows] @ self._svd_V)
        cf = _zscore_rows(self.U[rows] @ self.V)
        content = _zscore_rows((self.P[rows] @ self.F.T).toarray())
        if mode == "cf":
            return cf
        if mode == "content":
            return content
        return alpha * cf + (1 - alpha) * content

    # ---- evaluation (random 20% holdout of each user's liked movies) ------
    def _evaluate(self, k=10, seen_users_min=5):
        rng = np.random.default_rng(RANDOM_STATE)
        L = self.L.tocoo()
        n_liked = np.asarray(self.L.sum(axis=1)).ravel()
        eligible = n_liked[L.row] >= seen_users_min
        is_test = (rng.random(L.nnz) < 0.2) & eligible
        T = sparse.csr_matrix((np.ones(is_test.sum(), np.float32), (L.row[is_test], L.col[is_test])), shape=L.shape)
        L_train = (self.L - T).tocsr(); L_train.eliminate_zeros()
        A_train = (self.A - T).tocsr(); A_train.eliminate_zeros()

        self._train(L_train)
        svd = TruncatedSVD(n_components=50, random_state=RANDOM_STATE)   # baseline for comparison
        self._svd_U, self._svd_V = svd.fit_transform(L_train), svd.components_
        users = np.where(np.asarray(T.sum(axis=1)).ravel() > 0)[0]

        results = {}
        modes = {"popularity": ("popularity", None), "collaborative (SVD)": ("svd", None),
                 "collaborative (ALS)": ("cf", None),
                 "content": ("content", None)}
        for a in (0.3, 0.5, 0.7, 0.9):
            modes[f"hybrid a={a}"] = ("hybrid", a)
        for name, (mode, a) in modes.items():
            prec, rec = [], []
            for s in range(0, len(users), 256):
                rows = users[s:s + 256]
                sc = self._scores(rows, a, mode)
                sc[A_train[rows].nonzero()] = -np.inf         # hide already-seen
                top = np.argpartition(-sc, k, axis=1)[:, :k]
                hits = np.asarray(T[rows][np.arange(len(rows))[:, None], top].todense()).sum(axis=1)
                n_test = np.asarray(T[rows].sum(axis=1)).ravel()
                prec.append(hits / k); rec.append(hits / n_test)
            results[name] = {f"precision@{k}": float(np.concatenate(prec).mean()),
                             f"recall@{k}": float(np.concatenate(rec).mean())}
        self._svd_U = self._svd_V = None
        return results

    # ---- inference --------------------------------------------------------
    def recommend(self, user_id, n=10):
        """Top-n unseen movies for user_id -> DataFrame(movieId, title, genres, score).
        Unknown users fall back to the most popular highly-rated movies."""
        if user_id not in self.user_index:
            top = np.argsort(-self.pop)[:n]
            scores = self.pop[top].astype(float)
        else:
            u = self.user_index[user_id]
            sc = self._scores(np.array([u]))[0]
            sc[self.A[u].indices] = -np.inf                   # remove already-rated
            top = np.argsort(-sc)[:n]
            scores = sc[top]
        out = self.titles.loc[self.movie_ids[top]].reset_index()
        out["score"] = scores
        return out

    def popular(self, genre=None, limit=20):
        """Most-liked movies overall, or within one genre. DataFrame(movieId, title, genres)."""
        df = self.titles.loc[self.movie_ids[np.argsort(-self.pop)]]   # most liked first
        if genre:
            df = df[df["genres"].str.split("|").apply(lambda g: genre in g)]
        return df.head(limit).reset_index()

    def search(self, query, limit=20):
        """Movies whose title contains `query` (case-insensitive), most popular first.
        Returns DataFrame(movieId, title, genres)."""
        mask = self.titles["title"].str.contains(query.strip(), case=False, regex=False)
        found = self.titles[mask]
        if found.empty:
            return found.reset_index()
        pop = np.array([self.pop[self.movie_index[m]] for m in found.index])
        return found.iloc[np.argsort(-pop)[:limit]].reset_index()

    def recommend_for_new_user(self, liked_movie_ids, n=10):
        """Cold start: recommend for someone NOT in the training data, from a few movies
        they say they like. Same two parts as recommend(), built on the fly:
          - collaborative: "fold in" the user = solve one ALS user update against the
            trained movie factors (no retraining needed)
          - content: taste profile = average genre/tag vector of the liked movies
        Returns DataFrame(movieId, title, genres, score)."""
        idx = np.array(sorted({self.movie_index[m] for m in liked_movie_ids
                               if m in self.movie_index}))
        if idx.size == 0:
            raise ValueError("None of the given movieIds are known")

        Y = self.V[:, idx].T                                  # factors of the liked movies
        A = (self.V @ self.V.T + (self.confidence - 1) * (Y.T @ Y)
             + self.reg * np.eye(self.V.shape[0]))
        b = self.confidence * Y.sum(axis=0)
        user_vec = np.linalg.solve(A, b)                      # this user's ALS factors
        cf = _zscore_rows((user_vec @ self.V)[None, :])

        profile = normalize(sparse.csr_matrix(self.F[idx].sum(axis=0)))
        content = _zscore_rows((profile @ self.F.T).toarray())

        sc = (self.alpha * cf + (1 - self.alpha) * content)[0]
        sc[idx] = -np.inf                                     # don't recommend what they picked
        top = np.argsort(-sc)[:n]
        out = self.titles.loc[self.movie_ids[top]].reset_index()
        out["score"] = sc[top]
        return out

    def save(self, path=MODEL_PATH):
        with open(path, "wb") as f:
            pickle.dump(self, f)


def load_recommender(path=MODEL_PATH):
    with open(path, "rb") as f:
        return pickle.load(f)


def recommend_movies(user_id, n=10, model_path=MODEL_PATH):
    """userId in -> recommended movies out."""
    return load_recommender(model_path).recommend(user_id, n)


def main():
    movies, ratings, tags = load_data()
    build_ratings_dataset(movies, ratings, tags).to_csv(MERGED_CSV, index=False)
    rec = MovieRecommender().fit(movies, ratings, tags)
    print("Hold-out results:")
    print(pd.DataFrame(rec.metrics).T.round(4).to_string())
    rec.save()
    demo_user = int(rec.user_ids[0])
    print(f"\nTop 10 for user {demo_user}:")
    print(rec.recommend(demo_user, 10).to_string(index=False))


if __name__ == "__main__":
    # Re-import this file as a module so the pickled model references
    # "reccomendationsystem.MovieRecommender" (loadable from any other script)
    # instead of "__main__.MovieRecommender".
    import reccomendationsystem
    reccomendationsystem.main()

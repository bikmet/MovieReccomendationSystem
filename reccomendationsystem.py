import pandas as pd
import numpy as np

movies = pd.read_csv("dataset\movies.csv")
ratings = pd.read_csv("dataset\\ratings.csv")
tags = pd.read_csv("dataset\\tags.csv")


ratings = pd.merge(ratings, movies, on='movieId')


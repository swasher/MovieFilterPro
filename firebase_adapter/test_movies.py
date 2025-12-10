# start = time.perf_counter()
# movies = MovieRepository(client)
# print(f"object: {time.perf_counter() - start:.6f} сек")


import time
from client import FirebaseClient
from movies import MovieRepository

# -----------------------------
# Инициализация
# -----------------------------
client = FirebaseClient("movie-vault-17cc7-firebase-adminsdk-fbsvc-1eeb501dbf.json")
client.initialize()

USER_ID = "test_user"
movies = MovieRepository(client.db, USER_ID)

TMDB_ID = "550"
IMDB_ID = "tt0137523"
TITLE = "Fight Club"
ORIGINAL_TITLE = "Fight Club"
YEAR = 1999
LIST_NAME = "favorites"

# -----------------------------
# 1. Create
# -----------------------------
start = time.perf_counter()
movies.create(IMDB_ID, TMDB_ID, TITLE, ORIGINAL_TITLE, YEAR)
print(f"create: {time.perf_counter() - start:.6f} сек")

# -----------------------------
# 2. Get
# -----------------------------
start = time.perf_counter()
data = movies.get(TMDB_ID)
print(f"get: {data}, {time.perf_counter() - start:.6f} сек")

# -----------------------------
# 3. Update
# -----------------------------
start = time.perf_counter()
movies.update(TMDB_ID, {"title": "Fight Club (Updated)"})
print(f"update: {time.perf_counter() - start:.6f} сек")

# -----------------------------
# 4. Set status
# -----------------------------
start = time.perf_counter()
movies.set_status(TMDB_ID, "watched")
print(f"set_status: {time.perf_counter() - start:.6f} сек")

# -----------------------------
# 5. Add to list
# -----------------------------
start = time.perf_counter()
movies.add_to_list(TMDB_ID, LIST_NAME)
print(f"add_to_list: {time.perf_counter() - start:.6f} сек")

# -----------------------------
# 6. List by list name
# -----------------------------
start = time.perf_counter()
list_movies = movies.list_by_listname(LIST_NAME)
print(f"list_by_listname: {list_movies}, {time.perf_counter() - start:.6f} сек")

# -----------------------------
# 7. List all
# -----------------------------
start = time.perf_counter()
all_movies = movies.list_all()
print(f"list_all: {all_movies}, {time.perf_counter() - start:.6f} сек")

# -----------------------------
# 8. Remove from list
# -----------------------------
start = time.perf_counter()
movies.remove_from_list(TMDB_ID, LIST_NAME)
print(f"remove_from_list: {time.perf_counter() - start:.6f} сек")

# -----------------------------
# 9. Delete
# -----------------------------
start = time.perf_counter()
movies.delete(TMDB_ID)
print(f"delete: {time.perf_counter() - start:.6f} сек")

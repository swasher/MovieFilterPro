import time
from client import FirebaseClient
from movielists import ListRepository

# -----------------------------
# Инициализация
# -----------------------------
client = FirebaseClient("movie-vault-17cc7-firebase-adminsdk-fbsvc-1eeb501dbf.json")
client.initialize()

USER_ID = "test_user"
lists = ListRepository(client.db, USER_ID)

LIST_ID1 = "favorites"
LIST_NAME1 = "Favorites"
LIST_ID2 = "watched"
LIST_NAME2 = "Watched"
NEW_NAME = "Top Favorites"

MOVIE_1 = {
    "tmdb_id": "550",
    "title": "Fight Club",
    "year": 1999,
    "poster_path": "/abc.jpg"
}

MOVIE_2 = {
    "tmdb_id": "680",
    "title": "Pulp Fiction",
    "year": 1994,
    "poster_path": "/def.jpg"
}

# -----------------------------
# 1. Create two list
# -----------------------------
start = time.perf_counter()
lists.create_list(LIST_ID1, LIST_NAME1)
lists.create_list(LIST_ID2, LIST_NAME2)
print(f"create_list: {time.perf_counter() - start:.6f} сек")

# -----------------------------
# 2. Get list
# -----------------------------
start = time.perf_counter()
data = lists.get_list(LIST_ID1)
print(f"get_list: {data}, {time.perf_counter() - start:.6f} сек")

# -----------------------------
# 3. Rename list
# -----------------------------
start = time.perf_counter()
lists.rename_list(LIST_ID1, NEW_NAME)
print(f"rename_list: {time.perf_counter() - start:.6f} сек")

# -----------------------------
# 4. Add movies
# -----------------------------
start = time.perf_counter()
lists.add_movie(LIST_ID1, MOVIE_1)
lists.add_movie(LIST_ID1, MOVIE_2)
lists.add_movie(LIST_ID2, MOVIE_1)
print(f"add_movie x2: {time.perf_counter() - start:.6f} сек")

# -----------------------------
# 5. Pagination test
# -----------------------------
start = time.perf_counter()
items = lists.list_items(LIST_ID1, limit=10)
print(items)
print(f"list_items: {items}, {time.perf_counter() - start:.6f} сек")

# -----------------------------
# 6. Remove a movie
# -----------------------------
# start = time.perf_counter()
# lists.remove_movie(LIST_ID, MOVIE_1["tmdb_id"])
# print(f"remove_movie: {time.perf_counter() - start:.6f} сек")

# -----------------------------
# 7. Delete list
# -----------------------------
# start = time.perf_counter()
# lists.delete_list(LIST_ID)
# print(f"delete_list: {time.perf_counter() - start:.6f} сек")

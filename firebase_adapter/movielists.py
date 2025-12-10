from typing import Optional, Dict, Any
from firebase_admin import firestore


class ListRepository:
    def __init__(self, client: firestore.Client, user_id: str):
        self.client = client
        self.user_id = user_id
        self.base = (
            self.client.collection("users")
            .document(self.user_id)
            .collection("lists")
        )

    # -----------------------------
    # List management
    # -----------------------------
    def create_list(self, list_id: str, name: str):
        self.base.document(list_id).set({
            "name": name,
            "count": 0
        }, merge=True)

    def delete_list(self, list_id: str):
        self.base.document(list_id).delete()

    def rename_list(self, list_id: str, new_name: str):
        self.base.document(list_id).update({"name": new_name})

    def get_list(self, list_id: str) -> Optional[Dict[str, Any]]:
        doc = self.base.document(list_id).get()
        return doc.to_dict() if doc.exists else None

    def list_all_lists(self):
        return [d.to_dict() for d in self.base.stream()]

    # -----------------------------
    # Items
    # -----------------------------
    def add_movie(self, list_id: str, movie_data: Dict[str, Any]):
        """
        movie_data = {
            "tmdb_id": "550",
            "title": "Fight Club",
            "year": 1999,
            "poster_path": "...",
        }
        """

        item_ref = self.base.document(list_id)\
            .collection("items").document(movie_data["tmdb_id"])

        short = {
            "title": movie_data["title"],
            "year": movie_data["year"],
            "poster_path": movie_data.get("poster_path"),
            "added_at": firestore.SERVER_TIMESTAMP
        }

        item_ref.set(short)
        self._increment_count(list_id, +1)

    def remove_movie(self, list_id: str, tmdb_id: str):
        self.base.document(list_id)\
            .collection("items").document(tmdb_id).delete()

        self._increment_count(list_id, -1)

    # -----------------------------
    # Pagination
    # -----------------------------
    def list_items(self, list_id: str, limit: int = 20, start_after=None):
        ref = self.base.document(list_id).collection("items")
        q = ref.order_by("added_at", direction=firestore.Query.DESCENDING).limit(limit)

        if start_after:
            q = q.start_after({u"added_at": start_after})

        return [d.to_dict() for d in q.stream()]

    # -----------------------------
    # Counter update
    # -----------------------------
    def _increment_count(self, list_id: str, delta: int):
        list_ref = self.base.document(list_id)
        list_ref.update({"count": firestore.Increment(delta)})

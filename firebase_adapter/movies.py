from typing import Optional, Dict, Any
from firebase_admin import firestore


class MovieRepository:
    def __init__(self, client: firestore.Client, user_id: str):
        self.client = client
        self.user_id = user_id
        self.collection = (
            self.client.collection("users")
            .document(self.user_id)
            .collection("movies")
        )

    # -----------------------------
    # Create or overwrite
    # -----------------------------
    def create(
        self,
        imdb_id: Optional[str],
        tmdb_id: str,
        title: str,
        original_title: str,
        year: int,
    ):
        doc = self.collection.document(tmdb_id)
        payload = {
            "tmdb_id": tmdb_id,
            "imdb_id": imdb_id,
            "title": title,
            "original_title": original_title,
            "year": year,
            "status": None,     # optional поле
            "lists": [],        # имена списков
        }
        doc.set(payload, merge=True)

    # -----------------------------
    # Read
    # -----------------------------
    def get(self, tmdb_id: str) -> Optional[Dict[str, Any]]:
        doc = self.collection.document(tmdb_id).get()
        if not doc.exists:
            return None
        return doc.to_dict()

    # -----------------------------
    # Partial update
    # -----------------------------
    def update(self, tmdb_id: str, fields: Dict[str, Any]):
        """
        fields = {"title": "...", "year": 1995}
        """
        self.collection.document(tmdb_id).update(fields)

    # -----------------------------
    # Delete
    # -----------------------------
    def delete(self, tmdb_id: str):
        self.collection.document(tmdb_id).delete()

    # -----------------------------
    # Set status (watched, planned...)
    # -----------------------------
    def set_status(self, tmdb_id: str, status: Optional[str]):
        self.collection.document(tmdb_id).update({"status": status})

    # -----------------------------
    # Add/remove from lists
    # -----------------------------
    def add_to_list(self, tmdb_id: str, list_name: str):
        doc = self.collection.document(tmdb_id)
        doc.update({"lists": firestore.ArrayUnion([list_name])})

    def remove_from_list(self, tmdb_id: str, list_name: str):
        doc = self.collection.document(tmdb_id)
        doc.update({"lists": firestore.ArrayRemove([list_name])})

    # -----------------------------
    # All movies
    # -----------------------------
    def list_all(self):
        return [d.to_dict() for d in self.collection.stream()]

    # -----------------------------
    # Movies by list
    # -----------------------------
    def list_by_listname(self, list_name: str):
        query = self.collection.where("lists", "array_contains", list_name)
        return [d.to_dict() for d in query.stream()]

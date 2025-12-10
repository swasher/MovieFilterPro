from pathlib import Path
from typing import Optional

import firebase_admin
from firebase_admin import credentials, firestore


class FirebaseClient:
    """
    Управляет соединением с Firestore и предоставляет доступ к коллекциям.
    """

    def __init__(self, credentials_path: str):
        self._credentials_path = Path(credentials_path)
        self._app = None
        self._db = None

    def initialize(self):
        """
        Инициализация Firebase Admin SDK (идемпотентная).
        """
        if not firebase_admin._apps:
            cred = credentials.Certificate(str(self._credentials_path))
            self._app = firebase_admin.initialize_app(cred)
        else:
            self._app = firebase_admin.get_app()

        self._db = firestore.client()

    @property
    def db(self):
        if self._db is None:
            raise RuntimeError("FirebaseClient not initialized. Call initialize() first.")
        return self._db

    def collection(self, name: str):
        return self.db.collection(name)

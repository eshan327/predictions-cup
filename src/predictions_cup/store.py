"""Append-only observations, normalized books, and durable paper events in SQLite."""

import hashlib
import json
import sqlite3
from pathlib import Path


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Store:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        path.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          PRAGMA journal_mode=WAL;
          PRAGMA foreign_keys=ON;
          CREATE TABLE IF NOT EXISTS observations(
            id INTEGER PRIMARY KEY, path TEXT NOT NULL, params TEXT NOT NULL,
            started TEXT NOT NULL, received TEXT NOT NULL, sha256 TEXT NOT NULL,
            body TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS observation_time ON observations(path, received);
          CREATE TABLE IF NOT EXISTS books(
            id INTEGER PRIMARY KEY, tournament TEXT NOT NULL, exchange_id TEXT NOT NULL,
            received REAL NOT NULL, sequence INTEGER, body TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS book_time ON books(tournament, exchange_id, received);
          CREATE TABLE IF NOT EXISTS runs(
            id INTEGER PRIMARY KEY, received REAL NOT NULL, status TEXT NOT NULL,
            body TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS paper_events(
            id INTEGER PRIMARY KEY, event_key TEXT UNIQUE NOT NULL, body TEXT NOT NULL);
        """)

    def capture(self, path, params, body, started, received):
        # Account metadata is irrelevant to research; retain only financial fields.
        if path == "/account":
            body = {k: body[k] for k in ("balance", "buyingPower", "availableAdvance")}
        payload = encode(body)
        with self.db:
            self.db.execute(
                "INSERT INTO observations VALUES(NULL,?,?,?,?,?,?)",
                (
                    path,
                    encode(params),
                    started,
                    received,
                    hashlib.sha256(payload.encode()).hexdigest(),
                    payload,
                ),
            )

    def add_book(self, book):
        with self.db:
            self.db.execute(
                "INSERT INTO books VALUES(NULL,?,?,?,?,?)",
                (
                    book.tournament,
                    book.exchange_id,
                    book.received,
                    book.sequence,
                    book.model_dump_json(),
                ),
            )

    def run(self, received, status, body):
        with self.db:
            self.db.execute("INSERT INTO runs VALUES(NULL,?,?,?)", (received, status, encode(body)))

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g


def db():
    if "db" not in g:
        g.db = sqlite3.connect(Path(current_app.config["DATA_DIR"]) / "nexa.sqlite3", timeout=30)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def now():
    return datetime.now(timezone.utc).isoformat()


def init_app(app):
    @app.teardown_appcontext
    def close_db(error):
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    with app.app_context():
        db().executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, width INTEGER NOT NULL,
                height INTEGER NOT NULL, detections TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
                question TEXT NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS questions_analysis ON questions(analysis_id);
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                question TEXT NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS messages_conversation ON messages(conversation_id);
        """)


def serialize(row, include_questions=True):
    result = dict(row)
    result["detections"] = json.loads(result["detections"])
    result["image_url"] = f"/api/analyses/{result['id']}/image"
    if include_questions:
        result["questions"] = [
            {"id": q["id"], "question": q["question"], "result": json.loads(q["result"]), "created_at": q["created_at"]}
            for q in db().execute("SELECT * FROM questions WHERE analysis_id=? ORDER BY id", (result["id"],))
        ]
    return result


def conversation(row, include_messages=True):
    result = dict(row)
    if include_messages:
        result["messages"] = [
            {"id": m["id"], "question": m["question"], "result": json.loads(m["result"]), "created_at": m["created_at"]}
            for m in db().execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (result["id"],))
        ]
    return result

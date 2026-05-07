"""
SQLite database for user accounts and saved playlists.
"""
import sqlite3
import json

DB_PATH = "tune_drop.db"


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS playlists (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            name       TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS playlist_tracks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id INTEGER NOT NULL,
            track_json  TEXT NOT NULL,
            added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (playlist_id) REFERENCES playlists(id)
        );
    """)
    conn.commit()
    conn.close()


# ── Users ─────────────────────────────────────────────────────────────────────

def create_user(username, password_hash):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # username taken
    finally:
        conn.close()


def get_user(username):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Playlists ─────────────────────────────────────────────────────────────────

def create_playlist(user_id, name):
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO playlists (user_id, name) VALUES (?, ?)", (user_id, name)
    )
    playlist_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return playlist_id


def get_user_playlists(user_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM playlists WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def rename_playlist(playlist_id, new_name, user_id):
    conn = get_db()
    conn.execute(
        "UPDATE playlists SET name = ? WHERE id = ? AND user_id = ?",
        (new_name, playlist_id, user_id),
    )
    conn.commit()
    conn.close()


def delete_playlist(playlist_id, user_id):
    conn = get_db()
    conn.execute("DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,))
    conn.execute(
        "DELETE FROM playlists WHERE id = ? AND user_id = ?", (playlist_id, user_id)
    )
    conn.commit()
    conn.close()


# ── Tracks ────────────────────────────────────────────────────────────────────

def add_tracks_to_playlist(playlist_id, tracks):
    conn = get_db()
    for track in tracks:
        conn.execute(
            "INSERT INTO playlist_tracks (playlist_id, track_json) VALUES (?, ?)",
            (playlist_id, json.dumps(track)),
        )
    conn.commit()
    conn.close()


def get_playlist_tracks(playlist_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT track_json FROM playlist_tracks WHERE playlist_id = ? ORDER BY added_at",
        (playlist_id,),
    ).fetchall()
    conn.close()
    return [json.loads(r["track_json"]) for r in rows]

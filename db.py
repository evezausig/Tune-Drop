"""
Database layer — PostgreSQL (Streamlit Cloud) with SQLite fallback (local dev).

Set DATABASE_URL in .streamlit/secrets.toml to enable PostgreSQL.
Without it, falls back to a local SQLite file.
"""
import json
import sqlite3
from datetime import datetime

# ── Backend detection ─────────────────────────────────────────────────────────

def _db_url():
    try:
        import streamlit as st
        return st.secrets.get("DATABASE_URL") or st.secrets.get("database_url")
    except Exception:
        return None


def _use_pg():
    return bool(_db_url())


# ── Connection helpers ────────────────────────────────────────────────────────

SQLITE_PATH = "tune_drop.db"


def _pg_conn():
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(_db_url())
    conn.autocommit = False
    return conn


def _sqlite_conn():
    conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_db():
    return _pg_conn() if _use_pg() else _sqlite_conn()


# ── SQL dialect helpers ───────────────────────────────────────────────────────
# PostgreSQL uses %s placeholders; SQLite uses ?

def _p(n=1):
    """Return n positional placeholders for the active backend."""
    ph = "%s" if _use_pg() else "?"
    return ", ".join([ph] * n)


def _ph():
    return "%s" if _use_pg() else "?"


# ── Schema init ───────────────────────────────────────────────────────────────

def init_db():
    if _use_pg():
        _init_pg()
    else:
        _init_sqlite()


def _init_sqlite():
    conn = _sqlite_conn()
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
        CREATE TABLE IF NOT EXISTS liked_songs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            track_id   INTEGER NOT NULL,
            track_json TEXT NOT NULL,
            added_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE (user_id, track_id)
        );
        CREATE TABLE IF NOT EXISTS song_stats (
            track_id   INTEGER NOT NULL,
            track_json TEXT NOT NULL,
            likes      INTEGER DEFAULT 0,
            skips      INTEGER DEFAULT 0,
            week       TEXT NOT NULL,
            PRIMARY KEY (track_id, week)
        );
        CREATE TABLE IF NOT EXISTS social_feed (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            username   TEXT NOT NULL,
            track_id   INTEGER NOT NULL,
            track_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS mood_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            mood_label   TEXT NOT NULL,
            day_of_week  INTEGER NOT NULL,
            logged_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


def _init_pg():
    conn = _pg_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS playlists (
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER NOT NULL REFERENCES users(id),
            name       TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS playlist_tracks (
            id          SERIAL PRIMARY KEY,
            playlist_id INTEGER NOT NULL REFERENCES playlists(id),
            track_json  TEXT NOT NULL,
            added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS liked_songs (
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER NOT NULL REFERENCES users(id),
            track_id   BIGINT NOT NULL,
            track_json TEXT NOT NULL,
            added_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, track_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS song_stats (
            track_id   BIGINT NOT NULL,
            track_json TEXT NOT NULL,
            likes      INTEGER DEFAULT 0,
            skips      INTEGER DEFAULT 0,
            week       TEXT NOT NULL,
            PRIMARY KEY (track_id, week)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS social_feed (
            id         SERIAL PRIMARY KEY,
            username   TEXT NOT NULL,
            track_id   BIGINT NOT NULL,
            track_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mood_log (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            mood_label  TEXT NOT NULL,
            day_of_week INTEGER NOT NULL,
            logged_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


# ── Generic query helpers ─────────────────────────────────────────────────────

def _fetchall(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    if _use_pg():
        cols = [d[0] for d in cur.description]
        cur.close()
        return [dict(zip(cols, r)) for r in rows]
    cur.close()
    return [dict(r) for r in rows]


# ── Users ─────────────────────────────────────────────────────────────────────

def create_user(username, password_hash):
    conn = get_db()
    try:
        ph = _ph()
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO users (username, password_hash) VALUES ({ph}, {ph})",
            (username, password_hash),
        )
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        err = str(e).lower()
        if "unique" in err or "duplicate" in err:
            return False
        raise
    finally:
        conn.close()


def get_user(username):
    conn = get_db()
    ph = _ph()
    rows = _fetchall(conn, f"SELECT * FROM users WHERE username = {ph}", (username,))
    conn.close()
    return rows[0] if rows else None


# ── Playlists ─────────────────────────────────────────────────────────────────

def create_playlist(user_id, name):
    conn = get_db()
    ph = _ph()
    cur = conn.cursor()
    if _use_pg():
        cur.execute(
            f"INSERT INTO playlists (user_id, name) VALUES ({ph}, {ph}) RETURNING id",
            (user_id, name),
        )
        playlist_id = cur.fetchone()[0]
    else:
        cur.execute(
            f"INSERT INTO playlists (user_id, name) VALUES ({ph}, {ph})",
            (user_id, name),
        )
        playlist_id = cur.lastrowid
    conn.commit()
    cur.close()
    conn.close()
    return playlist_id


def get_user_playlists(user_id):
    conn = get_db()
    ph = _ph()
    rows = _fetchall(
        conn,
        f"SELECT * FROM playlists WHERE user_id = {ph} ORDER BY created_at DESC",
        (user_id,),
    )
    conn.close()
    return rows


def rename_playlist(playlist_id, new_name, user_id):
    conn = get_db()
    ph = _ph()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE playlists SET name = {ph} WHERE id = {ph} AND user_id = {ph}",
        (new_name, playlist_id, user_id),
    )
    conn.commit()
    cur.close()
    conn.close()


def delete_playlist(playlist_id, user_id):
    conn = get_db()
    ph = _ph()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM playlist_tracks WHERE playlist_id = {ph}", (playlist_id,))
    cur.execute(
        f"DELETE FROM playlists WHERE id = {ph} AND user_id = {ph}",
        (playlist_id, user_id),
    )
    conn.commit()
    cur.close()
    conn.close()


# ── Tracks ────────────────────────────────────────────────────────────────────

def add_tracks_to_playlist(playlist_id, tracks):
    conn = get_db()
    ph = _ph()
    cur = conn.cursor()
    for track in tracks:
        cur.execute(
            f"INSERT INTO playlist_tracks (playlist_id, track_json) VALUES ({ph}, {ph})",
            (playlist_id, json.dumps(track)),
        )
    conn.commit()
    cur.close()
    conn.close()


def get_playlist_tracks(playlist_id):
    conn = get_db()
    ph = _ph()
    rows = _fetchall(
        conn,
        f"SELECT track_json FROM playlist_tracks WHERE playlist_id = {ph} ORDER BY added_at",
        (playlist_id,),
    )
    conn.close()
    return [json.loads(r["track_json"]) for r in rows]


# ── Anonymous Song Stats ───────────────────────────────────────────────────────

def _current_week():
    return datetime.now().strftime("%Y-W%W")


def record_interaction(track, action):
    """Record a like or skip anonymously. action: 'like' or 'skip'."""
    week = _current_week()
    ph = _ph()
    conn = get_db()
    cur = conn.cursor()
    if _use_pg():
        cur.execute(
            f"INSERT INTO song_stats (track_id, track_json, week) VALUES ({ph}, {ph}, {ph}) "
            f"ON CONFLICT (track_id, week) DO NOTHING",
            (track["id"], json.dumps(track), week),
        )
    else:
        cur.execute(
            f"INSERT OR IGNORE INTO song_stats (track_id, track_json, week) VALUES ({ph}, {ph}, {ph})",
            (track["id"], json.dumps(track), week),
        )
    col = "likes" if action == "like" else "skips"
    cur.execute(
        f"UPDATE song_stats SET {col} = {col} + 1 WHERE track_id = {ph} AND week = {ph}",
        (track["id"], week),
    )
    conn.commit()
    cur.close()
    conn.close()


def get_top_liked(limit=8):
    """Returns the most-liked tracks this week as (track_dict, likes) tuples."""
    week = _current_week()
    ph = _ph()
    conn = get_db()
    rows = _fetchall(
        conn,
        f"SELECT track_json, likes FROM song_stats WHERE week = {ph} AND likes > 0 "
        f"ORDER BY likes DESC LIMIT {ph}",
        (week, limit),
    )
    conn.close()
    return [(json.loads(r["track_json"]), r["likes"]) for r in rows]


def record_social_like(username, track):
    """Record a named like for the social feed."""
    conn = get_db()
    ph = _ph()
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO social_feed (username, track_id, track_json) VALUES ({ph}, {ph}, {ph})",
        (username, track["id"], json.dumps(track)),
    )
    conn.commit()
    cur.close()
    conn.close()


def get_social_feed(limit=10):
    """Return the most recent named likes across all users."""
    conn = get_db()
    ph = _ph()
    rows = _fetchall(
        conn,
        f"SELECT username, track_json, created_at FROM social_feed ORDER BY created_at DESC LIMIT {ph}",
        (limit,),
    )
    conn.close()
    return [(r["username"], json.loads(r["track_json"])) for r in rows]


def record_mood(user_id, mood_label):
    """Log a mood/genre selection for a user."""
    day = datetime.now().weekday()  # 0=Monday, 6=Sunday
    conn = get_db()
    ph = _ph()
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO mood_log (user_id, mood_label, day_of_week) VALUES ({ph}, {ph}, {ph})",
        (user_id, mood_label, day),
    )
    conn.commit()
    cur.close()
    conn.close()


def get_mood_stats(user_id):
    """Return a dict of {mood_label: count} for this user's top moods."""
    conn = get_db()
    ph = _ph()
    rows = _fetchall(
        conn,
        f"SELECT mood_label, COUNT(*) as cnt FROM mood_log WHERE user_id = {ph} GROUP BY mood_label ORDER BY cnt DESC LIMIT 5",
        (user_id,),
    )
    conn.close()
    return {r["mood_label"]: r["cnt"] for r in rows}

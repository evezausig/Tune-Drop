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
    url = _db_url()
    # Supabase (and most managed PostgreSQL) requires SSL
    conn = psycopg2.connect(url, sslmode="require")
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
    try:
        if _use_pg():
            _init_pg()
        else:
            _init_sqlite()
    except Exception as e:
        # Log but don't crash — the app can still run read-only if DB is temporarily down
        import streamlit as st
        st.error(f"⚠️ Database connection failed: {e}\n\nCheck your DATABASE_URL in Streamlit secrets, or try refreshing in a moment.")


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
        CREATE TABLE IF NOT EXISTS friendships (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_id INTEGER NOT NULL,
            addressee_id INTEGER NOT NULL,
            status       TEXT NOT NULL DEFAULT 'pending',
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (requester_id) REFERENCES users(id),
            FOREIGN KEY (addressee_id) REFERENCES users(id),
            UNIQUE (requester_id, addressee_id)
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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS friendships (
            id           SERIAL PRIMARY KEY,
            requester_id INTEGER NOT NULL REFERENCES users(id),
            addressee_id INTEGER NOT NULL REFERENCES users(id),
            status       TEXT NOT NULL DEFAULT 'pending',
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (requester_id, addressee_id)
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


# ── Liked songs (persistent) ─────────────────────────────────────────────────

def save_liked_song(user_id, track):
    """Persist a liked song to the database for the given user (ignore duplicates)."""
    conn = get_db()
    ph = _ph()
    cur = conn.cursor()
    try:
        if _use_pg():
            cur.execute(
                f"INSERT INTO liked_songs (user_id, track_id, track_json) VALUES ({ph}, {ph}, {ph}) ON CONFLICT (user_id, track_id) DO NOTHING",
                (user_id, track["id"], json.dumps(track)),
            )
        else:
            cur.execute(
                f"INSERT OR IGNORE INTO liked_songs (user_id, track_id, track_json) VALUES ({ph}, {ph}, {ph})",
                (user_id, track["id"], json.dumps(track)),
            )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def get_liked_songs_from_db(user_id):
    """Return all liked songs for a user from the database, newest first."""
    conn = get_db()
    ph = _ph()
    rows = _fetchall(
        conn,
        f"SELECT track_json FROM liked_songs WHERE user_id = {ph} ORDER BY added_at DESC",
        (user_id,),
    )
    conn.close()
    return [json.loads(r["track_json"]) for r in rows]


def remove_liked_song(user_id, track_id):
    """Remove a liked song from the database."""
    conn = get_db()
    ph = _ph()
    cur = conn.cursor()
    cur.execute(
        f"DELETE FROM liked_songs WHERE user_id = {ph} AND track_id = {ph}",
        (user_id, track_id),
    )
    conn.commit()
    cur.close()
    conn.close()


# ── Friends ───────────────────────────────────────────────────────────────────

def send_friend_request(from_user_id, to_username):
    """
    Send a friend request from from_user_id to the user with to_username.
    Returns 'sent', 'not_found', 'self', or 'already'.
    """
    conn = get_db()
    ph = _ph()
    # Look up target user
    rows = _fetchall(conn, f"SELECT id FROM users WHERE username = {ph}", (to_username,))
    if not rows:
        conn.close()
        return "not_found"
    to_user_id = rows[0]["id"]
    if to_user_id == from_user_id:
        conn.close()
        return "self"
    # Check if friendship already exists in either direction
    existing = _fetchall(
        conn,
        f"SELECT id FROM friendships WHERE (requester_id = {ph} AND addressee_id = {ph}) OR (requester_id = {ph} AND addressee_id = {ph})",
        (from_user_id, to_user_id, to_user_id, from_user_id),
    )
    if existing:
        conn.close()
        return "already"
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO friendships (requester_id, addressee_id, status) VALUES ({ph}, {ph}, 'pending')",
        (from_user_id, to_user_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return "sent"


def get_pending_requests(user_id):
    """Return list of {id, username, requester_id} for requests sent TO user_id."""
    conn = get_db()
    ph = _ph()
    rows = _fetchall(
        conn,
        f"""SELECT f.id, u.username, u.id as requester_id
            FROM friendships f
            JOIN users u ON u.id = f.requester_id
            WHERE f.addressee_id = {ph} AND f.status = 'pending'
            ORDER BY f.created_at DESC""",
        (user_id,),
    )
    conn.close()
    return rows


def accept_friend_request(user_id, requester_id):
    """Accept a pending friend request."""
    conn = get_db()
    ph = _ph()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE friendships SET status = 'accepted' WHERE requester_id = {ph} AND addressee_id = {ph}",
        (requester_id, user_id),
    )
    conn.commit()
    cur.close()
    conn.close()


def decline_friend_request(user_id, requester_id):
    """Decline (delete) a pending friend request."""
    conn = get_db()
    ph = _ph()
    cur = conn.cursor()
    cur.execute(
        f"DELETE FROM friendships WHERE requester_id = {ph} AND addressee_id = {ph}",
        (requester_id, user_id),
    )
    conn.commit()
    cur.close()
    conn.close()


def remove_friend(user_id, friend_id):
    """Remove an accepted friendship (either direction)."""
    conn = get_db()
    ph = _ph()
    cur = conn.cursor()
    cur.execute(
        f"DELETE FROM friendships WHERE (requester_id = {ph} AND addressee_id = {ph}) OR (requester_id = {ph} AND addressee_id = {ph})",
        (user_id, friend_id, friend_id, user_id),
    )
    conn.commit()
    cur.close()
    conn.close()


def get_friends(user_id):
    """Return list of {id, username} for all accepted friends of user_id."""
    conn = get_db()
    ph = _ph()
    rows = _fetchall(
        conn,
        f"""SELECT u.id, u.username
            FROM friendships f
            JOIN users u ON u.id = f.addressee_id
            WHERE f.requester_id = {ph} AND f.status = 'accepted'
            UNION
            SELECT u.id, u.username
            FROM friendships f
            JOIN users u ON u.id = f.requester_id
            WHERE f.addressee_id = {ph} AND f.status = 'accepted'
            ORDER BY username""",
        (user_id, user_id),
    )
    conn.close()
    return rows


def get_friends_liked_songs(user_id, limit=20):
    """Return list of {username, track_json, added_at} for all friends' liked songs."""
    friends = get_friends(user_id)
    if not friends:
        return []
    friend_ids = [f["id"] for f in friends]
    conn = get_db()
    ph = _ph()
    placeholders = ", ".join([ph] * len(friend_ids))
    rows = _fetchall(
        conn,
        f"""SELECT u.username, ls.track_json, ls.added_at
            FROM liked_songs ls
            JOIN users u ON u.id = ls.user_id
            WHERE ls.user_id IN ({placeholders})
            ORDER BY ls.added_at DESC
            LIMIT {ph}""",
        tuple(friend_ids) + (limit,),
    )
    conn.close()
    return [(r["username"], json.loads(r["track_json"])) for r in rows]


def get_friends_playlists(user_id):
    """Return list of {username, playlist_id, name, track_count} for all friends' playlists."""
    friends = get_friends(user_id)
    if not friends:
        return []
    friend_ids = [f["id"] for f in friends]
    conn = get_db()
    ph = _ph()
    placeholders = ", ".join([ph] * len(friend_ids))
    rows = _fetchall(
        conn,
        f"""SELECT u.username, p.id as playlist_id, p.name,
                   COUNT(pt.id) as track_count
            FROM playlists p
            JOIN users u ON u.id = p.user_id
            LEFT JOIN playlist_tracks pt ON pt.playlist_id = p.id
            WHERE p.user_id IN ({placeholders})
            GROUP BY u.username, p.id, p.name
            ORDER BY p.created_at DESC""",
        tuple(friend_ids),
    )
    conn.close()
    return rows

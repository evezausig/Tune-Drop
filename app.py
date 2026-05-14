import io
import csv
import random
import collections
from concurrent.futures import ThreadPoolExecutor

import requests
import streamlit as st

from emotion_recipes import EMOTION_RECIPES
from genre_recipes import GENRE_RECIPES
from metadata_filter import find_matching_songs
import spotify_export
import db
import auth

# Run schema init once per server process, not on every rerun
@st.cache_resource
def _init_db_once():
    db.init_db()
    return True

_init_db_once()

st.title("Tune-Drop 🎵")
st.write("Discover new music, one song at a time")

# ── OAuth callbacks (must run before any UI is rendered) ──────────────────────
_params = dict(st.query_params)
if _params.get("state") == "spotify" and "code" in _params:
    try:
        token_info = spotify_export.exchange_code(_params["code"])
        st.session_state["spotify_token"] = token_info["access_token"]
        st.success("✅ Connected to Spotify!")
    except Exception as e:
        st.error(f"Spotify auth failed: {e}")
    st.query_params.clear()


_DEFAULTS = {
    "tracks": [],
    "current_index": 0,
    "saved_playlist": [],
    "selected_emotion": None,
    "selected_genre": None,
    "spotify_token": None,
    "liked_songs": [],
    "show_spotify_links": False,
    "show_deezer_links": False,
    "user": None,
    "renaming_pl_id": None,
    "open_playlist_tracks": None,
    "open_playlist_name": None,
    "open_playlist_is_liked": False,
    "open_friends_view": False,
    "open_friend_playlist": None,   # (username, playlist_id, name)
}
for _key, _val in _DEFAULTS.items():
    if _key not in st.session_state:
        st.session_state[_key] = _val

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Tighten audio players */
audio { width: 100% !important; }

/* Pill-style emotion/genre buttons */
div.stButton > button {
    border-radius: 20px;
}

/* Larger cover art */
div[data-testid="stImage"] img {
    border-radius: 12px;
}

/* Muted caption color */
div[data-testid="stCaptionContainer"] {
    opacity: 0.75;
}
</style>
""", unsafe_allow_html=True)


def playlist_to_csv(tracks):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Title", "Artist", "Album", "Deezer Link", "Spotify Search"])
    for t in tracks:
        query = f"{t['title']} {t['artist']['name']}".replace(" ", "%20")
        spotify_url = f"https://open.spotify.com/search/{query}"
        writer.writerow([
            t["title"],
            t["artist"]["name"],
            t.get("album", {}).get("title", ""),
            t.get("link", f"https://www.deezer.com/track/{t['id']}"),
            spotify_url,
        ])
    return output.getvalue()


# ── Cached DB helpers (defined before sidebar so they're available everywhere) ─

@st.cache_data(ttl=60)
def _cached_top_liked():
    return db.get_top_liked(limit=8)

@st.cache_data(ttl=120)
def _cached_playlist_tracks(playlist_id):
    return db.get_playlist_tracks(playlist_id)

@st.cache_data(ttl=30)
def _cached_user_playlists(user_id):
    return db.get_user_playlists(user_id)

@st.cache_data(ttl=30)
def _cached_playlist_track_count(playlist_id):
    return db.get_playlist_track_count(playlist_id)

@st.cache_data(ttl=30)
def _cached_friends(user_id):
    return db.get_friends(user_id)

@st.cache_data(ttl=20)
def _cached_pending_requests(user_id):
    return db.get_pending_requests(user_id)


# ── Sidebar — account / saved playlists ──────────────────────────────────────

with st.sidebar:
    st.header("👤 My Account")

    # ── DB backend indicator ──────────────────────────────────────────────────
    if db._use_pg():
        st.caption("🟢 Connected to database")
    else:
        st.warning("⚠️ Using local storage — accounts will reset on redeploy. Set DATABASE_URL in Streamlit secrets to fix this.")

    if not st.session_state["user"]:
        tab_login, tab_reg = st.tabs(["Login", "Register"])

        with tab_login:
            lu = st.text_input("Username", key="li_user")
            lp = st.text_input("Password", type="password", key="li_pass")
            if st.button("Login", use_container_width=True, key="li_btn"):
                user = auth.login(lu, lp)
                if user:
                    st.session_state["user"] = user
                    # Restore liked songs from DB
                    st.session_state["liked_songs"] = db.get_liked_songs_from_db(user["id"])
                    st.rerun()
                else:
                    st.error("Wrong username or password.")

        with tab_reg:
            ru = st.text_input("Username", key="reg_user")
            rp = st.text_input("Password", type="password", key="reg_pass")
            rp2 = st.text_input("Confirm password", type="password", key="reg_pass2")
            if st.button("Create account", use_container_width=True, key="reg_btn"):
                if rp != rp2:
                    st.error("Passwords don't match.")
                else:
                    ok, msg = auth.register(ru, rp)
                    if ok:
                        logged_in = auth.login(ru, rp)
                        st.session_state["user"] = logged_in
                        if logged_in:
                            st.session_state["liked_songs"] = db.get_liked_songs_from_db(logged_in["id"])
                        st.rerun()
                    else:
                        st.error(msg)
    else:
        user = st.session_state["user"]
        st.write(f"**{user['username']}**")

        if st.button("Logout", use_container_width=True):
            st.session_state["user"] = None
            st.session_state["renaming_pl_id"] = None
            st.rerun()

        st.write("---")
        st.write("**🎵 My Playlists**")

        playlists = _cached_user_playlists(user["id"])
        if not playlists:
            st.caption("No saved playlists yet.")

        for pl in playlists:
            track_count = _cached_playlist_track_count(pl["id"])
            with st.expander(f"📋 {pl['name']} ({track_count} songs)"):
                if track_count > 0:
                    if st.button("▶️ Open playlist", key=f"open_{pl['id']}", use_container_width=True):
                        st.session_state["open_playlist_tracks"] = _cached_playlist_tracks(pl["id"])
                        st.session_state["open_playlist_name"] = pl["name"]
                        st.session_state["open_playlist_is_liked"] = False
                        st.rerun()

                    csv_data = playlist_to_csv(_cached_playlist_tracks(pl["id"]))
                    st.download_button(
                        "⬇️ Download CSV",
                        data=csv_data,
                        file_name=f"{pl['name']}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key=f"csv_{pl['id']}",
                    )

                st.write("")

                # ── Manage ───────────────────────────────────────────────
                col_r, col_d = st.columns(2)
                with col_r:
                    if st.button("✏️ Rename", key=f"ren_{pl['id']}", use_container_width=True):
                        st.session_state["renaming_pl_id"] = pl["id"]
                with col_d:
                    if st.button("🗑️ Delete", key=f"del_{pl['id']}", use_container_width=True):
                        db.delete_playlist(pl["id"], user["id"])
                        _cached_user_playlists.clear()
                        _cached_playlist_track_count.clear()
                        st.rerun()

                if st.session_state["renaming_pl_id"] == pl["id"]:
                    new_name = st.text_input("New name", value=pl["name"], key=f"newname_{pl['id']}")
                    if st.button("Save", key=f"savename_{pl['id']}", use_container_width=True):
                        if new_name.strip():
                            db.rename_playlist(pl["id"], new_name.strip(), user["id"])
                            st.session_state["renaming_pl_id"] = None
                            _cached_user_playlists.clear()
                            st.rerun()

        # ── Liked Songs ───────────────────────────────────────────────────────
        st.write("---")
        liked = st.session_state["liked_songs"]
        st.write(f"**👍 Liked Songs ({len(liked)})**")

        if not liked:
            st.caption("No liked songs yet. Tap 👍 while discovering.")
        else:
            if st.button("▶️ Open liked songs", use_container_width=True):
                st.session_state["open_playlist_tracks"] = "liked"
                st.session_state["open_playlist_name"] = "👍 Liked Songs"
                st.session_state["open_playlist_is_liked"] = True
                st.rerun()

            if st.button("🗑️ Clear liked songs", use_container_width=True):
                st.session_state["liked_songs"] = []
                st.rerun()

        # ── Taste Profile ─────────────────────────────────────────────────────
        if st.session_state["current_index"] > 0:
            st.write("---")
            with st.expander("📊 Your Taste Profile"):
                total_discovered = len(st.session_state["tracks"]) + st.session_state["current_index"]
                st.write(f"**Songs discovered this session:** {total_discovered}")

                _playlists = _cached_user_playlists(user["id"])
                total_saved = sum(_cached_playlist_track_count(pl["id"]) for pl in _playlists)
                st.write(f"**Liked:** {len(st.session_state['liked_songs'])}  |  **Saved in playlists:** {total_saved}")

                liked_songs = st.session_state["liked_songs"]
                genre_counts = collections.Counter(
                    t.get("_genre", "") for t in liked_songs if t.get("_genre")
                )
                if genre_counts:
                    top_genre = genre_counts.most_common(1)[0][0]
                    st.write(f"**Top genre:** {top_genre.replace('-', ' ').title()}")

                vibe_counts = collections.Counter(
                    t.get("_vibe", "") for t in liked_songs if t.get("_vibe")
                )
                if vibe_counts:
                    top_vibe = vibe_counts.most_common(1)[0][0]
                    st.write(f"**Top vibe:** {top_vibe}")

                mood_stats = db.get_mood_stats(user["id"])
                if mood_stats:
                    st.write("**🎭 Your top moods:**")
                    for mood, count in mood_stats.items():
                        st.caption(f"{mood} — {count}x")

        # ── Friends ───────────────────────────────────────────────────────────
        st.write("---")
        with st.expander("👫 Friends", expanded=False):
            # Add a friend
            st.write("**Add a friend**")
            add_username = st.text_input("Friend's username", key="add_friend_input", placeholder="e.g. alice")
            if st.button("Send request", key="send_friend_btn", use_container_width=True):
                if add_username.strip():
                    result = db.send_friend_request(user["id"], add_username.strip())
                    if result == "sent":
                        st.success(f"Friend request sent to **{add_username.strip()}**!")
                    elif result == "not_found":
                        st.error("User not found.")
                    elif result == "self":
                        st.error("You can't add yourself.")
                    elif result == "already":
                        st.info("Friend request already sent or you're already friends.")

            # Pending requests
            pending = _cached_pending_requests(user["id"])
            if pending:
                st.write("**Pending requests**")
                for req in pending:
                    st.write(f"🙋 **{req['username']}** wants to be your friend")
                    col_a, col_d = st.columns(2)
                    with col_a:
                        if st.button("✅ Accept", key=f"acc_{req['id']}", use_container_width=True):
                            db.accept_friend_request(user["id"], req["requester_id"])
                            st.rerun()
                    with col_d:
                        if st.button("❌ Decline", key=f"dec_{req['id']}", use_container_width=True):
                            db.decline_friend_request(user["id"], req["requester_id"])
                            st.rerun()

            # Friends list
            friends = _cached_friends(user["id"])
            if friends:
                st.write("**Your friends**")
                for f in friends:
                    col_name, col_btn = st.columns([3, 1])
                    with col_name:
                        st.write(f"👤 {f['username']}")
                    with col_btn:
                        if st.button("✕", key=f"unfriend_{f['id']}", help="Remove friend"):
                            db.remove_friend(user["id"], f["id"])
                            st.rerun()
                st.write("")
                if st.button("👥 See what friends liked", use_container_width=True, key="open_friends_feed"):
                    st.session_state["open_friends_view"] = True
                    st.session_state["open_playlist_tracks"] = None
                    st.rerun()
            elif not pending:
                st.caption("No friends yet. Add someone by username above.")


# ── Helper functions ─────────────────────────────────────────────────────────

def _deezer_get(url, **kwargs):
    """Wraps requests.get with error handling; returns None on failure."""
    try:
        return requests.get(url, **kwargs)
    except Exception:
        return None


def get_tracks_from_playlist(playlist_query):
    """Finds a Deezer playlist matching the query and returns its tracks."""
    url = f"https://api.deezer.com/search/playlist?q={playlist_query}"
    response = _deezer_get(url)
    if response is None:
        return []
    playlists = response.json().get("data", [])
    if not playlists:
        return []
    playlist_id = playlists[0]["id"]
    tracks_url = f"https://api.deezer.com/playlist/{playlist_id}"
    tracks_response = _deezer_get(tracks_url)
    if tracks_response is None:
        return []
    playlist_data = tracks_response.json()
    return playlist_data.get("tracks", {}).get("data", [])


def get_tracks_from_artist_discovery(artist_name):
    """Finds an artist + similar artists, returns a mixed list of their top tracks."""
    search_url = f"https://api.deezer.com/search/artist?q={artist_name}"
    response = _deezer_get(search_url)
    if response is None:
        return []
    artists = response.json().get("data", [])
    if not artists:
        return []
    main_artist_id = artists[0]["id"]
    all_tracks = []
    top_url = f"https://api.deezer.com/artist/{main_artist_id}/top?limit=10"
    top_response = _deezer_get(top_url)
    if top_response is not None:
        all_tracks.extend(top_response.json().get("data", []))
    related_url = f"https://api.deezer.com/artist/{main_artist_id}/related"
    related_response = _deezer_get(related_url)
    similar_artists = related_response.json().get("data", []) if related_response is not None else []
    for artist in similar_artists[:12]:
        artist_top_url = f"https://api.deezer.com/artist/{artist['id']}/top?limit=4"
        artist_top_response = _deezer_get(artist_top_url)
        if artist_top_response is not None:
            all_tracks.extend(artist_top_response.json().get("data", []))
    return all_tracks


@st.cache_data(ttl=86400)
def _get_release_year(album_id):
    """Fetch release year for a Deezer album (cached for 24 h)."""
    try:
        resp = requests.get(f"https://api.deezer.com/album/{album_id}", timeout=5)
        date = resp.json().get("release_date", "")
        return date[:4] if date else ""
    except Exception:
        return ""


def _fetch_one_deezer_track(song):
    """Helper: search Deezer for a single song."""
    query = f'{song["track_name"]} {song["artist"]}'
    search_url = f"https://api.deezer.com/search/track?q={query}&limit=1"
    try:
        response = requests.get(search_url, timeout=5)
        results = response.json().get("data", [])
        if results:
            track = results[0]
            track["_genre"] = song.get("track_genre", "")
            return track
        return None
    except Exception:
        return None


def get_tracks_from_recipe(recipe):
    """Filters the dataset by emotion recipe, then fetches Deezer tracks in parallel."""
    matching_songs = find_matching_songs(recipe, limit=50)
    if not matching_songs:
        return []
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(_fetch_one_deezer_track, matching_songs)
    return [t for t in results if t is not None]


def _limit_per_artist(tracks, max_per_artist=3):
    counts = {}
    result = []
    for t in tracks:
        artist = t.get("artist", {}).get("name", "")
        if counts.get(artist, 0) < max_per_artist:
            result.append(t)
            counts[artist] = counts.get(artist, 0) + 1
    return result


def build_discovery_queue(query, mode="search"):
    """Decides which strategy to use and returns a shuffled list of tracks."""
    if mode == "vibe":
        tracks = get_tracks_from_playlist(query)
    elif mode == "recipe":
        tracks = get_tracks_from_recipe(query)
    else:  # mode == "search"
        tracks = get_tracks_from_artist_discovery(query)
        if not tracks:
            fallback_url = f"https://api.deezer.com/search?q={query}"
            fallback_response = _deezer_get(fallback_url)
            tracks = fallback_response.json().get("data", []) if fallback_response is not None else []

    tracks = [t for t in tracks if t.get("preview")]

    # Deduplicate by track ID
    seen_ids = set()
    deduped = []
    for t in tracks:
        tid = t.get("id")
        if tid not in seen_ids:
            deduped.append(t)
            if tid:
                seen_ids.add(tid)
    tracks = deduped

    # Max 3 songs per artist
    tracks = _limit_per_artist(tracks)

    random.shuffle(tracks)
    return tracks


def start_new_session(query, mode="search", vibe_label=None):
    """Resets the queue with new tracks, filtering out already liked/saved songs."""
    tracks = build_discovery_queue(query, mode=mode)
    for t in tracks:
        if vibe_label:
            t["_vibe"] = vibe_label

    # Start with songs liked or saved in the current session
    seen_ids = {
        t["id"] for t in
        st.session_state["liked_songs"] + st.session_state["saved_playlist"]
        if t.get("id")
    }

    # Also exclude songs already saved in any DB playlist for this user
    user = st.session_state.get("user")
    if user:
        for pl in db.get_user_playlists(user["id"]):
            for t in db.get_playlist_tracks(pl["id"]):
                if t.get("id"):
                    seen_ids.add(t["id"])

    filtered = [t for t in tracks if t.get("id") not in seen_ids]

    if not tracks:
        st.warning("No songs found — try a different search, mood, or genre.")
    elif not filtered:
        st.info("You've already heard everything here! Try a different search to find new songs.")

    st.session_state["tracks"] = filtered
    st.session_state["current_index"] = 0
    st.session_state["selected_emotion"] = None
    st.session_state["selected_genre"] = None


def get_recommended_recipe(liked_songs):
    """Builds a recipe dict from the top genres in liked songs."""
    genre_counts = collections.Counter(
        t.get("_genre", "") for t in liked_songs if t.get("_genre")
    )
    if not genre_counts:
        return None
    top_genres = [g for g, _ in genre_counts.most_common(5)]
    return {"track_genre": top_genres}


# ── UI ───────────────────────────────────────────────────────────────────────

# ── Most Loved This Week ──────────────────────────────────────────────────────
top_songs = _cached_top_liked()
if top_songs:
    with st.expander("🔥 Most Loved This Week", expanded=False):
        for t, likes in top_songs:
            album_id = t.get("album", {}).get("id")
            year = _get_release_year(album_id) if album_id else ""
            genre_tag = t.get("_genre", "")
            meta = f"📅 {year}" if year else ""
            if genre_tag:
                meta += f"  ·  🎵 {genre_tag.replace('-', ' ').title()}"
            col_info, col_likes = st.columns([5, 1])
            with col_info:
                st.write(f"**{t['title']}** by {t['artist']['name']}")
                if meta:
                    st.caption(meta)
            with col_likes:
                st.markdown(f"❤️ **{likes}**")

st.write("")

# ── Search bar ───────────────────────────────────────────────────────────────
search_query = st.text_input("Search an artist, song, or genre", placeholder="e.g. Taylor Swift, jazz, The Weeknd")

if st.button("Start discovering 🎧"):
    if search_query.strip():
        start_new_session(search_query, mode="search", vibe_label=search_query)

# ── Emotion picker ───────────────────────────────────────────────────────────
st.write("**How are you feeling?**")
st.caption("Pick an emotion, then tell us what it means to *you*.")

emotion_cols = st.columns(len(EMOTION_RECIPES))
emotion_names = list(EMOTION_RECIPES.keys())

for i, emotion in enumerate(emotion_names):
    with emotion_cols[i]:
        if st.button(emotion, key=f"emotion_{i}"):
            st.session_state["selected_emotion"] = emotion
            st.session_state["selected_genre"] = None  # close genre picker
            st.session_state["tracks"] = []

# ── Emotion sub-category picker ──────────────────────────────────────────────
if st.session_state["selected_emotion"]:
    emotion = st.session_state["selected_emotion"]
    st.write(f"### What does **{emotion}** mean to you?")
    
    sub_categories = EMOTION_RECIPES[emotion]
    sub_cols = st.columns(2)
    sub_names = list(sub_categories.keys())
    
    for i, sub in enumerate(sub_names):
        col = sub_cols[i % 2]
        with col:
            if st.button(sub, key=f"sub_{i}", use_container_width=True):
                with st.spinner(f"Finding songs that feel like '{sub}'..."):
                    recipe = sub_categories[sub]
                    if st.session_state.get("user"):
                        db.record_mood(st.session_state["user"]["id"], f"{emotion} · {sub}")
                    start_new_session(recipe, mode="recipe", vibe_label=f"{emotion} · {sub}")
                    st.rerun()

# ── Genre picker ─────────────────────────────────────────────────────────────
st.write("**Or explore a genre:**")
st.caption("Pick a genre, then choose your style.")

genre_cols = st.columns(4)
genre_names = list(GENRE_RECIPES.keys())

for i, name in enumerate(genre_names):
    with genre_cols[i % 4]:
        if st.button(name, key=f"genre_{i}"):
            st.session_state["selected_genre"] = name
            st.session_state["selected_emotion"] = None  # close emotion picker
            st.session_state["tracks"] = []

# ── Genre sub-category picker ────────────────────────────────────────────────
if st.session_state["selected_genre"]:
    genre = st.session_state["selected_genre"]
    st.write(f"### What kind of **{genre}**?")

    sub_categories = GENRE_RECIPES[genre]
    sub_cols = st.columns(2)
    sub_names = list(sub_categories.keys())

    for i, sub in enumerate(sub_names):
        col = sub_cols[i % 2]
        with col:
            if st.button(sub, key=f"genre_sub_{i}", use_container_width=True):
                with st.spinner(f"Finding {sub} tracks..."):
                    recipe = sub_categories[sub]
                    if st.session_state.get("user"):
                        db.record_mood(st.session_state["user"]["id"], f"{genre} · {sub}")
                    start_new_session(recipe, mode="recipe", vibe_label=f"{genre} · {sub}")
                    st.rerun()

# ── Friends feed & playlists view ───────────────────────────────────────────
if st.session_state.get("open_friends_view") and st.session_state.get("user"):
    _fuser = st.session_state["user"]
    st.write("---")
    col_fhead, col_fclose = st.columns([5, 1])
    with col_fhead:
        st.subheader("👫 Friends Activity")
    with col_fclose:
        if st.button("✕ Close", key="close_friends_view", use_container_width=True):
            st.session_state["open_friends_view"] = False
            st.session_state["open_friend_playlist"] = None
            st.rerun()

    friends = db.get_friends(_fuser["id"])
    if not friends:
        st.info("You don't have any friends yet. Add friends from the sidebar!")
    else:
        # ── Friend playlist viewer ────────────────────────────────────────────
        if st.session_state.get("open_friend_playlist"):
            fp_username, fp_pl_id, fp_pl_name = st.session_state["open_friend_playlist"]
            fp_tracks = db.get_playlist_tracks(fp_pl_id)
            st.subheader(f"📋 {fp_pl_name} — by {fp_username}")
            if st.button("← Back to friends", key="back_from_friend_pl"):
                st.session_state["open_friend_playlist"] = None
                st.rerun()
            if not fp_tracks:
                st.caption("This playlist is empty.")
            for t in fp_tracks:
                st.write(f"**{t['title']}** by {t['artist']['name']}")
                if t.get("preview"):
                    st.audio(t["preview"], format="audio/mp3")
                st.write("")
        else:
            # ── Friends' liked songs ──────────────────────────────────────────
            st.write("**❤️ What your friends have liked recently**")
            friends_liked = db.get_friends_liked_songs(_fuser["id"], limit=20)
            if not friends_liked:
                st.caption("Your friends haven't liked any songs yet.")
            else:
                for _fusername, _ft in friends_liked:
                    col_fi, col_fa = st.columns([5, 2])
                    with col_fi:
                        st.write(f"**{_fusername}** liked **{_ft['title']}** by {_ft['artist']['name']}")
                    with col_fa:
                        if _ft.get("preview"):
                            st.audio(_ft["preview"], format="audio/mp3")
                    st.write("")

            # ── Friends' playlists ────────────────────────────────────────────
            st.write("---")
            st.write("**🎵 Your friends' playlists**")
            friends_pls = db.get_friends_playlists(_fuser["id"])
            if not friends_pls:
                st.caption("Your friends haven't created any playlists yet.")
            else:
                for fp in friends_pls:
                    col_fpl, col_fop = st.columns([4, 1])
                    with col_fpl:
                        st.write(f"📋 **{fp['name']}** by {fp['username']} · {fp['track_count']} songs")
                    with col_fop:
                        if fp["track_count"] > 0:
                            if st.button("▶️ Open", key=f"open_fpl_{fp['playlist_id']}", use_container_width=True):
                                st.session_state["open_friend_playlist"] = (
                                    fp["username"], fp["playlist_id"], fp["name"]
                                )
                                st.rerun()

# ── Playlist list view ───────────────────────────────────────────────────────
elif st.session_state["open_playlist_tracks"] is not None:
    is_liked_view = st.session_state["open_playlist_is_liked"]
    pl_tracks = st.session_state["liked_songs"] if is_liked_view else st.session_state["open_playlist_tracks"]
    pl_name = st.session_state["open_playlist_name"] or "Playlist"
    st.write("---")
    col_head, col_close = st.columns([5, 1])
    with col_head:
        st.subheader(f"{pl_name}")
    with col_close:
        if st.button("✕ Close", use_container_width=True):
            st.session_state["open_playlist_tracks"] = None
            st.session_state["open_playlist_name"] = None
            st.session_state["open_playlist_is_liked"] = False
            st.rerun()

    if is_liked_view and not pl_tracks:
        st.caption("No liked songs. Tap 👍 while discovering to add some.")

    if is_liked_view and pl_tracks:
        if st.button("🎯 Recommended for you", use_container_width=True, key="liked_view_reco"):
            recipe = get_recommended_recipe(pl_tracks)
            if recipe:
                st.session_state["open_playlist_tracks"] = None
                st.session_state["open_playlist_name"] = None
                st.session_state["open_playlist_is_liked"] = False
                start_new_session(recipe, mode="recipe", vibe_label="🎯 Based on your taste")
                st.rerun()
            else:
                # Fall back: use artist names from liked songs to build a discovery queue
                artists = list({t["artist"]["name"] for t in pl_tracks if t.get("artist", {}).get("name")})
                if artists:
                    pick = random.choice(artists)
                    st.session_state["open_playlist_tracks"] = None
                    st.session_state["open_playlist_name"] = None
                    st.session_state["open_playlist_is_liked"] = False
                    start_new_session(pick, mode="search", vibe_label=f"🎯 Similar to {pick}")
                    st.rerun()
                else:
                    st.info("Like some songs first to get personalised recommendations.")

    for i, t in enumerate(pl_tracks):
        st.write(f"**{t['title']}** by {t['artist']['name']}")
        if t.get("preview"):
            st.audio(t["preview"], format="audio/mp3")
        if is_liked_view:
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button("❤️ Save to playlist", key=f"liked_save_{i}", use_container_width=True):
                    st.session_state["saved_playlist"].append(t)
                    st.rerun()
            with btn_col2:
                if st.button("👎 Unlike", key=f"liked_remove_{i}", use_container_width=True):
                    removed = st.session_state["liked_songs"].pop(i)
                    if st.session_state.get("user") and removed.get("id"):
                        db.remove_liked_song(st.session_state["user"]["id"], removed["id"])
                    st.rerun()
        st.write("")

    if not is_liked_view:
        st.write("---")
        link_col1, link_col2 = st.columns(2)
        with link_col1:
            if st.button("🎵 Open in Spotify", key="pl_view_sp", use_container_width=True):
                st.session_state["pl_view_show_sp"] = not st.session_state.get("pl_view_show_sp", False)
                st.session_state["pl_view_show_dz"] = False
            if st.session_state.get("pl_view_show_sp"):
                for t in pl_tracks:
                    q = f"{t['title']} {t['artist']['name']}".replace(" ", "%20")
                    st.markdown(f"[{t['title']}](https://open.spotify.com/search/{q})")
        with link_col2:
            if st.button("🎧 Open in Deezer", key="pl_view_dz", use_container_width=True):
                st.session_state["pl_view_show_dz"] = not st.session_state.get("pl_view_show_dz", False)
                st.session_state["pl_view_show_sp"] = False
            if st.session_state.get("pl_view_show_dz"):
                for t in pl_tracks:
                    url = t.get("link", f"https://www.deezer.com/track/{t['id']}")
                    st.markdown(f"[{t['title']}]({url})")

# ── Swipe view ───────────────────────────────────────────────────────────────
else:
    tracks = st.session_state["tracks"]
    index = st.session_state["current_index"]

    if tracks and index < len(tracks):
        current_track = tracks[index]
        st.write("---")
        cover = current_track.get("album", {}).get("cover_big") or current_track.get("album", {}).get("cover_medium") or current_track.get("album", {}).get("cover")
        if cover:
            st.image(cover)
        st.subheader(current_track["title"])
        st.write(f"by **{current_track['artist']['name']}**")
        progress = (index + 1) / len(tracks)
        st.progress(progress)
        st.caption(f"Song {index + 1} of {len(tracks)}")

        # ── Why This Song? ────────────────────────────────────────────────
        info_parts = []
        album_id = current_track.get("album", {}).get("id")
        year = _get_release_year(album_id) if album_id else ""
        if year:
            info_parts.append(f"📅 {year}")
        genre_tag = current_track.get("_genre", "")
        if genre_tag:
            info_parts.append(f"🎵 {genre_tag.replace('-', ' ').title()}")
        vibe_tag = current_track.get("_vibe", "")
        if vibe_tag:
            info_parts.append(f"🎭 {vibe_tag}")
        if info_parts:
            st.caption(" · ".join(info_parts))

        st.audio(current_track["preview"])

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("👎 Skip"):
                try:
                    db.record_interaction(current_track, "skip")
                except Exception:
                    pass
                st.session_state["current_index"] += 1
                st.rerun()
        with col2:
            if st.button("👍 Like"):
                try:
                    db.record_interaction(current_track, "like")
                    if st.session_state.get("user"):
                        db.save_liked_song(st.session_state["user"]["id"], current_track)
                except Exception:
                    pass
                st.session_state["liked_songs"].append(current_track)
                st.session_state["current_index"] += 1
                st.rerun()
        with col3:
            if st.button("❤️ Save"):
                saved_ids = {t["id"] for t in st.session_state["saved_playlist"] if t.get("id")}
                if current_track.get("id") in saved_ids:
                    st.toast("Already in your playlist!")
                else:
                    try:
                        db.record_interaction(current_track, "like")
                        if st.session_state.get("user"):
                            db.save_liked_song(st.session_state["user"]["id"], current_track)
                    except Exception:
                        pass
                    st.session_state["saved_playlist"].append(current_track)
                st.session_state["current_index"] += 1
                st.rerun()

    elif tracks and index >= len(tracks):
        st.write("---")
        st.success("🎉 You've swiped through all the songs! Pick another vibe to discover more.")
        if st.button("🎯 Discover more like your liked songs", use_container_width=True):
            liked = st.session_state["liked_songs"]
            recipe = get_recommended_recipe(liked)
            if recipe:
                start_new_session(recipe, mode="recipe", vibe_label="🎯 Based on your taste")
                st.rerun()
            elif liked:
                pick = random.choice(liked)["artist"]["name"]
                start_new_session(pick, mode="search", vibe_label=f"🎯 Similar to {pick}")
                st.rerun()
            else:
                st.info("Like some songs first to get personalised recommendations.")

    elif not tracks and index == 0:
        st.info("👆 Search for an artist, pick a mood above, or explore a genre to start discovering music.")


# ── Current session playlist ─────────────────────────────────────────────────
st.write("---")
saved_playlist = st.session_state["saved_playlist"]
st.header(f"❤️ My Playlist ({len(saved_playlist)} songs)")

if not saved_playlist:
    st.write("No songs saved yet. Tap ❤️ on songs you love!")
else:
    for saved in saved_playlist:
        st.write(f"- **{saved['title']}** by {saved['artist']['name']}")

    # ── Save to account ───────────────────────────────────────────────────────
    st.write("")
    if st.session_state["user"]:
        st.subheader("💾 Save to my account")
        user = st.session_state["user"]
        existing = _cached_user_playlists(user["id"])
        pl_names = [pl["name"] for pl in existing]

        save_mode = st.radio(
            "Save to",
            ["New playlist", "Existing playlist"] if existing else ["New playlist"],
            horizontal=True,
            label_visibility="collapsed",
        )

        if save_mode == "New playlist":
            new_pl_name = st.text_input("Playlist name", placeholder="e.g. Summer Bangers")
            if st.button("💾 Save", use_container_width=True):
                if new_pl_name.strip():
                    pl_id = db.create_playlist(user["id"], new_pl_name.strip())
                    db.add_tracks_to_playlist(pl_id, saved_playlist)
                    st.session_state["saved_playlist"] = []
                    _cached_user_playlists.clear()
                    _cached_playlist_track_count.clear()
                    st.success(f"✅ Saved to **{new_pl_name}**! Like new songs to build your next playlist.")
                    st.rerun()
                else:
                    st.warning("Enter a playlist name first.")
        else:
            chosen = st.selectbox("Choose playlist", pl_names)
            if st.button("💾 Add to playlist", use_container_width=True):
                pl_id = next(pl["id"] for pl in existing if pl["name"] == chosen)
                db.add_tracks_to_playlist(pl_id, saved_playlist)
                st.session_state["saved_playlist"] = []
                _cached_playlist_track_count.clear()
                st.success(f"✅ Added to **{chosen}**! Like new songs to build your next playlist.")
                st.rerun()
    else:
        st.caption("🔒 [Log in](#) to save playlists to your account.")

    st.write("")
    st.subheader("Export playlist and save songs")

    export_col1, export_col2 = st.columns(2)

    # ── CSV download ──────────────────────────────────────────────────────────
    with export_col1:
        csv_data = playlist_to_csv(saved_playlist)
        st.download_button(
            label="⬇️ Download CSV",
            data=csv_data,
            file_name="my_playlist.csv",
            mime="text/csv",
            use_container_width=True,
            help="Includes Deezer & Spotify search links for every song",
        )

    # ── Spotify ───────────────────────────────────────────────────────────────
    with export_col2:
        if st.button("🎵 Open in Spotify", use_container_width=True):
            st.session_state["show_spotify_links"] = True
            st.session_state["show_deezer_links"] = False

    if st.button("🎧 Open in Deezer", use_container_width=True):
        st.session_state["show_deezer_links"] = True
        st.session_state["show_spotify_links"] = False

    if st.session_state.get("show_spotify_links"):
        st.write("**Search each song on Spotify:**")
        for t in saved_playlist:
            q = f"{t['title']} {t['artist']['name']}".replace(" ", "%20")
            url = f"https://open.spotify.com/search/{q}"
            st.markdown(f"- [{t['title']} — {t['artist']['name']}]({url})")

    if st.session_state.get("show_deezer_links"):
        st.write("**Open each song on Deezer:**")
        for t in saved_playlist:
            url = t.get("link", f"https://www.deezer.com/track/{t['id']}")
            st.markdown(f"- [{t['title']} — {t['artist']['name']}]({url})")
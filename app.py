import io
import csv
import random
from concurrent.futures import ThreadPoolExecutor

import requests
import streamlit as st

from emotion_recipes import EMOTION_RECIPES
from genre_recipes import GENRE_RECIPES
from metadata_filter import find_matching_songs
import spotify_export
import db
import auth

db.init_db()

st.title("Music-Tok 🎵")
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
}
for _key, _val in _DEFAULTS.items():
    if _key not in st.session_state:
        st.session_state[_key] = _val

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


# ── Sidebar — account / saved playlists ──────────────────────────────────────

with st.sidebar:
    st.header("👤 My Account")

    if not st.session_state["user"]:
        tab_login, tab_reg = st.tabs(["Login", "Register"])

        with tab_login:
            lu = st.text_input("Username", key="li_user")
            lp = st.text_input("Password", type="password", key="li_pass")
            if st.button("Login", use_container_width=True, key="li_btn"):
                user = auth.login(lu, lp)
                if user:
                    st.session_state["user"] = user
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
                        st.session_state["user"] = auth.login(ru, rp)
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

        playlists = db.get_user_playlists(user["id"])
        if not playlists:
            st.caption("No saved playlists yet.")

        for pl in playlists:
            tracks = db.get_playlist_tracks(pl["id"])
            with st.expander(f"📋 {pl['name']} ({len(tracks)} songs)"):
                if tracks:
                    if st.button("▶️ Open playlist", key=f"open_{pl['id']}", use_container_width=True):
                        st.session_state["open_playlist_tracks"] = tracks
                        st.session_state["open_playlist_name"] = pl["name"]
                        st.session_state["open_playlist_is_liked"] = False
                        st.rerun()

                    csv_data = playlist_to_csv(tracks)
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
                        st.rerun()

                if st.session_state["renaming_pl_id"] == pl["id"]:
                    new_name = st.text_input("New name", value=pl["name"], key=f"newname_{pl['id']}")
                    if st.button("Save", key=f"savename_{pl['id']}", use_container_width=True):
                        if new_name.strip():
                            db.rename_playlist(pl["id"], new_name.strip(), user["id"])
                            st.session_state["renaming_pl_id"] = None
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


# ── Helper functions ─────────────────────────────────────────────────────────

def get_tracks_from_playlist(playlist_query):
    """Finds a Deezer playlist matching the query and returns its tracks."""
    url = f"https://api.deezer.com/search/playlist?q={playlist_query}"
    response = requests.get(url)
    playlists = response.json().get("data", [])
    if not playlists:
        return []
    playlist_id = playlists[0]["id"]
    tracks_url = f"https://api.deezer.com/playlist/{playlist_id}"
    tracks_response = requests.get(tracks_url)
    playlist_data = tracks_response.json()
    return playlist_data.get("tracks", {}).get("data", [])


def get_tracks_from_artist_discovery(artist_name):
    """Finds an artist + similar artists, returns a mixed list of their top tracks."""
    search_url = f"https://api.deezer.com/search/artist?q={artist_name}"
    response = requests.get(search_url)
    artists = response.json().get("data", [])
    if not artists:
        return []
    main_artist_id = artists[0]["id"]
    all_tracks = []
    top_url = f"https://api.deezer.com/artist/{main_artist_id}/top?limit=5"
    top_response = requests.get(top_url)
    all_tracks.extend(top_response.json().get("data", []))
    related_url = f"https://api.deezer.com/artist/{main_artist_id}/related"
    related_response = requests.get(related_url)
    similar_artists = related_response.json().get("data", [])
    for artist in similar_artists[:8]:
        artist_top_url = f"https://api.deezer.com/artist/{artist['id']}/top?limit=3"
        artist_top_response = requests.get(artist_top_url)
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
    matching_songs = find_matching_songs(recipe, limit=25)
    if not matching_songs:
        return []
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(_fetch_one_deezer_track, matching_songs)
    return [t for t in results if t is not None]


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
            fallback_response = requests.get(fallback_url)
            tracks = fallback_response.json().get("data", [])

    tracks = [t for t in tracks if t.get("preview")]
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

    st.session_state["tracks"] = [t for t in tracks if t.get("id") not in seen_ids]
    st.session_state["current_index"] = 0
    st.session_state["selected_emotion"] = None
    st.session_state["selected_genre"] = None


# ── UI ───────────────────────────────────────────────────────────────────────

# ── Most Loved This Week ──────────────────────────────────────────────────────
top_songs = db.get_top_liked(limit=8)
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
                    start_new_session(recipe, mode="recipe", vibe_label=f"{genre} · {sub}")
                    st.rerun()

# ── Playlist list view ───────────────────────────────────────────────────────
if st.session_state["open_playlist_tracks"] is not None:
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
                    st.session_state["liked_songs"].pop(i)
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
        st.image(current_track["album"]["cover_big"])
        st.subheader(current_track["title"])
        st.write(f"by **{current_track['artist']['name']}**")
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
                db.record_interaction(current_track, "skip")
                st.session_state["current_index"] += 1
                st.rerun()
        with col2:
            if st.button("👍 Like"):
                db.record_interaction(current_track, "like")
                st.session_state["liked_songs"].append(current_track)
                st.session_state["current_index"] += 1
                st.rerun()
        with col3:
            if st.button("❤️ Save"):
                db.record_interaction(current_track, "like")
                st.session_state["saved_playlist"].append(current_track)
                st.session_state["current_index"] += 1
                st.rerun()

    elif tracks and index >= len(tracks):
        st.write("---")
        st.success("🎉 You've swiped through all the songs! Pick another vibe to discover more.")


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
        existing = db.get_user_playlists(user["id"])
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
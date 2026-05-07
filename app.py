import io
import csv
import streamlit as st
import requests
import random
from emotion_recipes import EMOTION_RECIPES
from genre_recipes import GENRE_RECIPES
from metadata_filter import find_matching_songs
from concurrent.futures import ThreadPoolExecutor
import spotify_export

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


# ----------- SESSION STATE SETUP -----------
if "tracks" not in st.session_state:
    st.session_state["tracks"] = []
if "current_index" not in st.session_state:
    st.session_state["current_index"] = 0
if "saved_playlist" not in st.session_state:
    st.session_state["saved_playlist"] = []
if "selected_emotion" not in st.session_state:
    st.session_state["selected_emotion"] = None
if "selected_genre" not in st.session_state:
    st.session_state["selected_genre"] = None
if "spotify_token" not in st.session_state:
    st.session_state["spotify_token"] = None
if "show_spotify_links" not in st.session_state:
    st.session_state["show_spotify_links"] = False

# ================================================================
# HELPER FUNCTIONS — the "brain" of the app
# ================================================================

def get_tracks_from_playlist(playlist_query):
    """Finds a Deezer playlist matching the query and returns its tracks."""
    url = f"https://api.deezer.com/search/playlist?q={playlist_query}"
    response = requests.get(url)
    playlists = response.json().get("data", [])
    if len(playlists) == 0:
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
    if len(artists) == 0:
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


# 🆕 NEW: This is the magic function. It takes our Kaggle-filtered songs
# and looks each one up on Deezer to get a playable preview.
def _fetch_one_deezer_track(song):
    """Helper: search Deezer for a single song."""
    query = f'{song["track_name"]} {song["artist"]}'
    search_url = f"https://api.deezer.com/search/track?q={query}&limit=1"
    try:
        response = requests.get(search_url, timeout=5)
        results = response.json().get("data", [])
        return results[0] if results else None
    except Exception:
        return None


def get_tracks_from_recipe(recipe):
    """
    Filters Kaggle dataset by emotion recipe, then fetches all matches
    from Deezer IN PARALLEL (much faster).
    """
    matching_songs = find_matching_songs(recipe, limit=25)
    if len(matching_songs) == 0:
        return []
    
    # 🚀 FIX 1: Fire all Deezer requests at once instead of one at a time
    from concurrent.futures import ThreadPoolExecutor
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(_fetch_one_deezer_track, matching_songs)
    
    # Filter out the None values (failed searches)
    deezer_tracks = [t for t in results if t is not None]
    return deezer_tracks


def build_discovery_queue(query, mode="search"):
    """Decides which strategy to use and returns a shuffled list of tracks."""
    if mode == "vibe":
        tracks = get_tracks_from_playlist(query)
    elif mode == "recipe":
        tracks = get_tracks_from_recipe(query)
    else:  # mode == "search"
        tracks = get_tracks_from_artist_discovery(query)
        if len(tracks) == 0:
            fallback_url = f"https://api.deezer.com/search?q={query}"
            fallback_response = requests.get(fallback_url)
            tracks = fallback_response.json().get("data", [])

    tracks = [t for t in tracks if t.get("preview")]
    random.shuffle(tracks)
    return tracks


def start_new_session(query, mode="search"):
    """Resets the queue with new tracks."""
    st.session_state["tracks"] = build_discovery_queue(query, mode=mode)
    st.session_state["current_index"] = 0
    st.session_state["selected_emotion"] = None
    st.session_state["selected_genre"] = None


def playlist_to_csv(tracks):
    """Converts saved tracks to a CSV string with Deezer and Spotify links."""
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


# ================================================================
# UI — what the user sees
# ================================================================

# ----------- SEARCH BAR -----------
search_query = st.text_input("Search an artist, song, or genre", placeholder="e.g. Taylor Swift, jazz, The Weeknd")

if st.button("Start discovering 🎧"):
    if search_query.strip():
        start_new_session(search_query, mode="search")

# ----------- 🆕 NEW: PERSONALIZED EMOTION PICKER -----------
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

# ----------- 🆕 NEW: SUB-CATEGORY PICKER (shows after emotion selected) -----------
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
                    start_new_session(recipe, mode="recipe")
                    st.rerun()

# ----------- GENRE PICKER -----------
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

# ----------- GENRE SUB-CATEGORY PICKER -----------
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
                    start_new_session(recipe, mode="recipe")
                    st.rerun()

# ----------- THE SWIPE VIEW -----------
tracks = st.session_state["tracks"]
index = st.session_state["current_index"]

if len(tracks) > 0 and index < len(tracks):
    current_track = tracks[index]
    st.write("---")
    st.image(current_track["album"]["cover_big"])
    st.subheader(current_track["title"])
    st.write(f"by **{current_track['artist']['name']}**")
    st.caption(f"Song {index + 1} of {len(tracks)}")
    st.audio(current_track["preview"])
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("👎 Skip"):
            st.session_state["current_index"] += 1
            st.rerun()
    with col2:
        if st.button("👍 Like"):
            st.session_state["current_index"] += 1
            st.rerun()
    with col3:
        if st.button("❤️ Save"):
            st.session_state["saved_playlist"].append(current_track)
            st.session_state["current_index"] += 1
            st.rerun()

elif len(tracks) > 0 and index >= len(tracks):
    st.write("---")
    st.success("🎉 You've swiped through all the songs! Pick another vibe to discover more.")

# ----------- PLAYLIST -----------
st.write("---")
saved_playlist = st.session_state["saved_playlist"]
st.header(f"❤️ My Playlist ({len(saved_playlist)} songs)")

if len(saved_playlist) == 0:
    st.write("No songs saved yet. Tap ❤️ on songs you love!")
else:
    for saved in saved_playlist:
        deezer_url = saved.get("link", f"https://www.deezer.com/track/{saved['id']}")
        st.write(f"- **{saved['title']}** by {saved['artist']['name']} — [Open in Deezer]({deezer_url})")

    st.write("")
    st.subheader("Export playlist")

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

    if st.session_state.get("show_spotify_links"):
        st.write("**Search each song on Spotify:**")
        for t in saved_playlist:
            q = f"{t['title']} {t['artist']['name']}".replace(" ", "%20")
            url = f"https://open.spotify.com/search/{q}"
            st.markdown(f"- [{t['title']} — {t['artist']['name']}]({url})")
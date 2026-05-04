import streamlit as st
import requests
import random  # We'll use this to shuffle the songs for discovery

st.title("Music-Tok 🎵")
st.write("Discover new music, one song at a time")

# ----------- SESSION STATE SETUP -----------
if "tracks" not in st.session_state:
    st.session_state["tracks"] = []
if "current_index" not in st.session_state:
    st.session_state["current_index"] = 0
if "saved_playlist" not in st.session_state:
    st.session_state["saved_playlist"] = []

# ================================================================
# HELPER FUNCTIONS — the "brain" of the app
# ================================================================

def get_tracks_from_playlist(playlist_query):
    """Finds a Deezer playlist matching the query and returns its tracks."""
    # Step 1: search Deezer for playlists matching this vibe
    url = f"https://api.deezer.com/search/playlist?q={playlist_query}"
    response = requests.get(url)
    playlists = response.json().get("data", [])
    
    if len(playlists) == 0:
        return []  # No playlist found, return empty list
    
    # Step 2: take the first (most popular) playlist
    playlist_id = playlists[0]["id"]
    
    # Step 3: fetch the tracks in that playlist
    tracks_url = f"https://api.deezer.com/playlist/{playlist_id}"
    tracks_response = requests.get(tracks_url)
    playlist_data = tracks_response.json()
    
    return playlist_data.get("tracks", {}).get("data", [])


def get_tracks_from_artist_discovery(artist_name):
    """Finds an artist + similar artists, returns a mixed list of their top tracks."""
    # Step 1: search for the artist
    search_url = f"https://api.deezer.com/search/artist?q={artist_name}"
    response = requests.get(search_url)
    artists = response.json().get("data", [])
    
    if len(artists) == 0:
        return []  # Artist not found
    
    # Step 2: get that artist's ID
    main_artist_id = artists[0]["id"]
    
    # Step 3: get top tracks from the main artist (just a few, so similar artists get space)
    all_tracks = []
    top_url = f"https://api.deezer.com/artist/{main_artist_id}/top?limit=5"
    top_response = requests.get(top_url)
    all_tracks.extend(top_response.json().get("data", []))
    
    # Step 4: find similar artists
    related_url = f"https://api.deezer.com/artist/{main_artist_id}/related"
    related_response = requests.get(related_url)
    similar_artists = related_response.json().get("data", [])
    
    # Step 5: from each similar artist, grab their top 3 songs
    for artist in similar_artists[:8]:  # just take the first 8 similar artists
        artist_top_url = f"https://api.deezer.com/artist/{artist['id']}/top?limit=3"
        artist_top_response = requests.get(artist_top_url)
        all_tracks.extend(artist_top_response.json().get("data", []))
    
    return all_tracks


def build_discovery_queue(query, is_vibe=False):
    """The MAIN function — decides which strategy to use and returns a shuffled list of tracks."""
    if is_vibe:
        # Vibes use the playlist strategy
        tracks = get_tracks_from_playlist(query)
    else:
        # Artist/keyword search uses the discovery strategy
        tracks = get_tracks_from_artist_discovery(query)
        
        # If the artist search found nothing, fall back to a regular keyword search
        if len(tracks) == 0:
            fallback_url = f"https://api.deezer.com/search?q={query}"
            fallback_response = requests.get(fallback_url)
            tracks = fallback_response.json().get("data", [])
    
    # Remove tracks that have no preview (some songs don't have one)
    tracks = [t for t in tracks if t.get("preview")]
    
    # Shuffle them so each session feels different
    random.shuffle(tracks)
    
    return tracks


def start_new_session(query, is_vibe=False):
    """Resets the queue with new tracks."""
    st.session_state["tracks"] = build_discovery_queue(query, is_vibe=is_vibe)
    st.session_state["current_index"] = 0


# ================================================================
# UI — what the user sees
# ================================================================

# ----------- SEARCH BAR -----------
search_query = st.text_input("Search an artist, song, or genre", placeholder="e.g. Taylor Swift, jazz, The Weeknd")

if st.button("Start discovering 🎧"):
    if search_query.strip():  # only search if something was typed
        start_new_session(search_query, is_vibe=False)

# ----------- VIBE BUTTONS -----------
st.write("**Or pick a vibe:**")

vibes = {
    "😌 Chill": "chill vibes",
    "🍽️ Dinner Party": "dinner party",
    "💪 Workout": "workout motivation",
    "🚗 Road Trip": "road trip",
    "🥲 Sad": "sad songs",
    "🎉 Party": "party hits",
    "🌙 Late Night": "late night",
    "🧠 Focus": "focus study",
}

vibe_cols = st.columns(4)
vibe_names = list(vibes.keys())

for i in range(len(vibe_names)):
    col = vibe_cols[i % 4]
    with col:
        if st.button(vibe_names[i]):
            start_new_session(vibes[vibe_names[i]], is_vibe=True)

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
    st.success("🎉 You've swiped through all the songs! Search again to discover more.")

# ----------- PLAYLIST -----------
st.write("---")
st.header(f"❤️ My Playlist ({len(st.session_state['saved_playlist'])} songs)")

if len(st.session_state["saved_playlist"]) == 0:
    st.write("No songs saved yet. Tap ❤️ on songs you love!")
else:
    for saved in st.session_state["saved_playlist"]:
        st.write(f"- **{saved['title']}** by {saved['artist']['name']}")
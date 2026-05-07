"""
Deezer export — OAuth + playlist creation via the Deezer API.
Advantage: we already have Deezer track IDs, so no searching needed.
"""
from urllib.parse import urlencode
import requests
import streamlit as st

_AUTH_URL  = "https://connect.deezer.com/oauth/auth.php"
_TOKEN_URL = "https://connect.deezer.com/oauth/access_token.php"
_API_URL   = "https://api.deezer.com"


def _creds():
    return (
        st.secrets["DEEZER_APP_ID"],
        st.secrets["DEEZER_SECRET"],
        st.secrets.get("APP_REDIRECT_URI", "http://localhost:8501"),
    )


def is_configured():
    try:
        _creds()
        return True
    except Exception:
        return False


def get_auth_url():
    app_id, _, redirect_uri = _creds()
    params = {
        "app_id": app_id,
        "redirect_uri": redirect_uri,
        "perms": "manage_library",
        "state": "deezer",
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


def exchange_code(code):
    app_id, secret, _ = _creds()
    resp = requests.get(
        _TOKEN_URL,
        params={
            "app_id": app_id,
            "secret": secret,
            "code": code,
            "output": "json",
        },
    )
    resp.raise_for_status()
    return resp.json()  # {"access_token": ..., "expires": 0}


def create_playlist(saved_tracks, token, name="Music-Tok Playlist"):
    """
    Creates a Deezer playlist from saved_tracks (list of Deezer track dicts).
    Track IDs are already known — no searching needed.
    Returns (playlist_url, added_count, total_count).
    """
    # 1. Create empty playlist
    resp = requests.post(
        f"{_API_URL}/user/me/playlists",
        params={"access_token": token, "title": name},
    )
    resp.raise_for_status()
    playlist_id = resp.json()["id"]

    # 2. Add all track IDs in one request
    track_ids = [str(t["id"]) for t in saved_tracks if t.get("id")]
    if track_ids:
        requests.post(
            f"{_API_URL}/playlist/{playlist_id}/tracks",
            params={
                "access_token": token,
                "songs": ",".join(track_ids),
            },
        )

    playlist_url = f"https://www.deezer.com/playlist/{playlist_id}"
    return playlist_url, len(track_ids), len(saved_tracks)

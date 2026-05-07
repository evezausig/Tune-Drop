"""
Spotify export — OAuth + playlist creation via the Spotify Web API.
Uses requests directly (no spotipy dependency).
"""
import base64
from urllib.parse import urlencode
import requests
import streamlit as st

_AUTH_URL  = "https://accounts.spotify.com/authorize"
_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API_URL   = "https://api.spotify.com/v1"
_SCOPE     = "playlist-modify-public playlist-modify-private user-read-private"


def _creds():
    return (
        st.secrets["SPOTIFY_CLIENT_ID"],
        st.secrets["SPOTIFY_CLIENT_SECRET"],
        st.secrets.get("APP_REDIRECT_URI", "http://localhost:8501"),
    )


def is_configured():
    try:
        _creds()
        return True
    except Exception:
        return False


def get_auth_url():
    client_id, _, redirect_uri = _creds()
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": _SCOPE,
        "state": "spotify",
        "show_dialog": "true",
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


def exchange_code(code):
    client_id, client_secret, redirect_uri = _creds()
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = requests.post(
        _TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )
    resp.raise_for_status()
    return resp.json()  # {"access_token": ..., "refresh_token": ..., "expires_in": ...}


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _search_spotify_uri(title, artist, token):
    """Returns the Spotify URI for the best-matching track, or None."""
    query = f"track:{title} artist:{artist}"
    resp = requests.get(
        f"{_API_URL}/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": query, "type": "track", "limit": 1},
    )
    items = resp.json().get("tracks", {}).get("items", [])
    return items[0]["uri"] if items else None


def create_playlist(saved_tracks, token, name="Music-Tok Playlist"):
    """
    Creates a Spotify playlist from saved_tracks (list of Deezer track dicts).
    Returns (playlist_url, matched_count, total_count).
    """
    # 1. Get the user's Spotify ID
    me_resp = requests.get(f"{_API_URL}/me", headers=_headers(token))
    me = me_resp.json()
    if "error" in me:
        raise Exception(f"Spotify API error: {me['error'].get('message', me['error'])} (status {me['error'].get('status', '?')})")
    user_id = me["id"]

    # 2. Create an empty playlist
    pl_resp = requests.post(
        f"{_API_URL}/users/{user_id}/playlists",
        headers=_headers(token),
        json={"name": name, "public": True, "description": "Exported from Music-Tok 🎵"},
    )
    playlist = pl_resp.json()
    if "error" in playlist:
        raise Exception(f"Could not create playlist: {playlist['error'].get('message', playlist['error'])}")
    playlist_id  = playlist["id"]
    playlist_url = playlist["external_urls"]["spotify"]

    # 3. Search Spotify for each saved track
    uris = []
    for t in saved_tracks:
        uri = _search_spotify_uri(t["title"], t["artist"]["name"], token)
        if uri:
            uris.append(uri)

    # 4. Add matched tracks (Spotify allows max 100 per request)
    for i in range(0, len(uris), 100):
        requests.post(
            f"{_API_URL}/playlists/{playlist_id}/tracks",
            headers=_headers(token),
            json={"uris": uris[i : i + 100]},
        )

    return playlist_url, len(uris), len(saved_tracks)

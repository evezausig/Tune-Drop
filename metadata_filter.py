"""
Filters the Spotify dataset based on an emotion recipe (and optional genre).
"""
import os
import pandas as pd
import streamlit as st

CSV_PATH = "spotify_tracks.csv"
CSV_URL = "https://huggingface.co/datasets/maharshipandya/spotify-tracks-dataset/resolve/main/dataset.csv"


@st.cache_data
def load_dataset():
    # Auto-download the CSV if it's not present (e.g. first run on Streamlit Cloud)
    if not os.path.exists(CSV_PATH):
        with st.spinner("Loading the music database (first-time setup)..."):
            df = pd.read_csv(CSV_URL)
            df.to_csv(CSV_PATH, index=False)
            return df
    
    df = pd.read_csv(CSV_PATH)
    
    # Strip out junk genres if the genre_groups module exists
    try:
        from genre_groups import get_all_excluded_genres
        excluded = get_all_excluded_genres()
        df = df[~df["track_genre"].isin(excluded)]
    except ImportError:
        pass
    
    return df


def find_matching_songs(recipe, genre_group=None, limit=25):
    df = load_dataset()
    filtered = df.copy()
    
    if genre_group:
        try:
            from genre_groups import get_allowed_genres_for_group
            allowed = get_allowed_genres_for_group(genre_group)
            if allowed:
                filtered = filtered[filtered["track_genre"].isin(allowed)]
        except ImportError:
            pass
    
    for feature, value in recipe.items():
        if isinstance(value, tuple):
            low, high = value
            filtered = filtered[
                (filtered[feature] >= low) & (filtered[feature] <= high)
            ]
        elif isinstance(value, list):
            filtered = filtered[filtered[feature].isin(value)]
        else:
            filtered = filtered[filtered[feature] == value]
    
    filtered = filtered.sort_values("popularity", ascending=False)
    top = filtered.head(limit)
    
    results = []
    for _, row in top.iterrows():
        artist = str(row["artists"]).split(";")[0]
        results.append({
            "artist": artist,
            "track_name": row["track_name"],
            "track_genre": str(row.get("track_genre", "")),
        })
    return results
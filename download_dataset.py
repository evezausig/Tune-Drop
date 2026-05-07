import pandas as pd

# Direct download from Hugging Face (no Kaggle account required)
url = "https://huggingface.co/datasets/maharshipandya/spotify-tracks-dataset/resolve/main/dataset.csv"

print("Downloading Spotify dataset (~20 MB)...")
df = pd.read_csv(url)

# Save it locally so we don't re-download every time
df.to_csv("spotify_tracks.csv", index=False)

print(f"✅ Done! Saved {len(df)} tracks to spotify_tracks.csv")
print("\nColumns available:")
print(df.columns.tolist())
print("\nFirst 3 rows:")
print(df[["track_name", "artists", "valence", "energy", "danceability"]].head(3))
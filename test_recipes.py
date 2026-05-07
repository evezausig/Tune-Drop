from emotion_recipes import EMOTION_RECIPES
from metadata_filter import find_matching_songs

# Test: "Sad" → "Quiet & melancholic"
recipe = EMOTION_RECIPES["🥲 Sad"]["🌧️ Quiet & melancholic"]
matches = find_matching_songs(recipe, limit=10)

print("Top 10 'quiet & melancholic' songs:\n")
for song in matches:
    print(f"  • {song['track_name']} — {song['artist']}")
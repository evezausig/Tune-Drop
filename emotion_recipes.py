"""
Emotion recipes — different personal definitions of each emotion.
Each recipe is a set of filters we apply to the Spotify dataset.
"""

EMOTION_RECIPES = {
    "🥲 Sad": {
        "🌧️ Quiet & melancholic": {
            "valence": (0.0, 0.35),
            "energy": (0.0, 0.4),
            "acousticness": (0.5, 1.0),
        },
        "🎭 Dramatic & heavy": {
            "valence": (0.0, 0.4),
            "energy": (0.6, 1.0),
            "mode": 0,  # minor key
        },
        "💔 Bittersweet": {
            "valence": (0.3, 0.5),
            "energy": (0.2, 0.5),
            "acousticness": (0.4, 1.0),
        },
        "🎵 Sad lyrics, upbeat sound": {
            "valence": (0.0, 0.4),
            "danceability": (0.6, 1.0),
        },
    },

    "😊 Happy": {
        "☀️ Bright & sunny": {
            "valence": (0.7, 1.0),
            "energy": (0.5, 0.85),
            "danceability": (0.5, 1.0),
        },
        "🎉 Euphoric & loud": {
            "valence": (0.6, 1.0),
            "energy": (0.8, 1.0),
        },
        "🌸 Soft & content": {
            "valence": (0.6, 0.9),
            "energy": (0.3, 0.6),
            "acousticness": (0.3, 1.0),
        },
    },

    "🧠 Focus": {
        "📚 Deep concentration": {
            "energy": (0.2, 0.5),
            "instrumentalness": (0.5, 1.0),
            "speechiness": (0.0, 0.1),
        },
        "☕ Coffeeshop background": {
            "energy": (0.3, 0.6),
            "acousticness": (0.4, 1.0),
            "speechiness": (0.0, 0.15),
        },
    },

    "💪 Workout": {
        "🔥 High intensity": {
            "energy": (0.8, 1.0),
            "tempo": (140, 220),
            "danceability": (0.5, 1.0),
        },
        "🏃 Steady cardio": {
            "energy": (0.6, 0.9),
            "tempo": (120, 145),
        },
    },

    "🌙 Late Night": {
        "🌌 Atmospheric & dreamy": {
            "energy": (0.2, 0.5),
            "valence": (0.2, 0.6),
            "acousticness": (0.3, 1.0),
        },
        "🍷 Smooth & sultry": {
            "energy": (0.3, 0.6),
            "danceability": (0.5, 0.85),
            "valence": (0.3, 0.7),
        },
    },
}
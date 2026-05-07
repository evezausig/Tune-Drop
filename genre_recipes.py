"""
Genre recipes — each broad genre maps to subgenre flavors.
Each recipe filters the Spotify dataset by track_genre (list → isin)
and optionally by audio features.
"""

GENRE_RECIPES = {
    "🎤 Pop": {
        "✨ Mainstream Pop": {"track_genre": ["pop", "power-pop", "pop-film"]},
        "🌙 Indie Pop": {"track_genre": ["indie-pop", "indie"]},
        "🤖 Synth Pop": {"track_genre": ["synth-pop"]},
        "🌸 K-Pop / J-Pop": {"track_genre": ["k-pop", "j-pop", "j-dance"]},
    },
    "🎙️ Hip-Hop": {
        "🔥 Hip-Hop": {"track_genre": ["hip-hop"]},
        "💃 Dance Crossover": {
            "track_genre": ["hip-hop"],
            "danceability": (0.75, 1.0),
        },
        "🌙 Chill / Lo-fi": {
            "track_genre": ["hip-hop"],
            "energy": (0.0, 0.5),
            "instrumentalness": (0.3, 1.0),
        },
    },
    "🎸 Rock": {
        "🎵 Classic Rock": {"track_genre": ["rock", "rock-n-roll", "rockabilly"]},
        "🤘 Hard Rock & Punk": {"track_genre": ["hard-rock", "punk-rock", "punk"]},
        "🌀 Alternative & Grunge": {"track_genre": ["alt-rock", "alternative", "grunge", "emo"]},
        "🎸 Indie & Psych": {"track_genre": ["indie", "psych-rock"]},
    },
    "🎹 Electronic": {
        "🕺 Dance / EDM": {"track_genre": ["edm", "dance", "club", "electro", "disco"]},
        "🏠 House": {"track_genre": ["house", "deep-house", "chicago-house", "progressive-house"]},
        "⚡ Techno & Trance": {"track_genre": ["techno", "detroit-techno", "minimal-techno", "trance", "hardstyle"]},
        "🌊 Ambient & Trip-Hop": {"track_genre": ["electronic", "ambient", "new-age", "trip-hop", "idm", "breakbeat", "drum-and-bass"]},
    },
    "🎷 Jazz": {
        "🎷 Jazz": {"track_genre": ["jazz"]},
        "🎹 Instrumental": {"track_genre": ["piano", "guitar", "classical"]},
        "😴 Sleep & Ambient": {"track_genre": ["sleep", "ambient", "new-age"]},
    },
    "🎻 Classical": {
        "🎻 Orchestral": {"track_genre": ["classical"]},
        "🎭 Opera & Theatre": {"track_genre": ["opera", "show-tunes", "disney", "children"]},
        "🎹 Solo Piano": {
            "track_genre": ["piano", "classical"],
            "instrumentalness": (0.7, 1.0),
        },
    },
    "🤠 Country": {
        "🤠 Country": {"track_genre": ["country", "honky-tonk"]},
        "🪕 Folk & Acoustic": {"track_genre": ["folk", "acoustic", "bluegrass", "singer-songwriter", "songwriter"]},
        "🌿 Americana": {"track_genre": ["americana", "bluegrass", "rockabilly", "country"]},
    },
    "🌴 Reggae": {
        "🌴 Reggae & Dub": {"track_genre": ["reggae", "dub", "dancehall"]},
        "💃 Reggaeton": {"track_genre": ["reggaeton"]},
        "🌍 World & Afrobeat": {"track_genre": ["afrobeat", "world-music", "dancehall", "ska"]},
    },
    "💃 Latin": {
        "🌶️ Latin Pop": {"track_genre": ["latin", "latino"]},
        "💃 Salsa & Cumbia": {"track_genre": ["salsa", "samba", "forro", "pagode"]},
        "🇧🇷 Brazilian": {"track_genre": ["brazil", "mpb", "sertanejo"]},
        "💋 Tango & Romance": {"track_genre": ["tango", "romance", "spanish"]},
    },
    "🔥 R&B": {
        "🔥 R&B": {"track_genre": ["r-n-b"]},
        "🌊 Soul & Funk": {"track_genre": ["soul", "funk", "groove"]},
        "✝️ Gospel": {"track_genre": ["gospel"]},
    },
    "🤘 Metal": {
        "🤘 Heavy Metal": {"track_genre": ["metal", "heavy-metal"]},
        "⚡ Extreme Metal": {"track_genre": ["black-metal", "death-metal", "grindcore", "metalcore"]},
        "🔊 Hardcore & Industrial": {"track_genre": ["hardcore", "industrial", "goth"]},
    },
}

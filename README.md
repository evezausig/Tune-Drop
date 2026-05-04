# 💧🎵 Tune Drop

A TikTok-style music discovery app — swipe through 30-second song previews to find your next favorite song.

**Live demo:** [tune-drop.streamlit.app](https://tune-drop.streamlit.app)

---

## The Problem

Music discovery is broken. Streaming algorithms keep feeding you the same songs you already know, and traditional search only works if you already know what you're looking for. Meanwhile, TikTok has accidentally become the world's biggest music discovery engine — because short previews + quick decisions = people genuinely find new music they love.

Tune Drop brings that format to music itself: no videos, no influencers, no scrolling through endless lists. Just a clean feed of song previews you react to.

## How It Works

1. **Search** by artist name, song, or genre — *or* tap a vibe button (Chill, Dinner Party, Workout, Sad, etc.)
2. **Listen** to a 30-second preview of one song at a time
3. **React** with 👎 Skip, 👍 Like, or ❤️ Save
4. Songs you save build into your **personal playlist** at the bottom of the page
5. Discovery is smart: searching an artist pulls in their music *plus similar artists* so you actually discover something new

## Tech Stack

- **Python** — the language
- **Streamlit** — the web framework (turns Python into a website)
- **Deezer API** — provides music data, album art, and 30-second previews (free, no auth required)
- **Streamlit Community Cloud** — free hosting for the live site

## Project Structure

## How the Code is Organized

The app uses key concepts from the Intro to Programming course:

- **Functions** — `search_deezer()`, `build_discovery_queue()`, etc. — to avoid repetition and keep code clean
- **Dictionaries** — used for the vibes mapping and to access track data from the Deezer API
- **Lists** — to hold the queue of songs and the saved playlist
- **For loops** — to iterate through tracks and display them
- **If / elif / else** — to handle edge cases (no preview available, end of queue, empty search)
- **API calls** — `requests.get()` to fetch real music data from Deezer
- **Session state** — Streamlit's way of remembering things between user clicks

## How to Run Locally

If you want to run this on your own machine:

```bash
# 1. Clone the repo
git clone https://github.com/evezausig/Tune-Drop.git
cd Tune-Drop

# 2. Create a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install the libraries
pip install -r requirements.txt

# 4. Run the app
streamlit run app.py
```

## What's Next

Future improvements we're considering:
- **Refactor into classes** — `Track`, `Playlist`, `MusicFeed` for better code organization
- **Smarter discovery** — when you save a song, learn your taste and pull more similar music
- **AI-generated explanations** — "why you'd like this" blurbs powered by an LLM
- **Real swipe gestures** — currently uses buttons; future version could use touch gestures
- **Export playlists** — save your discoveries to a file or share with friends

---

*Group project for Intro to Programming, Nova SBE, 2026.*

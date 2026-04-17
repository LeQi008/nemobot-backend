from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import random
import json
import requests
import os
import html
from typing import Optional,List
from spotify_things.spotify_client import get_spotify_client, get_auth_manager


app = FastAPI(title="LQ Nemobot Backend", version="1.0.0")

# Add CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === Trivia Questions API ===

BASE_URL = "https://opentdb.com/api.php"

CATEGORY_MAP = {
    "General Knowledge": 9,
    "Entertainment: Books": 10,
    "Entertainment: Film": 11,
    "Entertainment: Music": 12,
    "Entertainment: Musicals & Theatres": 13,
    "Entertainment: Television": 14,
    "Entertainment: Video Games": 15,
    "Entertainment: Board Games": 16,
    "Science & Nature": 17,
    "Science: Computers": 18,
    "Science: Mathematics": 19,
    "Mythology": 20,
    "Sports": 21,
    "Geography": 22,
    "History": 23,
    "Politics": 24,
    "Art": 25,
    "Celebrities": 26,
    "Animals": 27,
    "Vehicles": 28,
    "Entertainment: Comics": 29,
    "Science: Gadgets": 30,
    "Entertainment: Japanese Anime & Manga": 31,
    "Entertainment: Cartoon & Animations": 32,
}

@app.get("/triviaQuestion")
def get_trivia_question(
    difficulty: str | None = Query(None),
    category: str | None = Query(None),  # MUST be str
):
    params = {
        "amount": 1,
        "encode": "url3986"
    }

    # Convert category name → ID
    if category:
        if category not in CATEGORY_MAP:
            return {
                "status": "error",
                "message": f"Invalid category: {category}"
            }
        params["category"] = CATEGORY_MAP[category]

    if difficulty:
        params["difficulty"] = difficulty.lower()

    try:
        response = requests.get(BASE_URL, params=params, timeout=5)
        response.raise_for_status()
    except requests.RequestException:
        return {
            "status": "error",
            "message": "Failed to fetch trivia question"
        }

    data = response.json()

    if data["response_code"] != 0:
        return {
            "status": "error",
            "message": f"No questions found (code {data['response_code']})"
        }

    q = data["results"][0]

    def decode(text):
        return html.unescape(requests.utils.unquote(text))

    correct = decode(q["correct_answer"])
    incorrect = [decode(a) for a in q["incorrect_answers"]]

    return {
        "status": "success",
        "question": decode(q["question"]),
        "category": q["category"],
        "difficulty": q["difficulty"],
        "type": q["type"],
        "correct_answer": correct,
        "incorrect_answers": incorrect,
        "all_answers": [correct] + incorrect
    }


# === Random Games API ===

# Allowed categories (normalized to lowercase)
ALLOWED_CATEGORIES = {
    "mmorpg", "shooter", "strategy", "moba", "racing", "sports", "social",
    "sandbox", "open-world", "survival", "pvp", "pve", "pixel", "voxel",
    "zombie", "turn-based", "first-person", "third-Person", "top-down",
    "tank", "space", "sailing", "side-scroller", "superhero", "permadeath",
    "card", "battle-royale", "mmo", "mmofps", "mmotps", "3d", "2d", "anime",
    "fantasy", "sci-fi", "fighting", "action-rpg", "action", "military",
    "martial-arts", "flight", "low-spec", "tower-defense", "horror", "mmorts"
}

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

@app.get("/randomGame")
def get_random_game(category: str = Query(...)):
    url = "https://free-to-play-games-database.p.rapidapi.com/api/games"

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "free-to-play-games-database.p.rapidapi.com"
    }

    params = {
        "platform": "browser",
        "category": category
    }

    try:
        response = requests.get(url, headers=headers, params=params)

        if response.status_code != 200:
            print("API ERROR:", response.text)
            raise HTTPException(
                status_code=response.status_code,
                detail="RapidAPI request failed"
            )

        games = response.json()

        if not games:
            raise HTTPException(
                status_code=404,
                detail=f"No games found for category '{category}'"
            )

        game = random.choice(games)

        game_url = game.get("game_url")
        print(f"gameurl: {game_url}")

        return {
            "title": game.get("title"),
            "description": game.get("short_description"),
            "url": game.get("game_url"),
            "genre": game.get("genre"),
            "platform": game.get("platform")
        }

    except Exception as e:
        print("ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))

# ==== Dad Joke ====

@app.get("/joke")
async def get_joke(category: Optional[str] = None):
    url = "https://groandeck.com/api/v1/random"

    try:
        params = {}
        if category:
            params["category"] = category

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Joke API failed"
            )

        data = response.json()

        return {
            "setup": data.get("setup"),
            "punchline": data.get("punchline"),
            "tags": data.get("tags"),
            "explanation": data.get("explanation"),
            "source": data.get("url")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/joke/categories")
async def get_joke_categories():
    url = "https://groandeck.com/api/v1/categories"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to fetch joke categories"
            )

        data = response.json()

        return data  # returns full structure with counts

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==== NASA API ====

@app.get("/nasaAPOD")
def get_nasa_apod():
    url = "https://api.nasa.gov/planetary/apod"
    
    params = {
        "api_key": os.getenv("NASA_API_KEY")
    }

    try:
        print("Before req")
        response = requests.get(url, params=params)
        print("after req")

        if response.status_code != 200:
            print("NASA ERROR:", response.text)  
            raise HTTPException(
                status_code=response.status_code,
                detail=response.text
            )

        data = response.json()

        return {
            "title": data.get("title"),
            "description": data.get("explanation"),
            "url": data.get("url"),
            "media_type": data.get("media_type"),
            "date": data.get("date")
        }

    except Exception as e:
        print("ERROR:", e)  
        raise HTTPException(status_code=500, detail=str(e))

# ==== SPOTIFY ====

GENRE_FILE_PATH = r"E:\SC4052 Cloud Computing\nemobot-weather-backend\spotify_things\genre-seeds.json"

with open(GENRE_FILE_PATH, "r") as f:
    data = json.load(f)

VALID_GENRES = set(data["genres"])

# temporary storage for Spotify API
TOKEN_INFO = None

# Since nemobot only accepts from http://localhost:8000/... WHILE spotify app DOES NOT ALLOw http://localhost:8000/ , so have to do a workaround after generating .cache that is
@app.get("/pseudoSpotify")
async def pseudo_spotify(request: Request):
    try:
        # Step 1: Get original query string
        query_string = request.url.query  # "genres=pop&genres=chill"

        # Step 2: Construct internal URL
        target_url = f"http://127.0.0.1:8000/create_playlist?{query_string}"

        # Step 3: Call your own backend
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(target_url)

        # Step 4: Return response directly
        return response.json()

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

@app.get("/callback")
def callback(code: str):
    global TOKEN_INFO
    auth_manager = get_auth_manager()
    # STEP 2: exchange code for token
    TOKEN_INFO = auth_manager.get_access_token(code)
    return RedirectResponse(url="/create_playlist")

@app.get("/create_playlist")
def create_playlist(genres: List[str] = Query(...)):
    global TOKEN_INFO

    print("RAW GENRES:", genres)

    auth_manager = get_auth_manager()

    # STEP 1: Not logged in → redirect to Spotify
    if TOKEN_INFO is None:
        auth_url = auth_manager.get_authorize_url()
        return RedirectResponse(auth_url)

    # Step 2: Call Spotify safely, if already logged in → create playlist
    try:
        sp = get_spotify_client(TOKEN_INFO)
        user = sp.me()

        cleaned_genres = [g.strip().lower() for g in genres] # clean
        
        # Step 3: Validate genres
        invalid = [g for g in cleaned_genres if g not in VALID_GENRES]
        if invalid:
            return {
                "status": "error",
                "message": f"Invalid genres: {invalid}"
            }
        
        # ensure max 2 genres as per spotify api, so that query is not too strict
        cleaned_genres = cleaned_genres[:2]

        query = " ".join(cleaned_genres)
        results = sp.search(
            q=query,
            type="track",
            limit=10
        )

        print(f"Results : {results}")

        # Since duplicate songs may appear because in different version/album
        seen = set()
        unique_tracks = []
        for t in results["tracks"]["items"]:
            key = (t["name"].lower(), t["artists"][0]["name"].lower())
            if key not in seen:
                seen.add(key)
                unique_tracks.append(t)
        track_uris = [t["uri"] for t in unique_tracks] # extract URIs

        for t in unique_tracks:
            print(t["name"], "-", t["artists"][0]["name"])

        # Since spotipy api does not work properly anymore...
        access_token = TOKEN_INFO["access_token"]

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # 1. Create playlist
        create_url = "https://api.spotify.com/v1/me/playlists"
        create_data = {
            "name": f"{', '.join(cleaned_genres)} playlist",
            "public": True
        }
        create_res = requests.post(create_url, headers=headers, json=create_data)
        playlist = create_res.json()
        playlist_id = playlist["id"]

        print("Created playlist")

        # 2. Add tracks
        add_url = f"https://api.spotify.com/v1/playlists/{playlist_id}/items"
        add_data = {
            "uris": track_uris   # list of track URIs
        }
        add_res = requests.post(add_url, headers=headers, json=add_data)
        print("Added tracks")

        # 3. Return result
        return {
            "status": "success",
            "playlist_url": playlist["external_urls"]["spotify"]
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

@app.get("/")
async def root():
    """Root endpoint to check if the API is running"""
    return {"message": "LQ Nemobot API Backend is running!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
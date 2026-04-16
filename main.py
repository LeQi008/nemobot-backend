from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
from typing import Optional
import asyncio
from spotify_things.spotify_client import get_spotify_client, get_auth_manager
import json
from typing import List
import requests

app = FastAPI(title="LQ Nemobot Backend", version="1.0.0")

# Add CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==== SPOTIFY ===

GENRE_FILE_PATH = r"E:\SC4052 Cloud Computing\nemobot-weather-backend\spotify_things\genre-seeds.json"

with open(GENRE_FILE_PATH, "r") as f:
    data = json.load(f)

VALID_GENRES = set(data["genres"])

# temporary storage for Spotify API
TOKEN_INFO = None

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

# TO REMOVE ===
    
GEOCODING_API_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"

async def get_coordinates_for_city(city: str):
    """Get latitude and longitude for a city using Open-Meteo Geocoding API"""
    params = {
        "name": city,
        "count": 1,
        "language": "en",
        "format": "json"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(GEOCODING_API_URL, params=params)
        
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Geocoding service error")
            
        data = response.json()
        
        if not data.get("results"):
            raise HTTPException(status_code=404, detail=f"City '{city}' not found")
            
        result = data["results"][0]
        return {
            "lat": result["latitude"],
            "lon": result["longitude"],
            "name": result["name"],
            "country": result.get("country", ""),
            "admin1": result.get("admin1", "")  # State/Province
        }

@app.get("/")
async def root():
    """Root endpoint to check if the API is running"""
    return {"message": "LQ Nemobot API Backend is running!"}

@app.get("/weather/{city}")
async def get_weather(city: str, units: Optional[str] = "celsius"):
    """
    Get weather data for a specific city
    
    Args:
        city: Name of the city
        units: Temperature units (celsius or fahrenheit). Default: celsius
    
    Returns:
        JSON response with weather data
    """
    if not city:
        raise HTTPException(status_code=400, detail="City name is required")
    
    try:
        # First, get coordinates for the city
        location = await get_coordinates_for_city(city)
        
        # Then get weather data
        return await get_weather_by_coordinates(
            location["lat"], 
            location["lon"], 
            units,
            city_info=location
        )
            
    except HTTPException:
        raise
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error connecting to weather service: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Unexpected error: {str(e)}"
        )

@app.get("/weather/coordinates/{lat}/{lon}")
async def get_weather_by_coordinates(lat: float, lon: float, units: Optional[str] = "celsius", city_info: Optional[dict] = None):
    """
    Get weather data for specific coordinates
    
    Args:
        lat: Latitude
        lon: Longitude
        units: Temperature units (celsius or fahrenheit). Default: celsius
        city_info: Optional city information from geocoding
    
    Returns:
        JSON response with weather data
    """
    # Determine temperature unit parameter for API
    temp_unit = "celsius" if units == "celsius" else "fahrenheit"
    
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": [
            "temperature_2m", 
            "relative_humidity_2m", 
            "apparent_temperature",
            "is_day",
            "precipitation",
            "weather_code",
            "cloud_cover",
            "pressure_msl",
            "surface_pressure",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m"
        ],
        "daily": [
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "apparent_temperature_max",
            "apparent_temperature_min",
            "precipitation_sum",
            "wind_speed_10m_max",
            "wind_gusts_10m_max",
            "wind_direction_10m_dominant"
        ],
        "temperature_unit": temp_unit,
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "timezone": "auto",
        "forecast_days": 1
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(WEATHER_API_URL, params=params)
            
            if response.status_code == 400:
                raise HTTPException(status_code=400, detail="Invalid coordinates")
            elif response.status_code != 200:
                raise HTTPException(
                    status_code=500, 
                    detail=f"Weather API error: {response.status_code}"
                )
            
            weather_data = response.json()
            current = weather_data["current"]
            daily = weather_data["daily"]
            
            # Weather code mapping (simplified version)
            weather_codes = {
                0: {"main": "Clear", "description": "Clear sky"},
                1: {"main": "Clear", "description": "Mainly clear"},
                2: {"main": "Clouds", "description": "Partly cloudy"},
                3: {"main": "Clouds", "description": "Overcast"},
                45: {"main": "Fog", "description": "Fog"},
                48: {"main": "Fog", "description": "Depositing rime fog"},
                51: {"main": "Drizzle", "description": "Light drizzle"},
                53: {"main": "Drizzle", "description": "Moderate drizzle"},
                55: {"main": "Drizzle", "description": "Dense drizzle"},
                61: {"main": "Rain", "description": "Slight rain"},
                63: {"main": "Rain", "description": "Moderate rain"},
                65: {"main": "Rain", "description": "Heavy rain"},
                71: {"main": "Snow", "description": "Slight snow"},
                73: {"main": "Snow", "description": "Moderate snow"},
                75: {"main": "Snow", "description": "Heavy snow"},
                80: {"main": "Rain", "description": "Slight rain showers"},
                81: {"main": "Rain", "description": "Moderate rain showers"},
                82: {"main": "Rain", "description": "Violent rain showers"},
                95: {"main": "Thunderstorm", "description": "Thunderstorm"},
                96: {"main": "Thunderstorm", "description": "Thunderstorm with slight hail"},
                99: {"main": "Thunderstorm", "description": "Thunderstorm with heavy hail"}
            }
            
            weather_code = current.get("weather_code", 0)
            weather_info = weather_codes.get(weather_code, {"main": "Unknown", "description": "Unknown weather"})
            
            # Format the response
            formatted_response = {
                "city": city_info.get("name", "Unknown") if city_info else "Unknown",
                "country": city_info.get("country", "") if city_info else "",
                "region": city_info.get("admin1", "") if city_info else "",
                "temperature": {
                    "current": current.get("temperature_2m"),
                    "feels_like": current.get("apparent_temperature"),
                    "min": daily["temperature_2m_min"][0] if daily.get("temperature_2m_min") else None,
                    "max": daily["temperature_2m_max"][0] if daily.get("temperature_2m_max") else None,
                    "units": temp_unit
                },
                "weather": {
                    "main": weather_info["main"],
                    "description": weather_info["description"],
                    "code": weather_code,
                    "is_day": current.get("is_day", 1) == 1
                },
                "humidity": current.get("relative_humidity_2m"),
                "pressure": current.get("pressure_msl"),
                "wind": {
                    "speed": current.get("wind_speed_10m"),
                    "direction": current.get("wind_direction_10m"),
                    "gusts": current.get("wind_gusts_10m")
                },
                "precipitation": current.get("precipitation"),
                "cloud_cover": current.get("cloud_cover"),
                "coordinates": {
                    "lat": lat,
                    "lon": lon
                },
                "timezone": weather_data.get("timezone"),
                "raw_data": weather_data  # Include full API response for flexibility
            }
            
            return formatted_response
            
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error connecting to weather service: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Unexpected error: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
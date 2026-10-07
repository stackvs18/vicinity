# Search suggestions while typing, tolerant of small spelling mistakes.
#
# Three sources, merged and ranked:
#   1. Areas we already scored (instant, from the database), matched with fuzzy string
#      similarity, so "koramangla" still finds "Koramangala, Bengaluru".
#   2. A built-in list of Indian cities (with common misspellings and old names), used to
#      understand the city part of the search, e.g. "navrangpura ahmdabad".
#   3. Photon, a free search-as-you-type geocoder built on OpenStreetMap, limited to India
#      and biased towards the city we recognised. If its answers look poor, we try again
#      with shortened words, because typos usually happen near the end of a word.

import difflib
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor

import requests
from django.conf import settings
from django.core.cache import cache

from areas.models import Area
from areas.services.scoring import haversine_metres

PHOTON_URL = "https://photon.komoot.io/api/"
INDIA_BOUNDING_BOX = "68.1,6.5,97.4,35.7"  # west, south, east, north
CACHE_SECONDS = 60 * 60 * 24  # suggestions for the same text are reused for a day

# Photon result types that are areas (good to score), not single buildings
AREA_TYPES = {"locality", "district", "city", "suburb", "neighbourhood", "county", "state"}

# Major Indian cities: name -> (latitude, longitude)
INDIAN_CITIES = {
    "Ahmedabad": (23.0225, 72.5714), "Bengaluru": (12.9716, 77.5946), "Mumbai": (19.0760, 72.8777),
    "New Delhi": (28.6139, 77.2090), "Delhi": (28.6139, 77.2090), "Kolkata": (22.5726, 88.3639),
    "Chennai": (13.0827, 80.2707), "Hyderabad": (17.3850, 78.4867), "Pune": (18.5204, 73.8567),
    "Surat": (21.1702, 72.8311), "Vadodara": (22.3072, 73.1812), "Rajkot": (22.3039, 70.8022),
    "Gandhinagar": (23.2156, 72.6369), "Jaipur": (26.9124, 75.7873), "Lucknow": (26.8467, 80.9462),
    "Kanpur": (26.4499, 80.3319), "Nagpur": (21.1458, 79.0882), "Indore": (22.7196, 75.8577),
    "Bhopal": (23.2599, 77.4126), "Patna": (25.5941, 85.1376), "Chandigarh": (30.7333, 76.7794),
    "Gurugram": (28.4595, 77.0266), "Noida": (28.5355, 77.3910), "Kochi": (9.9312, 76.2673),
    "Thiruvananthapuram": (8.5241, 76.9366), "Coimbatore": (11.0168, 76.9558),
    "Visakhapatnam": (17.6868, 83.2185), "Bhubaneswar": (20.2961, 85.8245), "Guwahati": (26.1445, 91.7362),
    "Dehradun": (30.3165, 78.0322), "Amritsar": (31.6340, 74.8723), "Mysuru": (12.2958, 76.6394),
    "Nashik": (19.9975, 73.7898), "Goa": (15.4909, 73.8278), "Varanasi": (25.3176, 82.9739),
}

# Other names people type for those cities
CITY_ALIASES = {
    "bangalore": "Bengaluru", "bengalore": "Bengaluru", "bombay": "Mumbai", "calcutta": "Kolkata",
    "madras": "Chennai", "gurgaon": "Gurugram", "baroda": "Vadodara", "mysore": "Mysuru",
    "trivandrum": "Thiruvananthapuram", "cochin": "Kochi", "vizag": "Visakhapatnam",
    "amdavad": "Ahmedabad", "panaji": "Goa",
}


# Lowercase, letters and digits only, single spaces: "Navrangpura,  Ahmedabad!" -> "navrangpura ahmedabad"
def normalize(text):
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


# How similar two texts are, from 0.0 (nothing alike) to 1.0 (identical)
def similarity(first_text, second_text):
    return difflib.SequenceMatcher(None, normalize(first_text), normalize(second_text)).ratio()


# Recognises a city word, even misspelled: "ahmdabad" -> "Ahmedabad". Returns the name or None.
def recognise_city(word):
    if len(word) < 4:
        return None
    if word in CITY_ALIASES:
        return CITY_ALIASES[word]

    best_city = None
    best_score = 0.8  # must be at least this similar
    for city in INDIAN_CITIES:
        score = similarity(word, city)
        if score >= best_score:
            best_city = city
            best_score = score
    for alias in CITY_ALIASES:
        score = similarity(word, alias)
        if score >= best_score:
            best_city = CITY_ALIASES[alias]
            best_score = score
    return best_city


# Splits "navrangpura ahmdabad" into ("navrangpura", "Ahmedabad").
# If no city is recognised, the whole text is the place part.
def split_place_and_city(text):
    words = normalize(text).split()
    if len(words) >= 2:
        city = recognise_city(words[-1])
        if city is not None:
            return " ".join(words[:-1]), city
        if len(words) >= 3:
            city = recognise_city(words[-2] + " " + words[-1])  # e.g. "new delhi"
            if city is not None:
                return " ".join(words[:-2]), city
    return " ".join(words), None


# "koramangla bandra wst" -> "koramang bandra w": cut the end off each word, where typos hide
def shorten_words(text):
    shortened = []
    for word in text.split():
        if len(word) >= 6:
            shortened.append(word[:-2])
        elif len(word) <= 3:
            shortened.append(word[0])
        else:
            shortened.append(word)
    return " ".join(shortened)


# Asks Photon (cached for a day). Returns a list of candidate places.
def ask_photon(query_text, city):
    key_text = normalize(query_text) + "|" + (city or "")
    cache_key = "photon-" + hashlib.md5(key_text.encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    params = {"q": query_text, "limit": 8, "bbox": INDIA_BOUNDING_BOX, "lang": "en"}
    if city is not None:
        params["lat"], params["lon"] = INDIAN_CITIES[city]
    try:
        response = requests.get(PHOTON_URL, params=params, timeout=6,
                                headers={"User-Agent": settings.VICINITY_USER_AGENT})
        features = response.json().get("features", [])
    except (requests.RequestException, ValueError):
        return []  # suggestions are a nice-to-have: fail quietly

    candidates = []
    for feature in features:
        properties = feature.get("properties", {})
        name = properties.get("name")
        if not name:
            continue
        longitude, latitude = feature["geometry"]["coordinates"]
        town = properties.get("city") or properties.get("county") or properties.get("district") or ""
        state = properties.get("state") or ""
        detail_parts = []
        for part in [town, state]:
            if part and part != name and part not in detail_parts:
                detail_parts.append(part)
        candidates.append({
            "label": name,
            "detail": ", ".join(detail_parts),
            "lat": latitude,
            "lon": longitude,
            "type": properties.get("type", ""),
            "town": town,
            "area_id": None,
            "score": None,
        })

    cache.set(cache_key, candidates, CACHE_SECONDS)
    return candidates


# Ranks a Photon candidate: similar name, an area (not a building), in the city we expect
def rank_candidate(candidate, place_text, city):
    rank = similarity(place_text, candidate["label"])
    if candidate["type"] in AREA_TYPES:
        rank = rank + 0.25
    if city is not None:
        city_lat, city_lon = INDIAN_CITIES[city]
        kilometres_away = haversine_metres(city_lat, city_lon, candidate["lat"], candidate["lon"]) / 1000
        if kilometres_away <= 40:
            rank = rank + 0.3  # in the city the user typed
        else:
            rank = rank - 0.6  # somewhere else in India: very unlikely to be what they meant
    return rank


# Used for sorting by rank
def get_rank(item):
    return item["rank"]


# Suggestions from areas we already scored, tolerant of typos
def scored_area_suggestions(text):
    results = []
    for area in Area.objects.only("id", "name", "lat", "lon", "score", "grade"):
        # Compare with the whole name and with just the part before the comma
        place_name = area.name.split(",")[0]
        rank = max(similarity(text, area.name), similarity(text, place_name))
        if normalize(text) in normalize(area.name):
            rank = max(rank, 0.9)  # typed text is inside the name: a strong match
        if rank >= 0.72:
            results.append({
                "label": area.name, "detail": f"Scored {area.score}/100 · {area.grade}",
                "lat": area.lat, "lon": area.lon, "type": "scored", "town": "",
                "area_id": area.pk, "score": area.score, "rank": rank + 0.8,
            })
    return results


# The main function: up to `limit` suggestions for what the user has typed so far.
# include_photon=False gives only the instant results from the database.
def suggest(text, limit=6, include_photon=True):
    text = text.strip()
    if len(normalize(text)) < 2:
        return []

    place_text, city = split_place_and_city(text)
    if place_text == "":
        place_text = normalize(text)

    # Step 1: areas we already scored
    suggestions = scored_area_suggestions(text)

    # Step 2 and 3: ask Photon twice AT THE SAME TIME: once with the text as typed, once with
    # shortened words (which survives typos). Running both together halves the waiting time.
    candidates = []
    if include_photon:
        city_suffix = "" if city is None else " " + city
        queries = [place_text + city_suffix]
        if len(place_text) >= 4:
            queries.append(shorten_words(place_text) + city_suffix)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = []
            for query in queries:
                futures.append(pool.submit(ask_photon, query, city))
            for future in futures:
                candidates = candidates + future.result()

    for candidate in candidates:
        candidate["rank"] = rank_candidate(candidate, place_text, city)
        suggestions.append(candidate)

    # Step 4: best first, without near-duplicates (same name within ~1 km)
    suggestions.sort(key=get_rank, reverse=True)
    unique = []
    for item in suggestions:
        is_duplicate = False
        for kept in unique:
            same_name = normalize(item["label"].split(",")[0]) == normalize(kept["label"].split(",")[0])
            close_by = abs(item["lat"] - kept["lat"]) < 0.01 and abs(item["lon"] - kept["lon"]) < 0.01
            if same_name and close_by:
                is_duplicate = True
                break
        if not is_duplicate:
            unique.append(item)
        if len(unique) == limit:
            break

    # Only send what the browser needs
    clean = []
    for item in unique:
        clean.append({
            "label": item["label"], "detail": item["detail"], "lat": item["lat"], "lon": item["lon"],
            "area_id": item["area_id"], "score": item["score"],
        })
    return clean


# The single best match for a search that was submitted without picking a suggestion
def best_match(text):
    results = suggest(text, limit=1)
    if len(results) == 0:
        return None
    return results[0]

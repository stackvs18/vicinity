# Turns an address into coordinates (and coordinates back into an address) using
# Nominatim, OpenStreetMap's free geocoder.
#
# Nominatim's usage policy: at most 1 request per second, and identify your app in the
# User-Agent. So we wait between requests, and we save every answer in the database
# (GeocodeResult) so the same search never asks Nominatim twice.

import threading
import time

import requests
from django.conf import settings

from areas.models import GeocodeResult
from areas.services.errors import AddressNotFound, MapServiceBusy

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
SECONDS_BETWEEN_REQUESTS = 1.1

# Shared by all requests in this process, so two searches can't break the 1-per-second rule
nominatim_lock = threading.Lock()
last_request_time = 0.0

# Address parts that make a good short name, from most to least specific
LOCAL_PART_KEYS = ["suburb", "neighbourhood", "quarter", "city_district", "village", "hamlet"]
CITY_PART_KEYS = ["city", "town", "municipality", "state_district", "county", "state"]


# Asks Nominatim, waiting first if the last request was less than a second ago
def ask_nominatim(url, params):
    global last_request_time

    with nominatim_lock:
        seconds_since_last = time.monotonic() - last_request_time
        if seconds_since_last < SECONDS_BETWEEN_REQUESTS:
            time.sleep(SECONDS_BETWEEN_REQUESTS - seconds_since_last)
        last_request_time = time.monotonic()

        try:
            response = requests.get(
                url,
                params=params,
                headers={"User-Agent": settings.VICINITY_USER_AGENT},
                timeout=15,
            )
        except requests.RequestException:
            raise MapServiceBusy("The address service is not responding.")

    if response.status_code != 200:
        raise MapServiceBusy("The address service is busy (HTTP " + str(response.status_code) + ").")
    return response.json()


# Builds a short name like "Navrangpura, Ahmedabad" from Nominatim's address parts
def make_short_name(address_parts, full_address):
    local_part = None
    for key in LOCAL_PART_KEYS:
        if key in address_parts:
            local_part = address_parts[key]
            break

    city_part = None
    for key in CITY_PART_KEYS:
        if key in address_parts:
            city_part = address_parts[key]
            break

    if local_part and city_part and local_part != city_part:
        return local_part + ", " + city_part
    if local_part:
        return local_part
    if city_part:
        return city_part

    # Fall back to the first two pieces of the full address
    pieces = full_address.split(",")
    first_two = []
    for piece in pieces[:2]:
        first_two.append(piece.strip())
    return ", ".join(first_two)


# Turns one Nominatim result into the dict the rest of Vicinity uses
def result_to_place(result):
    full_address = result["display_name"]
    return {
        "name": make_short_name(result.get("address", {}), full_address)[:200],
        "full_address": full_address[:500],
        "lat": float(result["lat"]),
        "lon": float(result["lon"]),
    }


# Saves a geocoding answer so the same search is answered from the database next time
def save_to_cache(query_key, place):
    GeocodeResult.objects.update_or_create(
        query=query_key,
        defaults={
            "name": place["name"],
            "full_address": place["full_address"],
            "lat": place["lat"],
            "lon": place["lon"],
        },
    )


# Reads a cached answer, or returns None
def read_from_cache(query_key):
    cached = GeocodeResult.objects.filter(query=query_key).first()
    if cached is None:
        return None
    return {
        "name": cached.name,
        "full_address": cached.full_address,
        "lat": cached.lat,
        "lon": cached.lon,
    }


# Address text -> {"name", "full_address", "lat", "lon"}
def geocode(address_text):
    query_key = " ".join(address_text.lower().split())[:300]  # lowercase, single spaces
    if query_key == "":
        raise AddressNotFound("Please type an address.")

    # Step 1: answered before? Use the saved answer.
    cached_place = read_from_cache(query_key)
    if cached_place is not None:
        return cached_place

    # Step 2: ask Nominatim
    results = ask_nominatim(NOMINATIM_SEARCH_URL, {
        "q": address_text,
        "format": "jsonv2",
        "limit": 1,
        "addressdetails": 1,
    })
    if len(results) == 0:
        raise AddressNotFound("Couldn't find \"" + address_text + "\". Try adding the city name.")

    # Step 3: save it for next time
    place = result_to_place(results[0])
    save_to_cache(query_key, place)
    return place


# Coordinates -> {"name", "full_address", "lat", "lon"} (used by "Use my location")
def reverse_geocode(latitude, longitude):
    query_key = "@" + str(round(latitude, 4)) + "," + str(round(longitude, 4))

    cached_place = read_from_cache(query_key)
    if cached_place is not None:
        return cached_place

    result = ask_nominatim(NOMINATIM_REVERSE_URL, {
        "lat": latitude,
        "lon": longitude,
        "format": "jsonv2",
        "zoom": 16,
        "addressdetails": 1,
    })
    if "error" in result:
        raise AddressNotFound("No address found at that location.")

    place = result_to_place(result)
    # Keep the user's exact coordinates, not the address's centre point
    place["lat"] = latitude
    place["lon"] = longitude
    save_to_cache(query_key, place)
    return place

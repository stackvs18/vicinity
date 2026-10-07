# Finds every useful place (shops, hospitals, bus stops, parks...) around a point using
# Overpass, OpenStreetMap's free query service.
#
# The main Overpass server is often overloaded, so we try a list of servers in order
# and use the first one that answers.

import logging
import time

import requests
from django.conf import settings

from areas.categories import categorize
from areas.services.errors import MapServiceBusy

logger = logging.getLogger(__name__)

OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
ROUNDS = 2  # try the whole list twice
SECONDS_BETWEEN_ROUNDS = 5
SECONDS_PER_SERVER = 35  # mirrors can be slow; the main server usually answers in ~6 s
MAX_TOTAL_SECONDS = 60

# Overpass query template. "nwr" = nodes, ways and relations (a park is usually drawn as
# an area, not a point). "out center" gives us one point for each area.
QUERY_TEMPLATE = """
[out:json][timeout:25];
(
  nwr["shop"~"^(supermarket|convenience|greengrocer|grocery|bakery|dairy|general|butcher|deli|chemist)$"](around:{radius},{lat},{lon});
  nwr["amenity"~"^(marketplace|pharmacy|hospital|clinic|doctors|dentist|bus_station|school|college|university|kindergarten|restaurant|cafe|fast_food|food_court|ice_cream|atm|bank|police|fire_station)$"](around:{radius},{lat},{lon});
  nwr["leisure"~"^(park|garden|playground|fitness_centre|sports_centre|stadium|swimming_pool)$"](around:{radius},{lat},{lon});
  nwr["healthcare"~"^(pharmacy|hospital|clinic|doctor|dentist|centre)$"](around:{radius},{lat},{lon});
  node["highway"="bus_stop"](around:{radius},{lat},{lon});
  nwr["railway"~"^(station|halt|subway_entrance|tram_stop)$"](around:{radius},{lat},{lon});
  nwr["public_transport"="station"](around:{radius},{lat},{lon});
);
out center tags 2000;
"""

# The tag we use to give an unnamed place a readable name ("bus_stop" -> "Bus stop")
NAME_TAGS = ["amenity", "shop", "leisure", "highway", "railway", "public_transport"]


# Gives a place a readable name, even if OpenStreetMap has no name for it
def readable_name(tags):
    if tags.get("name:en"):
        return tags["name:en"]
    if tags.get("name"):
        return tags["name"]
    for tag in NAME_TAGS:
        if tags.get(tag):
            return tags[tag].replace("_", " ").capitalize()
    return "Unnamed place"


# Turns one Overpass element into {"category", "name", "lat", "lon"} (or None to skip it)
def element_to_place(element):
    tags = element.get("tags", {})
    category = categorize(tags)
    if category is None:
        return None

    # Points have lat/lon directly; areas (ways/relations) have a "center"
    if "lat" in element:
        latitude, longitude = element["lat"], element["lon"]
    elif "center" in element:
        latitude, longitude = element["center"]["lat"], element["center"]["lon"]
    else:
        return None

    # Bus stops are often named after a landmark ("Canara Bank"), so say what it is
    name = readable_name(tags)
    if tags.get("highway") == "bus_stop" and "stop" not in name.lower():
        name = name + " (bus stop)"
    elif tags.get("railway") == "station" and "station" not in name.lower():
        name = name + " station"

    return {
        "category": category,
        "name": name[:200],
        "lat": latitude,
        "lon": longitude,
    }


# Sends the query to one server. Returns the list of elements, or raises an error.
def ask_server(server_url, query, timeout_seconds):
    response = requests.post(
        server_url,
        data={"data": query},
        headers={"User-Agent": settings.VICINITY_USER_AGENT},
        timeout=timeout_seconds,
    )
    if response.status_code != 200:
        raise MapServiceBusy("HTTP " + str(response.status_code))
    return response.json()["elements"]


# Tries every server, twice, and returns the first answer (or None if all failed).
# Gives up after MAX_TOTAL_SECONDS, so a visitor never waits more than about a minute.
def ask_any_server(query):
    start_time = time.monotonic()
    for round_number in range(ROUNDS):
        if round_number > 0:
            time.sleep(SECONDS_BETWEEN_ROUNDS)  # busy servers often free up in a few seconds
        for server_url in OVERPASS_SERVERS:
            seconds_left = MAX_TOTAL_SECONDS - (time.monotonic() - start_time)
            if seconds_left < 5:
                return None
            try:
                return ask_server(server_url, query, min(seconds_left, SECONDS_PER_SERVER))
            except (requests.RequestException, ValueError, KeyError, MapServiceBusy) as error:
                logger.warning("Overpass server %s failed: %s", server_url, error)
    return None


# All useful places within radius_metres of a point
def fetch_places(latitude, longitude, radius_metres):
    query = QUERY_TEMPLATE.format(radius=radius_metres, lat=latitude, lon=longitude)

    # Step 1: ask the servers until one answers
    elements = ask_any_server(query)
    if elements is None:
        raise MapServiceBusy("The map data servers are busy. Please try again in a minute.")

    # Step 2: keep the elements that belong to one of our categories
    place_list = []
    for element in elements:
        place = element_to_place(element)
        if place is not None:
            place_list.append(place)
    return place_list

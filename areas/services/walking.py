# Real walking times along streets, from OSRM (an open-source router running on
# OpenStreetMap data). One "table" request gives the walking time from home to many
# places at once.
#
# If the routing server is down, we estimate instead: straight-line distance x 1.3
# (streets aren't straight) at 80 metres per minute (about 4.8 km/h).

import requests
from django.conf import settings

OSRM_TABLE_URL = "https://routing.openstreetmap.de/routed-foot/table/v1/foot/"
DETOUR_FACTOR = 1.3
WALKING_METRES_PER_MINUTE = 80


# Estimated walking minutes for a straight-line distance
def estimate_walk_minutes(distance_metres):
    return round(distance_metres * DETOUR_FACTOR / WALKING_METRES_PER_MINUTE, 1)


# Walking minutes from home to each destination, in the same order.
# Returns None if the routing server can't be used (the caller then estimates).
def walking_minutes(home_lat, home_lon, destinations):
    if len(destinations) == 0:
        return []

    # Step 1: OSRM wants "lon,lat" pairs separated by ";" with home first
    coordinate_texts = [f"{home_lon},{home_lat}"]
    for destination_lat, destination_lon in destinations:
        coordinate_texts.append(f"{destination_lon},{destination_lat}")
    url = OSRM_TABLE_URL + ";".join(coordinate_texts)

    # Step 2: ask for durations from home (source 0) to everything
    try:
        response = requests.get(
            url,
            params={"sources": "0", "annotations": "duration"},
            headers={"User-Agent": settings.VICINITY_USER_AGENT},
            timeout=15,
        )
        data = response.json()
    except (requests.RequestException, ValueError):
        return None
    if response.status_code != 200 or data.get("code") != "Ok":
        return None

    # Step 3: durations[0] is the row for home; skip the first value (home to home)
    minutes_list = []
    for seconds in data["durations"][0][1:]:
        if seconds is None:
            minutes_list.append(None)  # no walking route found
        else:
            minutes_list.append(round(seconds / 60, 1))
    return minutes_list

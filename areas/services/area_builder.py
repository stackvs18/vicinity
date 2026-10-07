# Builds (or re-uses) the score for a location. This is the heart of Vicinity:
#
#   address -> coordinates (geocoding.py)
#           -> every useful place within a 15-minute walk (overpass.py)
#           -> real walking time to the nearest place of each kind (walking.py)
#           -> points per category and a score out of 100 (scoring.py)
#           -> saved in the database (Area, CategoryScore, Place)
#
# Areas are cached: a location within ~110 m of one scored in the last 30 days re-uses it,
# so popular areas never hit the free map services twice.

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from areas.categories import CATEGORIES
from areas.models import Area, CategoryScore, Place
from areas.services import geocoding, overpass, scoring, suggestions, walking
from areas.services.errors import AddressNotFound, MapServiceBusy

# How many places per category we save for the map (the nearest ones)
PLACES_SAVED_PER_CATEGORY = 20


# The location rounded to about 110 m, e.g. "23.036,72.564"
def make_grid_key(latitude, longitude):
    return f"{round(latitude, 3):.3f},{round(longitude, 3):.3f}"


# Used for sorting places by distance
def get_distance(place):
    return place["distance_metres"]


# Groups places by category, nearest first: {"grocery": [place, place, ...], ...}
def group_places_by_category(place_list, home_lat, home_lon, radius_metres):
    places_by_category = {}
    for category in CATEGORIES:
        places_by_category[category["key"]] = []

    for place in place_list:
        distance = scoring.haversine_metres(home_lat, home_lon, place["lat"], place["lon"])
        if distance > radius_metres:
            continue  # Overpass's circle is slightly generous; keep it exact
        place["distance_metres"] = round(distance)
        places_by_category[place["category"]].append(place)

    for category_key in places_by_category:
        places_by_category[category_key].sort(key=get_distance)
    return places_by_category


# Works out the walking time to the nearest place of each category (one routing request)
def nearest_walk_minutes(home_lat, home_lon, places_by_category):
    # Step 1: the nearest place of each category that has one
    category_keys = []
    destinations = []
    for category_key in places_by_category:
        if len(places_by_category[category_key]) > 0:
            nearest = places_by_category[category_key][0]
            category_keys.append(category_key)
            destinations.append((nearest["lat"], nearest["lon"]))

    # Step 2: ask the router for real walking times
    routed_minutes = walking.walking_minutes(home_lat, home_lon, destinations)

    # Step 3: use routed times where we have them, estimates otherwise
    result = {}  # category key -> (minutes, is_estimate)
    for position in range(len(category_keys)):
        category_key = category_keys[position]
        nearest = places_by_category[category_key][0]
        if routed_minutes is not None and routed_minutes[position] is not None:
            result[category_key] = (routed_minutes[position], False)
        else:
            result[category_key] = (walking.estimate_walk_minutes(nearest["distance_metres"]), True)
    return result


# Scores a location and saves it. Re-uses a fresh cached Area when there is one.
def build_area(name, full_address, latitude, longitude, force_refresh=False):
    radius = settings.VICINITY_RADIUS_METRES
    grid_key = make_grid_key(latitude, longitude)

    # Step 1: already scored recently? Re-use it.
    existing_area = Area.objects.filter(grid_key=grid_key).first()
    if existing_area is not None and existing_area.is_fresh() and not force_refresh:
        return existing_area

    # Step 2: download the places and sort them into categories.
    # If the map servers are down but we have an older score, show that instead of an error.
    try:
        place_list = overpass.fetch_places(latitude, longitude, radius)
    except MapServiceBusy:
        if existing_area is not None:
            return existing_area
        raise
    places_by_category = group_places_by_category(place_list, latitude, longitude, radius)
    walk_times = nearest_walk_minutes(latitude, longitude, places_by_category)

    # Step 3: score every category
    category_results = []
    total_points = 0.0
    total_places = 0
    for category in CATEGORIES:
        places = places_by_category[category["key"]]
        minutes, is_estimate = walk_times.get(category["key"], (None, False))
        points = scoring.category_points(category["weight"], minutes, len(places))
        total_points = total_points + points
        total_places = total_places + len(places)
        category_results.append({
            "key": category["key"],
            "label": category["label"],
            "points": points,
            "max_points": category["weight"],
            "count": len(places),
            "nearest": places[0] if len(places) > 0 else None,
            "minutes": minutes,
            "is_estimate": is_estimate,
        })

    score = round(total_points)

    # Step 4: save everything in one transaction (all or nothing)
    with transaction.atomic():
        area, created = Area.objects.update_or_create(
            grid_key=grid_key,
            defaults={
                "name": name,
                "full_address": full_address,
                "lat": latitude,
                "lon": longitude,
                "score": score,
                "grade": scoring.grade_for(score),
                "verdict": scoring.make_verdict(category_results),
                "place_count": total_places,
                "fetched_at": timezone.now(),
            },
        )
        # Replace any old details from a previous fetch
        area.category_scores.all().delete()
        area.places.all().delete()

        new_category_scores = []
        for result in category_results:
            nearest = result["nearest"]
            new_category_scores.append(CategoryScore(
                area=area,
                category=result["key"],
                points=result["points"],
                max_points=result["max_points"],
                place_count=result["count"],
                nearest_name=nearest["name"] if nearest else "",
                nearest_metres=nearest["distance_metres"] if nearest else None,
                nearest_walk_minutes=result["minutes"],
                walk_time_is_estimate=result["is_estimate"],
            ))
        CategoryScore.objects.bulk_create(new_category_scores)

        new_places = []
        for category_key in places_by_category:
            for place in places_by_category[category_key][:PLACES_SAVED_PER_CATEGORY]:
                new_places.append(Place(
                    area=area,
                    category=category_key,
                    name=place["name"],
                    lat=place["lat"],
                    lon=place["lon"],
                    distance_metres=place["distance_metres"],
                ))
        Place.objects.bulk_create(new_places)

    return area


# Address text -> scored Area, in the fastest way that works:
#   1. a strong match among areas we already scored (instant, typo-tolerant)
#   2. Nominatim, for a properly written address
#   3. typo-tolerant suggestions (Photon), if Nominatim found nothing
def score_address(address_text):
    # Step 1: already scored? (strong matches only)
    local_matches = suggestions.suggest(address_text, limit=1, include_photon=False)
    if len(local_matches) > 0 and local_matches[0]["area_id"] is not None:
        area = Area.objects.get(pk=local_matches[0]["area_id"])
        if area.is_fresh() and suggestions.similarity(address_text, area.name.split(",")[0]) >= 0.75:
            return area

    # Step 2: Nominatim
    try:
        location = geocoding.geocode(address_text)
        return build_area(location["name"], location["full_address"], location["lat"], location["lon"])
    except AddressNotFound:
        pass

    # Step 3: spelling mistakes: take the best suggestion
    match = suggestions.best_match(address_text)
    if match is None:
        raise AddressNotFound("Couldn't find \"" + address_text + "\". Try adding the city name.")
    if match["area_id"] is not None:
        return Area.objects.get(pk=match["area_id"])
    return score_suggestion(match["label"], match["detail"], match["lat"], match["lon"])


# A suggestion the user clicked (we already know its coordinates) -> scored Area
def score_suggestion(label, detail, latitude, longitude):
    name = label
    if detail:
        name = label + ", " + detail.split(",")[0]
    full_address = label if not detail else label + ", " + detail
    return build_area(name[:200], full_address[:500], latitude, longitude)


# Coordinates (e.g. from "Use my location") -> scored Area
def score_coordinates(latitude, longitude):
    location = geocoding.reverse_geocode(latitude, longitude)
    return build_area(location["name"], location["full_address"], location["lat"], location["lon"])

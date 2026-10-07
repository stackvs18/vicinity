# The scoring formula. Plain functions with no database or internet, so they're easy to
# test and easy to explain.
#
# Each category is worth "weight" points (all weights add up to 100):
#
#     category points = weight x closeness factor x variety factor
#
#   closeness: how many minutes' walk to the NEAREST one (closer = better)
#   variety:   how many there are within a 15-minute walk (more choice = better)
#
# The area's score is the sum of all category points, rounded.

import math

EARTH_RADIUS_METRES = 6_371_000


# Straight-line distance between two points on Earth, in metres (the haversine formula)
def haversine_metres(lat1, lon1, lat2, lon2):
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_METRES * math.asin(math.sqrt(a))


# 1.0 if the nearest one is a 5-minute walk or less, then less and less
def closeness_factor(walk_minutes):
    if walk_minutes is None:
        return 0.0
    if walk_minutes <= 5:
        return 1.0
    if walk_minutes <= 10:
        return 0.85
    if walk_minutes <= 15:
        return 0.65
    if walk_minutes <= 20:
        return 0.45
    return 0.25


# 1.0 if there are 4 or more to choose from within a 15-minute walk
def variety_factor(count):
    if count <= 0:
        return 0.0
    if count == 1:
        return 0.7
    if count <= 3:
        return 0.85
    return 1.0


# Points for one category
def category_points(weight, nearest_walk_minutes, count):
    points = weight * closeness_factor(nearest_walk_minutes) * variety_factor(count)
    return round(points, 1)


# A word for the score
def grade_for(score):
    if score >= 80:
        return "Excellent"
    if score >= 65:
        return "Very good"
    if score >= 50:
        return "Good"
    if score >= 35:
        return "Fair"
    return "Limited"


# Joins words like a person would: "a", "a and b", "a, b and c"
def join_words(words):
    if len(words) == 0:
        return ""
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " and " + words[-1]


# A one-line summary, e.g. "Great for groceries, transport and food. Missing: parks."
# results = list of {"label", "points", "max_points"}
def make_verdict(results):
    strong_labels = []
    missing_labels = []
    for result in results:
        if result["points"] >= result["max_points"] * 0.85:
            strong_labels.append(result["label"].lower())
        elif result["points"] == 0:
            missing_labels.append(result["label"].lower())

    sentences = []
    if len(strong_labels) > 0:
        sentences.append("Great for " + join_words(strong_labels[:4]) + ".")
    if len(missing_labels) > 0:
        sentences.append("Nothing within a 15-minute walk for " + join_words(missing_labels) + ".")
    if len(sentences) == 0:
        sentences.append("A bit of everything, but nothing really close.")
    return " ".join(sentences)

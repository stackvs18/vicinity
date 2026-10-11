# The 10 things Vicinity looks for around an address.
#
# weight = how many of the 100 points this category is worth (they add up to 100)
# color  = the colour of its markers on the map

CATEGORIES = [
    {"key": "grocery", "label": "Groceries", "icon": "🛒", "weight": 15, "color": "#22c55e"},
    {"key": "health", "label": "Hospitals & clinics", "icon": "🏥", "weight": 15, "color": "#ef4444"},
    {"key": "transport", "label": "Bus & metro", "icon": "🚌", "weight": 15, "color": "#3b82f6"},
    {"key": "pharmacy", "label": "Pharmacies", "icon": "💊", "weight": 10, "color": "#ec4899"},
    {"key": "education", "label": "Schools & colleges", "icon": "🎓", "weight": 10, "color": "#a855f7"},
    {"key": "parks", "label": "Parks", "icon": "🌳", "weight": 10, "color": "#10b981"},
    {"key": "food", "label": "Food & cafés", "icon": "☕", "weight": 10, "color": "#f97316"},
    {"key": "banking", "label": "ATMs & banks", "icon": "🏧", "weight": 5, "color": "#eab308"},
    {"key": "safety", "label": "Police & fire", "icon": "🚓", "weight": 5, "color": "#0ea5e9"},
    {"key": "fitness", "label": "Gyms & sports", "icon": "🏋️", "weight": 5, "color": "#14b8a6"},
]

# For Django model fields: [("grocery", "Groceries"), ...]
CATEGORY_CHOICES = []
for category in CATEGORIES:
    CATEGORY_CHOICES.append((category["key"], category["label"]))

# Quick lookup: "grocery" -> {"key": "grocery", "label": "Groceries", ...}
CATEGORY_BY_KEY = {}
for category in CATEGORIES:
    CATEGORY_BY_KEY[category["key"]] = category


# ---- Which OpenStreetMap tags belong to which category -------------------------------
# OpenStreetMap describes every place with tags, e.g. {"amenity": "pharmacy"}.

GROCERY_SHOPS = {"supermarket", "convenience", "greengrocer", "grocery", "bakery", "dairy",
                 "general", "butcher", "deli"}
HEALTH_AMENITIES = {"hospital", "clinic", "doctors", "dentist"}
HEALTHCARE_TYPES = {"hospital", "clinic", "doctor", "dentist", "centre"}
EDUCATION_AMENITIES = {"school", "college", "university", "kindergarten"}
FOOD_AMENITIES = {"restaurant", "cafe", "fast_food", "food_court", "ice_cream"}
BANKING_AMENITIES = {"atm", "bank"}
SAFETY_AMENITIES = {"police", "fire_station"}
PARK_LEISURE = {"park", "garden", "playground"}
FITNESS_LEISURE = {"fitness_centre", "sports_centre", "stadium", "swimming_pool"}
TRANSPORT_RAILWAY = {"station", "halt", "subway_entrance", "tram_stop"}


# Decides which category an OpenStreetMap place belongs to (or None if we don't use it)
def categorize(tags):
    shop = tags.get("shop")
    amenity = tags.get("amenity")
    leisure = tags.get("leisure")

    if shop in GROCERY_SHOPS or amenity == "marketplace":
        return "grocery"
    healthcare = tags.get("healthcare")
    if amenity == "pharmacy" or shop == "chemist" or healthcare == "pharmacy":
        return "pharmacy"
    if amenity in HEALTH_AMENITIES or healthcare in HEALTHCARE_TYPES:
        return "health"
    if tags.get("highway") == "bus_stop" or amenity == "bus_station":
        return "transport"
    if tags.get("railway") in TRANSPORT_RAILWAY or tags.get("public_transport") == "station":
        return "transport"
    if amenity in EDUCATION_AMENITIES:
        return "education"
    if leisure in PARK_LEISURE:
        return "parks"
    if amenity in FOOD_AMENITIES:
        return "food"
    if amenity in BANKING_AMENITIES:
        return "banking"
    if amenity in SAFETY_AMENITIES:
        return "safety"
    if leisure in FITNESS_LEISURE:
        return "fitness"
    return None

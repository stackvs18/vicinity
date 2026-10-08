from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from areas.categories import CATEGORIES
from areas.models import Area, SavedArea
from areas.services.area_builder import score_address, score_coordinates, score_suggestion
from areas.services.errors import AddressNotFound, MapServiceBusy

# Clickable examples on the home page
EXAMPLE_SEARCHES = [
    "Navrangpura, Ahmedabad",
    "Koramangala, Bengaluru",
    "Bandra West, Mumbai",
    "Connaught Place, New Delhi",
    "Park Street, Kolkata",
]


# Home page: search, live numbers, the leaderboard, the categories and how it works
def home(request):
    # Total places mapped across every scored area
    place_total = Area.objects.aggregate(total=Sum("place_count"))["total"] or 0

    context = {
        "examples": EXAMPLE_SEARCHES,
        "top_areas": Area.objects.order_by("-score")[:6],
        "recent_areas": Area.objects.order_by("-created_at")[:6],
        "ticker_areas": Area.objects.order_by("-score")[:12],
        "area_count": Area.objects.count(),
        "place_total": place_total,
        "categories": CATEGORIES,
    }
    return render(request, "areas/home.html", context)


# Runs the search box: address -> scored area -> its page
def search(request):
    address_text = request.GET.get("q", "").strip()
    if address_text == "":
        return redirect("home")

    try:
        area = score_address(address_text)
    except AddressNotFound as error:
        messages.error(request, str(error))
        return redirect("home")
    except MapServiceBusy as error:
        messages.error(request, str(error))
        return redirect("home")

    return redirect(area)


# "Use my location": the browser sends coordinates -> scored area -> its page
def locate(request):
    try:
        latitude = float(request.GET.get("lat", ""))
        longitude = float(request.GET.get("lon", ""))
    except ValueError:
        messages.error(request, "Couldn't read your location.")
        return redirect("home")

    if latitude < -90 or latitude > 90 or longitude < -180 or longitude > 180:
        messages.error(request, "That location is not on Earth.")
        return redirect("home")

    try:
        label = request.GET.get("name", "").strip()
        if label != "":
            # Came from a clicked suggestion: we already know the name
            area = score_suggestion(label, request.GET.get("detail", ""), latitude, longitude)
        else:
            # Came from "Use my location": look the address up
            area = score_coordinates(latitude, longitude)
    except (AddressNotFound, MapServiceBusy) as error:
        messages.error(request, str(error))
        return redirect("home")

    return redirect(area)


# Everything the map on the area page needs, as plain data (sent to JavaScript)
def build_map_data(area):
    place_list = []
    for place in area.places.all():
        place_list.append({
            "lat": place.lat,
            "lon": place.lon,
            "name": place.name,
            "category": place.category,
            "distance": place.distance_metres,
        })

    category_list = []
    for category in CATEGORIES:
        category_list.append({
            "key": category["key"],
            "label": category["label"],
            "icon": category["icon"],
            "color": category["color"],
        })

    return {
        "center": [area.lat, area.lon],
        "radius": 1200,
        "name": area.name,
        "places": place_list,
        "categories": category_list,
    }


# A word and a colour for a category's result, like the status pills on a lab report
def status_for(category_score):
    if category_score.place_count == 0:
        return "Missing", "missing"
    percent = category_score.percent()
    if percent >= 85:
        return "Excellent", "excellent"
    if percent >= 60:
        return "Good", "good"
    return "Far", "far"


# The page for one scored area: score, category breakdown and map
def area_detail(request, pk):
    area = get_object_or_404(Area, pk=pk)

    category_rows = []
    for category_score in area.category_scores.all():
        status_text, status_class = status_for(category_score)
        category_rows.append({
            "score": category_score,
            "info": category_score.info(),
            "status_text": status_text,
            "status_class": status_class,
        })

    is_saved = False
    if request.user.is_authenticated:
        is_saved = SavedArea.objects.filter(user=request.user, area=area).exists()

    context = {
        "area": area,
        "category_rows": category_rows,
        "map_data": build_map_data(area),
        "is_saved": is_saved,
    }
    return render(request, "areas/area_detail.html", context)


# Scores two addresses and shows them side by side
def compare(request):
    first_text = request.GET.get("a", "").strip()
    second_text = request.GET.get("b", "").strip()
    context = {"first_text": first_text, "second_text": second_text}

    if first_text == "" or second_text == "":
        return render(request, "areas/compare.html", context)

    try:
        first_area = score_address(first_text)
        second_area = score_address(second_text)
    except (AddressNotFound, MapServiceBusy) as error:
        messages.error(request, str(error))
        return render(request, "areas/compare.html", context)

    # One row per category with both results and the winner
    first_scores = {}
    for category_score in first_area.category_scores.all():
        first_scores[category_score.category] = category_score
    second_scores = {}
    for category_score in second_area.category_scores.all():
        second_scores[category_score.category] = category_score

    rows = []
    for category in CATEGORIES:
        first = first_scores.get(category["key"])
        second = second_scores.get(category["key"])
        if first is None or second is None:
            continue
        winner = "tie"
        if first.points > second.points:
            winner = "first"
        elif second.points > first.points:
            winner = "second"
        rows.append({"info": category, "first": first, "second": second, "winner": winner})

    context["first_area"] = first_area
    context["second_area"] = second_area
    context["rows"] = rows
    return render(request, "areas/compare.html", context)


# Saves or un-saves an area for the logged-in user
@login_required
@require_POST
def toggle_save(request, pk):
    area = get_object_or_404(Area, pk=pk)
    saved = SavedArea.objects.filter(user=request.user, area=area).first()
    if saved is None:
        SavedArea.objects.create(user=request.user, area=area)
        messages.success(request, "Saved " + area.name + ".")
    else:
        saved.delete()
        messages.success(request, "Removed " + area.name + " from your saved areas.")
    return redirect(area)


# The logged-in user's saved areas
@login_required
def saved_areas(request):
    saved_list = SavedArea.objects.filter(user=request.user).select_related("area")
    return render(request, "areas/saved.html", {"saved_list": saved_list})


# Creates an account and logs the new user in
def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Welcome to Vicinity, " + user.username + "!")
            return redirect("home")
    else:
        form = UserCreationForm()
    return render(request, "registration/signup.html", {"form": form})

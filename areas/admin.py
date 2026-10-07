from django.contrib import admin

from areas.models import Area, CategoryScore, GeocodeResult, Place, SavedArea


class CategoryScoreInline(admin.TabularInline):
    model = CategoryScore
    extra = 0
    readonly_fields = ["category", "points", "max_points", "place_count", "nearest_name",
                       "nearest_walk_minutes"]


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ["name", "score", "grade", "place_count", "fetched_at"]
    list_filter = ["grade"]
    search_fields = ["name", "full_address"]
    inlines = [CategoryScoreInline]


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "area", "distance_metres"]
    list_filter = ["category"]
    search_fields = ["name"]


@admin.register(SavedArea)
class SavedAreaAdmin(admin.ModelAdmin):
    list_display = ["user", "area", "created_at"]


@admin.register(GeocodeResult)
class GeocodeResultAdmin(admin.ModelAdmin):
    list_display = ["query", "name", "lat", "lon", "created_at"]
    search_fields = ["query", "name"]

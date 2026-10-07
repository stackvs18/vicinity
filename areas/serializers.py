# Serializers turn models into JSON for the REST API.

from rest_framework import serializers

from areas.models import Area, CategoryScore, Place


class CategoryScoreSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()
    icon = serializers.SerializerMethodField()

    class Meta:
        model = CategoryScore
        fields = ["category", "label", "icon", "points", "max_points", "place_count",
                  "nearest_name", "nearest_metres", "nearest_walk_minutes",
                  "walk_time_is_estimate"]

    def get_label(self, category_score):
        return category_score.info()["label"]

    def get_icon(self, category_score):
        return category_score.info()["icon"]


class PlaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Place
        fields = ["category", "name", "lat", "lon", "distance_metres"]


class AreaListSerializer(serializers.ModelSerializer):
    """A short version for lists."""

    url = serializers.HyperlinkedIdentityField(view_name="api_area_detail")

    class Meta:
        model = Area
        fields = ["id", "url", "name", "score", "grade", "lat", "lon", "place_count", "fetched_at"]


class AreaDetailSerializer(serializers.ModelSerializer):
    """The full version: score breakdown and every place."""

    categories = CategoryScoreSerializer(source="category_scores", many=True, read_only=True)
    places = PlaceSerializer(many=True, read_only=True)

    class Meta:
        model = Area
        fields = ["id", "name", "full_address", "lat", "lon", "score", "grade", "verdict",
                  "place_count", "fetched_at", "categories", "places"]

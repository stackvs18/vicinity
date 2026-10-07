from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from areas.categories import CATEGORY_BY_KEY, CATEGORY_CHOICES


class Area(models.Model):
    """One scored location. Nearby addresses share one Area (see grid_key)."""

    name = models.CharField(max_length=200)  # short, e.g. "Navrangpura, Ahmedabad"
    full_address = models.CharField(max_length=500)
    lat = models.FloatField()
    lon = models.FloatField()

    # The location rounded to 3 decimals (about 110 m), e.g. "23.036,72.564".
    # Two searches that land within ~110 m of each other re-use the same Area.
    grid_key = models.CharField(max_length=40, unique=True)

    score = models.PositiveSmallIntegerField(default=0)  # 0 to 100
    grade = models.CharField(max_length=20, blank=True)  # "Excellent", "Good", ...
    verdict = models.CharField(max_length=300, blank=True)  # one-line summary
    place_count = models.PositiveIntegerField(default=0)

    fetched_at = models.DateTimeField(default=timezone.now)  # when map data was downloaded
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score"]
        indexes = [models.Index(fields=["-score"]), models.Index(fields=["-created_at"])]

    def __str__(self):
        return f"{self.name} ({self.score})"

    def get_absolute_url(self):
        return reverse("area_detail", args=[self.pk])

    # True if the map data is recent enough to re-use
    def is_fresh(self):
        age = timezone.now() - self.fetched_at
        return age < timedelta(days=settings.VICINITY_CACHE_DAYS)


class CategoryScore(models.Model):
    """How one area does in one category, e.g. "Groceries: 13.5 / 15"."""

    area = models.ForeignKey(Area, on_delete=models.CASCADE, related_name="category_scores")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    points = models.FloatField(default=0)
    max_points = models.PositiveSmallIntegerField()
    place_count = models.PositiveIntegerField(default=0)  # how many within a 15-min walk

    nearest_name = models.CharField(max_length=200, blank=True)
    nearest_metres = models.PositiveIntegerField(null=True, blank=True)
    nearest_walk_minutes = models.FloatField(null=True, blank=True)
    walk_time_is_estimate = models.BooleanField(default=False)  # True if routing was down

    class Meta:
        ordering = ["-max_points", "category"]
        constraints = [
            models.UniqueConstraint(fields=["area", "category"], name="one_score_per_category"),
        ]

    def __str__(self):
        return f"{self.area.name} · {self.category}: {self.points}/{self.max_points}"

    # Label, icon and colour from areas/categories.py
    def info(self):
        return CATEGORY_BY_KEY[self.category]

    # Points as a percentage of the maximum (for the progress bar)
    def percent(self):
        if self.max_points == 0:
            return 0
        return round(self.points / self.max_points * 100)


class Place(models.Model):
    """One place near an area: a pharmacy, a bus stop, a park..."""

    area = models.ForeignKey(Area, on_delete=models.CASCADE, related_name="places")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    name = models.CharField(max_length=200)
    lat = models.FloatField()
    lon = models.FloatField()
    distance_metres = models.PositiveIntegerField()  # straight-line distance from the area

    class Meta:
        ordering = ["distance_metres"]
        indexes = [models.Index(fields=["area", "category"])]

    def __str__(self):
        return f"{self.name} ({self.category}, {self.distance_metres} m)"


class SavedArea(models.Model):
    """An area a logged-in user bookmarked."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="saved_areas")
    area = models.ForeignKey(Area, on_delete=models.CASCADE, related_name="saved_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "area"], name="save_area_once"),
        ]

    def __str__(self):
        return f"{self.user} ★ {self.area.name}"


class GeocodeResult(models.Model):
    """Remembers what an address search returned, so Nominatim is asked only once."""

    query = models.CharField(max_length=300, unique=True)  # lowercased search text
    name = models.CharField(max_length=200)
    full_address = models.CharField(max_length=500)
    lat = models.FloatField()
    lon = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.query} -> {self.name}"

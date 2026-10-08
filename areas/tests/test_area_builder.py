# Tests for building an area. The map services are replaced with fakes (mock.patch),
# so these tests never touch the internet.

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from areas.models import Area
from areas.services import area_builder
from areas.services.errors import MapServiceBusy

HOME_LAT = 23.0360
HOME_LON = 72.5643

# Three fake places: a supermarket ~110 m away, a pharmacy ~220 m away, and a park 5 km away
FAKE_PLACES = [
    {"category": "grocery", "name": "Fresh Mart", "lat": 23.0370, "lon": 72.5643},
    {"category": "pharmacy", "name": "City Chemist", "lat": 23.0380, "lon": 72.5643},
    {"category": "parks", "name": "Far Away Park", "lat": 23.0810, "lon": 72.5643},
]


class BuildAreaTests(TestCase):

    @mock.patch("areas.services.area_builder.walking.walking_minutes", return_value=[2.0, 4.0])
    @mock.patch("areas.services.area_builder.overpass.fetch_places", return_value=FAKE_PLACES)
    def test_scores_and_saves_an_area(self, fake_fetch, fake_walking):
        area = area_builder.build_area("Navrangpura, Ahmedabad", "full", HOME_LAT, HOME_LON)

        self.assertEqual(Area.objects.count(), 1)
        self.assertEqual(area.place_count, 2)  # the park is outside the 1.2 km circle
        grocery = area.category_scores.get(category="grocery")
        self.assertEqual(grocery.nearest_name, "Fresh Mart")
        self.assertEqual(grocery.nearest_walk_minutes, 2.0)
        self.assertFalse(grocery.walk_time_is_estimate)
        self.assertEqual(area.category_scores.get(category="parks").points, 0)
        self.assertGreater(area.score, 0)

    @mock.patch("areas.services.area_builder.walking.walking_minutes", return_value=[2.0, 4.0])
    @mock.patch("areas.services.area_builder.overpass.fetch_places", return_value=FAKE_PLACES)
    def test_nearby_search_reuses_the_cached_area(self, fake_fetch, fake_walking):
        first = area_builder.build_area("A", "full", HOME_LAT, HOME_LON)
        second = area_builder.build_area("A", "full", HOME_LAT + 0.0001, HOME_LON)  # ~11 m away
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(fake_fetch.call_count, 1)  # map data downloaded only once

    @mock.patch("areas.services.area_builder.walking.walking_minutes", return_value=None)
    @mock.patch("areas.services.area_builder.overpass.fetch_places", return_value=FAKE_PLACES)
    def test_router_down_means_estimated_walk_times(self, fake_fetch, fake_walking):
        area = area_builder.build_area("A", "full", HOME_LAT, HOME_LON)
        grocery = area.category_scores.get(category="grocery")
        self.assertTrue(grocery.walk_time_is_estimate)
        self.assertGreater(grocery.nearest_walk_minutes, 0)

    @mock.patch("areas.services.area_builder.walking.walking_minutes", return_value=[2.0, 4.0])
    @mock.patch("areas.services.area_builder.overpass.fetch_places", return_value=FAKE_PLACES)
    def test_old_score_is_shown_when_servers_are_down(self, fake_fetch, fake_walking):
        area = area_builder.build_area("A", "full", HOME_LAT, HOME_LON)
        Area.objects.filter(pk=area.pk).update(fetched_at=timezone.now() - timedelta(days=90))

        fake_fetch.side_effect = MapServiceBusy("down")
        again = area_builder.build_area("A", "full", HOME_LAT, HOME_LON)
        self.assertEqual(again.pk, area.pk)

    def test_typed_name_is_kept_when_the_address_contains_it(self):
        name = area_builder.prefer_typed_name(
            "Satellite, Ahmedabad", "Ramdev nagar, Ahmedabad",
            "Satellite Road, Ramdev nagar, Vejalpur Taluka, Ahmedabad, Gujarat, India")
        self.assertEqual(name, "Satellite, Ahmedabad")
        # A typed name that isn't in the address is not trusted
        self.assertEqual(area_builder.prefer_typed_name("Xyz", "Powai, Mumbai", "Powai, Mumbai"),
                         "Powai, Mumbai")

    @mock.patch("areas.services.area_builder.overpass.fetch_places", side_effect=MapServiceBusy("down"))
    def test_new_area_with_servers_down_raises(self, fake_fetch):
        with self.assertRaises(MapServiceBusy):
            area_builder.build_area("A", "full", HOME_LAT, HOME_LON)

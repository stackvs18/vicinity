# Tests for the pages and the REST API, with the map services faked.

from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from areas.models import SavedArea
from areas.services import area_builder
from areas.services.errors import AddressNotFound
from areas.tests.test_area_builder import FAKE_PLACES, HOME_LAT, HOME_LON

FAKE_LOCATION = {"name": "Navrangpura, Ahmedabad", "full_address": "Navrangpura, Ahmedabad, India",
                 "lat": HOME_LAT, "lon": HOME_LON}


@mock.patch("areas.services.suggestions.ask_photon", return_value=[])
@mock.patch("areas.services.area_builder.walking.walking_minutes", return_value=[2.0, 4.0])
@mock.patch("areas.services.area_builder.overpass.fetch_places", return_value=FAKE_PLACES)
@mock.patch("areas.services.area_builder.geocoding.geocode", return_value=FAKE_LOCATION)
class PageTests(TestCase):

    def test_home_page(self, *fakes):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "How livable is")

    def test_search_redirects_to_the_area_page(self, *fakes):
        response = self.client.get(reverse("search"), {"q": "Navrangpura"})
        self.assertEqual(response.status_code, 302)
        page = self.client.get(response["Location"])
        self.assertContains(page, "Navrangpura, Ahmedabad")
        self.assertContains(page, "Fresh Mart")

    def test_unknown_address_shows_a_message(self, fake_geocode, *fakes):
        fake_geocode.side_effect = AddressNotFound("not found")
        response = self.client.get(reverse("search"), {"q": "zzzz"}, follow=True)
        self.assertContains(response, "Couldn&#x27;t find")

    def test_saving_needs_login_and_toggles(self, *fakes):
        area = area_builder.build_area("A", "full", HOME_LAT, HOME_LON)
        url = reverse("toggle_save", args=[area.pk])

        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

        user = User.objects.create_user("vraj", password="a-strong-password-123")
        self.client.force_login(user)
        self.client.post(url)
        self.assertTrue(SavedArea.objects.filter(user=user, area=area).exists())
        self.client.post(url)
        self.assertFalse(SavedArea.objects.filter(user=user, area=area).exists())

    def test_misspelled_search_opens_the_scored_area(self, *fakes):
        area = area_builder.build_area("Koramangala, Bengaluru", "full", HOME_LAT, HOME_LON)
        response = self.client.get(reverse("search"), {"q": "koramangla"})
        self.assertRedirects(response, area.get_absolute_url())

    def test_clicked_suggestion_skips_reverse_geocoding(self, *fakes):
        with mock.patch("areas.services.area_builder.geocoding.reverse_geocode") as fake_reverse:
            response = self.client.get(reverse("locate"), {
                "lat": HOME_LAT, "lon": HOME_LON, "name": "Powai", "detail": "Mumbai, Maharashtra"})
            fake_reverse.assert_not_called()
        page = self.client.get(response["Location"])
        self.assertContains(page, "Powai, Mumbai")

    def test_compare_page(self, *fakes):
        response = self.client.get(reverse("compare"), {"a": "One", "b": "Two"})
        self.assertContains(response, "Groceries")


@mock.patch("areas.services.suggestions.ask_photon", return_value=[])
@mock.patch("areas.services.area_builder.walking.walking_minutes", return_value=[2.0, 4.0])
@mock.patch("areas.services.area_builder.overpass.fetch_places", return_value=FAKE_PLACES)
@mock.patch("areas.services.area_builder.geocoding.geocode", return_value=FAKE_LOCATION)
class ApiTests(TestCase):

    def test_score_endpoint_returns_breakdown(self, *fakes):
        response = self.client.get(reverse("api_score"), {"address": "Navrangpura"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Navrangpura, Ahmedabad")
        self.assertEqual(len(data["categories"]), 10)

    def test_score_endpoint_needs_input(self, *fakes):
        response = self.client.get(reverse("api_score"))
        self.assertEqual(response.status_code, 400)

    def test_score_endpoint_unknown_address_is_404(self, fake_geocode, *fakes):
        fake_geocode.side_effect = AddressNotFound("nope")
        response = self.client.get(reverse("api_score"), {"address": "zzzz"})
        self.assertEqual(response.status_code, 404)

    def test_suggest_endpoint_is_typo_tolerant(self, *fakes):
        area_builder.build_area("Navrangpura, Ahmedabad", "full", HOME_LAT, HOME_LON)
        results = self.client.get(reverse("api_suggest"), {"q": "navrangpra", "local": "1"}).json()["results"]
        self.assertEqual(results[0]["label"], "Navrangpura, Ahmedabad")
        self.assertIsNotNone(results[0]["area_id"])

    def test_area_list_and_detail(self, *fakes):
        area = area_builder.build_area("A", "full", HOME_LAT, HOME_LON)
        listing = self.client.get(reverse("api_area_list")).json()
        self.assertEqual(listing["count"], 1)
        detail = self.client.get(reverse("api_area_detail", args=[area.pk])).json()
        self.assertEqual(len(detail["places"]), 2)

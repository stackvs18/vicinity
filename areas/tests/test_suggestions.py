# Tests for typo-tolerant search suggestions (Photon is faked, no internet needed).

from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from areas.services import suggestions

FAKE_PHOTON = [
    {"label": "Sateli", "detail": "Durgkondal, Chhattisgarh", "lat": 20.1, "lon": 81.0,
     "type": "city", "town": "Durgkondal", "area_id": None, "score": None},
    {"label": "Satellite", "detail": "Ahmedabad, Gujarat", "lat": 23.03, "lon": 72.52,
     "type": "suburb", "town": "Ahmedabad", "area_id": None, "score": None},
]


class SuggestionTests(TestCase):

    def setUp(self):
        cache.clear()

    def test_city_is_recognised_even_misspelled(self):
        self.assertEqual(suggestions.split_place_and_city("navrangpra ahmdabad"), ("navrangpra", "Ahmedabad"))
        self.assertEqual(suggestions.split_place_and_city("indiranagar bangalore"), ("indiranagar", "Bengaluru"))
        self.assertEqual(suggestions.split_place_and_city("powai"), ("powai", None))

    def test_shortened_words_survive_typos(self):
        self.assertEqual(suggestions.shorten_words("koramangla bandra wst"), "koramang band w")

    @mock.patch("areas.services.suggestions.ask_photon", return_value=FAKE_PHOTON)
    def test_place_in_the_typed_city_wins(self, fake_photon):
        results = suggestions.suggest("satelite ahmedabad")
        self.assertEqual(results[0]["label"], "Satellite")

    @mock.patch("areas.services.suggestions.ask_photon", return_value=[])
    def test_too_short_text_gives_nothing(self, fake_photon):
        self.assertEqual(suggestions.suggest("a"), [])

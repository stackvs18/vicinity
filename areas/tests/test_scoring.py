# Tests for the scoring formula and the OpenStreetMap tag rules. No internet needed.

from django.test import SimpleTestCase

from areas.categories import CATEGORIES, categorize
from areas.services import scoring


class ScoringTests(SimpleTestCase):

    def test_weights_add_up_to_100(self):
        total = 0
        for category in CATEGORIES:
            total = total + category["weight"]
        self.assertEqual(total, 100)

    def test_closer_is_better(self):
        self.assertEqual(scoring.closeness_factor(3), 1.0)
        self.assertEqual(scoring.closeness_factor(8), 0.85)
        self.assertEqual(scoring.closeness_factor(25), 0.25)
        self.assertEqual(scoring.closeness_factor(None), 0.0)

    def test_more_choice_is_better(self):
        self.assertEqual(scoring.variety_factor(0), 0.0)
        self.assertEqual(scoring.variety_factor(1), 0.7)
        self.assertEqual(scoring.variety_factor(10), 1.0)

    def test_category_points(self):
        self.assertEqual(scoring.category_points(15, 4, 10), 15.0)  # close and plenty
        self.assertEqual(scoring.category_points(15, None, 0), 0.0)  # nothing nearby

    def test_grades(self):
        self.assertEqual(scoring.grade_for(92), "Excellent")
        self.assertEqual(scoring.grade_for(55), "Good")
        self.assertEqual(scoring.grade_for(10), "Limited")

    def test_verdict_mentions_strong_and_missing(self):
        results = [
            {"label": "Groceries", "points": 15, "max_points": 15},
            {"label": "Parks", "points": 0, "max_points": 10},
        ]
        verdict = scoring.make_verdict(results)
        self.assertIn("Great for groceries", verdict)
        self.assertIn("parks", verdict)

    def test_haversine_known_distance(self):
        # Ahmedabad to Gandhinagar is about 23 km in a straight line
        distance = scoring.haversine_metres(23.0225, 72.5714, 23.2156, 72.6369)
        self.assertAlmostEqual(distance / 1000, 22.5, delta=1.5)


class CategoryRuleTests(SimpleTestCase):

    def test_tags_map_to_categories(self):
        self.assertEqual(categorize({"shop": "supermarket"}), "grocery")
        self.assertEqual(categorize({"amenity": "pharmacy"}), "pharmacy")
        self.assertEqual(categorize({"healthcare": "pharmacy"}), "pharmacy")
        self.assertEqual(categorize({"amenity": "hospital"}), "health")
        self.assertEqual(categorize({"highway": "bus_stop"}), "transport")
        self.assertEqual(categorize({"railway": "subway_entrance"}), "transport")
        self.assertEqual(categorize({"leisure": "park"}), "parks")
        self.assertEqual(categorize({"amenity": "atm"}), "banking")

    def test_unknown_tags_are_ignored(self):
        self.assertIsNone(categorize({"amenity": "bench"}))
        self.assertIsNone(categorize({}))

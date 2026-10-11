# python manage.py load_demo_areas
#
# Gets the demo areas ready, so the home page has data and a live demo never has to wait
# for the free map servers. build.sh runs it on every deploy.
#
#   Step 1: a brand-new database gets the 10 pre-scored demo areas from
#           areas/fixtures/demo_areas.json. Instant, no internet needed.
#   Step 2: no fixture file either? Score the demo addresses using the map servers.
#   Step 3: demo areas older than 30 days are re-scored at their saved location
#           (no address lookup, so names never change and no duplicates appear).
#
# python manage.py load_demo_areas --save-fixture
#   Saves the demo areas from YOUR database into areas/fixtures/demo_areas.json.
#   Run it on your laptop after re-scoring, then commit the file.

import json
import time
from pathlib import Path

from django.core import serializers
from django.core.management import call_command
from django.core.management.base import BaseCommand

from areas.models import Area, CategoryScore, Place
from areas.services.area_builder import build_area, score_address
from areas.services.errors import AddressNotFound, MapServiceBusy

DEMO_ADDRESSES = [
    "Navrangpura, Ahmedabad",
    "Satellite, Ahmedabad",
    "Koramangala, Bengaluru",
    "Indiranagar, Bengaluru",
    "Bandra West, Mumbai",
    "Connaught Place, New Delhi",
    "Park Street, Kolkata",
    "T. Nagar, Chennai",
    "Kothrud, Pune",
    "Gachibowli, Hyderabad",
]

# areas/fixtures/demo_areas.json (this file is in areas/management/commands/)
FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "demo_areas.json"


class Command(BaseCommand):
    help = "Gets the demo areas ready (safe to run many times; fresh areas are skipped)."

    def add_arguments(self, parser):
        parser.add_argument("--quiet", action="store_true", help="Print less.")
        parser.add_argument("--save-fixture", action="store_true",
                            help="Save the demo areas into areas/fixtures/demo_areas.json.")

    def handle(self, *args, **options):
        quiet = options["quiet"]

        if options["save_fixture"]:
            demo_areas = self.score_demo_addresses(quiet)
            self.save_fixture(demo_areas)
            return

        # Step 1: a brand-new database gets the pre-scored demo areas straight away
        if Area.objects.count() == 0 and FIXTURE_PATH.exists():
            call_command("loaddata", str(FIXTURE_PATH), verbosity=0)
            self.stdout.write(f"Loaded {Area.objects.count()} pre-scored demo areas from the fixture.")

        # Step 2: still empty (no fixture file)? Score the demo addresses the slow way
        if Area.objects.count() == 0:
            self.score_demo_addresses(quiet)

        # Step 3: keep the demo areas fresh
        self.refresh_old_demo_areas(quiet)

    # Scores every demo address with the map servers. Returns the areas it got.
    def score_demo_addresses(self, quiet):
        demo_areas = []
        for address in DEMO_ADDRESSES:
            try:
                area = score_address(address)
                demo_areas.append(area)
                if not quiet:
                    self.stdout.write(f"{area.score:>3}  {area.grade:<10} {area.name}")
            except (AddressNotFound, MapServiceBusy) as error:
                self.stdout.write(self.style.WARNING(f"skipped {address}: {error}"))
            time.sleep(2)  # be gentle with the free map servers

        self.stdout.write(self.style.SUCCESS(f"{len(demo_areas)} of {len(DEMO_ADDRESSES)} demo areas scored."))
        return demo_areas

    # Re-scores demo areas (the ones in the fixture) whose map data is older than 30 days
    def refresh_old_demo_areas(self, quiet):
        if not FIXTURE_PATH.exists():
            return

        # Step 1: which areas are the demo areas? Their ids are in the fixture.
        with open(FIXTURE_PATH, encoding="utf-8") as fixture_file:
            fixture_rows = json.load(fixture_file)
        demo_area_ids = []
        for row in fixture_rows:
            if row["model"] == "areas.area":
                demo_area_ids.append(row["pk"])

        # Step 2: re-score the old ones at their saved location (same grid key = same area)
        refreshed = 0
        for area in Area.objects.filter(pk__in=demo_area_ids):
            if area.is_fresh():
                continue
            try:
                area = build_area(area.name, area.full_address, area.lat, area.lon, force_refresh=True)
                refreshed = refreshed + 1
                if not quiet:
                    self.stdout.write(f"{area.score:>3}  {area.grade:<10} {area.name} (refreshed)")
            except MapServiceBusy as error:
                self.stdout.write(self.style.WARNING(f"kept the old score for {area.name}: {error}"))
            time.sleep(2)  # be gentle with the free map servers

        self.stdout.write(self.style.SUCCESS(f"Demo areas ready ({refreshed} refreshed, the rest still fresh)."))

    # Writes the demo areas, their category scores and their places into the fixture file
    def save_fixture(self, demo_areas):
        area_ids = []
        for area in demo_areas:
            area_ids.append(area.pk)

        rows = []
        rows.extend(Area.objects.filter(pk__in=area_ids))
        rows.extend(CategoryScore.objects.filter(area_id__in=area_ids))
        rows.extend(Place.objects.filter(area_id__in=area_ids))

        FIXTURE_PATH.parent.mkdir(exist_ok=True)
        with open(FIXTURE_PATH, "w", encoding="utf-8") as fixture_file:
            serializers.serialize("json", rows, stream=fixture_file, indent=1)
        self.stdout.write(self.style.SUCCESS(f"Saved {len(area_ids)} areas ({len(rows)} rows) to {FIXTURE_PATH}"))

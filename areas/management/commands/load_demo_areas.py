# python manage.py load_demo_areas
#
# Scores a few well-known Indian neighbourhoods ahead of time, so the home page has data
# and a live demo never has to wait for the free map servers.

import time

from django.core.management.base import BaseCommand

from areas.services.area_builder import score_address
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


class Command(BaseCommand):
    help = "Pre-scores a list of demo areas (safe to run many times; fresh areas are skipped)."

    def add_arguments(self, parser):
        parser.add_argument("--quiet", action="store_true", help="Print less.")

    def handle(self, *args, **options):
        scored = 0
        for address in DEMO_ADDRESSES:
            try:
                area = score_address(address)
                scored = scored + 1
                if not options["quiet"]:
                    self.stdout.write(f"{area.score:>3}  {area.grade:<10} {area.name}")
            except (AddressNotFound, MapServiceBusy) as error:
                self.stdout.write(self.style.WARNING(f"skipped {address}: {error}"))
            time.sleep(2)  # be gentle with the free map servers

        self.stdout.write(self.style.SUCCESS(f"{scored} of {len(DEMO_ADDRESSES)} demo areas ready."))

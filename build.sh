#!/usr/bin/env bash
# Render runs this on every deploy (see render.yaml)
set -o errexit

# Step 1: install the Python packages
pip install -r requirements.txt

# Step 2: gather CSS/JS into staticfiles/ (WhiteNoise serves them)
python manage.py collectstatic --noinput

# Step 3: create or update the database tables on Neon
python manage.py migrate

# Step 4: the admin account, from DJANGO_SUPERUSER_USERNAME / _EMAIL / _PASSWORD.
# Fails harmlessly if those aren't set or the account already exists.
python manage.py createsuperuser --noinput || echo "Admin account: skipped (already exists or not set)"

# Step 5: the demo areas (first deploy: copied from the fixture; later: refreshed if older
# than 30 days). Never fails the deploy, even if the map servers are down.
python manage.py load_demo_areas --quiet || true

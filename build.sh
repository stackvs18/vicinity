#!/usr/bin/env bash
# Render runs this on every deploy
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
python manage.py load_demo_areas --quiet || true   # pre-score demo areas; never fails the deploy

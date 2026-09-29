#!/usr/bin/env bash
# Update the PythonAnywhere site to the latest code on GitHub. In a Bash console:
#
#   bash ~/interview_time_logger/deploy/pythonanywhere-update.sh
#
# Your data and settings (.env) are kept.
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source "$HOME/.virtualenvs/tracker/bin/activate"

git pull --ff-only
pip install --quiet -r requirements.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput

# Changing the WSGI file makes PythonAnywhere reload the site.
shopt -s nullglob
wsgi_files=(/var/www/*_wsgi.py)
if [ ${#wsgi_files[@]} -gt 0 ]; then
  touch "${wsgi_files[@]}"
  echo "Updated. The site is running the new version."
else
  echo "Updated. Now click the green Reload button on the Web tab."
fi

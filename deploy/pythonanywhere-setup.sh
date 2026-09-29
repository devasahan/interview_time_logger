#!/usr/bin/env bash
# First-time setup on a free PythonAnywhere account. In a PythonAnywhere Bash console:
#
#   git clone https://github.com/devasahan/interview_time_logger.git
#   cd interview_time_logger
#   bash deploy/pythonanywhere-setup.sh
#
# It installs the app, writes the settings file (.env), creates the database and your
# admin account, then prints exactly what to fill in on the Web tab. Safe to run again.
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
VENV="$HOME/.virtualenvs/tracker"
PA_USER="${USER:-$(whoami)}"

# The newest Python that Django 5.2 supports.
PYTHON=""
for version in 3.13 3.12 3.11 3.10; do
  if command -v "python$version" >/dev/null 2>&1; then
    PYTHON="python$version"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Python 3.10 or newer is needed, but none was found." >&2
  exit 1
fi
PYTHON_VERSION="${PYTHON#python}"

echo "== Installing the app with Python $PYTHON_VERSION (takes a few minutes)"
if [ ! -x "$VENV/bin/python" ]; then
  "$PYTHON" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

if [ -f .env ]; then
  echo "== Keeping the existing settings in .env"
  DOMAIN="$(sed -n "s/^DJANGO_ALLOWED_HOSTS='\{0,1\}\([^',]*\).*/\1/p" .env | head -n 1)"
else
  echo
  echo "== A few questions (press Enter to accept the answer in brackets)"
  read -r -p "Your site address [$PA_USER.pythonanywhere.com]: " DOMAIN
  DOMAIN="${DOMAIN:-$PA_USER.pythonanywhere.com}"
  DOMAIN="${DOMAIN#https://}"
  DOMAIN="${DOMAIN#http://}"
  DOMAIN="${DOMAIN%%/*}"

  while true; do
    read -r -p "Your time zone, e.g. Asia/Manila, Asia/Colombo, America/New_York [UTC]: " TZ_NAME
    TZ_NAME="${TZ_NAME:-UTC}"
    if python -c "import sys, zoneinfo; zoneinfo.ZoneInfo(sys.argv[1])" "$TZ_NAME" 2>/dev/null; then
      break
    fi
    echo "  '$TZ_NAME' isn't a time zone name. Use Region/City, like Asia/Manila."
  done

  read -r -p "Currency symbol shown before amounts [\$]: " CURRENCY
  CURRENCY="${CURRENCY:-\$}"
  CURRENCY="${CURRENCY//\'/}"

  SECRET_KEY="$(python -c "import secrets; print(secrets.token_urlsafe(50))")"
  umask 077
  cat > .env <<EOF
# Settings for this site. Keep this file private: it holds the secret key.
DJANGO_DEBUG=False
DJANGO_SECRET_KEY='$SECRET_KEY'
DJANGO_ALLOWED_HOSTS='$DOMAIN'
DJANGO_CSRF_TRUSTED_ORIGINS='https://$DOMAIN'
# PythonAnywhere's "Force HTTPS" switch (Web tab) sends visitors to https.
DJANGO_SSL_REDIRECT=False
TIME_ZONE='$TZ_NAME'
CURRENCY_SYMBOL='$CURRENCY'
WEEK_START_DAY=0
EOF
  umask 022
  echo "== Saved the settings in $PROJECT_DIR/.env"
fi

echo
echo "== Setting up the database"
python manage.py migrate --noinput
python manage.py collectstatic --noinput

echo
if python manage.py shell -v 0 -c "import sys; from accounts.models import User; sys.exit(0 if User.objects.filter(is_superuser=True).exists() else 1)"; then
  echo "== Your admin account already exists"
else
  echo "== Create your admin account (this is you, the one who approves members and pays them)"
  python manage.py createsuperuser
fi

WSGI_FILE="/var/www/$(echo "$DOMAIN" | tr '.' '_')_wsgi.py"
cat <<EOF

=====================================================================
 Almost done. Open the "Web" tab on PythonAnywhere and:

 1. Click "Add a new web app" > Next > "Manual configuration"
    (not "Django") > "Python $PYTHON_VERSION" > Next.

 2. In the "Code" section, set both "Source code" and
    "Working directory" to:
        $PROJECT_DIR

 3. Click the "WSGI configuration file" link
    ($WSGI_FILE),
    delete everything in it, paste these 3 lines, and click Save:

        import sys
        sys.path.insert(0, "$PROJECT_DIR")
        from config.wsgi import application

 4. Back on the Web tab, in "Virtualenv", enter:
        $VENV

 5. In "Static files", add:
        URL:        /static/
        Directory:  $PROJECT_DIR/staticfiles

 6. In "Security", switch "Force HTTPS" on.

 7. Click the green "Reload" button at the top, then open:
        https://$DOMAIN
=====================================================================
EOF

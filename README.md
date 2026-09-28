# Interview Time Logger

A small web app where team members log the interviews they take part in, and the admin pays them weekly at each member's own hourly rate.

**Members can:**
- Sign up, then wait for the admin to approve them and set their hourly rate.
- Log each interview: date, start and end time, who the interview was with, the role, and the interview type (HR, Technical, Culture Call, …).
- See their history by week or by month, with hours, earnings, what's been paid and what's still to be paid.
- See every payment they've received and what's coming up next.

**The admin can:**
- Approve new sign-ups in one step on the **Team** page by entering their hourly rate, and change rates later. Only the admin can do this.
- See everyone's interviews by week or month, filtered by member.
- Change any interview's pay status between **To be paid** and **Paid** right in the interview lists (Overview, Interviews, each pay week). Members see the new status, with the date it was paid.
- Or run weekly payroll: review a week, pay a member (or everyone) in one go, and record it with an optional note such as a transfer reference. A payment recorded by mistake can be undone.
- Manage the list of interview types.
- Deactivate members who leave. Their history is kept.

Built with Django 5.2 (LTS). It uses SQLite locally and Postgres in production.

---

## Run it on your computer

You need **Python 3.10 or newer**.

```bash
git clone <this repo> && cd interview_time_logger

python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                 # Windows: copy .env.example .env
python manage.py migrate
python manage.py createsuperuser     # this is you, the admin
python manage.py runserver
```

Open http://127.0.0.1:8000 and log in with the admin account.

### Try the whole flow

1. Open a private browser window, go to http://127.0.0.1:8000/accounts/signup/ and create a member account. It says "waiting for approval".
2. In your admin window go to **Team**, type an hourly rate next to the new member and click **Approve**.
3. As the member, click **+ Log interview** and add a few interviews. Look at **My interviews** (week and month tabs) and **Payments**.
4. As the admin, change an interview's status to **Paid** in **Interviews** (or open **Payroll**, pick the week, click **Pay …** and **Mark as paid** to pay a whole week).
5. As the member, **Payments** now shows the payment, and those interviews show as **Paid**.

Run the tests with `python manage.py test`.

---

## How pay works

- **Amount = duration × hourly rate**, rounded to the cent for each interview.
- **Pay weeks run Monday–Sunday** by default. Change this with `WEEK_START_DAY`.
- **Rate changes have an effective date.** An interview uses the rate in effect on its date. A member's first rate also covers anything they logged before it was set.
- **Paid means locked.** When you mark a week as paid, the rate and amount of each interview are saved with the payment. Later rate changes never alter what was already paid. Members can't edit or delete paid interviews. To fix one, set its status back to **To be paid** (or undo the payment) first.
- **You pay exactly what you reviewed.** If a member edits, adds or deletes something while you have the payment page open, recording the payment is refused and you're asked to review again. Interviews logged later for an already-paid week show up as a new unpaid amount for that week.
- Interviews that run past midnight are handled: enter 23:30 → 00:30 and it counts as one hour ending the next day. An interview can't be longer than 12 hours, can't overlap another one from the same member (so double submissions are blocked), and can't be in the future.

---

## Settings

All settings are environment variables. For local use, put them in `.env` (see `.env.example`).

| Variable | Default | What it does |
| --- | --- | --- |
| `DJANGO_DEBUG` | `False` | `True` only on your own computer. |
| `DJANGO_SECRET_KEY` | none | **Required in production.** Generate one with `python -c "import secrets; print(secrets.token_urlsafe(50))"`. |
| `DJANGO_ALLOWED_HOSTS` | none | **Required in production.** Your domain(s), comma-separated, e.g. `timelog.example.com`. |
| `DATABASE_URL` | SQLite file | e.g. `postgres://user:pass@host:5432/dbname` |
| `TIME_ZONE` | `UTC` | Decides what "today" and "this week" mean, e.g. `America/New_York`, `Asia/Colombo`. |
| `CURRENCY_SYMBOL` | `$` | Shown in front of amounts, e.g. `€`, `£`, `Rs.` |
| `WEEK_START_DAY` | `0` | First day of the pay week: `0` = Monday … `6` = Sunday. Set it before your first payment. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_EMAIL` | none | If set, the admin account is created at startup (the Docker image does this). Useful on hosts without a shell. An existing account is never changed. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | none | Only if forms fail with "CSRF verification failed", e.g. `https://timelog.example.com`. |
| `DJANGO_USE_HTTPS` | on when not debugging | Secure cookies and redirect to HTTPS. Set `False` only to try a production build over plain http on your own machine. |
| `DJANGO_HSTS_SECONDS` | `0` | Optional HSTS once HTTPS works, e.g. `31536000`. |

---

## Deploy

Checklist for any host:

1. **Use Postgres** and set `DATABASE_URL`. Most hosts wipe the local disk on every deploy, so a SQLite file would lose your data.
2. Set `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS`. Leave `DJANGO_DEBUG` unset.
3. Set `TIME_ZONE`, `CURRENCY_SYMBOL` and, if you like, `WEEK_START_DAY`.
4. Set `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `ADMIN_EMAIL` so your admin account is created on the first start. You can remove them afterwards.

### With Docker (Render, Railway, Fly.io, DigitalOcean, any VPS)

The included `Dockerfile` builds the app, collects static files, and on start runs migrations, creates the admin account if asked, and starts gunicorn on `$PORT` (default 8000).

```bash
docker build -t interview-time-logger .
docker run -p 8000:8000 --env-file production.env interview-time-logger
```

- **Render:** create a PostgreSQL database and a Web Service from this repo (it detects the Dockerfile). Set the environment variables, with `DATABASE_URL` from the database's internal URL. Your `*.onrender.com` hostname is allowed automatically. Health check path: `/healthz/`.
- **Railway:** add a Postgres database to the project and reference its `DATABASE_URL` in the app service. Generate a public domain; it's allowed automatically.

### Without Docker

- Build: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
- Before each start (or as a release command): `python manage.py migrate && python manage.py ensure_admin`
- Start: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`

To check the production settings, run `python manage.py check --deploy` with your production environment variables set.

### After deploying

Share `https://<your-domain>/accounts/signup/` with your team. New members appear under **Team** with a count in the menu until you approve them.

Forgotten passwords: the admin can set a new one in the built-in Django admin at `/django-admin/` (the member's page in **Team** links to it).

---

## Project layout

```
config/      settings, URLs, WSGI entry point
accounts/    user model, sign-up, login (username or email), ensure_admin command
tracker/     interviews, hourly rates, payouts, all pages
  periods.py   pay weeks and months
  services.py  pay calculations, summaries, recording and undoing payouts
  views.py     member pages          manage_views.py  admin pages
templates/   HTML templates
static/      CSS, favicon, small JS for the live duration preview
```

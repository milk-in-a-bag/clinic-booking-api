# Clinic Booking API

A REST API for a small clinic booking system — 5 doctors, 30-minute appointment
slots, patient-facing booking/cancel/reschedule.

## System Design

### Models identified

**Doctor**

- `name`
- `specialty` (optional — not required by the brief, added for future growth)

**WorkingHours**

- `doctor` (FK)
- `weekday` (0–6)
- `start_time`, `end_time`

Kept as its own table rather than fields on `Doctor`, because "set working hours"
could reasonably vary by day (e.g. half-day Saturdays). The cost is one extra table;
the benefit is not having to migrate the schema later if that assumption changes.

**Patient**

- `name`
- `phone` or `email`

No authentication in this version — patients are identified by ID only. Given the
brief's "we're starting small but want to grow" framing, I treated auth as out of
scope for now and a clear extension point later, rather than over-building it upfront.

**Appointment**

- `doctor` (FK), `patient` (FK)
- `start_time`, `end_time` (datetime, not just time — needs the date)
- `status`: `booked` | `cancelled`
- `cancellation_reason` (nullable)

`status` is a field rather than a boolean `is_cancelled`, so it's extensible if
future states are needed (e.g. `completed`, `no_show`) without another migration.

### Key decision: preventing double-booking under concurrency

The core risk in this system is two requests booking the same slot at the same time.
Relying only on an application-level "is this slot free?" check before insert has a
race condition — two concurrent requests can both pass the check before either
commits.

Decision: use a **database-level partial unique constraint** on
`(doctor, start_time)` where `status='booked'`, on top of an app-level check.

- The app-level check gives clean, immediate error messages for the common case.
- The DB constraint is the actual correctness guarantee under concurrency — Django
  raises an `IntegrityError` on the rare race, which we catch and convert to a
  409 response.
- The constraint is scoped to `status='booked'` (not a plain `unique_together`)
  so a cancelled appointment doesn't block that slot from being rebooked.

### Trade-offs considered

- **Single Django app vs. split apps** (`doctors`, `patients`, `appointments`):
  chose a single `bookings` app since the four models are tightly coupled and
  splitting now adds import overhead for no real benefit at this scale.
- **Slot granularity**: fixed at 30 minutes per the brief, generated dynamically
  from `WorkingHours` rather than pre-materialized as rows — avoids a slot-table
  that needs to be seeded/maintained per doctor per day.
- **Timezone handling**: assumed a single clinic timezone (Africa/Nairobi) rather
  than per-doctor or per-patient timezones, since the brief describes one physical
  clinic.
- **Overlap prevention**: relies on all appointments being created on fixed
  30-minute boundaries via the API's slot validation. The DB constraint checks
  exact `(doctor, start_time)` matches rather than time-range overlap; this is
  sufficient given the fixed-grid design but wouldn't catch misaligned appointments
  created outside the normal booking flow (e.g. direct admin edits).

## How to Run Locally

```powershell
git clone <repo-url>
cd clinic-booking-api
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
# create a .env file with:
#   DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<dbname>
#   SECRET_KEY=<any-random-string-for-local-dev>
#   DEBUG=True
#   ALLOWED_HOSTS=localhost,127.0.0.1
python manage.py migrate
python manage.py runserver
```

## CI/CD

- **Deployed at (production):** https://clinic-booking-api-7hxm.onrender.com
- **Deploy trigger:** Render auto-deploys on every push to `main` (Blueprint-managed
  via `render.yaml`).
- **CI pipeline:** GitHub Actions (`.github/workflows/ci.yml`) runs the `test` job on
  every pull request into `main`. It spins up a disposable Postgres 16 service
  container, runs migrations, and runs the Django test suite. `main` is protected —
  PRs must pass the `test` check before merging.

## AI Reflection

_(Section 4 — to be filled in at the end)_

# Clinic Booking API

A REST API for a small clinic booking system: 5 doctors, 30-minute appointment
slots, patient-facing booking/cancel/reschedule.

## System Design

### Models identified

**Doctor**

- `name`
- `specialty` (optional, not required by the brief, added for future growth)

**WorkingHours**

- `doctor` (FK)
- `weekday` (0 to 6)
- `start_time`, `end_time`

Kept as its own table rather than fields on `Doctor`, because "set working hours"
could reasonably vary by day (e.g. half-day Saturdays). The cost is one extra table;
the benefit is not having to migrate the schema later if that assumption changes.

**Patient**

- `name`
- `phone` or `email`

No authentication in this version, patients are identified by ID only. Given the
brief's "we're starting small but want to grow" framing, I treated auth as out of
scope for now and a clear extension point later, rather than over-building it upfront.

**Appointment**

- `doctor` (FK), `patient` (FK)
- `start_time`, `end_time` (datetime, not just time, needs the date)
- `status`: `booked` | `cancelled`
- `cancellation_reason` (nullable)

`status` is a field rather than a boolean `is_cancelled`, so it's extensible if
future states are needed (e.g. `completed`, `no_show`) without another migration.

### Key decision: preventing double-booking under concurrency

The core risk in this system is two requests booking the same slot at the same time.
Relying only on an application-level "is this slot free?" check before insert has a
race condition: two concurrent requests can both pass the check before either
commits.

Decision: use a **database-level partial unique constraint** on
`(doctor, start_time)` where `status='booked'`, on top of an app-level check.

- The app-level check gives clean, immediate error messages for the common case.
- The DB constraint is the actual correctness guarantee under concurrency. Django
  raises an `IntegrityError` on the rare race, which we catch and convert to a
  409 response.
- The constraint is scoped to `status='booked'` (not a plain `unique_together`)
  so a cancelled appointment doesn't block that slot from being rebooked.
- The constraint also sets an explicit `violation_error_code` so application code
  can reliably detect a slot conflict by error code rather than by matching text
  in an exception message.

## API Endpoints

All routes are prefixed with `/api/`.

| Method  | Endpoint                                          | Description                                                                        |
| ------- | ------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `GET`   | `/api/doctors/{id}/availability/?date=YYYY-MM-DD` | Returns available 30-minute slots for a doctor on a given date.                    |
| `POST`  | `/api/appointments/`                              | Books a slot. Body: `doctor`, `patient`, `start_time`.                             |
| `PATCH` | `/api/appointments/{id}/cancel/`                  | Cancels an appointment. Body: `cancellation_reason`.                               |
| `PATCH` | `/api/appointments/{id}/reschedule/`              | Moves an appointment to a new slot. Body: `start_time`.                            |
| `GET`   | `/api/patients/{id}/appointments/`                | Returns a patient's upcoming (booked, not cancelled) appointments, sorted by date. |

Live base URL: `https://clinic-booking-api-7hxm.onrender.com/api/`

### Trade-offs considered

- **Single Django app vs. split apps** (`doctors`, `patients`, `appointments`):
  chose a single `bookings` app since the four models are tightly coupled and
  splitting now adds import overhead for no real benefit at this scale.
- **Slot granularity**: fixed at 30 minutes per the brief, generated dynamically
  from `WorkingHours` rather than pre-materialized as rows. This avoids a slot
  table that needs to be seeded and maintained per doctor per day.
- **Timezone handling**: assumed a single clinic timezone (Nairobi) rather
  than per-doctor or per-patient timezones, since the brief describes one physical
  clinic.
- **Overlap prevention**: relies on all appointments being created on fixed
  30-minute boundaries via the API's slot validation. The DB constraint checks
  exact `(doctor, start_time)` matches rather than time-range overlap. This is
  sufficient given the fixed-grid design but wouldn't catch misaligned appointments
  created outside the normal booking flow (e.g. direct admin edits).
- **"Upcoming" appointments (bonus endpoint)**: `GET /patients/{id}/appointments`
  only returns appointments with `status='booked'`, not cancelled ones, even if
  their `start_time` is in the future. A cancelled appointment isn't meaningfully
  "upcoming" from the patient's point of view.
- **1-hour booking buffer (bonus rule)**: enforced inside the shared
  `validate_slot_is_bookable` validator, so it automatically applies to both
  `POST /appointments` and `PATCH /appointments/{id}/reschedule`, not just fresh
  bookings. This wasn't explicitly required for reschedule by the brief, but
  keeping the rule in one place made it a natural side effect of a consistent
  design rather than something to special-case.

  Overlap prevention relies on all appointments being created on fixed 30-minute boundaries via the API's slot validation. The DB constraint checks for exact (doctor, start_time) matches rather than time-range overlap; this is sufficient given the fixed-grid design but wouldn't catch misaligned appointments created outside the normal booking flow (e.g. direct admin edits).

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
  container, runs migrations, and runs the Django test suite. `main` is protected,
  PRs must pass the `test` check before merging.

## AI Reflection

### 1. What did you use AI for across the four sections?

- System design: talking through model structure, trade-offs (single app vs.
  split apps, WorkingHours granularity, timezone handling), and the
  concurrency-safety approach for double-booking before writing any code.
- API implementation: generating first drafts of serializers, views, and
  validators, diagnosing test failures, automated code review (Sourcery).
- Deployment/CI/CD: diagnosing Render deploy failures,
  correcting GitHub Actions workflow, and
  debugging environment/encoding issues.
- Debugging: root-causing several test failures, including two that turned
  out to be genuine bugs in the application code, not the tests.

### 2. Give one example where an AI suggestion improved your work. What did you prompt it with?

Sourcery flagged that catching a bare `IntegrityError` in the booking view
made it impossible to distinguish a real slot conflict from any other
database error. I asked for a fix, and the result was narrowing the except
block to check for the specific constraint name before returning a 409.
Anything else now re-raises as a genuine 500 instead of being mislabeled as
"someone else booked this slot." Small change, but it directly protects the
correctness guarantee the whole booking design depends on.

### 3. Give one example where AI output was wrong or incomplete and how you caught it.

While adding the "no bookings within 1 hour" bonus rule, an AI-suggested
edit to `validate_slot_is_bookable` left an old, duplicate version of the
function further down in the same file. Python silently used the last
definition, so the buffer rule was defined but never actually enforced.
Every other test still passed, which made it easy to miss on a normal read
through. I found it because the dedicated buffer test kept returning
201 instead of 400. Reading through the traceback and then the file line by
line surfaced the second, shadowing definition. It was a good reminder that
a green test suite only proves what you've written tests for, and that
AI-assisted edits to a large file need a full re-read, not just a diff of
what changed.

### 4. Name two decisions you made without AI. Why did you trust your own judgment there?

- **Keeping the partial unique constraint as exact-match rather than
  range-overlap.** AI (via Sourcery) suggested the uniqueness check should
  handle overlapping time ranges, not just exact start-time matches. I kept
  the simpler exact-match version because every appointment in this system
  is created through the API on a fixed 30-minute grid. Overlap and exact
  match are equivalent given that constraint, and the added complexity
  wouldn't protect against anything that can actually happen through normal
  use. I documented this as a known limitation (direct DB/admin edits could
  bypass it) rather than building unused generality.
- **Choosing 400 over 409 for "already cancelled."** This wasn't something I
  asked AI to weigh in on. 409 is for state conflicts arising from
  concurrent requests (like double-booking), while "cancel an already
  cancelled appointment" is a client sending a request that doesn't match
  the resource's current state, which is more naturally a validation
  failure than a race condition. I trusted this distinction because it
  follows directly from what each status code is meant to communicate, not
  from a rule I looked up.

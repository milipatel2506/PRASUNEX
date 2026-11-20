# SAARTHI: AI Student Success Copilot

Team InnoTech (Mili Patel, Krishna Gajera) | Prasunex Innovathon 2026, Round 3 prototype

SAARTHI spots struggling students early, explains why, drafts a teacher action plan, and writes a
parent message in the parent's own language. The teacher approves everything. Outcomes are logged so
the school learns which actions work.

## Run it (Windows)

Double-click `run.bat`. It starts the app and opens http://127.0.0.1:8000.

Manual way:

```
cd backend
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

First time on a new machine: `python -m venv .venv` then `.venv\Scripts\python -m pip install -r requirements.txt`
inside `backend`. The built dashboard is already in `frontend/dist`. To rebuild it: `cd frontend`, `npm install`, `npm run build`.

Reset the demo data at any time: `cd backend` then `.venv\Scripts\python -m app.db`.

### Demo sign-ins (password for all: `demo123`)

| Username | Role | Can do |
|---|---|---|
| hetal | Faculty | classes 9A, 9B: weekly data, action plans, approve messages, track delivery |
| nikhil | Faculty | classes 8A, 8B |
| rina | Faculty | class 10A |
| principal | Principal | read-only view of every class, school overview, messages, AI audit log |
| admin | Admin | everything above, plus users, students, parent contacts and settings |

Sign in with the username and password form (the demo accounts on the sign-in page fill it in for you).

The demo password is for the prototype only. Passwords are stored hashed, logins are rate limited and tokens expire;
a real deployment would add single sign-on.

### Optional: real WhatsApp messages (Twilio sandbox, free)

1. Create a free Twilio account and open the WhatsApp sandbox page. From your phone, send the shown join code
   to the sandbox number on WhatsApp.
2. Set these environment variables before starting the app: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
   `TWILIO_WHATSAPP_FROM` (the sandbox number, +14155238886). Never put them in code or commit them.
3. Sign in as admin, open Students, edit one student's parent contact and enter your own phone number.
4. Sign in as faculty and approve a plan for that student. The message arrives on your phone, and the Messages page
   shows its status (use Refresh status). Admin, Settings shows whether WhatsApp is connected.

Placeholder demo numbers (+91 00000 ...) are never sent to, even when WhatsApp is connected.

### Optional: use a real AI model

Without any key, plans and messages come from the built-in template engine and everything works.
To use an AI language model, set the environment variable `ANTHROPIC_API_KEY` before starting. The model
receives only anonymised data (a reference like S-0042, grade, risk reasons, topics), never names or contact
details. Its output passes guardrails; on any failure the template engine takes over.

## What is implemented

- 150 synthetic students in 5 classes, 8 weeks of attendance, homework, five subjects and behaviour records
- Risk model: gradient boosting, with SHAP explanations grouped into plain-language reasons
- Teacher dashboard: ranked risk radar, flagged students only by default, trend charts, "why flagged" panel
- Action plan: three practical, editable actions plus topics to revisit
- Parent message in English, Gujarati or Hindi, shown as a phone-style preview, with a voice button
- Approve-before-send workflow; sending is simulated
- Outcome tracker and "which actions work best" chart
- Principal view: school overview and an AI audit log showing exactly what was sent to the AI
- Username and password sign-in with three roles (Faculty, Principal, Admin); faculty cannot open other classes
- Weekly data entry: faculty record attendance, homework, incidents and marks; risk scores update immediately
- Subjects: the five built-in subjects plus any subjects faculty add for their class (for example Computer Science); added subjects count towards the risk score and the weak-subject advice
- Past weeks: view every recorded week for a class, by week or by student, and a weekly record on each student's page
- Faculty: add or remove students in their own classes, and save each parent's WhatsApp number on the student page
- Admin: create and disable accounts, reset passwords, assign classes, add students, import a CSV, edit parent contacts
- Messages outbox: every parent message with parent, language and status (sent, delivered, read, failed), plus a
  phone view of what the parent sees
- Optional real WhatsApp delivery through the Twilio sandbox (off by default; see below)
- Safety checks: blocked phrases, contact details, wrong-script detection, length limit, template fallback

## Model results (synthetic held-out data)

AUC 0.95. When the model and a manual rule-of-thumb flag the same share of students (about 15%), the model reaches
84% precision and 72% recall, against 64% and 55% for the rule. Gender is not a model input; a fairness check on flag
rate and recall is shown on the Model and safety page. The labels come from the same simulation as the data, so these
numbers show that the pipeline works, not real-world accuracy.

## Tests

60 automated tests cover login and roles, access control, safe approval (no double-send, blocked phone numbers and
links, input limits), weekly data entry and re-scoring, admin user and student management, the messages lifecycle,
WhatsApp delivery (with a fake sender), upgrading an older database, the AI guardrails, the audit log and the model. Run them from `backend`:
`.venv\Scripts\python -m pytest -q`. They use a throwaway database and never touch the demo data.

## Known limitations (honest list)

- All data is synthetic. The model has not been validated on real school data.
- WhatsApp sending is simulated by default, so the seeded demo parents (placeholder numbers) never receive anything.
  Real delivery needs your own Twilio account (see below) and has not been tested end to end with a live phone
  by the authors of this prototype; it is covered by automated tests with a fake sender.
- Voice uses the browser's built-in text-to-speech. It needs a voice for the language on the device; Gujarati voices
  are not available everywhere.
- Gujarati and Hindi text were written for the template engine and should be reviewed by a native speaker before
  real use.
- The "which actions work best" chart mixes seeded last-term demo history with live outcomes.
- Login tokens live in server memory (8-hour expiry) and reset when the server restarts. Passwords are hashed, but
  the demo accounts share one password and there is no single sign-on.
- No real ERP connection yet.

## Future plans

Live PRASUNEX ERP integration through REST and webhooks, real WhatsApp delivery, more languages, a pilot in a
real school, monthly model retraining, and a parent-facing portal.

## Project layout

```
backend/app/datagen.py   synthetic data
backend/app/model.py     risk model + SHAP reasons
backend/app/content.py   action and message library (en, gu, hi)
backend/app/actions.py   AI layer, guardrails, template fallback
backend/app/db.py        SQLite storage and seeding
backend/app/main.py      API
frontend/src/            React dashboard
```

## 3-minute demo script

1. (20s) Open as Ms. Hetal Shah. "Teachers get a ranked list of who needs help today, not a wall of data."
2. (40s) Open a student. Show the trend lines and the "why flagged" reasons. "Every flag explains itself."
3. (40s) Create an action plan. "Three practical steps, editable by the teacher."
4. (40s) Switch the parent message to Gujarati, then Hindi. Play the voice. "Parents get a message they can read and hear in their own language."
5. (20s) Approve and send. "Nothing goes out without the teacher."
6. (20s) Sign in as the principal. Show the overview and open the AI audit log. "Full transparency, and no names ever reach the AI."

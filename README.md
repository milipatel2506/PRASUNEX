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

| User | Role | Sees |
|---|---|---|
| hetal | Teacher | classes 9A, 9B |
| nikhil | Teacher | classes 8A, 8B |
| rina | Teacher | class 10A |
| principal | Principal | whole school, AI audit log |

The demo password is for the prototype only. A real deployment would use hashed passwords and SSO.

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
- Role-based access: teachers cannot open other teachers' classes
- Safety checks: blocked phrases, contact details, wrong-script detection, length limit, template fallback

## Model results (synthetic held-out data)

AUC 0.95. Flagging the top 20% of students gives about 74% precision and 84% recall, against 64% and 55% for a
manual rule-of-thumb baseline. Gender is not a model input; a fairness check on flag rate and recall is shown on
the Model and safety page.

## Known limitations (honest list)

- All data is synthetic. The model has not been validated on real school data.
- WhatsApp and SMS sending is simulated. Nothing leaves the machine.
- Voice uses the browser's built-in text-to-speech. It needs a voice for the language on the device; Gujarati voices
  are not available everywhere.
- Gujarati and Hindi text were written for the template engine and should be reviewed by a native speaker before
  real use.
- The "which actions work best" chart mixes seeded last-term demo history with live outcomes.
- Login tokens live in server memory and reset when the server restarts.
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

# CiteWise Backend

Medical citation & research impact intelligence. FastAPI + SQLAlchemy + SQLite.
Determines **verified citations** (self/internal/external classification),
waterfall accounting, integrity flags, and tamper-evident reports with Merkle
roots. Built for the hackathon category **Best Use of AI**.

## Setup / Run / Test

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows; use source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
copy .env.example .env          # Windows; use cp on macOS/Linux
python scripts/seed_db.py       # one-command demo bootstrap (<30s)
uvicorn app.main:app --reload --port 8000
pytest -q                       # 19 tests, all must pass
```

API docs: http://localhost:8000/docs — Health: `GET /health`

## Layout

- `app/` — FastAPI app, routers (`/api/...`), services (pipeline stages), models, schemas
- `scripts/seed_db.py` — loads `data/demo/*.json`, runs the pipeline, prints UI links
- `data/demo/` — synthetic OpenAlex-style demo dataset + `ground_truth.json`
- `tests/` — pytest suite for PRD T1–T15

See `DECISIONS.md` for deviations from the PRD and `SETUP_GUIDE.md` for the
teammate UI setup walkthrough.

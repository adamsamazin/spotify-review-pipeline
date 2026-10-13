# Dashboard: database, backend, front end

Live: https://spotify-review-dashboard-adam-samazins-projects.vercel.app (public, no login).

```
saved pipeline outputs (runs/full, grading/, results/, evals/, cost/)
   │  dashboard/load_db.py        (offline bulk load, owner login)
   ▼
Neon Postgres (free tier, ~310 MB)  ──read-only role──▶  api/index.py (FastAPI, Vercel Python function)
                                                          │  /api/summary /api/ranking /api/topics /api/trend
                                                          │  /api/issues/{id} /api/memo /api/reviews/{id} /api/evals
                                                          ▼
                                                   public/index.html + app.js (static page, Chart.js)
```

No model calls happen in the dashboard; the AI recommendation was generated and validated by the pipeline.

## Set up from scratch

1. **Database:** create a Postgres database (we used Neon free tier, project `spotify-pipeline`). Copy its
   connection string into `.env` as `DATABASE_URL=` (owner login; never committed).
2. **Load data:** `.venv/Scripts/python -m dashboard.load_db runs/full` drops and recreates the tables
   (`run_info, reviews, issues, membership, ranking, topic_rollup, memo, claims, monthly, evals`) and bulk-loads them
   with COPY (about 30 s for 660,622 reviews). Summary counts are precomputed into `run_info`.
3. **Read-only login:** `.venv/Scripts/python -m dashboard.create_reader` creates `dashboard_reader` (SELECT only,
   read-only transactions) and writes `DASHBOARD_DATABASE_URL` to `.env`. Reloads re-grant read access automatically.
4. **Deploy:** create a Vercel project with root `dashboard/` (framework: Other). In project Settings, set
   environment variable `DATABASE_URL` = the `DASHBOARD_DATABASE_URL` value, and turn **Vercel Authentication** off
   under Deployment Protection so the page is public. Deploy (`vercel.json` routes `/api/*` to `api/index.py`).
5. **Verify:** `.venv/Scripts/python scripts/check_dashboard.py` compares the live API with `grading/ranking.csv`,
   `grading/claims.csv` and the record counts ([evals/results/dashboard_check.json](../evals/results/dashboard_check.json)).

Local preview: `.venv/Scripts/python -m uvicorn dashboard.dev_server:app --port 8765` (uses `DATABASE_URL`).

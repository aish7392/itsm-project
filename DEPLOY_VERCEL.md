# Deploying I-ITSM on Vercel

The app becomes **two Vercel projects from one GitHub repo**, plus a free **Neon PostgreSQL** database:

| Vercel project | Root directory | What it is | Example URL |
|---|---|---|---|
| Backend | `backend` | FastAPI API (runs as Vercel Functions) | `https://itsm-api-xxxx.vercel.app` |
| Frontend | `frontend` | React website (static) | `https://itsm-xxxx.vercel.app` |

Running locally or with Docker is unchanged.

## 1. Put the code on GitHub
From the project folder (in your WSL terminal):
```bash
git init
git add .
git commit -m "I-ITSM project"
```
Create an empty repository on github.com (no README), then run the two commands GitHub shows you:
```bash
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main        # if it complains, run: git branch -M main  first
```

## 2. Create the database
1. Sign in at vercel.com with your GitHub account.
2. **Storage → Create Database → Neon (Serverless Postgres) → free plan**, region **Singapore** (closest to India). Create it.

## 3. Deploy the backend
1. **Add New → Project →** import your repo.
2. **Root Directory: `backend`**. Framework should show **FastAPI** (pick it if not).
3. **Environment Variables:** add `JWT_SECRET` = any long random text
   (e.g. run `openssl rand -hex 32` in your terminal and paste the result).
4. Click **Deploy**. (If this first deploy errors, that's expected: there's no database yet.)
5. In this project: **Storage → Connect Database →** choose the Neon database from step 2. This adds `DATABASE_URL` automatically.
6. **Deployments → ⋯ on the latest → Redeploy**.
7. Open `https://<your-backend>.vercel.app/api/health`. You should see `{"status":"ok"}`.
   The very first request creates the tables and loads the demo data, so it can take 10-20 seconds.

## 4. Deploy the frontend
1. **Add New → Project →** import the **same** repo again.
2. **Root Directory: `frontend`**. Framework: **Vite**.
3. **Environment Variables:** `VITE_API_URL` = your backend URL from step 3, e.g. `https://itsm-api-xxxx.vercel.app` (no `/` at the end).
4. **Deploy**, then open the frontend URL and log in (password `Password123`).

## How it behaves on Vercel
- **SLA monitor:** Vercel doesn't keep a server running, and its free plan only allows daily scheduled jobs. So the SLA check (warnings, violations, escalation) runs automatically during normal use, at most every 30 seconds. An open browser keeps it ticking, because the page checks notifications every 15 s. Admins can also press **Run SLA check now**.
- **First load is slow:** after a period of no use, the first request takes a few seconds while Vercel and Neon wake up.
- **Email:** simulated (visible under Admin → Email outbox) unless you add `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SENDER` to the backend's environment variables.
- **Every `git push`** redeploys both projects automatically.
- **Reset demo data:** in Neon (Vercel → Storage → your database → Open in Neon → SQL Editor) run
  `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` then open `/api/health` on the backend again.

## Security note
The demo password is in this README. If the repo or the site is public, log in as admin after deploying and change the passwords (Users & technicians), or keep the repo private and give your instructors access.

## Optional settings (backend environment variables)
| Variable | Default on Vercel | Meaning |
|---|---|---|
| `CORS_ORIGIN_REGEX` | `https://.*\.vercel\.app` | Which frontends may call the API. Set it to your exact frontend URL to lock it down. |
| `SLA_MONITOR_INTERVAL` | `30` | Seconds between SLA checks |
| `AUTO_SEED` | `true` | Load demo data into an empty database |

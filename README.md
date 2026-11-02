# Tech / Daily Newsletter

Tech / Daily is a scheduled technology-news newsletter. The backend is a
FastAPI service backed by Firestore; the frontend is a static HTML/CSS/JavaScript
site that collects newsletter preferences and calls the API.

## Project layout

```text
backend/
  api.py              FastAPI application and subscription endpoints
  firebase_db.py      Firestore access helpers
  news_fetch.py       RSS feed retrieval
  scheduler.py        Delivery scheduler
  send_email.py       SMTP newsletter and confirmation email delivery
  timezone_utils.py   IANA timezone loading
  requirements.txt    Python dependencies
frontend/
  index.html          Subscription page
  confirm.html        Email confirmation page
  script.js           API integration
  styles.css          Frontend styling
```

## Security requirements

- Never commit `.env`, private keys, service-account JSON files, SMTP
  passwords, or other credentials.
- Rotate any credential that has ever been exposed outside the secret manager.
- Store `FIREBASE_SERVICE_ACCOUNT_JSON` and `NEWS_EMAIL_APP_PASSWORD` as
  deployment secrets, not source files.
- Set `ALLOWED_ORIGINS` to the exact production frontend origin. Do not use
  `*`.
- Use HTTPS for both the frontend and API in production.
- Keep `ENABLE_SCHEDULER=true` only when exactly one backend process is running.
  With multiple Render instances or workers, run one separate scheduler process
  and set it to `false` on the web service.

## Local development

1. Install Python 3.11 or newer.
2. Create and activate a virtual environment.
3. Install backend dependencies:

   ```powershell
   python -m pip install -r backend\requirements.txt
   ```

4. Create `backend\.env` from `backend\.env.example` and fill it with local
   credentials. Do not paste credentials into this README or commit the file.
5. Start the API:

   ```powershell
   uvicorn api:app --app-dir backend --reload --host 127.0.0.1 --port 8000
   ```

6. Serve the frontend from its directory:

   ```powershell
   python -m http.server 5500 --directory frontend
   ```

7. Open <http://localhost:5500>. The frontend uses
   `http://localhost:8000` automatically when served locally and the
   production API URL when deployed.

## Configuration

Use `backend\.env.example` as the configuration reference.

Important values:

| Variable | Purpose |
| --- | --- |
| `NEWS_EMAIL_ADDRESS` | SMTP sender address |
| `NEWS_EMAIL_APP_PASSWORD` | SMTP app password stored as a secret |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Firebase Admin credentials stored as a secret |
| `ALLOWED_ORIGINS` | Comma-separated exact browser origins allowed by CORS; `FRONTEND_URL` is used as a fallback |
| `FRONTEND_URL` | Public frontend URL used in confirmation links |
| `ENABLE_SCHEDULER` | Starts the scheduler in the API process |
| `RSS_FEEDS` | Comma-separated RSS feed URLs |

`NEWS_EMAIL_RECIPIENT` is only for the optional manual test command. It may
remain empty in normal production operation because confirmed subscribers are
loaded from Firestore.

## API endpoints

- `GET /api/health` — liveness check.
- `POST /api/register` — creates a pending subscription and sends a
  confirmation email.
- `GET /api/confirm?token=...` — activates a pending subscription using a
  single-use, time-limited token.

## Deploying the backend to Render

### 1. Create the Render service

1. Push this project to a Git provider.
2. In Render, choose **New → Web Service** and select the repository.
3. Use these settings:

   - **Root Directory:** `backend`
   - **Runtime:** `Python`
   - **Build Command:**

     ```text
     pip install -r requirements.txt
     ```

   - **Start Command:**

     ```text
     uvicorn api:app --host 0.0.0.0 --port $PORT
     ```

4. Choose a production instance appropriate for the expected traffic.

### 2. Add Render environment variables

In the service's **Environment → Environment Variables** section, add:

```text
NEWS_EMAIL_ADDRESS=<SMTP sender address>
NEWS_EMAIL_APP_PASSWORD=<SMTP app password>
FIREBASE_SERVICE_ACCOUNT_JSON=<complete service-account JSON as one value>
ALLOWED_ORIGINS=https://<your-frontend-domain>
FRONTEND_URL=https://<your-frontend-domain>
ENABLE_SCHEDULER=true
ARTICLES_PER_FEED=5
NEWS_REQUEST_TIMEOUT=15
SCHEDULER_CHECK_INTERVAL=30
SCHEDULER_DUE_WINDOW_MINUTES=10
DELIVERY_RETRY_SECONDS=300
RSS_FEEDS=https://feeds.arstechnica.com/arstechnica/index,https://feeds.bbci.co.uk/news/technology/rss.xml,https://www.theverge.com/rss/index.xml,https://www.wired.com/feed/rss,https://techcrunch.com/feed/
```

Do not add real values to `render.yaml`, source code, screenshots, issue
descriptions, or documentation.

### 3. Configure the health check

Set the Render health check path to:

```text
/api/health
```

After deployment, verify:

```text
https://<your-render-service>.onrender.com/api/health
```

Expected response:

```json
{"status":"ok"}
```

### 4. Deploy the frontend

The frontend is static and can be deployed to Render Static Site, Netlify,
Vercel, or another static host.

For a Render Static Site:

1. Choose **New → Static Site**.
2. Select the same repository.
3. Set the publish directory to `frontend`.
4. Update the API URL in `frontend/script.js` from the local default to the
   deployed API URL, or inject a deployment-specific frontend configuration.
5. Set the deployed frontend origin in the backend's `ALLOWED_ORIGINS`.
6. Set the same public frontend URL in `FRONTEND_URL`.

The frontend automatically uses the local API URL on localhost and the
production API URL on a deployed site. After deployment, verify that
`FRONTEND_URL` points to the deployed frontend so confirmation links activate
the subscription.

### 5. Scheduler deployment choices

For one Render web service with one process:

```text
ENABLE_SCHEDULER=true
```

For multiple web instances/workers, set:

```text
ENABLE_SCHEDULER=false
```

and run exactly one separate scheduler service/process with:

```text
python scheduler.py
```

Never run the scheduler in multiple replicas unless delivery coordination has
been redesigned for that deployment topology.

## Operational checks

- Confirm `/api/health` returns HTTP 200 after each deployment.
- Submit a test subscription with an email address you control.
- Confirm the email link activates the subscription only once.
- Verify a scheduled delivery in a controlled test window.
- Monitor Render logs and Firebase delivery records.
- Rotate SMTP and Firebase credentials periodically and immediately after any
  suspected exposure.

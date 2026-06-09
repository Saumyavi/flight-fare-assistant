# Flight Fare Bot

WhatsApp flight price tracker. Send a route + budget, get alerted when fares drop.

**Stack:** FastAPI · SQLModel · Supabase (Postgres) · Duffel (flight search) · Twilio WhatsApp · OpenAI

---

## Project layout

```
mvp/
├── api/
│   └── index.py           Vercel entrypoint
├── app/
│   ├── main.py            FastAPI app, webhook, cron, debug endpoints
│   ├── config.py          Settings (reads from .env / Vercel env vars)
│   ├── db.py              SQLModel models: User, Watch, PriceSample
│   ├── airports.py        City name → IATA code lookup
│   ├── llm_parser.py      OpenAI structured-output message parser
│   ├── flights_client.py  Duffel flight search wrapper
│   ├── whatsapp.py        Twilio WhatsApp sender
│   ├── handlers.py        Intent → DB → reply string
│   └── poll.py            Price-poll logic (called by /cron/poll)
├── vercel.json            Vercel build + cron config
├── requirements.txt
├── .env.example
└── .env                   (git-ignored — your local secrets)
```

---

## Local development

### 1. Prerequisites

- Python 3.11+
- A [Supabase](https://supabase.com) project (free tier)
- A [Duffel](https://duffel.com) account (test key)
- An [OpenAI](https://platform.openai.com) API key (or any OpenAI-compatible endpoint)
- A [Twilio](https://twilio.com) account with WhatsApp Sandbox enabled

### 2. Install and configure

```powershell
cd mvp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Fill in .env with your keys
```

### 3. Run

```powershell
uvicorn app.main:app --reload --port 8000
```

Health check: http://localhost:8000/health → `{"ok": true, "db": true}`

### 4. Test without Twilio

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/debug/simulate `
  -Headers @{ "X-Debug-Secret" = "mysecret"; "Content-Type" = "application/json" } `
  -Body '{"from": "whatsapp:+911234567890", "body": "DEL to GOI under 4000 5-15 July"}'
```

Example commands to try:
- `Mumbai to Dubai return 1-10 Aug budget 18k`
- `LIST`
- `PAUSE 1` / `RESUME 1` / `STOP 1` / `STOP ALL`
- `HELP`

### 5. Trigger a price poll manually

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/cron/poll `
  -Headers @{ "Content-Type" = "application/json" }
```

---

## Deploy to Vercel

### 1. Push to GitHub

Push the `mvp/` folder contents to a GitHub repo.

### 2. Import in Vercel

1. Go to [vercel.com](https://vercel.com) → New Project → Import your repo
2. Set **Root Directory** to `mvp` (or wherever `vercel.json` lives)
3. Framework Preset: **Other**

### 3. Set environment variables

In Vercel → Project → Settings → Environment Variables, add all keys from `.env.example`:

| Variable | Notes |
|---|---|
| `DATABASE_URL` | Supabase Session Pooler URI (`postgresql+psycopg://...`) |
| `TWILIO_ACCOUNT_SID` | From Twilio Console |
| `TWILIO_AUTH_TOKEN` | From Twilio Console |
| `TWILIO_WHATSAPP_FROM` | `whatsapp:+14155238886` for sandbox |
| `WEBHOOK_URL` | `https://your-app.vercel.app/twilio/whatsapp` |
| `VALIDATE_TWILIO_SIGNATURE` | `true` in production |
| `DUFFEL_API_KEY` | `duffel_live_...` for production |
| `OPENAI_API_KEY` | Your key |
| `OPENAI_MODEL` | `gpt-4o-mini` |
| `CRON_SECRET` | Any random secret — Vercel sends this with cron requests |
| `DEBUG_SECRET` | Leave **empty** in production |

### 4. Set Twilio webhook

After deploy, go to Twilio Console → Messaging → WhatsApp Sandbox settings and set:

**"When a message comes in"** → `https://your-app.vercel.app/twilio/whatsapp` (POST)

### 5. Cron schedule

`vercel.json` configures a daily poll at 02:00 UTC (`0 2 * * *`).
Vercel Hobby plan supports one cron per day. Upgrade to Pro for more frequent polling.

---

## How it works

1. User sends WhatsApp message → Twilio POSTs to `/twilio/whatsapp`
2. OpenAI parses the message into structured intent (route, dates, budget)
3. Watch is saved to Supabase
4. Vercel Cron calls `/cron/poll` daily → Duffel is queried for each active watch
5. If `price ≤ max_price`, a WhatsApp alert is sent via Twilio with a Skyscanner booking link

---

## Known limitations

- Duffel test key returns synthetic fares — switch to `duffel_live_...` for real prices
- IATA resolver is a static dict; unknown cities fail gracefully with a hint
- Vercel Hobby cron fires once per day; upgrade to Pro for every-2-hour polling
- Twilio sandbox requires each user to opt in by texting `join <code>` first

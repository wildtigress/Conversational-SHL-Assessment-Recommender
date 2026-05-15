# SHL Assessment Recommender — Complete Windows 11 Setup Guide

## Your Project Files (already written for you)

```
C:\shl-recommender\
├── app\
│   ├── __init__.py         ← package marker
│   ├── main.py             ← FastAPI server (GET /health, POST /chat)
│   ├── agent.py            ← Claude-powered conversation logic
│   ├── retrieval.py        ← FAISS vector search over catalog
│   ├── scraper.py          ← HTTP scraper (try this first)
│   └── scraper_playwright.py ← Browser scraper (if HTTP gets blocked)
├── catalog.json            ← Pre-built catalog (90+ assessments)
├── test_agent.py           ← Test suite (run before deploying)
├── requirements.txt        ← All dependencies
├── render.yaml             ← Render.com deployment config
└── .env                    ← Your API key (NEVER commit this)
```

---

## STEP 1: Install Python

1. Go to https://www.python.org/downloads/
2. Download Python 3.12.x (the big yellow button)
3. Run the installer
4. **CRITICAL**: Tick "Add Python to PATH" at the bottom ← don't miss this
5. Click "Install Now"
6. Open VS Code (Ctrl+Space to open terminal inside VS Code)
7. Verify:
   ```
   python --version
   pip --version
   ```
   Both should print version numbers. If "not recognized" — restart VS Code.

---

## STEP 2: Create & Open Project Folder

In VS Code terminal:
```
mkdir C:\shl-recommender
cd C:\shl-recommender
```

Then: File → Open Folder → select `C:\shl-recommender`

---

## STEP 3: Copy All Files

Copy ALL files from this zip into `C:\shl-recommender\`
Make sure you preserve the folder structure (app\ subfolder).

---

## STEP 4: Create Virtual Environment

```
python -m venv venv
venv\Scripts\activate
```

You'll see `(venv)` at the start of your terminal line.
**Always run the activate command when you open VS Code for this project.**

---

## STEP 5: Install Dependencies

```
pip install -r requirements.txt
```

This installs FastAPI, Claude SDK, sentence-transformers, FAISS, etc.
Takes 3–10 minutes. Let it finish completely.

---

## STEP 6: Set Your API Key

1. Get free Groq key → console.groq.com 
create account → API Keys → Create key
2. create account → API Keys → Create key
3. Open `.env` in VS Code and edit it:
   ```
   GROQ_API_KEY=sk-ant-YOUR_KEY_HERE
   ```
   Save the file.

---

## STEP 7: (Optional) Run Full Scraper

The project already includes `catalog.json` with 90+ assessments.
To get the COMPLETE catalog (all ~384 items), run the Playwright scraper:

```
pip install playwright
playwright install chromium
python app\scraper_playwright.py
```

This opens a browser, visits all 32 catalog pages, and updates catalog.json.
Takes about 15–20 minutes. Watch it work!

---

## STEP 8: Start the Server

```
python -m uvicorn app.main:app --reload --port 8000
```

You should see output like:
```
[startup] Initialising retrieval index…
[retrieval] Loading embedding model…
[retrieval] Embedding 90 assessments…
[retrieval] Index built: 90 vectors, dim=384
[startup] Ready.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

The server is running! Leave this terminal open.

---

## STEP 9: Test Locally

Open a NEW terminal (keep the server running in the other one).

**Test 1 — Health check:**
```
curl http://localhost:8000/health
```
Expected: `{"status":"ok"}`

**Test 2 — Vague query (should clarify, not recommend):**
```
curl -X POST http://localhost:8000/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"messages\": [{\"role\": \"user\", \"content\": \"I need an assessment\"}]}"
```
Expected: reply asking for more info, empty recommendations array.

**Test 3 — Clear role (should recommend):**
```
curl -X POST http://localhost:8000/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"messages\": [{\"role\": \"user\", \"content\": \"I am hiring a mid-level Python developer with 4 years of experience\"}]}"
```
Expected: reply with 1–10 Python/tech assessment recommendations.

**Run all 6 automated tests:**
```
python test_agent.py
```

---

## STEP 10: Deploy to Render.com (Free)

### 10A. Push to GitHub

1. Go to https://github.com → Sign Up (free) → New Repository
2. Name it `shl-recommender`, make it **Private**, click Create
3. Back in VS Code terminal:
   ```
   git init
   git add .
   git commit -m "Initial SHL recommender"
   git remote add origin https://github.com/YOUR_USERNAME/shl-recommender.git
   git push -u origin main
   ```
   (VS Code will ask you to log into GitHub)

### 10B. Create .gitignore (don't upload your API key!)

Create a file named `.gitignore` with:
```
.env
venv/
__pycache__/
*.pyc
.DS_Store
```
Then:
```
git add .gitignore
git commit -m "Add gitignore"
git push
```

### 10C. Deploy on Render

1. Go to https://render.com → Sign Up (free, use GitHub login)
2. New → Web Service → Connect your GitHub repo
3. Settings:
   - **Name**: shl-recommender
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free
4. Click "Advanced" → "Add Environment Variable":
   - Key: `ANTHROPIC_API_KEY`
   - Value: your key from step 6
5. Click "Create Web Service"

Wait 3–5 minutes for the build to complete.

### 10D. Get Your Public URL

Render gives you a URL like:
```
https://shl-recommender-xxxx.onrender.com
```

**Test your deployed service:**
```
curl https://shl-recommender-xxxx.onrender.com/health
```

**Important**: Render free tier sleeps after 15 minutes of inactivity.
The first /health call after sleeping takes up to 2 minutes to wake up.
The evaluator allows 2 minutes for this — you're fine.

---

## STEP 11: Run Your Test Suite One More Time

Point tests at your live URL:
```
curl -X POST https://shl-recommender-xxxx.onrender.com/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"messages\": [{\"role\": \"user\", \"content\": \"Hiring a Java developer with stakeholder management needs, 4 years experience\"}]}"
```

---

## Common Errors & Fixes

| Error | Fix |
|-------|-----|
| `'python' is not recognized` | Reinstall Python with "Add to PATH" checked |
| `venv\Scripts\activate` fails | Run in PowerShell as admin, or use CMD not PowerShell |
| `ModuleNotFoundError` | Make sure venv is active (you see `(venv)`) and re-run `pip install -r requirements.txt` |
| `ANTHROPIC_API_KEY not set` | Check .env file is saved and has no extra spaces |
| `catalog.json not found` | The file must be at `C:\shl-recommender\catalog.json` (not inside app\) |
| Render build fails | Check the build logs on Render dashboard for the specific error |
| `/health` times out on Render | Wait 2 minutes — free tier has cold starts |

---

## What the Evaluator Tests

1. **Schema compliance** — every response must have `reply`, `recommendations`, `end_of_conversation`
2. **Catalog-only URLs** — no hallucinated SHL URLs
3. **Turn cap** — agent must not exceed 8 turns
4. **Vague query handling** — agent must clarify before recommending on turn 1
5. **Refinement** — updating shortlist when user changes requirements
6. **Off-topic refusal** — declining non-assessment questions
7. **Hallucination rate** — agent must not invent assessment details

---

## Submission Checklist

- [ ] `/health` returns `{"status": "ok"}` publicly
- [ ] `/chat` responds within 30 seconds
- [ ] Responses always have the exact 3-field schema
- [ ] All URLs start with `https://www.shl.com/products/product-catalog/view/`
- [ ] Agent clarifies vague queries (doesn't recommend on turn 1)
- [ ] Agent recommends when role is clear
- [ ] 2-page approach document written
- [ ] Submitted via the Qualtrics form before 17 May 2026 6PM

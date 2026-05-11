# Sermon Library
### A searchable archive of William Hawley's 40 years of preaching

Live app: https://[your-github-username].github.io/sermon-library

---

## What This Is

A full-stack web application that:
- Stores all sermon data in Firebase Firestore (cloud database)
- Hosts the front-end on GitHub Pages (free, permanent URL)
- Analyzes sermons with Claude AI during ingestion
- Provides runtime AI to ask questions about the collection
- Works on any device, synced for the whole family

---

## Architecture

```
OneDrive (sermon files)
    ↓  ingest.py (runs once locally)
Firebase Firestore (database)
    ↓  React app (reads data)
GitHub Pages (public URL)
    ↓  Anthropic API (runtime AI)
Family browser
```

---

## Initial Setup (One Time)

### Step 1 — Clone the repo

```bash
git clone https://github.com/[your-username]/sermon-library.git
cd sermon-library
npm install
```

### Step 2 — Firebase setup

1. Go to https://console.firebase.google.com
2. Open your `sermon-library-89f46` project
3. **Firestore:** Build → Firestore Database → Create database (test mode)
4. **Deploy security rules:**
   ```bash
   npm install -g firebase-tools
   firebase login
   firebase use sermon-library-89f46
   firebase deploy --only firestore:rules,firestore:indexes
   ```

### Step 3 — Environment variables

```bash
cp .env.example .env.local
```

Edit `.env.local`:
```
REACT_APP_ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
```

### Step 4 — Run locally to verify

```bash
npm start
```

Opens at http://localhost:3000 — will show "No Collections Yet" until you run ingestion.

### Step 5 — GitHub Pages deployment

1. Push to GitHub:
   ```bash
   git add .
   git commit -m "Initial commit"
   git push origin main
   ```

2. GitHub repo → **Settings → Pages → Source: GitHub Actions**

3. GitHub repo → **Settings → Secrets → Actions → New repository secret**
   - Name: `REACT_APP_ANTHROPIC_API_KEY`
   - Value: your Anthropic API key

4. GitHub repo → **Actions → Deploy to GitHub Pages → Run workflow**

Your app is live at: `https://[username].github.io/sermon-library`

---

## Running the Ingestion Script

The ingestion script runs **locally on your computer**, reads from OneDrive, and writes to Firestore. You only need to run it when adding new sermons.

### Setup

```bash
cd scripts
pip install anthropic firebase-admin requests msal python-docx PyPDF2 tqdm mammoth
```

Copy your Firebase service account JSON file to:
```
scripts/firebase-credentials.json
```

Set your Anthropic API key:
```bash
# Windows
set ANTHROPIC_API_KEY=sk-ant-api03-your-key-here

# Mac/Linux
export ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
```

### Run

```bash
# Full ingestion (William Hawley collection)
python ingest.py

# Resume after interruption (skips already-processed files)
python ingest.py --resume

# Add a different pastor's collection
python ingest.py --pastor "Billy Graham" --folder "Graham/Sermons" --desc "Billy Graham Crusade Sermons"

# Just recompute stats (fast)
python ingest.py --stats-only
```

### What it does

1. Logs into your Microsoft account (device code flow — browser-based, no password stored)
2. Crawls the OneDrive folder recursively
3. Downloads each sermon file
4. Extracts text (.doc, .docx, .pdf all supported)
5. Sends to Claude AI for: title, summary, theme, structure, Bible verses, keywords, cleaned text
6. Writes everything to Firestore
7. Computes stats document for fast UI rendering

**Time estimate:** ~6-10 seconds per sermon. 1,040 sermons ≈ 2-3 hours.
**Cost estimate:** ~$5-15 in Anthropic API credits for the full collection.
**Resume:** If it stops, run `python ingest.py --resume` — it skips already-done files.

---

## Folder Structure

```
sermon-library/
├── public/
│   └── index.html              HTML shell
├── src/
│   ├── lib/
│   │   ├── firebase.js         Firestore queries
│   │   └── ai.js               Anthropic runtime AI
│   ├── components/
│   │   ├── Header.js           Top navigation
│   │   ├── Sidebar.js          Filter panel
│   │   └── SermonCard.js       Sermon card (grid + list)
│   ├── pages/
│   │   ├── LibraryPage.js      Main sermon browser
│   │   ├── SermonPage.js       Individual sermon + print
│   │   ├── AskPage.js          AI conversation interface
│   │   └── StatsPage.js        Collection insights
│   ├── styles/
│   │   └── globals.css         Design tokens + typography
│   ├── App.js                  Router + pastor state
│   └── index.js                React entry point
├── scripts/
│   └── ingest.py               Sermon ingestion pipeline
├── .github/
│   └── workflows/
│       └── deploy.yml          Auto-deploy to GitHub Pages
├── firestore.rules             Database security rules
├── firestore.indexes.json      Query indexes
├── .env.example                Environment variable template
├── .gitignore                  Keeps secrets off GitHub
└── package.json
```

---

## Adding More Sermons Later

If you find another folder of sermons:

```bash
python ingest.py --pastor "William Hawley" --folder "Dad's Files/NewFolder" --resume
```

The `--resume` flag ensures already-processed sermons are skipped.

---

## Firestore Data Model

```
/pastors/{id}
  name, description, created_at

/sermons/{id}
  pastor_id, filename, folder, web_url
  author, is_primary_pastor
  date, series_name, series_number
  title, title_lower, summary, main_theme
  structure { has_introduction, main_points, has_conclusion }
  keywords[], bible_books[], scripture_references[]
  full_text_raw, full_text_clean
  word_count, estimated_length
  extraction_quality, processing_status
  processed_at, file_modified

/stats/{pastor_id}
  total_sermons, william_hawley_count, other_preachers_count
  top_keywords[], top_bible_books[]
  computed_at
```

---

## Cost Summary (Annual Estimate)

| Service | Cost |
|---|---|
| Firebase Firestore (free tier) | $0 |
| GitHub Pages | $0 |
| Anthropic API (ingestion, one-time) | ~$10-20 |
| Anthropic API (runtime AI, family use) | ~$1-5/year |
| **Total** | **~$10-20 first year, <$5/year after** |

---

## Troubleshooting

**App shows "No Collections Yet"**
→ Run the ingestion script first

**Microsoft login fails**
→ Make sure you're logging in with the account that has OneDrive access

**Ingestion stops mid-way**
→ Run `python ingest.py --resume` — it picks up where it left off

**"Ask" feature not working**
→ Check that `REACT_APP_ANTHROPIC_API_KEY` is set in `.env.local` and in GitHub Secrets

**Firebase permission denied**
→ Deploy the security rules: `firebase deploy --only firestore:rules`

**App 404 on GitHub Pages**
→ Make sure Pages source is set to "GitHub Actions" not "Deploy from branch"

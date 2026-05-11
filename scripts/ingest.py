#!/usr/bin/env python3
"""
ingest.py — Sermon Library Ingestion Script
============================================
Reads sermon files from OneDrive, analyzes each with Claude AI,
and writes structured data to Firebase Firestore.

Features:
  - Multi-pastor support (point at any folder)
  - Incremental processing (skips already-done files)
  - Auto token refresh for long runs
  - Graceful error handling with retry logic
  - Full text extraction (.doc, .docx, .pdf)
  - AI analysis: summary, structure, verses, keywords, cleaned text
  - Pre-computes stats document for fast UI rendering
  - Configurable via command line or config file

Usage:
  python ingest.py
  python ingest.py --pastor "Billy Graham" --folder "Graham Sermons"
  python ingest.py --resume          (skip already-processed files)
  python ingest.py --reprocess-failed (retry files that errored)
  python ingest.py --stats-only       (just recompute stats)

Requirements:
  pip install anthropic firebase-admin requests msal python-docx PyPDF2 tqdm mammoth
"""

import os, sys, json, re, time, io, logging, argparse, hashlib
from pathlib import Path
from datetime import datetime
from collections import Counter

# ── Dependency check & install ────────────────────────────────────────────────
def ensure_deps():
    import subprocess
    pkgs = [
        ("anthropic",       "anthropic"),
        ("firebase-admin",  "firebase_admin"),
        ("requests",        "requests"),
        ("msal",            "msal"),
        ("python-docx",     "docx"),
        ("PyPDF2",          "PyPDF2"),
        ("tqdm",            "tqdm"),
        ("mammoth",         "mammoth"),
    ]
    for pip_name, import_name in pkgs:
        try:
            __import__(import_name)
        except ImportError:
            print(f"Installing {pip_name}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name, "-q"])

ensure_deps()

import anthropic
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import msal
from tqdm import tqdm
import mammoth
import PyPDF2

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

# ── Paths to credential files ─────────────────────────────────────────────────
# Put your Firebase service account JSON file path here
FIREBASE_CREDENTIALS_PATH = "firebase-credentials.json"

# Your Anthropic API key
# Best practice: set as environment variable ANTHROPIC_API_KEY
# Or paste here (do NOT commit this file to GitHub with a key in it)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ── Microsoft Graph (OneDrive) ─────────────────────────────────────────────────
MS_CLIENT_ID  = "14d82eec-204b-4c2f-b7e8-296a70dab67e"  # Graph Explorer
MS_AUTHORITY  = "https://login.microsoftonline.com/common"
MS_SCOPES     = ["Files.Read", "Files.Read.All"]

# ── Default ingestion target ───────────────────────────────────────────────────
DEFAULT_PASTOR_NAME   = "William Hawley"
DEFAULT_PASTOR_DESC   = "40 years of faithful preaching"
DEFAULT_ONEDRIVE_PATH = "Dad's Files/Sermons1"

# ── Folder classification ──────────────────────────────────────────────────────
# Folders where files belong to OTHER preachers (not the primary pastor)
# Key = folder name (lowercase), Value = author name override (None = skip folder)
OTHER_PREACHER_FOLDERS = {
    "billy sunday":    "Billy Sunday",
    "chapman":         "J. Wilbur Chapman",
    "hughes":          "Hughes",
    "johnston":        "Johnston",
    "illustrations":   None,   # Skip entirely
}

# Folders that ARE the primary pastor (organized by church/location/series)
PRIMARY_PASTOR_FOLDERS = {
    "franklin sermons",
    "fbis - cloud",
    "browning",
}

# ── Processing ─────────────────────────────────────────────────────────────────
BATCH_SIZE        = 50    # Write to Firestore every N sermons
MAX_TEXT_FOR_AI   = 8000  # Characters sent to Claude per sermon
REQUEST_DELAY     = 0.25  # Seconds between API calls (be polite)
MAX_RETRIES       = 3

# ══════════════════════════════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════════════════════════════

log = logging.getLogger("ingest")
log.setLevel(logging.DEBUG)
fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", "%Y-%m-%d %H:%M:%S")
fh  = logging.FileHandler("ingest.log", encoding="utf-8")
fh.setFormatter(fmt)
ch  = logging.StreamHandler(sys.stdout)
ch.setFormatter(fmt)
ch.setLevel(logging.INFO)
log.addHandler(fh)
log.addHandler(ch)


# ══════════════════════════════════════════════════════════════════════════════
#  FIREBASE
# ══════════════════════════════════════════════════════════════════════════════

def init_firebase():
    if not os.path.exists(FIREBASE_CREDENTIALS_PATH):
        log.error(f"Firebase credentials not found at: {FIREBASE_CREDENTIALS_PATH}")
        log.error("Download your service account key from Firebase Console → Project Settings → Service Accounts")
        sys.exit(1)
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)
    return firestore.client()


# ══════════════════════════════════════════════════════════════════════════════
#  MICROSOFT GRAPH CLIENT
# ══════════════════════════════════════════════════════════════════════════════

class GraphClient:
    BASE = "https://graph.microsoft.com/v1.0"

    def __init__(self):
        self._app   = msal.PublicClientApplication(MS_CLIENT_ID, authority=MS_AUTHORITY)
        self._token = None
        self._authenticate()

    def _authenticate(self):
        # Try cached token first
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(MS_SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._token = result["access_token"]
                log.info("Using cached Microsoft token")
                return

        # Device code flow
        flow = self._app.initiate_device_flow(scopes=MS_SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Device flow failed: {flow.get('error_description')}")

        print("\n" + "="*60)
        print("MICROSOFT LOGIN REQUIRED")
        print("="*60)
        print(f"\n1. Open: {flow['verification_uri']}")
        print(f"2. Enter code: {flow['user_code']}")
        print("\nWaiting for login...\n")

        result = self._app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(f"Auth failed: {result.get('error_description')}")

        self._token = result["access_token"]
        log.info("Microsoft login successful")

    def _refresh_if_needed(self, status_code):
        if status_code != 401:
            return False
        log.warning("Token expired, refreshing...")
        accounts = self._app.get_accounts()
        if not accounts:
            return False
        result = self._app.acquire_token_silent(MS_SCOPES, account=accounts[0])
        if result and "access_token" in result:
            self._token = result["access_token"]
            log.info("Token refreshed")
            return True
        return False

    @property
    def _headers(self):
        return {"Authorization": f"Bearer {self._token}"}

    def get_json(self, path):
        for attempt in range(2):
            r = requests.get(f"{self.BASE}{path}", headers=self._headers)
            if r.status_code == 401 and attempt == 0 and self._refresh_if_needed(401):
                continue
            r.raise_for_status()
            return r.json()

    def get_bytes(self, url):
        for attempt in range(2):
            r = requests.get(url, headers=self._headers)
            if r.status_code == 401 and attempt == 0 and self._refresh_if_needed(401):
                continue
            r.raise_for_status()
            return r.content

    def find_folder_by_path(self, path):
        """Find a OneDrive folder by its full path."""
        encoded = requests.utils.quote(path, safe="/")
        try:
            item = self.get_json(f"/me/drive/root:/{encoded}")
            if item.get("folder"):
                return item
        except requests.HTTPError as e:
            log.error(f"Folder not found: {path} ({e})")
        return None

    def list_children(self, item_id):
        """List all children of a folder (handles pagination)."""
        items = []
        url   = f"{self.BASE}/me/drive/items/{item_id}/children"
        while url:
            for attempt in range(2):
                r = requests.get(url, headers=self._headers)
                if r.status_code == 401 and attempt == 0 and self._refresh_if_needed(401):
                    continue
                r.raise_for_status()
                data = r.json()
                break
            items.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
        return items

    def download(self, item_id):
        """Download a file by item ID."""
        meta = self.get_json(f"/me/drive/items/{item_id}")
        url  = meta.get("@microsoft.graph.downloadUrl")
        if not url:
            raise ValueError(f"No download URL for {item_id}")
        return self.get_bytes(url)


# ══════════════════════════════════════════════════════════════════════════════
#  TEXT EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def extract_text(filename: str, content: bytes) -> tuple[str, str]:
    """
    Extract text from a file.
    Returns (text, quality) where quality is 'high' | 'medium' | 'low'
    """
    ext = Path(filename).suffix.lower()

    try:
        if ext == ".pdf":
            return _extract_pdf(content)
        elif ext == ".docx":
            return _extract_docx(content)
        elif ext == ".doc":
            return _extract_doc(content)
        else:
            text = content.decode("utf-8", errors="ignore")
            return text, "medium"
    except Exception as e:
        log.warning(f"Extraction failed for {filename}: {e}")
        return "", "low"


def _extract_pdf(content: bytes) -> tuple[str, str]:
    reader = PyPDF2.PdfReader(io.BytesIO(content))
    pages  = [p.extract_text() or "" for p in reader.pages]
    text   = "\n\n".join(p for p in pages if p.strip())
    quality = "high" if len(text) > 200 else "low"
    return text, quality


def _extract_docx(content: bytes) -> tuple[str, str]:
    # Use mammoth for high-quality docx extraction
    result = mammoth.extract_raw_text(io.BytesIO(content))
    text = result.value or ""
    quality = "high" if len(text) > 200 else "medium"
    return text, quality


def _extract_doc(content: bytes) -> tuple[str, str]:
    # First try mammoth (handles some .doc files)
    try:
        result = mammoth.extract_raw_text(io.BytesIO(content))
        if result.value and len(result.value.strip()) > 100:
            return result.value, "high"
    except Exception:
        pass

    # Fall back to raw text decoding
    for encoding in ["utf-8", "latin-1", "cp1252"]:
        try:
            text = content.decode(encoding, errors="ignore")
            # Strip binary garbage
            text = re.sub(r'[^\x20-\x7E\n\r\t\u2019\u2018\u201c\u201d]', ' ', text)
            text = re.sub(r' {3,}', ' ', text)
            text = re.sub(r'\n{3,}', '\n\n', text)
            if len(text.strip()) > 100:
                return text.strip(), "medium"
        except Exception:
            continue

    return "", "low"


# ══════════════════════════════════════════════════════════════════════════════
#  FILENAME PARSING
# ══════════════════════════════════════════════════════════════════════════════

DATE_PATTERNS = [
    (r'\((\d{1,2}-\d{1,2}-\d{2,4})\)', ["%m-%d-%y", "%m-%d-%Y"]),
    (r'\((\d{1,2}/\d{1,2}/\d{2,4})\)', ["%m/%d/%y", "%m/%d/%Y"]),
    (r'(\d{4}-\d{2}-\d{2})',            ["%Y-%m-%d"]),
]

def parse_filename(filename: str) -> dict:
    stem = Path(filename).stem

    # Date
    date = None
    for pattern, formats in DATE_PATTERNS:
        m = re.search(pattern, stem)
        if m:
            raw = m.group(1)
            for fmt in formats:
                try:
                    date = datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    pass
            if date:
                break

    # Series number prefix (e.g. "03-Feast of Unleavened Bread")
    series_num = None
    clean_name = stem
    m = re.match(r'^(\d+)[-\s]+(.+)', stem)
    if m:
        series_num = int(m.group(1))
        clean_name = m.group(2).strip()

    # Strip date from clean name
    clean_name = re.sub(r'\s*\(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\)', '', clean_name).strip()
    # Strip -whawley-PC and similar editor suffixes
    clean_name = re.sub(r'[-_](whawley|pc|backup|copy|final|draft).*$', '', clean_name, flags=re.I).strip()

    return {
        "clean_name":    clean_name,
        "date":          date,
        "series_number": series_num,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CLAUDE ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

ANALYSIS_PROMPT = """Analyze this sermon and return ONLY a valid JSON object. No preamble, no markdown fences, no explanation.

SERMON FILENAME: {filename}
SERMON TEXT (may be truncated):
---
{text}
---

Return this exact JSON structure:
{{
  "title": "The sermon title found in the text (not the filename). If not found, use filename.",
  "author_detected": "Full author name if found in the text (e.g. 'By Pastor William Hawley'), otherwise null",
  "date_detected": "Date found in sermon text in YYYY-MM-DD format, otherwise null",
  "summary": "2-3 sentence summary of the sermon's central message and application",
  "main_theme": "One short phrase (3-6 words) capturing the central theme",
  "series_name": "If this is part of a named sermon series, the series name. Otherwise null.",
  "structure": {{
    "has_introduction": true,
    "main_points": ["Point 1 title", "Point 2 title"],
    "has_conclusion": true,
    "has_altar_call": false
  }},
  "scripture_references": [
    {{
      "reference": "Full normalized reference e.g. John 3:16",
      "book": "John",
      "chapter": 3,
      "verse_start": 16,
      "verse_end": 16,
      "context": "Brief note on how this passage is used in the sermon"
    }}
  ],
  "keywords": ["keyword1", "keyword2"],
  "full_text_clean": "The sermon text cleaned up: fix obvious OCR errors, normalize spacing and paragraphs, preserve the actual content and wording faithfully.",
  "estimated_length": "short",
  "notes": "Any notable observations about this sermon (optional, null if nothing to note)"
}}

Rules:
- keywords: 5-10 theological/topical terms (e.g. faith, redemption, prayer, salvation, grace)
- scripture_references: ALL Bible references in the text, fully normalized
- estimated_length: "short" (<10 min), "medium" (10-20 min), "long" (20-40 min), "extended" (>40 min)
- full_text_clean: clean up the text but preserve the pastor's actual words and structure
- Return ONLY the JSON. Nothing else."""


def analyze_sermon(client: anthropic.Anthropic, text: str, filename: str) -> dict:
    """Send sermon to Claude for analysis. Returns structured dict."""
    truncated = text[:MAX_TEXT_FOR_AI] if len(text) > MAX_TEXT_FOR_AI else text

    if len(truncated.strip()) < 80:
        return _empty_analysis(filename, "text_too_short")

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": ANALYSIS_PROMPT.format(
                        filename=filename,
                        text=truncated
                    )
                }]
            )
            raw = resp.content[0].text.strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            parsed = json.loads(raw)
            parsed["_analysis_quality"] = "success"
            return parsed

        except json.JSONDecodeError as e:
            log.warning(f"JSON parse error attempt {attempt+1} for {filename}: {e}")
            time.sleep(1 * (attempt + 1))

        except anthropic.RateLimitError:
            wait = 60 * (attempt + 1)
            log.warning(f"Rate limited, waiting {wait}s...")
            time.sleep(wait)

        except anthropic.APIError as e:
            log.warning(f"API error attempt {attempt+1} for {filename}: {e}")
            time.sleep(2 * (attempt + 1))

    return _empty_analysis(filename, "analysis_failed")


def _empty_analysis(filename, reason):
    return {
        "title":               Path(filename).stem,
        "author_detected":     None,
        "date_detected":       None,
        "summary":             "",
        "main_theme":          "",
        "series_name":         None,
        "structure":           {},
        "scripture_references": [],
        "keywords":            [],
        "full_text_clean":     "",
        "estimated_length":    "unknown",
        "notes":               None,
        "_analysis_quality":   reason,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  FOLDER CRAWLER
# ══════════════════════════════════════════════════════════════════════════════

SERMON_EXTENSIONS = {".doc", ".docx", ".pdf", ".txt"}

def crawl_folder(graph: GraphClient, folder_id: str, folder_name: str | None, depth: int = 0) -> list[dict]:
    """Recursively crawl a folder, returning file metadata."""
    results = []

    for item in graph.list_children(folder_id):
        name = item.get("name", "")

        if item.get("folder"):
            name_lower = name.lower()

            # Skip completely
            if OTHER_PREACHER_FOLDERS.get(name_lower) is None and name_lower in OTHER_PREACHER_FOLDERS:
                log.info(f"{'  '*depth}⏭  Skipping: {name}")
                continue

            log.info(f"{'  '*depth}📁 {name}")
            sub_results = crawl_folder(graph, item["id"], name, depth + 1)
            results.extend(sub_results)

        elif item.get("file"):
            ext = Path(name).suffix.lower()
            if ext not in SERMON_EXTENSIONS:
                continue

            parsed = parse_filename(name)
            results.append({
                "graph_id":     item["id"],
                "filename":     name,
                "folder":       folder_name,
                "web_url":      item.get("webUrl", ""),
                "size_bytes":   item.get("size", 0),
                "modified":     item.get("lastModifiedDateTime", ""),
                "ext":          ext,
                **parsed,
            })

    return results


# ══════════════════════════════════════════════════════════════════════════════
#  AUTHOR RESOLUTION
# ══════════════════════════════════════════════════════════════════════════════

def resolve_author(file_meta: dict, analysis: dict, primary_pastor_name: str) -> tuple[str, bool]:
    """
    Returns (author_name, is_primary_pastor).
    Priority: detected in text > folder name > root-level default
    """
    detected = analysis.get("author_detected")
    folder   = (file_meta.get("folder") or "").lower()

    # Detected in text takes priority
    if detected and 3 < len(detected.strip()) < 60:
        is_primary = primary_pastor_name.lower() in detected.lower()
        return detected.strip(), is_primary

    # Known other-preacher folder
    if folder in OTHER_PREACHER_FOLDERS:
        author = OTHER_PREACHER_FOLDERS[folder]
        return (author or "Unknown"), False

    # Known primary pastor folder
    if folder in PRIMARY_PASTOR_FOLDERS or file_meta.get("folder") is None:
        return primary_pastor_name, True

    # Ambiguous folder — flag for review
    return f"Unknown ({file_meta.get('folder', 'root')})", False


# ══════════════════════════════════════════════════════════════════════════════
#  STATS COMPUTATION
# ══════════════════════════════════════════════════════════════════════════════

def compute_stats(sermons: list[dict], pastor_id: str) -> dict:
    all_keywords = []
    all_books    = []
    hawley_count = 0
    other_count  = 0

    for s in sermons:
        if s.get("is_primary_pastor"):
            hawley_count += 1
        else:
            other_count  += 1
        all_keywords.extend(s.get("keywords") or [])
        for ref in s.get("scripture_references") or []:
            if ref.get("book"):
                all_books.append(ref["book"])

    top_kw    = Counter(all_keywords).most_common(30)
    top_books = Counter(all_books).most_common(25)

    return {
        "pastor_id":             pastor_id,
        "total_sermons":         len(sermons),
        "william_hawley_count":  hawley_count,
        "other_preachers_count": other_count,
        "top_keywords":  [{"word": w, "count": c} for w, c in top_kw],
        "top_bible_books": [{"book": b, "count": c} for b, c in top_books],
        "computed_at":    datetime.now().isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  FIRESTORE WRITER
# ══════════════════════════════════════════════════════════════════════════════

def ensure_pastor(db, pastor_name: str, pastor_desc: str) -> str:
    """Create or find pastor document, return pastor_id."""
    pastors = db.collection("pastors")
    # Look for existing
    existing = pastors.where("name", "==", pastor_name).limit(1).get()
    if existing:
        return existing[0].id

    # Create new
    ref = pastors.add({
        "name":        pastor_name,
        "description": pastor_desc,
        "created_at":  firestore.SERVER_TIMESTAMP,
    })
    log.info(f"Created pastor document: {pastor_name} (id: {ref[1].id})")
    return ref[1].id


def write_sermon(db, sermon_doc: dict) -> str:
    """Write a sermon to Firestore. Returns document ID."""
    ref = db.collection("sermons").document()
    ref.set(sermon_doc)
    return ref.id


def write_stats(db, stats: dict, pastor_id: str):
    """Write pre-computed stats document."""
    db.collection("stats").document(pastor_id).set(stats)
    db.collection("stats").document("global").set({
        **stats,
        "pastor_id": "global",
    }, merge=True)
    log.info(f"Stats written for pastor {pastor_id}")


def get_existing_filenames(db, pastor_id: str) -> set[str]:
    """Get set of already-processed filenames to enable resume."""
    refs = db.collection("sermons").where("pastor_id", "==", pastor_id).select(["filename"]).get()
    return {r.get("filename") for r in refs if r.get("filename")}


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN INGESTION PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def run_ingestion(args):
    pastor_name   = args.pastor    or DEFAULT_PASTOR_NAME
    pastor_desc   = args.desc      or DEFAULT_PASTOR_DESC
    onedrive_path = args.folder    or DEFAULT_ONEDRIVE_PATH

    print("\n" + "═"*60)
    print(f"  SERMON LIBRARY INGESTION")
    print(f"  Pastor:  {pastor_name}")
    print(f"  Folder:  {onedrive_path}")
    print("═"*60 + "\n")

    # ── Init services ──────────────────────────────────────────
    if not ANTHROPIC_API_KEY:
        print("❌ ANTHROPIC_API_KEY not set.")
        print("   Set env variable: set ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    log.info("Initializing Firebase...")
    db = init_firebase()

    log.info("Initializing Anthropic...")
    ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    log.info("Connecting to Microsoft 365...")
    graph = GraphClient()

    # ── Ensure pastor exists ───────────────────────────────────
    pastor_id = ensure_pastor(db, pastor_name, pastor_desc)
    log.info(f"Pastor ID: {pastor_id}")

    # ── Find folder ────────────────────────────────────────────
    log.info(f"Finding OneDrive folder: {onedrive_path}")
    folder = graph.find_folder_by_path(onedrive_path)
    if not folder:
        log.error(f"Folder not found: {onedrive_path}")
        sys.exit(1)
    log.info(f"Found: {folder['name']} (id: {folder['id']})")

    # ── Crawl files ────────────────────────────────────────────
    log.info("Scanning files...")
    all_files = crawl_folder(graph, folder["id"], None)
    log.info(f"Found {len(all_files)} sermon files")

    # ── Resume: skip already processed ────────────────────────
    if args.resume:
        existing = get_existing_filenames(db, pastor_id)
        all_files = [f for f in all_files if f["filename"] not in existing]
        log.info(f"Resuming: {len(all_files)} files remaining")

    if not all_files:
        log.info("Nothing to process.")
        if args.stats_only or args.resume:
            _recompute_stats(db, pastor_id)
        return

    # ── Process each file ──────────────────────────────────────
    processed_sermons = []
    errors = []
    batch  = []

    for file_meta in tqdm(all_files, desc="Ingesting sermons", unit="sermon"):
        filename = file_meta["filename"]

        try:
            # 1. Download
            content = graph.download(file_meta["graph_id"])

            # 2. Extract text
            raw_text, extraction_quality = extract_text(filename, content)

            # 3. Analyze with Claude
            analysis = analyze_sermon(ai, raw_text, filename)

            # 4. Resolve author
            author, is_primary = resolve_author(file_meta, analysis, pastor_name)

            # 5. Build Firestore document
            bible_books = list({
                r["book"] for r in analysis.get("scripture_references", []) if r.get("book")
            })

            doc = {
                "pastor_id":           pastor_id,
                "filename":            filename,
                "folder":              file_meta.get("folder"),
                "web_url":             file_meta.get("web_url", ""),
                "author":              author,
                "is_primary_pastor":   is_primary,

                # Dates (best available)
                "date":                analysis.get("date_detected") or file_meta.get("date"),

                # Series
                "series_name":         analysis.get("series_name") or file_meta.get("series_name"),
                "series_number":       file_meta.get("series_number"),

                # Content
                "title":               analysis.get("title") or file_meta["clean_name"],
                "title_lower":         (analysis.get("title") or file_meta["clean_name"]).lower(),
                "summary":             analysis.get("summary", ""),
                "main_theme":          analysis.get("main_theme", ""),
                "structure":           analysis.get("structure", {}),

                # Search
                "keywords":            analysis.get("keywords", []),
                "bible_books":         bible_books,
                "scripture_references": analysis.get("scripture_references", []),

                # Full text
                "full_text_raw":       raw_text[:50000] if raw_text else "",
                "full_text_clean":     analysis.get("full_text_clean", "")[:50000],

                # Metadata
                "word_count":          len(raw_text.split()) if raw_text else 0,
                "estimated_length":    analysis.get("estimated_length", "unknown"),
                "extraction_quality":  extraction_quality,
                "processing_status":   analysis.get("_analysis_quality", "unknown"),
                "notes":               analysis.get("notes"),
                "processed_at":        datetime.now().isoformat(),
                "file_modified":       file_meta.get("modified", ""),
                "file_size_bytes":     file_meta.get("size_bytes", 0),
            }

            batch.append(doc)
            processed_sermons.append(doc)

            # Batch write every N sermons
            if len(batch) >= BATCH_SIZE:
                _flush_batch(db, batch)
                batch = []

            time.sleep(REQUEST_DELAY)

        except Exception as e:
            log.error(f"FAILED: {filename} — {e}", exc_info=True)
            errors.append({"filename": filename, "error": str(e)})

    # Flush remaining
    if batch:
        _flush_batch(db, batch)

    # ── Compute & write stats ──────────────────────────────────
    log.info("Computing stats...")
    _recompute_stats(db, pastor_id)

    # ── Summary ────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print(f"  ✅ INGESTION COMPLETE")
    print(f"  Processed: {len(processed_sermons)} sermons")
    print(f"  Errors:    {len(errors)}")
    if errors:
        print(f"  Error log: ingest.log")
    print(f"{'═'*60}\n")

    if errors:
        with open("failed_files.json", "w") as f:
            json.dump(errors, f, indent=2)
        print(f"  Failed files written to: failed_files.json")


def _flush_batch(db, batch):
    """Write a batch of sermon documents to Firestore."""
    fw = db.batch()
    for doc in batch:
        ref = db.collection("sermons").document()
        fw.set(ref, doc)
    fw.commit()
    log.info(f"Wrote batch of {len(batch)} sermons to Firestore")


def _recompute_stats(db, pastor_id):
    """Pull all sermons for a pastor and recompute the stats document."""
    log.info("Fetching all sermons for stats computation...")
    docs  = db.collection("sermons").where("pastor_id", "==", pastor_id).get()
    data  = [d.to_dict() for d in docs]
    stats = compute_stats(data, pastor_id)
    write_stats(db, stats, pastor_id)
    log.info(f"Stats: {stats['total_sermons']} total, {stats['william_hawley_count']} primary pastor")


# ══════════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest sermon files into the Sermon Library",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ingest.py
  python ingest.py --pastor "William Hawley" --folder "Dad's Files/Sermons1"
  python ingest.py --resume
  python ingest.py --stats-only
  python ingest.py --pastor "Billy Graham" --folder "Graham/Sermons" --desc "Billy Graham Crusade Sermons"
        """
    )
    parser.add_argument("--pastor",      help=f"Pastor name (default: {DEFAULT_PASTOR_NAME})")
    parser.add_argument("--desc",        help="Pastor description")
    parser.add_argument("--folder",      help=f"OneDrive folder path (default: {DEFAULT_ONEDRIVE_PATH})")
    parser.add_argument("--resume",      action="store_true", help="Skip already-processed files")
    parser.add_argument("--stats-only",  action="store_true", help="Only recompute stats, no ingestion")
    parser.add_argument("--reprocess-failed", action="store_true", help="Reprocess previously failed files")

    args = parser.parse_args()

    if args.stats_only:
        db = init_firebase()
        pastor_name = args.pastor or DEFAULT_PASTOR_NAME
        existing = db.collection("pastors").where("name", "==", pastor_name).limit(1).get()
        if existing:
            _recompute_stats(db, existing[0].id)
        else:
            print(f"Pastor '{pastor_name}' not found in database")
    else:
        run_ingestion(args)

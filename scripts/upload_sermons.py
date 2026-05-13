#!/usr/bin/env python3
"""
upload_sermons.py
=================
Phase 1 of 2: Upload raw sermon text to Firestore.

What this does:
  - Crawls local sermon files
  - Extracts text (LibreOffice .docx > mammoth > latin-1 fallback)
  - Fetches OneDrive web URLs via Microsoft Graph
  - Writes one Firestore document per sermon with raw data
  - NO Claude API calls — fast and cheap

What it does NOT do:
  - No Claude analysis
  - No scripture references
  - No Algolia indexing
  (All handled by enrich_sermons.py)

Each sermon document is written with processing_status = "pending"
so enrich_sermons.py knows what to process.

Usage:
  python upload_sermons.py              # Full run (prompts to wipe)
  python upload_sermons.py --resume     # Skip already-uploaded files
  python upload_sermons.py --no-wipe    # Skip wipe prompt, add new files

Run from the scripts folder.
"""

import sys, time, argparse
from pathlib import Path
from datetime import datetime

# ── Dependency bootstrap ───────────────────────────────────────────────────────
def ensure_deps():
    import subprocess
    for pip, imp in [
        ("firebase-admin", "firebase_admin"),
        ("mammoth",        "mammoth"),
        ("PyPDF2",         "PyPDF2"),
        ("tqdm",           "tqdm"),
        ("requests",       "requests"),
        ("msal",           "msal"),
    ]:
        try:
            __import__(imp)
        except ImportError:
            print(f"Installing {pip}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pip, "-q"])

ensure_deps()

import firebase_admin, requests, msal
from firebase_admin import credentials, firestore
from tqdm import tqdm
from shared import (
    LOCAL_BASE_PATH, FIREBASE_CREDS, DEFAULT_PASTOR_NAME, DEFAULT_PASTOR_DESC,
    make_logger, extract_text, crawl_local_folder, parse_filename,
)

# ── Configuration ──────────────────────────────────────────────────────────────
MS_CLIENT_ID    = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
MS_AUTHORITY    = "https://login.microsoftonline.com/common"
MS_SCOPES       = ["Files.Read", "Files.Read.All"]
ONEDRIVE_FOLDER = "Dad's Files/Sermons1"
SERMON_EXTENSIONS = {".doc", ".docx", ".pdf", ".txt", ".htm", ".html"}
BATCH_SIZE      = 25    # Conservative batch size to avoid quota hits
BATCH_SLEEP     = 3.0   # Seconds between batches to stay under rate limit

log = make_logger("upload", "upload.log")

# ── Firebase ───────────────────────────────────────────────────────────────────
def init_firebase():
    if not Path(FIREBASE_CREDS).exists():
        log.error(f"Firebase credentials not found: {FIREBASE_CREDS}")
        sys.exit(1)
    cred = credentials.Certificate(FIREBASE_CREDS)
    firebase_admin.initialize_app(cred)
    return firestore.client()

def wipe_collections(db):
    """Delete all documents from sermon-related collections."""
    log.info("Wiping Firestore collections...")
    for col in ["sermons", "scripture_references", "series", "pastors", "stats"]:
        deleted = 0
        while True:
            docs = list(db.collection(col).limit(400).stream())
            if not docs:
                break
            batch = db.batch()
            for d in docs:
                batch.delete(d.reference)
            batch.commit()
            deleted += len(docs)
            time.sleep(0.5)
        if deleted:
            log.info(f"  Deleted {deleted} documents from /{col}")
    log.info("Firestore wiped clean")

def ensure_pastor(db, name, desc):
    existing = list(
        db.collection("pastors").where("name", "==", name).limit(1).stream()
    )
    if existing:
        return existing[0].id
    ref = db.collection("pastors").document()
    ref.set({
        "name":        name,
        "description": desc,
        "created_at":  firestore.SERVER_TIMESTAMP,
    })
    log.info(f"Created pastor: {name} ({ref.id})")
    return ref.id

def get_existing_filenames(db, pastor_id):
    """Return set of filenames already uploaded for this pastor."""
    docs = db.collection("sermons").where("pastor_id", "==", pastor_id).stream()
    return {d.to_dict().get("filename") for d in docs if d.to_dict().get("filename")}

def commit_batch_with_retry(batch, max_attempts=5):
    """Commit a Firestore batch with exponential backoff on quota errors."""
    for attempt in range(max_attempts):
        try:
            batch.commit()
            return
        except Exception as e:
            if "429" in str(e) or "Quota" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait = 15 * (attempt + 1)
                log.warning(f"Firestore quota hit, waiting {wait}s (attempt {attempt+1})...")
                time.sleep(wait)
                if attempt == max_attempts - 1:
                    raise
            else:
                raise

# ── Microsoft Graph ────────────────────────────────────────────────────────────
class GraphClient:
    BASE = "https://graph.microsoft.com/v1.0"

    def __init__(self):
        self._app   = msal.PublicClientApplication(MS_CLIENT_ID, authority=MS_AUTHORITY)
        self._token = None
        self._login()

    def _login(self):
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(MS_SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._token = result["access_token"]
                log.info("Using cached Microsoft token")
                return
        flow = self._app.initiate_device_flow(scopes=MS_SCOPES)
        print(f"\n{'='*50}")
        print("MICROSOFT LOGIN (for OneDrive web URLs)")
        print(f"1. Open: {flow['verification_uri']}")
        print(f"2. Enter code: {flow['user_code']}")
        print("="*50 + "\n")
        result = self._app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(f"Microsoft auth failed: {result.get('error_description')}")
        self._token = result["access_token"]
        log.info("Microsoft login successful")

    @property
    def _headers(self):
        return {"Authorization": f"Bearer {self._token}"}

    def _refresh(self):
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(MS_SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._token = result["access_token"]
                return True
        return False

    def get_json(self, path):
        for attempt in range(2):
            r = requests.get(f"{self.BASE}{path}", headers=self._headers, timeout=15)
            if r.status_code == 401 and attempt == 0 and self._refresh():
                continue
            r.raise_for_status()
            return r.json()

    def list_children(self, item_id):
        items = []
        url   = f"{self.BASE}/me/drive/items/{item_id}/children"
        while url:
            for attempt in range(2):
                r = requests.get(url, headers=self._headers, timeout=15)
                if r.status_code == 401 and attempt == 0 and self._refresh():
                    continue
                r.raise_for_status()
                data = r.json()
                break
            items.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
        return items

    def find_folder(self, folder_path):
        encoded = requests.utils.quote(folder_path, safe="/")
        item = self.get_json(f"/me/drive/root:/{encoded}")
        return item if item.get("folder") else None

def fetch_web_urls(graph):
    """Crawl OneDrive and return {filename: web_url} for all sermon files."""
    log.info("Fetching OneDrive web URLs...")
    folder = graph.find_folder(ONEDRIVE_FOLDER)
    if not folder:
        log.warning("OneDrive folder not found — web URLs will be empty")
        return {}
    url_map = {}
    _crawl_for_urls(graph, folder["id"], url_map)
    log.info(f"Found {len(url_map)} web URLs")
    return url_map

def _crawl_for_urls(graph, folder_id, url_map):
    for item in graph.list_children(folder_id):
        name = item.get("name", "")
        if item.get("folder"):
            if name.lower() == "illustrations":
                continue
            _crawl_for_urls(graph, item["id"], url_map)
        elif item.get("file"):
            if Path(name).suffix.lower() in SERMON_EXTENSIONS:
                web_url = item.get("webUrl", "")
                if web_url:
                    url_map[name] = web_url

# ── Main ───────────────────────────────────────────────────────────────────────
def main(args):
    pastor_name = args.pastor or DEFAULT_PASTOR_NAME
    pastor_desc = args.desc   or DEFAULT_PASTOR_DESC
    local_path  = args.local  or LOCAL_BASE_PATH

    print("\n" + "="*60)
    print(f"  UPLOAD SERMONS — Phase 1 of 2")
    print(f"  Pastor: {pastor_name}")
    print(f"  Source: {local_path}")
    print("="*60 + "\n")

    if not Path(local_path).exists():
        print(f"ERROR: Source folder not found:\n  {local_path}")
        sys.exit(1)

    log.info("Initializing Firebase...")
    db = init_firebase()

    # Wipe or resume
    if not args.resume and not args.no_wipe:
        answer = input(
            "This will wipe all existing sermon data and start fresh.\n"
            "Type YES to confirm: "
        ).strip()
        if answer == "YES":
            wipe_collections(db)
        else:
            print("Wipe cancelled. Use --resume to add new files only.")
            sys.exit(0)

    pastor_id = ensure_pastor(db, pastor_name, pastor_desc)
    log.info(f"Pastor ID: {pastor_id}")

    # Fetch OneDrive web URLs upfront
    web_urls = {}
    try:
        graph    = GraphClient()
        web_urls = fetch_web_urls(graph)
    except Exception as e:
        log.warning(f"Could not fetch web URLs: {e}")
        log.warning("Sermons will be uploaded without web URLs.")

    # Scan local files
    log.info("Scanning local files...")
    all_files = crawl_local_folder(local_path, log=log)
    log.info(f"Found {len(all_files)} sermon files")

    if args.resume:
        existing  = get_existing_filenames(db, pastor_id)
        all_files = [f for f in all_files if f["filename"] not in existing]
        log.info(f"Resuming: {len(all_files)} new files to upload")

    if not all_files:
        log.info("Nothing to upload.")
        return

    # Upload in batches
    batch        = db.batch()
    batch_count  = 0
    total_done   = 0
    errors       = []

    for file_meta in tqdm(all_files, desc="Uploading", unit="sermon"):
        filename = file_meta["filename"]
        try:
            raw_text, quality = extract_text(file_meta["local_path"])

            # Check if converted .docx was used
            from shared import get_converted_path
            ext = file_meta["ext"]
            if ext == ".doc":
                converted = get_converted_path(Path(file_meta["local_path"]))
                if converted and converted.exists() and converted.stat().st_size > 0:
                    quality = "high"

            title = file_meta["clean_name"]

            doc = {
                # Identity
                "pastor_id":          pastor_id,
                "filename":           filename,
                "folder":             file_meta.get("folder"),
                "web_url":            web_urls.get(filename, ""),
                "file_size_bytes":    file_meta.get("size_bytes", 0),
                "ext":                ext,

                # Parsed from filename
                "title":              title,
                "title_lower":        title.lower(),
                "date":               file_meta.get("date"),
                "year":               file_meta.get("year"),
                "decade":             file_meta.get("decade"),
                "series_number":      file_meta.get("series_number"),

                # Raw text
                "full_text_raw":      raw_text[:50000] if raw_text else "",
                "word_count":         len(raw_text.split()) if raw_text else 0,
                "extraction_quality": quality,

                # Placeholders — filled in by enrich_sermons.py
                "author":             "",
                "is_primary_pastor":  False,
                "summary":            "",
                "main_theme":         "",
                "keywords":           [],
                "bible_books":        [],
                "structure":          {},
                "series_name":        None,
                "series_id":          None,
                "estimated_length":   "unknown",
                "notes":              None,
                "scripture_ref_count": 0,

                # Status
                "processing_status":  "pending",
                "uploaded_at":        datetime.now().isoformat(),
                "processed_at":       None,
            }

            ref = db.collection("sermons").document()
            batch.set(ref, doc)
            batch_count += 1
            total_done  += 1

            if batch_count >= BATCH_SIZE:
                commit_batch_with_retry(batch)
                batch       = db.batch()
                batch_count = 0
                time.sleep(BATCH_SLEEP)

        except Exception as e:
            log.error(f"FAILED: {filename} — {e}")
            errors.append({"filename": filename, "error": str(e)})

    # Flush remaining
    if batch_count > 0:
        commit_batch_with_retry(batch)

    print(f"\n{'='*60}")
    print(f"  UPLOAD COMPLETE")
    print(f"  Uploaded: {total_done}")
    print(f"  Errors:   {len(errors)}")
    print(f"{'='*60}\n")

    if errors:
        import json
        with open("upload_errors.json", "w") as f:
            json.dump(errors, f, indent=2)
        print("Errors saved to: upload_errors.json")

    print("Next step: python enrich_sermons.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload raw sermon text to Firestore")
    parser.add_argument("--pastor",   help=f"Pastor name (default: {DEFAULT_PASTOR_NAME})")
    parser.add_argument("--desc",     help="Pastor description")
    parser.add_argument("--local",    help="Override local sermon folder path")
    parser.add_argument("--resume",   action="store_true",
                        help="Skip already-uploaded files, add new ones only")
    parser.add_argument("--no-wipe",  action="store_true", dest="no_wipe",
                        help="Skip wipe prompt (for adding new pastors)")
    args = parser.parse_args()
    main(args)

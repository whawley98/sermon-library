#!/usr/bin/env python3
"""
ingest.py - Sermon Library Ingestion Script
============================================
Reads sermon files from a local folder, analyzes each with Claude AI,
and writes structured data to Firebase Firestore.

Usage:
  python ingest.py
  python ingest.py --resume
  python ingest.py --stats-only
  python ingest.py --pastor "Billy Graham" --local "C:/path/to/sermons"
"""

import os, sys, json, re, time, io, logging, argparse
from pathlib import Path
from datetime import datetime
from collections import Counter

# ── Dependency check ──────────────────────────────────────────────────────────
def ensure_deps():
    import subprocess
    pkgs = [
        ("anthropic",      "anthropic"),
        ("firebase-admin", "firebase_admin"),
        ("python-docx",    "docx"),
        ("PyPDF2",         "PyPDF2"),
        ("tqdm",           "tqdm"),
        ("mammoth",        "mammoth"),
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
import mammoth
import PyPDF2
from tqdm import tqdm

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

FIREBASE_CREDENTIALS_PATH = "firebase-credentials.json"

def _load_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    key_file = Path(__file__).parent / "api_key.txt"
    if key_file.exists():
        key = key_file.read_text(encoding="utf-8").strip()
        if key:
            print(f"Loaded API key from {key_file}")
            return key
    return ""

ANTHROPIC_API_KEY = _load_api_key()

DEFAULT_PASTOR_NAME  = "William Hawley"
DEFAULT_PASTOR_DESC  = "40 years of faithful preaching"
DEFAULT_LOCAL_PATH   = r"C:\Users\WilliamHawley\OneDrive - Juhls\Dad's Files\Sermons1"

OTHER_PREACHER_FOLDERS = {
    "billy sunday":   "Billy Sunday",
    "chapman":        "J. Wilbur Chapman",
    "hughes":         "Hughes",
    "johnston":       "Johnston",
    "illustrations":  None,
}

PRIMARY_PASTOR_FOLDERS = {"franklin sermons", "fbis - cloud", "browning"}

SERMON_EXTENSIONS = {".doc", ".docx", ".pdf", ".txt", ".htm", ".html"}
MAX_TEXT_FOR_AI   = 4000
MAX_RETRIES       = 3
BATCH_SIZE        = 50
REQUEST_DELAY     = 0.2

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
    if not Path(FIREBASE_CREDENTIALS_PATH).exists():
        log.error(f"Firebase credentials not found: {FIREBASE_CREDENTIALS_PATH}")
        sys.exit(1)
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)
    return firestore.client()

# ══════════════════════════════════════════════════════════════════════════════
#  TEXT EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def extract_text(filepath):
    ext = Path(filepath).suffix.lower()
    try:
        with open(filepath, "rb") as f:
            content = f.read()
        if ext == ".pdf":
            return _extract_pdf(content)
        elif ext == ".docx":
            return _extract_docx(content)
        elif ext in (".doc",):
            return _extract_doc(content)
        elif ext in (".htm", ".html"):
            text = content.decode("utf-8", errors="ignore")
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text, "medium"
        else:
            return content.decode("utf-8", errors="ignore"), "medium"
    except Exception as e:
        log.warning(f"Extraction failed for {filepath}: {e}")
        return "", "low"

def _extract_pdf(content):
    reader = PyPDF2.PdfReader(io.BytesIO(content))
    pages  = [p.extract_text() or "" for p in reader.pages]
    text   = "\n\n".join(p for p in pages if p.strip())
    return text, ("high" if len(text) > 200 else "low")

def _extract_docx(content):
    result = mammoth.extract_raw_text(io.BytesIO(content))
    text   = result.value or ""
    return text, ("high" if len(text) > 200 else "medium")

def _extract_doc(content):
    try:
        result = mammoth.extract_raw_text(io.BytesIO(content))
        if result.value and len(result.value.strip()) > 100:
            return result.value, "high"
    except Exception:
        pass
    for encoding in ["utf-8", "latin-1", "cp1252"]:
        try:
            text = content.decode(encoding, errors="ignore")
            text = re.sub(r"[^\x20-\x7E\n\r\t]", " ", text)
            text = re.sub(r" {3,}", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text)
            if len(text.strip()) > 100:
                return text.strip(), "medium"
        except Exception:
            continue
    return "", "low"

# ══════════════════════════════════════════════════════════════════════════════
#  FILENAME PARSING
# ══════════════════════════════════════════════════════════════════════════════

DATE_PATTERNS = [
    (r"\((\d{1,2}-\d{1,2}-\d{2,4})\)", ["%m-%d-%y", "%m-%d-%Y"]),
    (r"\((\d{1,2}/\d{1,2}/\d{2,4})\)", ["%m/%d/%y", "%m/%d/%Y"]),
    (r"(\d{4}-\d{2}-\d{2})",            ["%Y-%m-%d"]),
]

def parse_filename(filename):
    stem = Path(filename).stem
    date = None
    for pattern, formats in DATE_PATTERNS:
        m = re.search(pattern, stem)
        if m:
            for fmt in formats:
                try:
                    date = datetime.strptime(m.group(1), fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    pass
            if date:
                break

    series_num = None
    clean_name = stem
    m = re.match(r"^(\d+)[-\s]+(.+)", stem)
    if m:
        series_num = int(m.group(1))
        clean_name = m.group(2).strip()

    clean_name = re.sub(r"\s*\(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\)", "", clean_name).strip()
    clean_name = re.sub(r"[-_](whawley|pc|backup|copy|final|draft).*$", "", clean_name, flags=re.I).strip()

    return {"clean_name": clean_name, "date": date, "series_number": series_num}

# ══════════════════════════════════════════════════════════════════════════════
#  CLAUDE ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are a sermon analysis assistant. Respond with ONLY a valid JSON object. No markdown, no explanation, nothing before or after the JSON.

Required JSON structure:
{
  "title": "sermon title from text, or filename if not found",
  "author_detected": "author name if found in text, or null",
  "date_detected": "YYYY-MM-DD if date found in text, or null",
  "summary": "2-3 sentence summary of central message",
  "main_theme": "3-6 word theme phrase",
  "series_name": "series name if part of a series, or null",
  "structure": {
    "has_introduction": true,
    "main_points": ["point 1", "point 2"],
    "has_conclusion": true,
    "has_altar_call": false
  },
  "scripture_references": [
    {
      "reference": "John 3:16",
      "book": "John",
      "chapter": 3,
      "verse_start": 16,
      "verse_end": 16,
      "context": "how it is used"
    }
  ],
  "keywords": ["faith", "salvation"],
  "estimated_length": "short",
  "notes": null
}

Rules:
- keywords: 5-10 theological terms
- estimated_length: short, medium, long, or extended
- scripture_references: every Bible reference in the text
- Return ONLY the JSON object"""


def sanitize_for_prompt(text):
    """Remove characters that commonly corrupt JSON responses."""
    # Remove null bytes and control characters
    text = re.sub(r'[--]', ' ', text)
    # Replace curly smart quotes with straight ones
    text = text.replace('“', '"').replace('”', '"')
    text = text.replace('‘', "'").replace('’', "'")
    # Replace em/en dashes
    text = text.replace('—', '--').replace('–', '-')
    # Replace other common problematic chars
    text = text.replace('…', '...').replace(' ', ' ')
    # Remove any remaining non-ASCII that might cause issues
    text = text.encode('ascii', errors='replace').decode('ascii')
    # Collapse excessive whitespace
    text = re.sub(r'[ 	]{3,}', ' ', text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def analyze_sermon(client, text, filename):
    if len(text.strip()) < 80:
        return _empty_analysis(filename, "text_too_short")

    truncated = sanitize_for_prompt(text[:MAX_TEXT_FOR_AI])
    user_msg  = "Filename: " + filename + "\n\nSermon text:\n" + truncated

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1200,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}]
            )
            raw = resp.content[0].text.strip()
            # Extract JSON by finding first { and last } - immune to markdown fences
            start = raw.find("{")
            end   = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                raw = raw[start:end+1]
            parsed = json.loads(raw)
            parsed["_analysis_quality"] = "success"
            return parsed

        except json.JSONDecodeError as e:
            log.warning(f"JSON parse error attempt {attempt+1} for {filename}: {e}")
            time.sleep(attempt + 1)

        except anthropic.RateLimitError:
            wait = 60 * (attempt + 1)
            log.warning(f"Rate limited, waiting {wait}s...")
            time.sleep(wait)

        except Exception as e:
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
        "estimated_length":    "unknown",
        "notes":               None,
        "_analysis_quality":   reason,
    }

# ══════════════════════════════════════════════════════════════════════════════
#  LOCAL FOLDER CRAWLER
# ══════════════════════════════════════════════════════════════════════════════

def crawl_local_folder(folder_path, folder_name=None, depth=0):
    results = []
    try:
        items = sorted(Path(folder_path).iterdir())
    except PermissionError:
        log.warning(f"Permission denied: {folder_path}")
        return results

    for item in items:
        name       = item.name
        name_lower = name.lower()

        if item.is_dir():
            if OTHER_PREACHER_FOLDERS.get(name_lower) is None and name_lower in OTHER_PREACHER_FOLDERS:
                log.info(f"{'  '*depth}Skipping: {name}")
                continue
            log.info(f"{'  '*depth}Folder: {name}")
            results.extend(crawl_local_folder(str(item), name, depth + 1))

        elif item.is_file():
            if item.suffix.lower() not in SERMON_EXTENSIONS:
                continue
            parsed = parse_filename(name)
            results.append({
                "local_path": str(item),
                "filename":   name,
                "folder":     folder_name,
                "web_url":    "",
                "size_bytes": item.stat().st_size,
                "ext":        item.suffix.lower(),
                **parsed,
            })

    return results

# ══════════════════════════════════════════════════════════════════════════════
#  AUTHOR RESOLUTION
# ══════════════════════════════════════════════════════════════════════════════

def resolve_author(file_meta, analysis, primary_pastor_name):
    detected = analysis.get("author_detected")
    folder   = (file_meta.get("folder") or "").lower()

    if detected and 3 < len(detected.strip()) < 60:
        is_primary = primary_pastor_name.lower() in detected.lower()
        return detected.strip(), is_primary

    if folder in OTHER_PREACHER_FOLDERS:
        author = OTHER_PREACHER_FOLDERS[folder]
        return (author or "Unknown"), False

    if folder in PRIMARY_PASTOR_FOLDERS or file_meta.get("folder") is None:
        return primary_pastor_name, True

    return f"Unknown ({file_meta.get('folder', 'root')})", False

# ══════════════════════════════════════════════════════════════════════════════
#  STATS
# ══════════════════════════════════════════════════════════════════════════════

def compute_stats(sermons, pastor_id):
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

    return {
        "pastor_id":             pastor_id,
        "total_sermons":         len(sermons),
        "william_hawley_count":  hawley_count,
        "other_preachers_count": other_count,
        "top_keywords":    [{"word": w, "count": c} for w, c in Counter(all_keywords).most_common(30)],
        "top_bible_books": [{"book": b, "count": c} for b, c in Counter(all_books).most_common(25)],
        "computed_at":     datetime.now().isoformat(),
    }

# ══════════════════════════════════════════════════════════════════════════════
#  FIRESTORE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def ensure_pastor(db, pastor_name, pastor_desc):
    existing = list(db.collection("pastors").where("name", "==", pastor_name).limit(1).stream())
    if existing:
        return existing[0].id
    ref = db.collection("pastors").document()
    ref.set({"name": pastor_name, "description": pastor_desc, "created_at": firestore.SERVER_TIMESTAMP})
    log.info(f"Created pastor: {pastor_name} (id: {ref.id})")
    return ref.id

def get_existing_filenames(db, pastor_id):
    docs = db.collection("sermons").where("pastor_id", "==", pastor_id).stream()
    return {d.to_dict().get("filename") for d in docs if d.to_dict().get("filename")}

def flush_batch(db, batch_docs):
    wb = db.batch()
    for doc in batch_docs:
        ref = db.collection("sermons").document()
        wb.set(ref, doc)
    wb.commit()
    log.info(f"Wrote {len(batch_docs)} sermons to Firestore")

def write_stats(db, stats, pastor_id):
    db.collection("stats").document(pastor_id).set(stats)
    db.collection("stats").document("global").set(stats, merge=True)

def recompute_stats(db, pastor_id):
    log.info("Computing stats...")
    docs  = list(db.collection("sermons").where("pastor_id", "==", pastor_id).stream())
    data  = [d.to_dict() for d in docs]
    stats = compute_stats(data, pastor_id)
    write_stats(db, stats, pastor_id)
    log.info(f"Stats: {stats['total_sermons']} sermons")

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def run_ingestion(args):
    pastor_name = args.pastor or DEFAULT_PASTOR_NAME
    pastor_desc = args.desc   or DEFAULT_PASTOR_DESC
    local_path  = args.local  or DEFAULT_LOCAL_PATH

    print("\n" + "="*60)
    print(f"  SERMON LIBRARY INGESTION")
    print(f"  Pastor: {pastor_name}")
    print(f"  Folder: {local_path}")
    print("="*60 + "\n")

    if not ANTHROPIC_API_KEY:
        print("ERROR: Anthropic API key not found.")
        print("Create api_key.txt in this folder with your key.")
        sys.exit(1)

    if not Path(local_path).exists():
        print(f"ERROR: Folder not found: {local_path}")
        sys.exit(1)

    log.info("Initializing Firebase...")
    db = init_firebase()

    log.info("Initializing Anthropic...")
    ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    pastor_id = ensure_pastor(db, pastor_name, pastor_desc)
    log.info(f"Pastor ID: {pastor_id}")

    log.info("Scanning local files...")
    all_files = crawl_local_folder(local_path)
    log.info(f"Found {len(all_files)} sermon files")

    if args.resume:
        existing = get_existing_filenames(db, pastor_id)
        all_files = [f for f in all_files if f["filename"] not in existing]
        log.info(f"Resuming: {len(all_files)} files remaining")

    if not all_files:
        log.info("Nothing to process.")
        recompute_stats(db, pastor_id)
        return

    batch  = []
    errors = []

    for file_meta in tqdm(all_files, desc="Ingesting sermons", unit="sermon"):
        filename = file_meta["filename"]
        try:
            raw_text, extraction_quality = extract_text(file_meta["local_path"])
            analysis = analyze_sermon(ai, raw_text, filename)
            author, is_primary = resolve_author(file_meta, analysis, pastor_name)

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
                "date":                analysis.get("date_detected") or file_meta.get("date"),
                "series_name":         analysis.get("series_name") or file_meta.get("series_name"),
                "series_number":       file_meta.get("series_number"),
                "title":               analysis.get("title") or file_meta["clean_name"],
                "title_lower":         (analysis.get("title") or file_meta["clean_name"]).lower(),
                "summary":             analysis.get("summary", ""),
                "main_theme":          analysis.get("main_theme", ""),
                "structure":           analysis.get("structure", {}),
                "keywords":            analysis.get("keywords", []),
                "bible_books":         bible_books,
                "scripture_references": analysis.get("scripture_references", []),
                "full_text_raw":       raw_text[:50000] if raw_text else "",
                "word_count":          len(raw_text.split()) if raw_text else 0,
                "estimated_length":    analysis.get("estimated_length", "unknown"),
                "extraction_quality":  extraction_quality,
                "processing_status":   analysis.get("_analysis_quality", "unknown"),
                "notes":               analysis.get("notes"),
                "processed_at":        datetime.now().isoformat(),
                "file_size_bytes":     file_meta.get("size_bytes", 0),
            }

            batch.append(doc)
            if len(batch) >= BATCH_SIZE:
                flush_batch(db, batch)
                batch = []

            time.sleep(REQUEST_DELAY)

        except Exception as e:
            log.error(f"FAILED: {filename} — {e}", exc_info=True)
            errors.append({"filename": filename, "error": str(e)})

    if batch:
        flush_batch(db, batch)

    recompute_stats(db, pastor_id)

    print(f"\n{'='*60}")
    print(f"  COMPLETE")
    print(f"  Processed: {len(all_files) - len(errors)} sermons")
    print(f"  Errors:    {len(errors)}")
    print(f"{'='*60}\n")

    if errors:
        with open("failed_files.json", "w") as f:
            json.dump(errors, f, indent=2)
        print(f"Failed files saved to: failed_files.json")


# ══════════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest sermons into Firestore")
    parser.add_argument("--pastor",     help=f"Pastor name (default: {DEFAULT_PASTOR_NAME})")
    parser.add_argument("--desc",       help="Pastor description")
    parser.add_argument("--local",      help=f"Local folder path (default: {DEFAULT_LOCAL_PATH})")
    parser.add_argument("--resume",     action="store_true", help="Skip already-processed files")
    parser.add_argument("--stats-only", action="store_true", help="Only recompute stats")
    args = parser.parse_args()

    if args.stats_only:
        db = init_firebase()
        pastor_name = args.pastor or DEFAULT_PASTOR_NAME
        existing = list(db.collection("pastors").where("name", "==", pastor_name).limit(1).stream())
        if existing:
            recompute_stats(db, existing[0].id)
        else:
            print(f"Pastor not found: {pastor_name}")
    else:
        run_ingestion(args)

#!/usr/bin/env python3
"""
reprocess_failed.py — Reprocess sermons that failed analysis
=============================================================
Fetches all sermons with processing_status = "analysis_failed",
re-analyzes them with Claude, and updates Firestore.

Run from scripts folder: python reprocess_failed.py
"""

import os, sys, re, io, json, time, logging
from pathlib import Path
from datetime import datetime

def ensure_deps():
    import subprocess
    for pip, imp in [("anthropic","anthropic"),("firebase-admin","firebase_admin"),
                     ("mammoth","mammoth"),("PyPDF2","PyPDF2"),("tqdm","tqdm")]:
        try: __import__(imp)
        except ImportError: subprocess.check_call([sys.executable,"-m","pip","install",pip,"-q"])

ensure_deps()

import anthropic, firebase_admin, mammoth, PyPDF2
from firebase_admin import credentials, firestore
from tqdm import tqdm

# ── Config ────────────────────────────────────────────────────────────────────
FIREBASE_CREDENTIALS_PATH = "firebase-credentials.json"
LOCAL_BASE_PATH = r"C:\Users\WilliamHawley\OneDrive - Juhls\Dad's Files\Sermons1"
MAX_TEXT_FOR_AI = 4000
MAX_RETRIES     = 3

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    handlers=[logging.FileHandler("reprocess.log",encoding="utf-8"), logging.StreamHandler()])
log = logging.getLogger(__name__)

# ── API key ───────────────────────────────────────────────────────────────────
def load_key():
    key = os.environ.get("ANTHROPIC_API_KEY","").strip()
    if key: return key
    f = Path(__file__).parent / "API Key.txt"
    if f.exists(): return f.read_text(encoding="utf-8").strip()
    return ""

# ── Firebase ──────────────────────────────────────────────────────────────────
def init_firebase():
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)
    return firestore.client()

# ── Text extraction ───────────────────────────────────────────────────────────
def extract_text(filepath):
    ext = Path(filepath).suffix.lower()
    with open(filepath, "rb") as f:
        data = f.read()
    try:
        if ext == ".pdf":
            reader = PyPDF2.PdfReader(io.BytesIO(data))
            return "\n\n".join(p.extract_text() or "" for p in reader.pages), "high"
        elif ext in (".doc", ".docx"):
            try:
                r = mammoth.extract_raw_text(io.BytesIO(data))
                if r.value and len(r.value.strip()) > 100:
                    return r.value, "high"
            except Exception:
                pass
            for enc in ["utf-8","latin-1","cp1252"]:
                try:
                    text = data.decode(enc, errors="ignore")
                    text = re.sub(r"[^\x20-\x7E\n\r\t]"," ",text)
                    text = re.sub(r" {3,}"," ",text)
                    text = re.sub(r"\n{4,}","\n\n",text)
                    if len(text.strip()) > 100:
                        return text.strip(), "medium"
                except Exception:
                    pass
    except Exception as e:
        log.warning(f"Extraction failed for {filepath}: {e}")
    return "", "low"

# ── Sanitize ──────────────────────────────────────────────────────────────────
def sanitize(text):
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"," ",text)
    text = text.replace("\u201c",'"').replace("\u201d",'"')
    text = text.replace("\u2018","'").replace("\u2019","'")
    text = text.replace("\u2014","--").replace("\u2013","-")
    text = text.replace("\u2026","...").replace("\u00a0"," ")
    text = text.encode("ascii", errors="replace").decode("ascii")
    text = re.sub(r"[ \t]{3,}"," ",text)
    text = re.sub(r"\n{4,}","\n\n",text)
    return text.strip()

# ── Claude analysis ───────────────────────────────────────────────────────────
SYSTEM = """You are a sermon analysis assistant. Respond with ONLY a valid JSON object. No markdown, no fences.
Your response must start with { and end with }

Fields: title, author_detected, date_detected, summary, main_theme, series_name,
structure (has_introduction, main_points, has_conclusion, has_altar_call),
scripture_references (reference, book, chapter, verse_start, verse_end, context),
keywords, estimated_length, notes"""

def analyze(client, text, filename):
    if len(text.strip()) < 80:
        return None, "text_too_short"

    safe = sanitize(text[:MAX_TEXT_FOR_AI])
    msg  = f"Filename: {filename}\n\nSermon text:\n{safe}"

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1200,
                system=SYSTEM,
                messages=[{"role":"user","content":msg}],
            )
            raw   = resp.content[0].text.strip()
            start = raw.find("{")
            end   = raw.rfind("}")
            if start != -1 and end > start:
                raw = raw[start:end+1]
            parsed = json.loads(raw)
            parsed["_analysis_quality"] = "success"
            return parsed, "success"
        except json.JSONDecodeError as e:
            log.warning(f"JSON error attempt {attempt+1} for {filename}: {e}")
            time.sleep(attempt+1)
        except anthropic.RateLimitError:
            time.sleep(60*(attempt+1))
        except Exception as e:
            log.warning(f"API error attempt {attempt+1} for {filename}: {e}")
            time.sleep(2*(attempt+1))

    return None, "analysis_failed"

# ── Find local file ───────────────────────────────────────────────────────────
def find_local_file(filename, base_path):
    """Search for file recursively under base_path."""
    for p in Path(base_path).rglob(filename):
        return str(p)
    return None

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    key = load_key()
    if not key:
        print("ERROR: API key not found in API Key.txt")
        sys.exit(1)

    print("Connecting to Firebase...")
    db     = init_firebase()
    client = anthropic.Anthropic(api_key=key)

    # Fetch failed sermons
    print("Fetching failed sermons...")
    docs = list(db.collection("sermons")
                  .where("processing_status","==","analysis_failed")
                  .stream())
    print(f"Found {len(docs)} failed sermons to reprocess\n")

    if not docs:
        print("Nothing to reprocess!")
        return

    fixed  = 0
    still_failed = 0

    for doc in tqdm(docs, desc="Reprocessing", unit="sermon"):
        data     = doc.to_dict()
        filename = data.get("filename","")

        # Find file locally
        local_path = find_local_file(filename, LOCAL_BASE_PATH)
        if not local_path:
            log.warning(f"File not found locally: {filename}")
            still_failed += 1
            continue

        # Extract text
        raw_text, quality = extract_text(local_path)
        if not raw_text.strip():
            log.warning(f"No text extracted: {filename}")
            still_failed += 1
            continue

        # Analyze
        analysis, status = analyze(client, raw_text, filename)
        if not analysis:
            still_failed += 1
            continue

        # Build update
        bible_books = list({
            r["book"] for r in analysis.get("scripture_references",[]) if r.get("book")
        })

        update = {
            "title":                analysis.get("title") or data.get("title",""),
            "summary":              analysis.get("summary",""),
            "main_theme":           analysis.get("main_theme",""),
            "structure":            analysis.get("structure",{}),
            "keywords":             analysis.get("keywords",[]),
            "bible_books":          bible_books,
            "scripture_references": analysis.get("scripture_references",[]),
            "series_name":          analysis.get("series_name"),
            "estimated_length":     analysis.get("estimated_length","unknown"),
            "notes":                analysis.get("notes"),
            "full_text_raw":        raw_text[:50000],
            "word_count":           len(raw_text.split()),
            "extraction_quality":   quality,
            "processing_status":    "success",
            "processed_at":         datetime.now().isoformat(),
        }

        if analysis.get("author_detected"):
            detected = analysis["author_detected"]
            if "hawley" in detected.lower():
                update["is_primary_pastor"] = True
                update["author"] = detected

        doc.reference.update(update)
        fixed += 1
        time.sleep(0.3)

    print(f"\n{'='*50}")
    print(f"  REPROCESS COMPLETE")
    print(f"  Fixed:        {fixed}")
    print(f"  Still failed: {still_failed}")
    print(f"{'='*50}\n")

    if fixed > 0:
        print("Run 'python ingest.py --stats-only' to recompute stats.")

if __name__ == "__main__":
    main()

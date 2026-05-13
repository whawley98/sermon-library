#!/usr/bin/env python3
"""
enrich_sermons.py
=================
Phase 2 of 2: Enrich uploaded sermons with Claude AI analysis.

What this does:
  - Reads sermons with processing_status = "pending" from Firestore
  - For each sermon (one at a time, never in bulk):
      Phase 1: Claude call → title, author, summary, keywords, structure
      Phase 2: Claude call → all scripture references
  - Updates the sermon document with metadata
  - Writes scripture references to /scripture_references collection
  - Marks sermon as processing_status = "success"
  - Indexes sermon to Algolia
  - Detects series after all enrichment is done

Write strategy:
  - One sermon at a time (no batch pressure on Firestore)
  - 1 second sleep between sermons
  - Retry with exponential backoff on quota errors

Usage:
  python enrich_sermons.py              # Process all pending sermons
  python enrich_sermons.py --limit 50   # Process only first 50 (for testing)
  python enrich_sermons.py --stats-only # Only recompute stats

Run from the scripts folder. Fully resumable — re-running skips already-done sermons.
"""

import sys, json, time, argparse
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

# ── Dependency bootstrap ───────────────────────────────────────────────────────
def ensure_deps():
    import subprocess
    for pip, imp in [
        ("anthropic",      "anthropic"),
        ("firebase-admin", "firebase_admin"),
        ("tqdm",           "tqdm"),
        ("requests",       "requests"),
    ]:
        try:
            __import__(imp)
        except ImportError:
            print(f"Installing {pip}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pip, "-q"])

ensure_deps()

import anthropic, firebase_admin, requests
from firebase_admin import credentials, firestore
from tqdm import tqdm
from shared import (
    FIREBASE_CREDS, DEFAULT_PASTOR_NAME,
    make_logger, load_api_key, sanitize,
    resolve_author, normalize_book, get_osis_ref,
    is_hawley_name,
)

# ── Configuration ──────────────────────────────────────────────────────────────
ALGOLIA_APP_ID     = "A4149APL2C"
ALGOLIA_WRITE_KEY  = "3c79ff84634df740423519749e1c94a8"
ALGOLIA_INDEX_NAME = "sermons"

MAX_TEXT_PHASE1    = 3000   # chars sent to Claude for metadata
MAX_TEXT_PHASE2    = 5000   # chars sent to Claude for scripture refs
MAX_RETRIES        = 3
SERMON_SLEEP       = 1.0    # seconds between sermons

log = make_logger("enrich", "enrich.log")

# ── Firebase ───────────────────────────────────────────────────────────────────
def init_firebase():
    if not Path(FIREBASE_CREDS).exists():
        log.error(f"Firebase credentials not found: {FIREBASE_CREDS}")
        sys.exit(1)
    cred = credentials.Certificate(FIREBASE_CREDS)
    firebase_admin.initialize_app(cred)
    return firestore.client()

def firestore_update_with_retry(ref, data, max_attempts=5):
    """Update a Firestore document with exponential backoff on quota errors."""
    for attempt in range(max_attempts):
        try:
            ref.update(data)
            return
        except Exception as e:
            if "429" in str(e) or "Quota" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait = 15 * (attempt + 1)
                log.warning(f"Firestore quota hit on update, waiting {wait}s...")
                time.sleep(wait)
                if attempt == max_attempts - 1:
                    raise
            else:
                raise

def write_scripture_refs_with_retry(db, sermon_id, pastor_id, refs, max_attempts=5):
    """Write scripture references to Firestore with retry."""
    if not refs:
        return

    for attempt in range(max_attempts):
        try:
            batch = db.batch()
            for r in refs:
                book     = normalize_book(r.get("book", ""))
                osis_ref = get_osis_ref(book, r.get("chapter", 0), r.get("verse_start", 0))
                ref_doc  = db.collection("scripture_references").document()
                batch.set(ref_doc, {
                    "sermon_id":   sermon_id,
                    "pastor_id":   pastor_id,
                    "reference":   r.get("reference", ""),
                    "book":        book,
                    "chapter":     r.get("chapter", 0),
                    "verse_start": r.get("verse_start", 0),
                    "verse_end":   r.get("verse_end", 0),
                    "context":     r.get("context", ""),
                    "osis_ref":    osis_ref,
                })
            batch.commit()
            return
        except Exception as e:
            if "429" in str(e) or "Quota" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait = 15 * (attempt + 1)
                log.warning(f"Firestore quota hit on refs, waiting {wait}s...")
                time.sleep(wait)
                if attempt == max_attempts - 1:
                    raise
            else:
                raise

# ── Claude Phase 1: Metadata ───────────────────────────────────────────────────
PHASE1_SYSTEM = """Analyze this sermon and return ONLY a valid JSON object.
Use ASCII characters only. No smart quotes. No backslash before apostrophes.
Keep all string values concise.

Return exactly this structure:
{"title":"sermon title","author_detected":null,"date_detected":null,"summary":"2-3 sentence summary","main_theme":"3-6 word theme","series_name":null,"structure":{"has_introduction":true,"main_points":["point 1","point 2"],"has_conclusion":true,"has_altar_call":false},"keywords":["faith","salvation","grace"],"estimated_length":"medium","notes":null}

estimated_length must be one of: short, medium, long, extended"""


def call_phase1(client, text, filename):
    """
    Extract sermon metadata via Claude.
    Returns (dict, status_str) — dict is None on failure.
    """
    if not text or len(text.strip()) < 80:
        return None, "text_too_short"

    safe    = sanitize(text[:MAX_TEXT_PHASE1])
    message = f"Filename: {filename}\n\nSermon text:\n{safe}"

    for attempt in range(MAX_RETRIES):
        try:
            resp   = client.messages.create(
                model      = "claude-haiku-4-5-20251001",
                max_tokens = 600,
                system     = PHASE1_SYSTEM,
                messages   = [{"role": "user", "content": message}],
            )
            raw    = resp.content[0].text.strip()
            # Extract JSON object
            start  = raw.find("{")
            end    = raw.rfind("}")
            if start == -1 or end <= start:
                raise ValueError("No JSON object found in response")
            raw    = raw[start:end + 1]
            raw    = raw.replace("\\'", "'")   # fix invalid JSON escape
            parsed = json.loads(raw)
            return parsed, "success"

        except json.JSONDecodeError as e:
            log.warning(f"Phase1 JSON error (attempt {attempt+1}) for {filename}: {e}")
            time.sleep(attempt + 1)

        except anthropic.RateLimitError:
            wait = 60 * (attempt + 1)
            log.warning(f"Claude rate limit, waiting {wait}s...")
            time.sleep(wait)

        except Exception as e:
            log.warning(f"Phase1 error (attempt {attempt+1}) for {filename}: {e}")
            time.sleep(2 * (attempt + 1))

    return None, "analysis_failed"


# ── Claude Phase 2: Scripture References ──────────────────────────────────────
PHASE2_SYSTEM = """Extract ALL Bible scripture references from this sermon text.
Return ONLY a valid JSON array. ASCII only. No smart quotes. No backslash apostrophes.
Keep context fields under 8 words.
If no references found, return an empty array: []

Return exactly this structure (repeat for each reference found):
[{"reference":"John 3:16","book":"John","chapter":3,"verse_start":16,"verse_end":16,"context":"God loved the world"},{"reference":"Romans 8:28","book":"Romans","chapter":8,"verse_start":28,"verse_end":28,"context":"all things work together"}]"""


def call_phase2(client, text, filename):
    """
    Extract all scripture references via Claude.
    Returns (list, status_str) — list is [] on failure.
    """
    if not text or len(text.strip()) < 80:
        return [], "text_too_short"

    safe    = sanitize(text[:MAX_TEXT_PHASE2])
    message = f"Filename: {filename}\n\nSermon text:\n{safe}"

    for attempt in range(MAX_RETRIES):
        try:
            resp   = client.messages.create(
                model      = "claude-haiku-4-5-20251001",
                max_tokens = 2000,
                system     = PHASE2_SYSTEM,
                messages   = [{"role": "user", "content": message}],
            )
            raw    = resp.content[0].text.strip()
            # Extract JSON array
            start  = raw.find("[")
            end    = raw.rfind("]")
            if start == -1 or end <= start:
                return [], "no_references_found"
            raw    = raw[start:end + 1]
            raw    = raw.replace("\\'", "'")
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed, "success"
            return [], "invalid_format"

        except json.JSONDecodeError as e:
            log.warning(f"Phase2 JSON error (attempt {attempt+1}) for {filename}: {e}")
            time.sleep(attempt + 1)

        except anthropic.RateLimitError:
            wait = 60 * (attempt + 1)
            log.warning(f"Claude rate limit, waiting {wait}s...")
            time.sleep(wait)

        except Exception as e:
            log.warning(f"Phase2 error (attempt {attempt+1}) for {filename}: {e}")
            time.sleep(2 * (attempt + 1))

    return [], "analysis_failed"


# ── Algolia indexing ───────────────────────────────────────────────────────────
def algolia_index_sermon(doc, sermon_id):
    """Send one sermon to Algolia via REST API."""
    full_text = doc.get("full_text_raw", "") or ""
    record    = {
        "objectID":          sermon_id,
        "pastor_id":         doc.get("pastor_id", ""),
        "title":             doc.get("title", ""),
        "author":            doc.get("author", ""),
        "is_primary_pastor": doc.get("is_primary_pastor", False),
        "summary":           doc.get("summary", ""),
        "main_theme":        doc.get("main_theme", ""),
        "keywords":          doc.get("keywords", []),
        "bible_books":       doc.get("bible_books", []),
        "folder":            doc.get("folder", ""),
        "date":              doc.get("date", ""),
        "decade":            doc.get("decade", ""),
        "estimated_length":  doc.get("estimated_length", ""),
        "word_count":        doc.get("word_count", 0),
        "web_url":           doc.get("web_url", ""),
        "full_text_snippet": full_text[:8000],
    }
    url     = f"https://{ALGOLIA_APP_ID}.algolia.net/1/indexes/{ALGOLIA_INDEX_NAME}"
    headers = {
        "X-Algolia-Application-Id": ALGOLIA_APP_ID,
        "X-Algolia-API-Key":        ALGOLIA_WRITE_KEY,
        "Content-Type":             "application/json",
    }
    try:
        r = requests.post(url, headers=headers, json=record, timeout=10)
        r.raise_for_status()
    except Exception as e:
        log.warning(f"Algolia index failed for {sermon_id}: {e}")


def configure_algolia():
    """Set Algolia index settings once at startup."""
    url     = f"https://{ALGOLIA_APP_ID}.algolia.net/1/indexes/{ALGOLIA_INDEX_NAME}/settings"
    headers = {
        "X-Algolia-Application-Id": ALGOLIA_APP_ID,
        "X-Algolia-API-Key":        ALGOLIA_WRITE_KEY,
        "Content-Type":             "application/json",
    }
    settings = {
        "searchableAttributes": [
            "title", "summary", "main_theme",
            "keywords", "author", "full_text_snippet",
        ],
        "attributesForFaceting": [
            "author", "is_primary_pastor", "folder",
            "decade", "keywords", "bible_books",
        ],
        "customRanking": ["desc(word_count)"],
    }
    try:
        r = requests.put(url, headers=headers, json=settings, timeout=10)
        r.raise_for_status()
        log.info("Algolia index settings configured")
    except Exception as e:
        log.warning(f"Algolia settings failed: {e}")


# ── Series detection ───────────────────────────────────────────────────────────
def detect_and_write_series(db, pastor_id):
    """
    After all enrichment, group numbered sermons into series documents.
    Updates each sermon doc with its series_id.
    """
    log.info("Detecting sermon series...")
    docs    = list(db.collection("sermons").where("pastor_id", "==", pastor_id).stream())
    sermons = [{"id": d.id, **d.to_dict()} for d in docs]

    groups = defaultdict(list)
    for s in sermons:
        if s.get("series_number") is not None:
            folder     = s.get("folder") or "root"
            sname      = s.get("series_name") or folder
            key        = f"{folder}::{sname}"
            groups[key].append(s)
        elif s.get("series_name"):
            groups[f"named::{s['series_name']}"].append(s)

    written = 0
    for key, group in groups.items():
        if len(group) < 2:
            continue
        dates      = [s.get("date") for s in group if s.get("date")]
        sermon_ids = [s["id"] for s in group]
        sname      = group[0].get("series_name") or key.split("::")[-1]

        ref = db.collection("series").document()
        ref.set({
            "pastor_id":    pastor_id,
            "name":         sname,
            "sermon_ids":   sermon_ids,
            "sermon_count": len(group),
            "folder":       group[0].get("folder"),
            "date_start":   min(dates) if dates else None,
            "date_end":     max(dates) if dates else None,
            "created_at":   datetime.now().isoformat(),
        })
        series_id = ref.id

        # Update each sermon with series_id
        for s in group:
            db.collection("sermons").document(s["id"]).update({"series_id": series_id})

        written += 1

    log.info(f"Wrote {written} series")


# ── Stats ──────────────────────────────────────────────────────────────────────
def compute_and_write_stats(db, pastor_id):
    log.info("Computing stats...")
    sermons  = [d.to_dict() for d in
                db.collection("sermons").where("pastor_id", "==", pastor_id).stream()]
    refs     = [d.to_dict() for d in
                db.collection("scripture_references").where("pastor_id", "==", pastor_id).stream()]

    keywords = []
    primary  = other = 0
    decades  = defaultdict(int)

    for s in sermons:
        if s.get("is_primary_pastor"):
            primary += 1
        else:
            other += 1
        keywords.extend(s.get("keywords") or [])
        if s.get("decade"):
            decades[s["decade"]] += 1

    books  = [normalize_book(r.get("book", "")) for r in refs if r.get("book")]
    verses = [r.get("reference", "") for r in refs if r.get("reference")]

    stats = {
        "pastor_id":             pastor_id,
        "total_sermons":         len(sermons),
        "william_hawley_count":  primary,
        "other_preachers_count": other,
        "total_references":      len(refs),
        "top_keywords":    [{"word": w, "count": c} for w, c in Counter(keywords).most_common(30)],
        "top_bible_books": [{"book": b, "count": c} for b, c in Counter(books).most_common(66)],
        "top_verses":      [{"reference": v, "count": c} for v, c in Counter(verses).most_common(20)],
        "sermons_by_decade": dict(decades),
        "computed_at":     datetime.now().isoformat(),
    }
    db.collection("stats").document(pastor_id).set(stats)
    db.collection("stats").document("global").set(stats, merge=True)
    log.info(
        f"Stats: {len(sermons)} sermons, {len(refs)} refs, "
        f"{len(set(books))} Bible books"
    )


# ── Main ───────────────────────────────────────────────────────────────────────
def main(args):
    pastor_name = args.pastor or DEFAULT_PASTOR_NAME

    api_key = load_api_key()
    if not api_key:
        print("ERROR: Anthropic API key not found.")
        print(f"Create a file named 'API Key.txt' in the scripts folder.")
        sys.exit(1)

    log.info("Initializing Firebase...")
    db = init_firebase()

    # Stats-only mode
    if args.stats_only:
        existing = list(
            db.collection("pastors").where("name", "==", pastor_name).limit(1).stream()
        )
        if existing:
            compute_and_write_stats(db, existing[0].id)
        else:
            print(f"Pastor not found: {pastor_name}")
        return

    log.info("Configuring Algolia...")
    configure_algolia()

    log.info("Initializing Anthropic client...")
    ai = anthropic.Anthropic(api_key=api_key)

    # Find pastor
    existing = list(
        db.collection("pastors").where("name", "==", pastor_name).limit(1).stream()
    )
    if not existing:
        print(f"ERROR: Pastor '{pastor_name}' not found in Firestore.")
        print("Run upload_sermons.py first.")
        sys.exit(1)
    pastor_id = existing[0].id
    log.info(f"Pastor: {pastor_name} ({pastor_id})")

    # Fetch pending sermons
    log.info("Fetching pending sermons from Firestore...")
    query = (
        db.collection("sermons")
        .where("pastor_id",         "==", pastor_id)
        .where("processing_status", "==", "pending")
    )
    pending_docs = list(query.stream())
    log.info(f"Found {len(pending_docs)} pending sermons")

    if not pending_docs:
        log.info("No pending sermons — running stats and series detection.")
        detect_and_write_series(db, pastor_id)
        compute_and_write_stats(db, pastor_id)
        return

    # Apply limit if set
    if args.limit and args.limit > 0:
        pending_docs = pending_docs[:args.limit]
        log.info(f"Limiting to {len(pending_docs)} sermons (--limit)")

    success_count  = 0
    failed_count   = 0
    failed_files   = []

    for doc_snap in tqdm(pending_docs, desc="Enriching sermons", unit="sermon"):
        sermon_id = doc_snap.id
        data      = doc_snap.to_dict()
        filename  = data.get("filename", "unknown")
        ref       = db.collection("sermons").document(sermon_id)

        try:
            raw_text = data.get("full_text_raw", "")

            # ── Phase 1: Metadata ──────────────────────────────────────────────
            meta, status1 = call_phase1(ai, raw_text, filename)
            time.sleep(0.3)

            # ── Phase 2: Scripture References ──────────────────────────────────
            refs, status2 = call_phase2(ai, raw_text, filename)
            time.sleep(0.3)

            # ── Resolve author ─────────────────────────────────────────────────
            detected_author = (meta or {}).get("author_detected")
            author, is_primary = resolve_author(data, detected_author, pastor_name)

            # ── Normalize references ───────────────────────────────────────────
            for r in refs:
                r["book"] = normalize_book(r.get("book", ""))

            bible_books = list({r["book"] for r in refs if r.get("book")})

            # ── Build update dict ──────────────────────────────────────────────
            title      = (meta or {}).get("title") or data.get("title", filename)
            date_str   = (meta or {}).get("date_detected") or data.get("date")
            year       = data.get("year")
            decade     = data.get("decade")

            # Derive year/decade from detected date if not already set
            if date_str and not year:
                try:
                    from datetime import datetime as _dt
                    dt     = _dt.strptime(date_str, "%Y-%m-%d")
                    year   = dt.year
                    decade = f"{(year // 10) * 10}s"
                except Exception:
                    pass

            update = {
                "title":               title,
                "title_lower":         title.lower(),
                "author":              author,
                "is_primary_pastor":   is_primary,
                "date":                date_str,
                "year":                year,
                "decade":              decade,
                "series_name":         (meta or {}).get("series_name"),
                "summary":             (meta or {}).get("summary", ""),
                "main_theme":          (meta or {}).get("main_theme", ""),
                "structure":           (meta or {}).get("structure", {}),
                "keywords":            (meta or {}).get("keywords", []),
                "bible_books":         bible_books,
                "estimated_length":    (meta or {}).get("estimated_length", "unknown"),
                "notes":               (meta or {}).get("notes"),
                "scripture_ref_count": len(refs),
                "processing_status":   "success",
                "processed_at":        datetime.now().isoformat(),
            }

            # ── Write to Firestore ─────────────────────────────────────────────
            firestore_update_with_retry(ref, update)
            write_scripture_refs_with_retry(db, sermon_id, pastor_id, refs)

            # ── Index to Algolia ───────────────────────────────────────────────
            algolia_index_sermon({**data, **update}, sermon_id)

            success_count += 1
            log.debug(f"OK: {filename} ({len(refs)} refs)")

        except Exception as e:
            log.error(f"FAILED: {filename} — {e}")
            failed_count += 1
            failed_files.append({"filename": filename, "sermon_id": sermon_id, "error": str(e)})
            # Mark as failed so we can retry
            try:
                ref.update({"processing_status": "failed"})
            except Exception:
                pass

        time.sleep(SERMON_SLEEP)

    # ── Post-processing ────────────────────────────────────────────────────────
    log.info("Running series detection...")
    detect_and_write_series(db, pastor_id)

    log.info("Computing stats...")
    compute_and_write_stats(db, pastor_id)

    print(f"\n{'='*60}")
    print(f"  ENRICHMENT COMPLETE")
    print(f"  Success: {success_count}")
    print(f"  Failed:  {failed_count}")
    print(f"{'='*60}\n")

    if failed_files:
        with open("enrich_errors.json", "w") as f:
            json.dump(failed_files, f, indent=2)
        print("Failed files saved to: enrich_errors.json")
        print("Re-run enrich_sermons.py to retry failed sermons.")
        print("(Failed sermons are marked 'failed' — re-run will reprocess them)")

    if failed_count > 0:
        # Reset failed sermons to pending so next run retries them
        log.info(f"Resetting {failed_count} failed sermons to 'pending'...")
        for ff in failed_files:
            try:
                db.collection("sermons").document(ff["sermon_id"]).update(
                    {"processing_status": "pending"}
                )
            except Exception:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Enrich uploaded sermons with Claude AI analysis"
    )
    parser.add_argument("--pastor",     help=f"Pastor name (default: {DEFAULT_PASTOR_NAME})")
    parser.add_argument("--limit",      type=int, default=0,
                        help="Only process this many sermons (for testing)")
    parser.add_argument("--stats-only", action="store_true", dest="stats_only",
                        help="Only recompute stats and series, no Claude calls")
    args = parser.parse_args()
    main(args)

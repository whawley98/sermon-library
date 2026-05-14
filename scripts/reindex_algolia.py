#!/usr/bin/env python3
"""
reindex_algolia.py
==================
Reads all enriched sermons from Firestore and pushes them to Algolia.
Run this after enrich_sermons.py completes since Algolia indexing
failed during enrichment due to API endpoint issues.

Usage:
    python reindex_algolia.py

Takes about 2-3 minutes for 1,041 sermons.
"""

import sys, time, json
from pathlib import Path

def ensure_deps():
    import subprocess
    for pip, imp in [("firebase-admin","firebase_admin"),("requests","requests"),("tqdm","tqdm")]:
        try: __import__(imp)
        except ImportError:
            subprocess.check_call([sys.executable,"-m","pip","install",pip,"-q"])

ensure_deps()

import firebase_admin, requests
from firebase_admin import credentials, firestore
from tqdm import tqdm

FIREBASE_CREDS      = "firebase-credentials.json"
ALGOLIA_APP_ID      = "A4149APL2C"
ALGOLIA_WRITE_KEY   = "3c79ff84634df740423519749e1c94a8"
ALGOLIA_INDEX_NAME  = "sermons"
BATCH_SIZE          = 100   # Algolia batch size (their limit is 1000 objects per batch)

def init_firebase():
    cred = credentials.Certificate(FIREBASE_CREDS)
    firebase_admin.initialize_app(cred)
    return firestore.client()

def algolia_headers():
    return {
        "X-Algolia-Application-Id": ALGOLIA_APP_ID,
        "X-Algolia-API-Key":        ALGOLIA_WRITE_KEY,
        "Content-Type":             "application/json",
    }

def configure_index():
    url      = f"https://{ALGOLIA_APP_ID}.algolia.net/1/indexes/{ALGOLIA_INDEX_NAME}/settings"
    settings = {
        "searchableAttributes": [
            "title",
            "summary",
            "main_theme",
            "keywords",
            "author",
            "full_text_snippet",
        ],
        "attributesForFaceting": [
            "filterOnly(pastor_id)",
            "author",
            "is_primary_pastor",
            "folder",
            "decade",
            "keywords",
            "bible_books",
        ],
        "customRanking": ["desc(word_count)"],
        "highlightPreTag":  "<mark>",
        "highlightPostTag": "</mark>",
    }
    r = requests.put(url, headers=algolia_headers(), json=settings, timeout=15)
    r.raise_for_status()
    print("✅ Algolia index configured")

def build_record(doc_id, data):
    full_text = data.get("full_text_raw", "") or ""
    return {
        "objectID":          doc_id,
        "pastor_id":         data.get("pastor_id", ""),
        "title":             data.get("title", ""),
        "author":            data.get("author", ""),
        "is_primary_pastor": data.get("is_primary_pastor", False),
        "summary":           data.get("summary", ""),
        "main_theme":        data.get("main_theme", ""),
        "keywords":          data.get("keywords", []),
        "bible_books":       data.get("bible_books", []),
        "folder":            data.get("folder", ""),
        "date":              data.get("date", ""),
        "year":              data.get("year"),
        "decade":            data.get("decade", ""),
        "estimated_length":  data.get("estimated_length", ""),
        "word_count":        data.get("word_count", 0),
        "web_url":           data.get("web_url", ""),
        "series_name":       data.get("series_name", ""),
        "full_text_snippet": full_text[:3000],
    }

def push_batch(records):
    """Push records individually using PUT with objectID in URL."""
    succeeded = 0
    failed    = 0
    for rec in records:
        object_id = rec.get("objectID")
        if not object_id:
            continue
        url = f"https://{ALGOLIA_APP_ID}.algolia.net/1/indexes/{ALGOLIA_INDEX_NAME}/{object_id}"
        sent = False
        for attempt in range(3):
            try:
                r = requests.put(url, headers=algolia_headers(), json=rec, timeout=15)
                r.raise_for_status()
                sent = True
                break
            except Exception:
                time.sleep(attempt + 1)
        if sent:
            succeeded += 1
        else:
            failed += 1
    if failed:
        print(f"\n  ⚠️  {failed}/{len(records)} records failed in this batch")
    return succeeded, failed

def main():
    print("\n" + "="*50)
    print("  ALGOLIA RE-INDEX")
    print(f"  Index: {ALGOLIA_INDEX_NAME}")
    print("="*50 + "\n")

    if not Path(FIREBASE_CREDS).exists():
        print(f"ERROR: {FIREBASE_CREDS} not found")
        sys.exit(1)

    print("Connecting to Firebase...")
    db = init_firebase()

    print("Configuring Algolia index settings...")
    try:
        configure_index()
    except Exception as e:
        print(f"Warning: Could not configure index: {e}")

    print("Fetching all enriched sermons from Firestore...")
    docs = list(
        db.collection("sermons")
        .where("processing_status", "==", "success")
        .stream()
    )
    print(f"Found {len(docs)} sermons to index\n")

    if not docs:
        print("No enriched sermons found.")
        return

    # Build records and push in batches
    records     = []
    total_sent  = 0
    total_failed = 0

    for doc in tqdm(docs, desc="Indexing", unit="sermon"):
        records.append(build_record(doc.id, doc.to_dict()))

        if len(records) >= BATCH_SIZE:
            sent, failed = push_batch(records)
            total_sent   += sent
            total_failed += failed
            records = []
            time.sleep(0.2)

    # Push remaining
    if records:
        sent, failed  = push_batch(records)
        total_sent   += sent
        total_failed += failed

    print(f"\n{'='*50}")
    print(f"  COMPLETE")
    print(f"  Indexed:  {total_sent}")
    print(f"  Failed:   {total_failed}")
    print(f"{'='*50}\n")

    if total_failed == 0:
        print("✅ All sermons indexed in Algolia")
        print(f"   App ID:    {ALGOLIA_APP_ID}")
        print(f"   Index:     {ALGOLIA_INDEX_NAME}")
        print(f"   Records:   {total_sent}")
    else:
        print("⚠️  Some batches failed — re-run to retry")

if __name__ == "__main__":
    main()

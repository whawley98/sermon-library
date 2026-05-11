#!/usr/bin/env python3
"""
diagnose.py — Check data quality in Firestore
Run from scripts folder: python diagnose.py
Writes results to diagnose_output.txt
"""

import sys, json
from pathlib import Path
from collections import Counter

import firebase_admin
from firebase_admin import credentials, firestore

FIREBASE_CREDENTIALS_PATH = "firebase-credentials.json"

def init_firebase():
    if not Path(FIREBASE_CREDENTIALS_PATH).exists():
        print(f"ERROR: {FIREBASE_CREDENTIALS_PATH} not found")
        sys.exit(1)
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)
    return firestore.client()

def main():
    print("Connecting to Firebase...")
    db = init_firebase()

    print("Fetching all sermons...")
    docs = list(db.collection("sermons").stream())
    print(f"Total documents: {len(docs)}")

    sermons = [d.to_dict() for d in docs]

    # ── Data quality checks ────────────────────────────────────────
    has_summary          = sum(1 for s in sermons if s.get("summary"))
    has_keywords         = sum(1 for s in sermons if s.get("keywords"))
    has_scripture        = sum(1 for s in sermons if s.get("scripture_references"))
    has_web_url          = sum(1 for s in sermons if s.get("web_url"))
    has_full_text        = sum(1 for s in sermons if s.get("full_text_raw") and len(s.get("full_text_raw","")) > 100)
    has_bible_books      = sum(1 for s in sermons if s.get("bible_books"))
    primary_pastor       = sum(1 for s in sermons if s.get("is_primary_pastor"))
    processing_success   = sum(1 for s in sermons if s.get("processing_status") == "success")
    processing_failed    = sum(1 for s in sermons if s.get("processing_status") == "analysis_failed")
    processing_short     = sum(1 for s in sermons if s.get("processing_status") == "text_too_short")

    # ── Bible books ────────────────────────────────────────────────
    all_books = []
    for s in sermons:
        all_books.extend(s.get("bible_books") or [])
    book_counter = Counter(all_books)

    # ── Keywords ───────────────────────────────────────────────────
    all_keywords = []
    for s in sermons:
        all_keywords.extend(s.get("keywords") or [])
    keyword_counter = Counter(all_keywords)

    # ── Authors ────────────────────────────────────────────────────
    author_counter = Counter(s.get("author","Unknown") for s in sermons)

    # ── Extraction quality ─────────────────────────────────────────
    quality_counter = Counter(s.get("extraction_quality","unknown") for s in sermons)

    # ── Sample of failed/short sermons ────────────────────────────
    failed_samples = [
        {"filename": s.get("filename"), "status": s.get("processing_status"), "quality": s.get("extraction_quality")}
        for s in sermons
        if s.get("processing_status") in ("analysis_failed", "text_too_short")
    ][:20]

    # ── Build report ───────────────────────────────────────────────
    report = {
        "total_sermons": len(sermons),
        "data_completeness": {
            "has_summary":       f"{has_summary}/{len(sermons)} ({100*has_summary//len(sermons)}%)",
            "has_keywords":      f"{has_keywords}/{len(sermons)} ({100*has_keywords//len(sermons)}%)",
            "has_scripture":     f"{has_scripture}/{len(sermons)} ({100*has_scripture//len(sermons)}%)",
            "has_bible_books":   f"{has_bible_books}/{len(sermons)} ({100*has_bible_books//len(sermons)}%)",
            "has_web_url":       f"{has_web_url}/{len(sermons)} ({100*has_web_url//len(sermons)}%)",
            "has_readable_text": f"{has_full_text}/{len(sermons)} ({100*has_full_text//len(sermons)}%)",
            "is_primary_pastor": f"{primary_pastor}/{len(sermons)} ({100*primary_pastor//len(sermons)}%)",
        },
        "processing_status": {
            "success":       processing_success,
            "failed":        processing_failed,
            "text_too_short": processing_short,
            "other":         len(sermons) - processing_success - processing_failed - processing_short,
        },
        "extraction_quality": dict(quality_counter.most_common()),
        "unique_bible_books": len(book_counter),
        "top_30_bible_books": book_counter.most_common(30),
        "unique_keywords":    len(keyword_counter),
        "top_30_keywords":    keyword_counter.most_common(30),
        "authors":            author_counter.most_common(20),
        "failed_samples":     failed_samples,
    }

    # ── Print summary ──────────────────────────────────────────────
    print("\n" + "="*60)
    print("  DIAGNOSTIC REPORT")
    print("="*60)
    print(f"\nTotal sermons: {len(sermons)}")
    print(f"\nData Completeness:")
    for k, v in report["data_completeness"].items():
        print(f"  {k:<25} {v}")
    print(f"\nProcessing Status:")
    for k, v in report["processing_status"].items():
        print(f"  {k:<25} {v}")
    print(f"\nExtraction Quality:")
    for k, v in report["extraction_quality"].items():
        print(f"  {k:<25} {v}")
    print(f"\nUnique Bible books referenced: {report['unique_bible_books']}")
    print(f"Top 10 books: {[b for b,_ in report['top_30_bible_books'][:10]]}")
    print(f"\nUnique keywords: {report['unique_keywords']}")
    print(f"Top 10 keywords: {[k for k,_ in report['top_30_keywords'][:10]]}")
    print(f"\nAuthors:")
    for author, count in report["authors"][:10]:
        print(f"  {author:<40} {count}")

    # ── Write full report ──────────────────────────────────────────
    with open("diagnose_output.txt", "w", encoding="utf-8") as f:
        f.write("SERMON LIBRARY DIAGNOSTIC REPORT\n")
        f.write("="*60 + "\n\n")
        f.write(json.dumps(report, indent=2))

    print(f"\nFull report written to: diagnose_output.txt")
    print("="*60)

if __name__ == "__main__":
    main()

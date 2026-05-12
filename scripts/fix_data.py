#!/usr/bin/env python3
"""
fix_data.py — Fix data quality issues in Firestore
====================================================
1. Marks William Hawley name variants as is_primary_pastor = True
2. Merges "Psalm" into "Psalms" in bible_books arrays
3. Recomputes stats after fixes

Run from scripts folder: python fix_data.py
"""

import sys, time
from pathlib import Path
from collections import Counter

import firebase_admin
from firebase_admin import credentials, firestore
from tqdm import tqdm

FIREBASE_CREDENTIALS_PATH = "firebase-credentials.json"

HAWLEY_NAME_VARIANTS = [
    "william hawley",
    "william o. hawley",
    "william o. hawley, sr.",
    "william o hawley",
    "w. hawley",
    "pastor hawley",
    "pastor william hawley",
    "bill hawley",
]

def init_firebase():
    if not Path(FIREBASE_CREDENTIALS_PATH).exists():
        print(f"ERROR: {FIREBASE_CREDENTIALS_PATH} not found")
        sys.exit(1)
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)
    return firestore.client()

def is_hawley_name(name):
    if not name:
        return False
    return any(variant in name.lower() for variant in HAWLEY_NAME_VARIANTS)

def normalize_bible_books(books):
    if not books:
        return books
    normalized = []
    seen = set()
    for book in books:
        # Normalize Psalm -> Psalms
        b = "Psalms" if book.lower() in ("psalm", "psalms") else book
        if b not in seen:
            seen.add(b)
            normalized.append(b)
    return normalized

def main():
    print("Connecting to Firebase...")
    db = init_firebase()

    print("Fetching all sermon documents...")
    docs = list(db.collection("sermons").stream())
    print(f"Total documents: {len(docs)}")

    # ── Pass 1: Find documents needing fixes ──────────────────────
    to_fix_hawley = []
    to_fix_psalm  = []

    for doc in docs:
        data     = doc.to_dict()
        author   = data.get("author", "")
        is_primary = data.get("is_primary_pastor", False)
        books    = data.get("bible_books", [])

        # Check Hawley name variants not yet marked as primary
        if not is_primary and is_hawley_name(author):
            to_fix_hawley.append(doc)

        # Check for Psalm/Psalms mismatch
        if books and any(b.lower() == "psalm" for b in books):
            to_fix_psalm.append(doc)

    print(f"\nDocuments needing fixes:")
    print(f"  Hawley name variants not marked primary: {len(to_fix_hawley)}")
    print(f"  Psalm/Psalms normalization needed:       {len(to_fix_psalm)}")

    total_fixes = len(to_fix_hawley) + len(to_fix_psalm)
    if total_fixes == 0:
        print("\n✅ No fixes needed!")
        return

    # ── Pass 2: Apply fixes in batches ────────────────────────────
    print(f"\nApplying fixes...")

    batch       = db.batch()
    batch_count = 0
    fixed       = 0

    # Fix Hawley variants
    for doc in tqdm(to_fix_hawley, desc="Fixing Hawley names"):
        batch.update(doc.reference, {"is_primary_pastor": True})
        batch_count += 1
        fixed += 1
        if batch_count >= 400:
            batch.commit()
            batch = db.batch()
            batch_count = 0
            time.sleep(0.3)

    # Fix Psalm/Psalms
    for doc in tqdm(to_fix_psalm, desc="Normalizing Psalms"):
        data  = doc.to_dict()
        books = normalize_bible_books(data.get("bible_books", []))
        batch.update(doc.reference, {"bible_books": books})
        batch_count += 1
        fixed += 1
        if batch_count >= 400:
            batch.commit()
            batch = db.batch()
            batch_count = 0
            time.sleep(0.3)

    if batch_count > 0:
        batch.commit()

    print(f"\n✅ Fixed {fixed} documents")

    # ── Pass 3: Recompute stats ────────────────────────────────────
    print("\nRecomputing stats...")

    # Get pastor ID
    pastors = list(db.collection("pastors").stream())
    if not pastors:
        print("No pastors found, skipping stats update")
        return

    pastor_id = pastors[0].id
    pastor_name = pastors[0].to_dict().get("name", "Unknown")
    print(f"Pastor: {pastor_name} (id: {pastor_id})")

    # Fetch all updated sermons
    all_docs = list(db.collection("sermons").stream())
    sermons  = [d.to_dict() for d in all_docs]

    keywords = []
    books    = []
    primary  = 0
    other    = 0

    for s in sermons:
        if s.get("is_primary_pastor"):
            primary += 1
        else:
            other += 1
        keywords.extend(s.get("keywords") or [])
        books.extend(s.get("bible_books") or [])

    top_keywords = Counter(keywords).most_common(30)
    top_books    = Counter(books).most_common(66)

    stats = {
        "pastor_id":             pastor_id,
        "total_sermons":         len(sermons),
        "william_hawley_count":  primary,
        "other_preachers_count": other,
        "top_keywords":    [{"word": w, "count": c} for w, c in top_keywords],
        "top_bible_books": [{"book": b, "count": c} for b, c in Counter(books).most_common(66)],
    }

    db.collection("stats").document(pastor_id).set(stats)
    db.collection("stats").document("global").set(stats, merge=True)

    print(f"\n{'='*50}")
    print(f"  COMPLETE")
    print(f"  William Hawley sermons: {primary}")
    print(f"  Other preachers:        {other}")
    print(f"  Unique Bible books:     {len(set(books))}")
    print(f"  Unique keywords:        {len(set(keywords))}")
    print(f"  Top 5 books: {[b for b,_ in top_books[:5]]}")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    main()

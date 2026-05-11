#!/usr/bin/env python3
"""
cleanup.py — Wipe all sermon data from Firestore
=================================================
Deletes all documents in pastors, sermons, and stats collections.
Run this before a fresh ingestion to start clean.

Usage:
    python cleanup.py
    python cleanup.py --confirm    (skip the confirmation prompt)
"""

import sys
import argparse
from pathlib import Path

# ── Firebase init ─────────────────────────────────────────────
import firebase_admin
from firebase_admin import credentials, firestore

FIREBASE_CREDENTIALS_PATH = "firebase-credentials.json"

def init_firebase():
    if not Path(FIREBASE_CREDENTIALS_PATH).exists():
        print(f"❌ Firebase credentials not found: {FIREBASE_CREDENTIALS_PATH}")
        sys.exit(1)
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)
    return firestore.client()

# ── Delete a collection in batches ────────────────────────────
def delete_collection(db, collection_name, batch_size=100):
    col_ref = db.collection(collection_name)
    deleted = 0
    while True:
        docs = list(col_ref.limit(batch_size).stream())
        if not docs:
            break
        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()
        deleted += len(docs)
        print(f"  Deleted {deleted} documents from {collection_name}...", end="\r")
    print(f"  ✅ {collection_name}: {deleted} documents deleted          ")
    return deleted

# ── Main ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Wipe Firestore sermon data")
    parser.add_argument("--confirm", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    print("\n" + "="*50)
    print("  FIRESTORE CLEANUP")
    print("  Project: sermon-library-89f46")
    print("="*50)
    print("\nThis will delete ALL data in:")
    print("  - pastors")
    print("  - sermons")
    print("  - stats")

    if not args.confirm:
        answer = input("\nType YES to confirm: ").strip()
        if answer != "YES":
            print("Cancelled.")
            sys.exit(0)

    print("\nConnecting to Firebase...")
    db = init_firebase()

    for collection in ["sermons", "pastors", "stats"]:
        delete_collection(db, collection)

    print("\n✅ Firestore is clean. Ready for fresh ingestion.")
    print("   Run: python ingest.py\n")

if __name__ == "__main__":
    main()

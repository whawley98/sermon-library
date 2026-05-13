#!/usr/bin/env python3
"""
load_kjv.py - Load KJV Bible into Firestore
Downloads all 66 books individually from public domain source.
Run once: python load_kjv.py
"""

import sys, json, time
from pathlib import Path

def ensure_deps():
    import subprocess
    for pip, imp in [("firebase-admin","firebase_admin"),("requests","requests")]:
        try: __import__(imp)
        except ImportError:
            subprocess.check_call([sys.executable,"-m","pip","install",pip,"-q"])

ensure_deps()

import requests, firebase_admin
from firebase_admin import credentials, firestore

FIREBASE_CREDENTIALS_PATH = "firebase-credentials.json"

# All 66 canonical book names mapped to their file names in the repo
BOOKS = [
    ("Genesis","Genesis"),("Exodus","Exodus"),("Leviticus","Leviticus"),
    ("Numbers","Numbers"),("Deuteronomy","Deuteronomy"),("Joshua","Joshua"),
    ("Judges","Judges"),("Ruth","Ruth"),("1 Samuel","1Samuel"),
    ("2 Samuel","2Samuel"),("1 Kings","1Kings"),("2 Kings","2Kings"),
    ("1 Chronicles","1Chronicles"),("2 Chronicles","2Chronicles"),
    ("Ezra","Ezra"),("Nehemiah","Nehemiah"),("Esther","Esther"),
    ("Job","Job"),("Psalms","Psalms"),("Proverbs","Proverbs"),
    ("Ecclesiastes","Ecclesiastes"),("Song of Solomon","SongofSolomon"),
    ("Isaiah","Isaiah"),("Jeremiah","Jeremiah"),("Lamentations","Lamentations"),
    ("Ezekiel","Ezekiel"),("Daniel","Daniel"),("Hosea","Hosea"),
    ("Joel","Joel"),("Amos","Amos"),("Obadiah","Obadiah"),("Jonah","Jonah"),
    ("Micah","Micah"),("Nahum","Nahum"),("Habakkuk","Habakkuk"),
    ("Zephaniah","Zephaniah"),("Haggai","Haggai"),("Zechariah","Zechariah"),
    ("Malachi","Malachi"),("Matthew","Matthew"),("Mark","Mark"),
    ("Luke","Luke"),("John","John"),("Acts","Acts"),("Romans","Romans"),
    ("1 Corinthians","1Corinthians"),("2 Corinthians","2Corinthians"),
    ("Galatians","Galatians"),("Ephesians","Ephesians"),
    ("Philippians","Philippians"),("Colossians","Colossians"),
    ("1 Thessalonians","1Thessalonians"),("2 Thessalonians","2Thessalonians"),
    ("1 Timothy","1Timothy"),("2 Timothy","2Timothy"),("Titus","Titus"),
    ("Philemon","Philemon"),("Hebrews","Hebrews"),("James","James"),
    ("1 Peter","1Peter"),("2 Peter","2Peter"),("1 John","1John"),
    ("2 John","2John"),("3 John","3John"),("Jude","Jude"),
    ("Revelation","Revelation"),
]

BOOK_TO_OSIS = {
    "Genesis":"Gen","Exodus":"Exod","Leviticus":"Lev","Numbers":"Num",
    "Deuteronomy":"Deut","Joshua":"Josh","Judges":"Judg","Ruth":"Ruth",
    "1 Samuel":"1Sam","2 Samuel":"2Sam","1 Kings":"1Kgs","2 Kings":"2Kgs",
    "1 Chronicles":"1Chr","2 Chronicles":"2Chr","Ezra":"Ezra","Nehemiah":"Neh",
    "Esther":"Esth","Job":"Job","Psalms":"Ps","Proverbs":"Prov",
    "Ecclesiastes":"Eccl","Song of Solomon":"Song","Isaiah":"Isa",
    "Jeremiah":"Jer","Lamentations":"Lam","Ezekiel":"Ezek","Daniel":"Dan",
    "Hosea":"Hos","Joel":"Joel","Amos":"Amos","Obadiah":"Obad","Jonah":"Jonah",
    "Micah":"Mic","Nahum":"Nah","Habakkuk":"Hab","Zephaniah":"Zeph",
    "Haggai":"Hag","Zechariah":"Zech","Malachi":"Mal",
    "Matthew":"Matt","Mark":"Mark","Luke":"Luke","John":"John","Acts":"Acts",
    "Romans":"Rom","1 Corinthians":"1Cor","2 Corinthians":"2Cor",
    "Galatians":"Gal","Ephesians":"Eph","Philippians":"Phil",
    "Colossians":"Col","1 Thessalonians":"1Thess","2 Thessalonians":"2Thess",
    "1 Timothy":"1Tim","2 Timothy":"2Tim","Titus":"Titus","Philemon":"Phlm",
    "Hebrews":"Heb","James":"Jas","1 Peter":"1Pet","2 Peter":"2Pet",
    "1 John":"1John","2 John":"2John","3 John":"3John","Jude":"Jude",
    "Revelation":"Rev",
}

OT_BOOKS = {b for b,_ in BOOKS[:39]}

BASE_URL = "https://raw.githubusercontent.com/aruljohn/Bible-kjv/master"

def download_book(book_name, file_name):
    url = f"{BASE_URL}/{file_name}.json"
    r   = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()

def parse_book(book_name, data):
    """Parse a single book JSON into verse records.
    Format: {"book": "John", "chapters": [{"chapter": 1, "verses": [{"verse": 1, "text": "..."}]}]}
    """
    verses   = []
    chapters = data.get("chapters", [])
    order    = [b for b,_ in BOOKS].index(book_name) + 1 if book_name in [b for b,_ in BOOKS] else 0
    osis_book = BOOK_TO_OSIS.get(book_name, book_name.replace(" ",""))
    testament = "OT" if book_name in OT_BOOKS else "NT"

    for chap_data in chapters:
        chap_num   = chap_data.get("chapter", 0)
        verse_list = chap_data.get("verses", [])
        for v in verse_list:
            verse_num = v.get("verse", 0)
            text      = v.get("text", "").strip()
            osis_ref  = f"{osis_book}.{chap_num}.{verse_num}"
            reference = f"{book_name} {chap_num}:{verse_num}"
            verses.append({
                "osis_ref":  osis_ref,
                "reference": reference,
                "book":      book_name,
                "chapter":   chap_num,
                "verse":     verse_num,
                "text":      text,
                "book_order": order,
                "testament": testament,
            })
    return verses

def main():
    print("\n" + "="*50)
    print("  KJV BIBLE LOADER")
    print("  Source: 1769 Blayney KJV (public domain)")
    print("="*50 + "\n")

    if not Path(FIREBASE_CREDENTIALS_PATH).exists():
        print(f"ERROR: {FIREBASE_CREDENTIALS_PATH} not found")
        sys.exit(1)

    print("Connecting to Firebase...")
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    # Check if already loaded
    sample = db.collection("kjv").document("John.3.16").get()
    if sample.exists:
        answer = input("KJV already loaded. Re-load? (YES to confirm): ").strip()
        if answer != "YES":
            print("Skipped.")
            return

    all_verses = []
    print(f"Downloading {len(BOOKS)} books...")

    for book_name, file_name in BOOKS:
        try:
            data   = download_book(book_name, file_name)
            verses = parse_book(book_name, data)
            all_verses.extend(verses)
            print(f"  {book_name}: {len(verses)} verses", end="\r")
        except Exception as e:
            print(f"  ERROR {book_name}: {e}")

    print(f"\nTotal verses parsed: {len(all_verses)}")

    # Load to Firestore in batches
    print("Loading to Firestore...")
    batch  = db.batch()
    count  = 0
    total  = 0
    for verse in all_verses:
        ref = db.collection("kjv").document(verse["osis_ref"])
        batch.set(ref, verse)
        count += 1
        total += 1
        if count >= 400:
            batch.commit()
            batch = db.batch()
            count = 0
            print(f"  {total}/{len(all_verses)} verses loaded...", end="\r")
            time.sleep(0.1)
    if count > 0:
        batch.commit()

    print(f"\n✅ Loaded {total} verses")

    # Verify
    print("\nVerifying:")
    checks = [
        ("John.3.16",  "For God so loved"),
        ("Ps.23.1",    "LORD is my shepherd"),
        ("Gen.1.1",    "In the beginning"),
        ("Rom.8.28",   "all things work together"),
    ]
    for osis_ref, fragment in checks:
        doc = db.collection("kjv").document(osis_ref).get()
        if doc.exists:
            text = doc.to_dict().get("text","")
            ok = "✅" if fragment.lower() in text.lower() else "⚠️"
            print(f"  {ok} {osis_ref}: {text[:70]}")
        else:
            print(f"  ❌ {osis_ref}: NOT FOUND")

    print("\nDone! KJV loaded at /kjv/{osis_ref}")

if __name__ == "__main__":
    main()

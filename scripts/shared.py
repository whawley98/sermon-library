#!/usr/bin/env python3
"""
shared.py - Shared utilities for upload_sermons.py and enrich_sermons.py
"""

import os, io, re, logging
from pathlib import Path
from datetime import datetime

# mammoth and PyPDF2 imported lazily inside extraction functions

# ── Paths ──────────────────────────────────────────────────────────────────────
LOCAL_BASE_PATH = r"C:\Users\WilliamHawley\OneDrive - Juhls\Dad's Files\Sermons1"
CONVERTED_DIR   = r"C:\Users\WilliamHawley\Documents\Personal\sermon-library\converted_sermons"
FIREBASE_CREDS  = "firebase-credentials.json"
API_KEY_FILE    = "API Key.txt"

# ── Pastor / folder config ─────────────────────────────────────────────────────
DEFAULT_PASTOR_NAME = "William Hawley"
DEFAULT_PASTOR_DESC = "40 years of faithful preaching"

OTHER_PREACHER_FOLDERS = {
    "billy sunday":  "Billy Sunday",
    "chapman":       "J. Wilbur Chapman",
    "hughes":        "Hughes",
    "johnston":      "Johnston",
    "illustrations": None,   # skip
}
PRIMARY_PASTOR_FOLDERS = {"franklin sermons", "fbis - cloud", "browning"}
HAWLEY_NAME_VARIANTS   = [
    "william hawley", "william o. hawley", "william o. hawley, sr.",
    "william o hawley", "w. hawley", "pastor hawley",
    "pastor william hawley", "bill hawley",
]

SERMON_EXTENSIONS = {".doc", ".docx", ".pdf", ".txt", ".htm", ".html"}

# ── OSIS book map ──────────────────────────────────────────────────────────────
BOOK_TO_OSIS = {
    "genesis":"Gen","exodus":"Exod","leviticus":"Lev","numbers":"Num",
    "deuteronomy":"Deut","joshua":"Josh","judges":"Judg","ruth":"Ruth",
    "1 samuel":"1Sam","2 samuel":"2Sam","1 kings":"1Kgs","2 kings":"2Kgs",
    "1 chronicles":"1Chr","2 chronicles":"2Chr","ezra":"Ezra","nehemiah":"Neh",
    "esther":"Esth","job":"Job","psalms":"Ps","psalm":"Ps","proverbs":"Prov",
    "ecclesiastes":"Eccl","song of solomon":"Song","isaiah":"Isa",
    "jeremiah":"Jer","lamentations":"Lam","ezekiel":"Ezek","daniel":"Dan",
    "hosea":"Hos","joel":"Joel","amos":"Amos","obadiah":"Obad","jonah":"Jonah",
    "micah":"Mic","nahum":"Nah","habakkuk":"Hab","zephaniah":"Zeph",
    "haggai":"Hag","zechariah":"Zech","malachi":"Mal",
    "matthew":"Matt","mark":"Mark","luke":"Luke","john":"John","acts":"Acts",
    "romans":"Rom","1 corinthians":"1Cor","2 corinthians":"2Cor",
    "galatians":"Gal","ephesians":"Eph","philippians":"Phil",
    "colossians":"Col","1 thessalonians":"1Thess","2 thessalonians":"2Thess",
    "1 timothy":"1Tim","2 timothy":"2Tim","titus":"Titus","philemon":"Phlm",
    "hebrews":"Heb","james":"Jas","1 peter":"1Pet","2 peter":"2Pet",
    "1 john":"1John","2 john":"2John","3 john":"3John","jude":"Jude",
    "revelation":"Rev",
}

# ── Logging ────────────────────────────────────────────────────────────────────
def make_logger(name, logfile):
    log = logging.getLogger(name)
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        "%Y-%m-%d %H:%M:%S"
    )
    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(logging.INFO)
    log.addHandler(fh)
    log.addHandler(ch)
    return log

# ── API key ────────────────────────────────────────────────────────────────────
def load_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    f = Path(__file__).parent / API_KEY_FILE
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    return ""

# ── Text extraction ────────────────────────────────────────────────────────────
def get_converted_path(doc_path):
    """Return expected .docx path for a .doc file, or None if not applicable."""
    try:
        rel = Path(doc_path).relative_to(LOCAL_BASE_PATH)
        return Path(CONVERTED_DIR) / rel.with_suffix(".docx")
    except ValueError:
        return None

def extract_text(filepath):
    """
    Extract plain text from a sermon file.
    For .doc files: tries LibreOffice-converted .docx first, falls back to direct.
    Returns (text: str, quality: str)  quality = "high" | "medium" | "low"
    """
    path = Path(filepath)
    ext  = path.suffix.lower()

    # .doc → try converted version first
    if ext == ".doc":
        converted = get_converted_path(path)
        if converted and converted.exists() and converted.stat().st_size > 0:
            text, _ = _extract_docx_bytes(_read(converted))
            if text and len(text.strip()) > 100:
                return text, "high"

    data = _read(path)
    if data is None:
        return "", "low"

    if ext == ".pdf":
        return _extract_pdf(data)
    elif ext == ".docx":
        return _extract_docx_bytes(data)
    elif ext == ".doc":
        return _extract_doc(data)
    elif ext in (".htm", ".html"):
        text = data.decode("utf-8", errors="ignore")
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip(), "medium"
    else:
        return data.decode("utf-8", errors="ignore"), "medium"

def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None

def _extract_docx_bytes(data):
    try:
        import mammoth
        result = mammoth.extract_raw_text(io.BytesIO(data))
        text   = result.value or ""
        return text, ("high" if len(text) > 200 else "medium")
    except Exception:
        return "", "low"

def _extract_pdf(data):
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(data))
        pages  = [p.extract_text() or "" for p in reader.pages]
        text   = "\n\n".join(p for p in pages if p.strip())
        return text, ("high" if len(text) > 200 else "low")
    except Exception:
        return "", "low"

def _extract_doc(data):
    # Try mammoth first
    try:
        import mammoth
        result = mammoth.extract_raw_text(io.BytesIO(data))
        if result.value and len(result.value.strip()) > 100:
            return result.value, "medium"
    except Exception:
        pass
    # Fall back to latin-1 decode + cleanup
    for enc in ["utf-8", "latin-1", "cp1252"]:
        try:
            text = data.decode(enc, errors="ignore")
            text = re.sub(r"[^\x20-\x7E\n\r\t]", " ", text)
            text = re.sub(r" {3,}", " ", text)
            text = re.sub(r"\n{4,}", "\n\n", text)
            if len(text.strip()) > 100:
                return text.strip(), "low"
        except Exception:
            continue
    return "", "low"

# ── Text sanitization ──────────────────────────────────────────────────────────
def sanitize(text):
    """Sanitize text before sending to Claude API."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u2014", "--").replace("\u2013", "-")
    text = text.replace("\u2026", "...").replace("\u00a0", " ")
    text = text.encode("ascii", errors="replace").decode("ascii")
    text = re.sub(r"[ \t]{3,}", " ", text)
    text = re.sub(r"\n{4,}", "\n\n", text)
    return text.strip()

# ── Filename parsing ───────────────────────────────────────────────────────────
def parse_filename(filename):
    """
    Extract structured metadata from a sermon filename.
    Returns dict with: clean_name, date, year, decade, series_number
    """
    stem   = Path(filename).stem
    date   = None
    year   = None

    for pattern, formats in [
        (r"\((\d{1,2}-\d{1,2}-\d{2,4})\)", ["%m-%d-%y", "%m-%d-%Y"]),
        (r"\((\d{1,2}/\d{1,2}/\d{2,4})\)", ["%m/%d/%y", "%m/%d/%Y"]),
        (r"(\d{4}-\d{2}-\d{2})",            ["%Y-%m-%d"]),
    ]:
        m = re.search(pattern, stem)
        if m:
            for fmt in formats:
                try:
                    dt   = datetime.strptime(m.group(1), fmt)
                    date = dt.strftime("%Y-%m-%d")
                    year = dt.year
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
    clean_name = re.sub(
        r"[-_](whawley|pc|backup|copy|final|draft).*$", "",
        clean_name, flags=re.I
    ).strip()

    decade = f"{(year // 10) * 10}s" if year else None

    return {
        "clean_name":    clean_name,
        "date":          date,
        "year":          year,
        "decade":        decade,
        "series_number": series_num,
    }

# ── Author resolution ──────────────────────────────────────────────────────────
def is_hawley_name(name):
    if not name:
        return False
    return any(v in name.lower() for v in HAWLEY_NAME_VARIANTS)

def resolve_author(file_meta, detected_author, primary_pastor_name):
    """
    Determine the sermon author and whether they are the primary pastor.
    Priority: detected by Claude > folder-based rules > default to primary pastor.
    """
    folder = (file_meta.get("folder") or "").lower()

    if detected_author and 3 < len(detected_author.strip()) < 60:
        return detected_author.strip(), is_hawley_name(detected_author)

    if folder in OTHER_PREACHER_FOLDERS:
        author = OTHER_PREACHER_FOLDERS[folder]
        return (author or "Unknown"), False

    if folder in PRIMARY_PASTOR_FOLDERS or file_meta.get("folder") is None:
        return primary_pastor_name, True

    return f"Unknown ({file_meta.get('folder', 'root')})", False

# ── OSIS references ────────────────────────────────────────────────────────────
def normalize_book(book_name):
    """Normalize Psalm -> Psalms, strip whitespace."""
    b = book_name.strip()
    if b.lower() == "psalm":
        return "Psalms"
    return b

def get_osis_ref(book, chapter, verse_start):
    """Return OSIS reference string, e.g. John.3.16"""
    osis = BOOK_TO_OSIS.get(book.lower(), book.replace(" ", ""))
    return f"{osis}.{chapter}.{verse_start}"

# ── Local file crawler ─────────────────────────────────────────────────────────
def crawl_local_folder(folder_path, folder_name=None, depth=0, log=None):
    """
    Recursively scan folder_path for sermon files.
    Skips the Illustrations folder.
    Returns list of file metadata dicts.
    """
    results = []
    try:
        items = sorted(Path(folder_path).iterdir())
    except PermissionError:
        return results

    for item in items:
        name_lower = item.name.lower()

        if item.is_dir():
            if name_lower in OTHER_PREACHER_FOLDERS and OTHER_PREACHER_FOLDERS[name_lower] is None:
                if log:
                    log.info("  " * depth + f"Skipping: {item.name}")
                continue
            if log:
                log.info("  " * depth + f"Folder: {item.name}")
            results.extend(crawl_local_folder(str(item), item.name, depth + 1, log))

        elif item.is_file() and item.suffix.lower() in SERMON_EXTENSIONS:
            parsed = parse_filename(item.name)
            results.append({
                "local_path": str(item),
                "filename":   item.name,
                "folder":     folder_name,
                "ext":        item.suffix.lower(),
                "size_bytes": item.stat().st_size,
                **parsed,
            })

    return results

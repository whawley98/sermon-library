"""
Debug script - runs analyze_sermon on 12 OClock.doc and shows exactly what fails.
Place in scripts folder and run: python debug_ingest.py
"""
import os, sys, re, json, io
from pathlib import Path

# Load API key
key = Path("API Key.txt").read_text().strip()

import anthropic
import mammoth
import PyPDF2

SERMON_PATH = r"C:\Users\WilliamHawley\OneDrive - Juhls\Dad's Files\Sermons1\12 OClock.doc"

# --- Copy exact functions from ingest.py ---
def sanitize(text):
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u2014", "--").replace("\u2013", "-")
    text = text.replace("\u2026", "...").replace("\u00a0", " ")
    text = text.encode("ascii", errors="replace").decode("ascii")
    text = re.sub(r"[ \t]{3,}", " ", text)
    text = re.sub(r"\n{4,}", "\n\n", text)
    return text.strip()

def extract_json_from_response(text):
    text  = text.strip()
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end+1]
    return text

SYSTEM_PROMPT = """You are a sermon analysis assistant. Always respond with ONLY a valid JSON object. No markdown code fences, no explanation, no text before or after the JSON.

Your response must start with { and end with }

Required fields:
- title: string
- author_detected: string or null
- date_detected: string YYYY-MM-DD or null
- summary: string 2-3 sentences
- main_theme: string 3-6 words
- series_name: string or null
- structure: object with has_introduction, main_points array, has_conclusion, has_altar_call
- scripture_references: array of objects with reference, book, chapter, verse_start, verse_end, context
- keywords: array of 5-10 strings
- estimated_length: one of short medium long extended
- notes: string or null"""

# Extract text
with open(SERMON_PATH, "rb") as f:
    data = f.read()

try:
    result = mammoth.extract_raw_text(io.BytesIO(data))
    raw_text = result.value or ""
    print(f"Mammoth extracted: {len(raw_text)} chars")
except Exception as e:
    print(f"Mammoth failed: {e}, falling back")
    raw_text = data.decode("latin-1", errors="ignore")
    raw_text = re.sub(r"[^\x20-\x7E\n\r\t]", " ", raw_text)

safe = sanitize(raw_text[:4000])
print(f"Sanitized: {len(safe)} chars")

user_msg = "Filename: 12 OClock.doc\n\nSermon text:\n" + safe

client = anthropic.Anthropic(api_key=key)
resp = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1200,
    system=SYSTEM_PROMPT,
    messages=[{"role": "user", "content": user_msg}],
)

raw = resp.content[0].text.strip()
print(f"\nRaw response length: {len(raw)}")
print(f"Starts with: {repr(raw[:30])}")
print(f"Ends with:   {repr(raw[-30:])}")

extracted = extract_json_from_response(raw)
print(f"\nExtracted JSON length: {len(extracted)}")
print(f"Starts with: {repr(extracted[:30])}")
print(f"Ends with:   {repr(extracted[-30:])}")

try:
    parsed = json.loads(extracted)
    print(f"\nSUCCESS: {list(parsed.keys())}")
except json.JSONDecodeError as e:
    print(f"\nFAILED: {e}")
    # Show the exact problem area
    lines = extracted.split("\n")
    print(f"Problem at line {e.lineno}, col {e.colno}:")
    if e.lineno <= len(lines):
        print(f"  {repr(lines[e.lineno-1])}")
    print(f"\nFull response saved to debug_response.txt")
    with open("debug_response.txt", "w") as f:
        f.write(extracted)

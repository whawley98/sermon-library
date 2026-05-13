#!/usr/bin/env python3
"""
investigate_failures.py
Looks at what the consistently failing files have in common
and tests a fix approach.
"""
import os, sys, re, io, json
from pathlib import Path

import mammoth, PyPDF2, anthropic

LOCAL_BASE = r"C:\Users\WilliamHawley\OneDrive - Juhls\Dad's Files\Sermons1"

# Load API key
key = (Path(__file__).parent / "API Key.txt").read_text().strip()
client = anthropic.Anthropic(api_key=key)

# Test on one known failing file
# Find the file anywhere under Sermons1
import glob
matches = list(Path(LOCAL_BASE).rglob("Living Within The Realm Of God's Grace.doc"))
if not matches:
    print("File not found! Searching for any failed file...")
    matches = list(Path(LOCAL_BASE).rglob("In Jesus Name.doc"))
if not matches:
    print("Could not find test file. Check LOCAL_BASE path.")
    sys.exit(1)
TEST_FILE = str(matches[0])
print(f"Found: {TEST_FILE}")

def extract(path):
    with open(path, "rb") as f:
        data = f.read()
    try:
        r = mammoth.extract_raw_text(io.BytesIO(data))
        if r.value and len(r.value.strip()) > 100:
            return r.value
    except Exception:
        pass
    for enc in ["utf-8", "latin-1", "cp1252"]:
        try:
            text = data.decode(enc, errors="ignore")
            text = re.sub(r"[^\x20-\x7E\n\r\t]", " ", text)
            text = re.sub(r" {3,}", " ", text)
            text = re.sub(r"\n{4,}", "\n\n", text)
            if len(text.strip()) > 100:
                return text.strip()
        except Exception:
            pass
    return ""

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

text = extract(TEST_FILE)
safe = sanitize(text[:4000])

print(f"Text length: {len(text)}")
print(f"Sanitized length: {len(safe)}")
print(f"\nFirst 300 chars of sanitized text:")
print(repr(safe[:300]))

# Try a simpler prompt that avoids the JSON issue
SIMPLE_SYSTEM = """Analyze this sermon. Return ONLY a JSON object starting with { and ending with }.
Use only simple ASCII characters in all string values.
Do not use special punctuation like smart quotes or em dashes in your response.

Return this structure:
{"title":"...","author_detected":null,"date_detected":null,"summary":"...","main_theme":"...","series_name":null,"structure":{"has_introduction":true,"main_points":[],"has_conclusion":true,"has_altar_call":false},"scripture_references":[],"keywords":[],"estimated_length":"medium","notes":null}"""

print("\nSending to Claude...")
resp = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1200,
    system=SIMPLE_SYSTEM,
    messages=[{"role": "user", "content": f"Filename: Living Within The Realm Of God's Grace.doc\n\n{safe}"}],
)

raw = resp.content[0].text.strip()
start = raw.find("{")
end = raw.rfind("}")
if start != -1 and end > start:
    raw = raw[start:end+1]

print(f"\nResponse length: {len(raw)}")
print(f"First 100: {repr(raw[:100])}")
print(f"Last 100:  {repr(raw[-100:])}")

try:
    parsed = json.loads(raw)
    print(f"\nSUCCESS: {list(parsed.keys())}")
    print(f"Summary: {parsed.get('summary','')[:100]}")
except json.JSONDecodeError as e:
    print(f"\nFAILED: {e}")
    lines = raw.split("\n")
    if e.lineno <= len(lines):
        print(f"Problem line {e.lineno}: {repr(lines[e.lineno-1])}")
    # Show chars around the problem
    print(f"Context: {repr(raw[max(0,e.pos-50):e.pos+50])}")

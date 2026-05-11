"""
Quick test to see exactly what Claude returns for a problematic sermon.
Run from the scripts folder.
"""
import os, re, json, io, sys
from pathlib import Path

# Load API key
key_file = Path("api_key.txt")
if key_file.exists():
    api_key = key_file.read_text().strip()
else:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

if not api_key:
    print("No API key found")
    sys.exit(1)

import anthropic
import mammoth

SERMON_PATH = r"C:\Users\WilliamHawley\OneDrive - Juhls\Dad's Files\Sermons1\12 OClock.doc"

# Extract text
with open(SERMON_PATH, "rb") as f:
    content = f.read()

try:
    result = mammoth.extract_raw_text(io.BytesIO(content))
    raw_text = result.value or ""
except Exception:
    raw_text = content.decode("latin-1", errors="ignore")

print(f"Extracted {len(raw_text)} chars")
print("--- First 500 chars ---")
print(repr(raw_text[:500]))
print("--- Last 500 chars of what we send to Claude ---")
truncated = raw_text[:4000]
print(repr(truncated[-500:]))

# Sanitize
def sanitize(text):
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    text = text.replace('\u2018', "'").replace('\u2019', "'")
    text = text.replace('\u2014', '--').replace('\u2013', '-')
    text = text.replace('\u2026', '...').replace('\u00a0', ' ')
    text = text.encode('ascii', errors='replace').decode('ascii')
    text = re.sub(r'[ \t]{3,}', ' ', text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

safe = sanitize(truncated)
print(f"\nSanitized length: {len(safe)}")
print("--- Last 200 chars of sanitized text ---")
print(repr(safe[-200:]))

# Send to Claude
SYSTEM = """You are a sermon analysis assistant. Respond with ONLY a valid JSON object. No markdown, no explanation.

Required JSON structure:
{
  "title": "sermon title",
  "author_detected": null,
  "date_detected": null,
  "summary": "2-3 sentence summary",
  "main_theme": "theme phrase",
  "series_name": null,
  "structure": {"has_introduction": true, "main_points": [], "has_conclusion": true, "has_altar_call": false},
  "scripture_references": [{"reference": "John 3:16", "book": "John", "chapter": 3, "verse_start": 16, "verse_end": 16, "context": "usage"}],
  "keywords": ["faith"],
  "estimated_length": "medium",
  "notes": null
}"""

client = anthropic.Anthropic(api_key=api_key)
resp = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1200,
    system=SYSTEM,
    messages=[{"role": "user", "content": f"Filename: 12 OClock.doc\n\nSermon text:\n{safe}"}]
)

raw = resp.content[0].text
print("\n--- Claude raw response ---")
print(raw)
print("\n--- Trying to parse ---")
# Extract JSON by finding first { and last }
start = raw.find("{")
end   = raw.rfind("}")
if start != -1 and end != -1 and end > start:
    raw = raw[start:end+1]

try:
    parsed = json.loads(raw)
    print("SUCCESS:", list(parsed.keys()))
    print("\nTitle:", parsed.get("title"))
    print("Summary:", parsed.get("summary"))
    print("Keywords:", parsed.get("keywords"))
    print("Scripture refs:", len(parsed.get("scripture_references", [])))
except json.JSONDecodeError as e:
    print(f"FAILED: {e}")
    lines = raw.split('\n')
    print(f"Line {e.lineno}: {repr(lines[e.lineno-1] if e.lineno <= len(lines) else 'out of range')}")

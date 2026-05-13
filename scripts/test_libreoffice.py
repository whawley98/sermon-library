#!/usr/bin/env python3
"""
test_libreoffice.py
===================
Compares text extraction quality:
  1. Current method (mammoth direct on .doc)
  2. LibreOffice conversion (.doc -> .docx) then mammoth

Run from scripts folder: python test_libreoffice.py
"""

import sys, io, re, subprocess, tempfile, shutil
from pathlib import Path

import mammoth

LOCAL_BASE = r"C:\Users\WilliamHawley\OneDrive - Juhls\Dad's Files\Sermons1"

# LibreOffice executable path (standard Windows install location)
LIBREOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"

def find_test_file():
    """Find a .doc file that had bad extraction previously."""
    bad_files = [
        "A Fatal Mistake.doc",
        "Hindsight Is Not Always 20-20.doc", 
        "God Give Us A Heart.doc",
        "STILL GRACE.doc",
    ]
    for name in bad_files:
        matches = list(Path(LOCAL_BASE).rglob(name))
        if matches:
            return matches[0]
    # Fall back to any .doc file
    matches = list(Path(LOCAL_BASE).rglob("*.doc"))
    return matches[0] if matches else None

def extract_direct(filepath):
    """Current method: mammoth directly on .doc file."""
    with open(filepath, "rb") as f:
        data = f.read()
    try:
        result = mammoth.extract_raw_text(io.BytesIO(data))
        if result.value and len(result.value.strip()) > 100:
            return result.value, "mammoth"
    except Exception:
        pass
    # Fallback to latin-1
    text = data.decode("latin-1", errors="ignore")
    text = re.sub(r"[^\x20-\x7E\n\r\t]", " ", text)
    text = re.sub(r" {3,}", " ", text)
    text = re.sub(r"\n{4,}", "\n\n", text)
    return text.strip(), "latin-1 fallback"

def extract_via_libreoffice(filepath):
    """Convert .doc -> .docx with LibreOffice, then extract with mammoth."""
    if not Path(LIBREOFFICE).exists():
        return None, "LibreOffice not found"
    
    # Create temp directory for conversion
    tmpdir = tempfile.mkdtemp()
    try:
        # Run LibreOffice conversion
        result = subprocess.run([
            LIBREOFFICE,
            "--headless",
            "--convert-to", "docx",
            "--outdir", tmpdir,
            str(filepath)
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            return None, f"LibreOffice error: {result.stderr}"
        
        # Find the converted file
        converted = list(Path(tmpdir).glob("*.docx"))
        if not converted:
            return None, "No output file from LibreOffice"
        
        # Extract text from docx with mammoth
        with open(converted[0], "rb") as f:
            data = f.read()
        
        extract_result = mammoth.extract_raw_text(io.BytesIO(data))
        return extract_result.value or "", "libreoffice + mammoth"
    
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

def show_sample(text, method, chars=800):
    """Show a clean sample of extracted text."""
    print(f"\n{'='*60}")
    print(f"METHOD: {method}")
    print(f"Total length: {len(text)} chars")
    print(f"{'='*60}")
    
    # Show first 800 chars, skipping binary garbage
    sample = text[:chars]
    # Count readable vs garbage chars
    readable = sum(1 for c in text[:2000] if c.isprintable() or c in '\n\r\t')
    total = min(len(text), 2000)
    pct = 100 * readable // total if total > 0 else 0
    print(f"Readability: {pct}% printable chars in first 2000")
    print(f"\nSample text:")
    print("-" * 40)
    print(sample)
    print("-" * 40)

def main():
    print("Finding test file...")
    filepath = find_test_file()
    if not filepath:
        print("No .doc files found!")
        sys.exit(1)
    
    print(f"Testing: {filepath.name}")
    print(f"Full path: {filepath}")
    
    # Method 1: Current approach
    print("\n[1/2] Extracting with current method...")
    text1, method1 = extract_direct(filepath)
    show_sample(text1, method1)
    
    # Method 2: LibreOffice conversion
    print("\n[2/2] Extracting via LibreOffice conversion...")
    text2, method2 = extract_via_libreoffice(filepath)
    
    if text2 is None:
        print(f"LibreOffice extraction failed: {method2}")
        print(f"\nMake sure LibreOffice is installed at:")
        print(f"  {LIBREOFFICE}")
    else:
        show_sample(text2, method2)
        
        # Summary comparison
        print(f"\n{'='*60}")
        print("COMPARISON SUMMARY")
        print(f"{'='*60}")
        
        def readability(text):
            if not text: return 0
            sample = text[:5000]
            return 100 * sum(1 for c in sample if c.isprintable() or c in '\n\r\t') // len(sample)
        
        r1 = readability(text1)
        r2 = readability(text2)
        
        print(f"Current method:    {len(text1):,} chars, {r1}% readable")
        print(f"LibreOffice method:{len(text2):,} chars, {r2}% readable")
        print(f"Improvement:       +{r2-r1}% readability, {len(text2)-len(text1):+,} chars")
        
        # Save both to files for inspection
        with open("test_current.txt", "w", encoding="utf-8") as f:
            f.write(text1)
        with open("test_libreoffice.txt", "w", encoding="utf-8") as f:
            f.write(text2)
        print(f"\nFull text saved to:")
        print(f"  test_current.txt")
        print(f"  test_libreoffice.txt")
        print(f"\nOpen both in Notepad to compare quality.")

if __name__ == "__main__":
    main()

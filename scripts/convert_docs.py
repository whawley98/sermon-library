#!/usr/bin/env python3
"""
convert_docs.py
===============
Batch converts all .doc files to .docx using LibreOffice headless mode.
Mirrors the subfolder structure from the source into the output folder.
Resumable — skips already-converted files.

Usage:
    python convert_docs.py
    python convert_docs.py --force   (re-convert even if already done)

Requirements:
    LibreOffice installed at default location
"""

import sys, subprocess, logging, argparse, time
from pathlib import Path
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────────────────
SOURCE_DIR  = r"C:\Users\WilliamHawley\OneDrive - Juhls\Dad's Files\Sermons1"
OUTPUT_DIR  = r"C:\Users\WilliamHawley\Documents\Personal\sermon-library\converted_sermons"
LIBREOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"

# ── Logging ───────────────────────────────────────────────────────────────────
log = logging.getLogger("convert")
log.setLevel(logging.DEBUG)
fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", "%Y-%m-%d %H:%M:%S")
fh  = logging.FileHandler("convert.log", encoding="utf-8")
fh.setFormatter(fmt)
ch  = logging.StreamHandler(sys.stdout)
ch.setFormatter(fmt)
ch.setLevel(logging.INFO)
log.addHandler(fh)
log.addHandler(ch)

# ── Helpers ───────────────────────────────────────────────────────────────────

def find_doc_files(source_dir):
    """Find all .doc files recursively, skip Illustrations folder."""
    files = []
    for path in sorted(Path(source_dir).rglob("*.doc")):
        # Skip Illustrations folder
        if "illustrations" in str(path).lower():
            continue
        files.append(path)
    return files

def get_output_path(source_file, source_dir, output_dir):
    """Mirror the subfolder structure in output directory."""
    relative = source_file.relative_to(source_dir)
    output   = Path(output_dir) / relative.with_suffix(".docx")
    return output

def convert_file(doc_path, output_path, libreoffice):
    """Convert a single .doc file to .docx using LibreOffice."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    result = subprocess.run(
        [
            libreoffice,
            "--headless",
            "--convert-to", "docx",
            "--outdir", str(output_path.parent),
            str(doc_path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    
    # LibreOffice saves as original_name.docx
    expected = output_path.parent / (doc_path.stem + ".docx")
    
    if result.returncode != 0:
        return False, f"LibreOffice error: {result.stderr.strip()}"
    
    if not expected.exists():
        return False, f"Output file not created: {expected}"
    
    # Rename if necessary (handles case differences)
    if expected != output_path:
        expected.rename(output_path)
    
    return True, "OK"

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Convert .doc files to .docx using LibreOffice")
    parser.add_argument("--force", action="store_true", help="Re-convert even if already done")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  DOC → DOCX CONVERSION")
    print(f"  Source:  {SOURCE_DIR}")
    print(f"  Output:  {OUTPUT_DIR}")
    print("="*60 + "\n")

    # Check LibreOffice exists
    if not Path(LIBREOFFICE).exists():
        print(f"ERROR: LibreOffice not found at: {LIBREOFFICE}")
        print("Install from: https://www.libreoffice.org/download/libreoffice/")
        sys.exit(1)

    # Check source exists
    if not Path(SOURCE_DIR).exists():
        print(f"ERROR: Source folder not found: {SOURCE_DIR}")
        sys.exit(1)

    # Create output dir
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    # Find all .doc files
    log.info("Scanning for .doc files...")
    doc_files = find_doc_files(SOURCE_DIR)
    log.info(f"Found {len(doc_files)} .doc files")

    # Filter already converted (unless --force)
    if not args.force:
        remaining = []
        skipped   = 0
        for f in doc_files:
            out = get_output_path(f, SOURCE_DIR, OUTPUT_DIR)
            if out.exists() and out.stat().st_size > 0:
                skipped += 1
            else:
                remaining.append(f)
        if skipped:
            log.info(f"Skipping {skipped} already converted files")
        doc_files = remaining

    if not doc_files:
        log.info("Nothing to convert!")
        return

    log.info(f"Converting {len(doc_files)} files...\n")

    success_count = 0
    fail_count    = 0
    failed_files  = []
    start_time    = time.time()

    for i, doc_path in enumerate(doc_files, 1):
        output_path = get_output_path(doc_path, SOURCE_DIR, OUTPUT_DIR)
        
        # Progress
        elapsed  = time.time() - start_time
        rate     = i / elapsed if elapsed > 0 else 0
        remaining_count = len(doc_files) - i
        eta      = remaining_count / rate if rate > 0 else 0
        eta_min  = int(eta // 60)
        eta_sec  = int(eta % 60)
        
        print(f"[{i}/{len(doc_files)}] {doc_path.name[:50]:<50} ETA: {eta_min}m {eta_sec}s", end="\r")
        
        ok, msg = convert_file(doc_path, output_path, LIBREOFFICE)
        
        if ok:
            success_count += 1
            log.debug(f"OK: {doc_path.name}")
        else:
            fail_count += 1
            failed_files.append({"file": str(doc_path), "error": msg})
            log.warning(f"FAIL: {doc_path.name} — {msg}")

    print()  # newline after progress

    # Summary
    elapsed_total = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"  CONVERSION COMPLETE")
    print(f"  Converted: {success_count}")
    print(f"  Failed:    {fail_count}")
    print(f"  Time:      {int(elapsed_total//60)}m {int(elapsed_total%60)}s")
    print(f"{'='*60}\n")

    if failed_files:
        import json
        with open("convert_failed.json", "w") as f:
            json.dump(failed_files, f, indent=2)
        print(f"Failed files saved to: convert_failed.json")
        print(f"Run with --force to retry them.\n")
    
    log.info(f"Done. {success_count} converted, {fail_count} failed.")
    print("Next step: python ingest.py")

if __name__ == "__main__":
    main()

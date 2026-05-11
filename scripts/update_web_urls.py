#!/usr/bin/env python3
"""
update_web_urls.py
==================
Connects to Microsoft Graph, fetches the OneDrive web URL for every
sermon file, and updates the matching Firestore documents.

No re-analysis. No Claude API. Just a metadata update.

Usage:
    python update_web_urls.py
    python update_web_urls.py --dry-run   (preview without writing)
"""

import sys, time, logging
from pathlib import Path

# ── Deps ──────────────────────────────────────────────────────────────────────
def ensure_deps():
    import subprocess
    for pip, imp in [("firebase-admin","firebase_admin"),("requests","requests"),("msal","msal"),("tqdm","tqdm")]:
        try: __import__(imp)
        except ImportError: subprocess.check_call([sys.executable,"-m","pip","install",pip,"-q"])

ensure_deps()

import requests, msal, firebase_admin, argparse
from firebase_admin import credentials, firestore
from tqdm import tqdm

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════════════

FIREBASE_CREDENTIALS_PATH = "firebase-credentials.json"
MS_CLIENT_ID  = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
MS_AUTHORITY  = "https://login.microsoftonline.com/common"
MS_SCOPES     = ["Files.Read", "Files.Read.All"]
ONEDRIVE_PATH = "Dad's Files/Sermons1"
BATCH_SIZE    = 400   # Firestore batch limit

# ══════════════════════════════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.FileHandler("update_urls.log"), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  MICROSOFT GRAPH
# ══════════════════════════════════════════════════════════════════════════════

class GraphClient:
    BASE = "https://graph.microsoft.com/v1.0"

    def __init__(self):
        self._app   = msal.PublicClientApplication(MS_CLIENT_ID, authority=MS_AUTHORITY)
        self._token = None
        self._authenticate()

    def _authenticate(self):
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(MS_SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._token = result["access_token"]
                log.info("Using cached Microsoft token")
                return

        flow = self._app.initiate_device_flow(scopes=MS_SCOPES)
        print("\n" + "="*50)
        print("MICROSOFT LOGIN")
        print(f"1. Open: {flow['verification_uri']}")
        print(f"2. Enter code: {flow['user_code']}")
        print("="*50 + "\n")

        result = self._app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(f"Auth failed: {result.get('error_description')}")
        self._token = result["access_token"]
        log.info("Microsoft login successful")

    @property
    def _headers(self):
        return {"Authorization": f"Bearer {self._token}"}

    def _refresh(self):
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(MS_SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._token = result["access_token"]
                return True
        return False

    def get(self, path):
        for attempt in range(2):
            r = requests.get(f"{self.BASE}{path}", headers=self._headers)
            if r.status_code == 401 and attempt == 0 and self._refresh():
                continue
            r.raise_for_status()
            return r.json()

    def list_children(self, item_id):
        items = []
        url   = f"{self.BASE}/me/drive/items/{item_id}/children"
        while url:
            for attempt in range(2):
                r = requests.get(url, headers=self._headers)
                if r.status_code == 401 and attempt == 0 and self._refresh():
                    continue
                r.raise_for_status()
                data = r.json()
                break
            items.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
        return items

    def find_folder(self, path):
        encoded = requests.utils.quote(path, safe="/")
        item = self.get(f"/me/drive/root:/{encoded}")
        return item if item.get("folder") else None


# ══════════════════════════════════════════════════════════════════════════════
#  CRAWL ONEDRIVE FOR WEB URLS
# ══════════════════════════════════════════════════════════════════════════════

SERMON_EXTENSIONS = {".doc", ".docx", ".pdf", ".txt", ".htm", ".html"}

def crawl_for_urls(graph, folder_id, depth=0):
    """Returns dict of {filename: web_url}"""
    result = {}
    for item in graph.list_children(folder_id):
        name = item.get("name", "")
        if item.get("folder"):
            name_lower = name.lower()
            if name_lower == "illustrations":
                continue
            log.info(f"{'  '*depth}Scanning: {name}")
            sub = crawl_for_urls(graph, item["id"], depth + 1)
            result.update(sub)
        elif item.get("file"):
            ext = Path(name).suffix.lower()
            if ext in SERMON_EXTENSIONS:
                web_url = item.get("webUrl", "")
                if web_url:
                    result[name] = web_url
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  UPDATE FIRESTORE
# ══════════════════════════════════════════════════════════════════════════════

def update_firestore(db, url_map, dry_run=False):
    """Update web_url field on all sermon documents."""
    log.info("Fetching all sermon documents from Firestore...")
    docs = list(db.collection("sermons").stream())
    log.info(f"Found {len(docs)} sermon documents")

    updated  = 0
    missing  = 0
    skipped  = 0

    # Process in batches
    batch     = db.batch()
    batch_count = 0

    for doc in tqdm(docs, desc="Updating URLs", unit="sermon"):
        data     = doc.to_dict()
        filename = data.get("filename", "")
        current_url = data.get("web_url", "")

        if filename in url_map:
            new_url = url_map[filename]
            if new_url != current_url:
                if not dry_run:
                    batch.update(doc.reference, {"web_url": new_url})
                    batch_count += 1
                    if batch_count >= BATCH_SIZE:
                        batch.commit()
                        batch = db.batch()
                        batch_count = 0
                        time.sleep(0.5)
                updated += 1
            else:
                skipped += 1
        else:
            log.debug(f"No URL found for: {filename}")
            missing += 1

    # Flush remaining batch
    if batch_count > 0 and not dry_run:
        batch.commit()

    return updated, missing, skipped


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Update OneDrive web URLs in Firestore")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to Firestore")
    parser.add_argument("--folder",  default=ONEDRIVE_PATH, help=f"OneDrive folder path (default: {ONEDRIVE_PATH})")
    args = parser.parse_args()

    print("\n" + "="*50)
    print("  UPDATE WEB URLS")
    print(f"  Folder: {args.folder}")
    if args.dry_run:
        print("  MODE: DRY RUN (no changes will be made)")
    print("="*50 + "\n")

    # Init Firebase
    log.info("Connecting to Firebase...")
    if not Path(FIREBASE_CREDENTIALS_PATH).exists():
        print(f"ERROR: {FIREBASE_CREDENTIALS_PATH} not found")
        sys.exit(1)
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    # Connect to OneDrive
    log.info("Connecting to Microsoft 365...")
    graph = GraphClient()

    # Find the folder
    log.info(f"Finding folder: {args.folder}")
    folder = graph.find_folder(args.folder)
    if not folder:
        print(f"ERROR: Folder not found: {args.folder}")
        sys.exit(1)
    log.info(f"Found: {folder['name']}")

    # Crawl for URLs
    log.info("Scanning OneDrive for file URLs...")
    url_map = crawl_for_urls(graph, folder["id"])
    log.info(f"Found {len(url_map)} file URLs")

    # Update Firestore
    updated, missing, skipped = update_firestore(db, url_map, dry_run=args.dry_run)

    print(f"\n{'='*50}")
    print(f"  {'DRY RUN ' if args.dry_run else ''}COMPLETE")
    print(f"  Updated:  {updated} documents")
    print(f"  Skipped:  {skipped} (already had correct URL)")
    print(f"  Missing:  {missing} (filename not found in OneDrive)")
    print(f"{'='*50}\n")

    if args.dry_run:
        print("Run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()

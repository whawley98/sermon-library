#!/usr/bin/env python3
"""
ingest.py - Sermon Library Ingestion Pipeline v3
Two-phase Claude analysis:
  Phase 1: Sermon metadata
  Phase 2: Scripture references (separate collection, no cap)
Collections: pastors, sermons, scripture_references, series, stats, annotations
Algolia full-text search indexing.

Usage:
  python ingest.py
  python ingest.py --resume --no-wipe
  python ingest.py --stats-only
"""

import os, sys, json, re, time, io, logging, argparse
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

def ensure_deps():
    import subprocess
    for pip, imp in [
        ('anthropic','anthropic'),('firebase-admin','firebase_admin'),
        ('mammoth','mammoth'),('PyPDF2','PyPDF2'),
        ('tqdm','tqdm'),('requests','requests'),('msal','msal'),
        # algoliasearch handled via REST API directly
    ]:
        try: __import__(imp)
        except ImportError:
            print(f'Installing {pip}...')
            subprocess.check_call([sys.executable,'-m','pip','install',pip,'-q'])

ensure_deps()

import anthropic, firebase_admin, mammoth, PyPDF2, requests, msal
from firebase_admin import credentials, firestore
from tqdm import tqdm
# Algolia accessed via REST API directly (no client library needed)

# ═══ CONFIGURATION ═══════════════════════════════════════════════════════════
FIREBASE_CREDENTIALS_PATH = 'firebase-credentials.json'
CONVERTED_DIR   = r'C:\Users\WilliamHawley\Documents\Personal\sermon-library\converted_sermons'
LOCAL_BASE_PATH = r"C:\Users\WilliamHawley\OneDrive - Juhls\Dad's Files\Sermons1"
MS_CLIENT_ID    = '14d82eec-204b-4c2f-b7e8-296a70dab67e'
MS_AUTHORITY    = 'https://login.microsoftonline.com/common'
MS_SCOPES       = ['Files.Read', 'Files.Read.All']
ONEDRIVE_FOLDER = "Dad's Files/Sermons1"
ALGOLIA_APP_ID      = 'A4149APL2C'
ALGOLIA_WRITE_KEY   = '3c79ff84634df740423519749e1c94a8'
ALGOLIA_INDEX_NAME  = 'sermons'
DEFAULT_PASTOR_NAME = 'William Hawley'
DEFAULT_PASTOR_DESC = '40 years of faithful preaching'
OTHER_PREACHER_FOLDERS = {
    'billy sunday':  'Billy Sunday',
    'chapman':       'J. Wilbur Chapman',
    'hughes':        'Hughes',
    'johnston':      'Johnston',
    'illustrations': None,
}
PRIMARY_PASTOR_FOLDERS = {'franklin sermons', 'fbis - cloud', 'browning'}
HAWLEY_NAME_VARIANTS = [
    'william hawley','william o. hawley','william o. hawley, sr.',
    'william o hawley','w. hawley','pastor hawley',
    'pastor william hawley','bill hawley',
]
SERMON_EXTENSIONS = {'.doc', '.docx', '.pdf', '.txt', '.htm', '.html'}
MAX_TEXT_PHASE1   = 3000
MAX_TEXT_PHASE2   = 5000
MAX_RETRIES       = 3
BATCH_SIZE        = 50
REQUEST_DELAY     = 0.3

def load_api_key():
    key = os.environ.get('ANTHROPIC_API_KEY','').strip()
    if key: return key
    f = Path(__file__).parent / 'API Key.txt'
    if f.exists(): return f.read_text(encoding='utf-8').strip()
    return ''

ANTHROPIC_API_KEY = load_api_key()

# ═══ LOGGING ═════════════════════════════════════════════════════════════════
log = logging.getLogger('ingest')
log.setLevel(logging.DEBUG)
fmt = logging.Formatter('%(asctime)s  %(levelname)-8s  %(message)s', '%Y-%m-%d %H:%M:%S')
fh  = logging.FileHandler('ingest.log', encoding='utf-8')
fh.setFormatter(fmt)
ch  = logging.StreamHandler(sys.stdout)
ch.setFormatter(fmt)
ch.setLevel(logging.INFO)
log.addHandler(fh)
log.addHandler(ch)

# ═══ FIREBASE ════════════════════════════════════════════════════════════════
def init_firebase():
    if not Path(FIREBASE_CREDENTIALS_PATH).exists():
        log.error(f'Firebase credentials not found: {FIREBASE_CREDENTIALS_PATH}')
        sys.exit(1)
    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)
    return firestore.client()

def wipe_firestore(db):
    log.info('Wiping Firestore...')
    for col in ['sermons','scripture_references','series','pastors','stats','annotations']:
        deleted = 0
        while True:
            docs = list(db.collection(col).limit(400).stream())
            if not docs: break
            batch = db.batch()
            for d in docs: batch.delete(d.reference)
            batch.commit()
            deleted += len(docs)
        if deleted: log.info(f'  Deleted {deleted} from {col}')
    log.info('Firestore wiped clean')

# ═══ TEXT EXTRACTION ══════════════════════════════════════════════════════════
def get_converted_path(doc_path):
    try:
        rel = Path(doc_path).relative_to(LOCAL_BASE_PATH)
        return Path(CONVERTED_DIR) / rel.with_suffix('.docx')
    except ValueError:
        return None

def extract_text(filepath):
    path = Path(filepath)
    ext  = path.suffix.lower()
    if ext == '.doc':
        converted = get_converted_path(path)
        if converted and converted.exists() and converted.stat().st_size > 0:
            text, _ = _extract_docx_file(converted)
            if text and len(text.strip()) > 100:
                return text, 'high'
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
        if ext == '.pdf':    return _extract_pdf(data)
        elif ext == '.docx': return _extract_docx_bytes(data)
        elif ext == '.doc':  return _extract_doc(data)
        elif ext in ('.htm','.html'):
            text = data.decode('utf-8',errors='ignore')
            text = re.sub(r'<[^>]+>',' ',text)
            return re.sub(r'\s+',' ',text).strip(), 'medium'
        else:
            return data.decode('utf-8',errors='ignore'), 'medium'
    except Exception as e:
        log.warning(f'Extraction failed for {filepath}: {e}')
        return '', 'low'

def _extract_docx_file(path):
    with open(path,'rb') as f: data = f.read()
    return _extract_docx_bytes(data)

def _extract_docx_bytes(data):
    result = mammoth.extract_raw_text(io.BytesIO(data))
    text   = result.value or ''
    return text, ('high' if len(text) > 200 else 'medium')

def _extract_pdf(data):
    reader = PyPDF2.PdfReader(io.BytesIO(data))
    pages  = [p.extract_text() or '' for p in reader.pages]
    text   = '\n\n'.join(p for p in pages if p.strip())
    return text, ('high' if len(text) > 200 else 'low')

def _extract_doc(data):
    try:
        result = mammoth.extract_raw_text(io.BytesIO(data))
        if result.value and len(result.value.strip()) > 100:
            return result.value, 'medium'
    except Exception:
        pass
    for enc in ['utf-8','latin-1','cp1252']:
        try:
            text = data.decode(enc,errors='ignore')
            text = re.sub(r'[^\x20-\x7E\n\r\t]',' ',text)
            text = re.sub(r' {3,}',' ',text)
            text = re.sub(r'\n{4,}','\n\n',text)
            if len(text.strip()) > 100:
                return text.strip(), 'low'
        except Exception:
            pass
    return '', 'low'

def sanitize(text):
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]',' ',text)
    text = text.replace('\u201c','"').replace('\u201d','"')
    text = text.replace('\u2018',"'").replace('\u2019',"'")
    text = text.replace('\u2014','--').replace('\u2013','-')
    text = text.replace('\u2026','...').replace('\u00a0',' ')
    text = text.encode('ascii',errors='replace').decode('ascii')
    text = re.sub(r'[ \t]{3,}',' ',text)
    text = re.sub(r'\n{4,}','\n\n',text)
    return text.strip()

# ═══ FILENAME PARSING ════════════════════════════════════════════════════════
def parse_filename(filename):
    stem = Path(filename).stem
    date = None
    year = None
    for pattern, formats in [
        (r'\((\d{1,2}-\d{1,2}-\d{2,4})\)', ['%m-%d-%y','%m-%d-%Y']),
        (r'\((\d{1,2}/\d{1,2}/\d{2,4})\)', ['%m/%d/%y','%m/%d/%Y']),
        (r'(\d{4}-\d{2}-\d{2})',            ['%Y-%m-%d']),
    ]:
        m = re.search(pattern, stem)
        if m:
            for fmt in formats:
                try:
                    dt   = datetime.strptime(m.group(1), fmt)
                    date = dt.strftime('%Y-%m-%d')
                    year = dt.year
                    break
                except ValueError:
                    pass
        if date: break
    series_num = None
    clean_name = stem
    m = re.match(r'^(\d+)[-\s]+(.+)', stem)
    if m:
        series_num = int(m.group(1))
        clean_name = m.group(2).strip()
    clean_name = re.sub(r'\s*\(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\)','',clean_name).strip()
    clean_name = re.sub(r'[-_](whawley|pc|backup|copy|final|draft).*$','',clean_name,flags=re.I).strip()
    decade = f'{(year//10)*10}s' if year else None
    return {'clean_name':clean_name,'date':date,'year':year,'decade':decade,'series_number':series_num}

# ═══ OSIS REFERENCE FORMAT ═══════════════════════════════════════════════════
BOOK_TO_OSIS = {
    'genesis':'Gen','exodus':'Exod','leviticus':'Lev','numbers':'Num',
    'deuteronomy':'Deut','joshua':'Josh','judges':'Judg','ruth':'Ruth',
    '1 samuel':'1Sam','2 samuel':'2Sam','1 kings':'1Kgs','2 kings':'2Kgs',
    '1 chronicles':'1Chr','2 chronicles':'2Chr','ezra':'Ezra','nehemiah':'Neh',
    'esther':'Esth','job':'Job','psalms':'Ps','psalm':'Ps','proverbs':'Prov',
    'ecclesiastes':'Eccl','song of solomon':'Song','isaiah':'Isa',
    'jeremiah':'Jer','lamentations':'Lam','ezekiel':'Ezek','daniel':'Dan',
    'hosea':'Hos','joel':'Joel','amos':'Amos','obadiah':'Obad','jonah':'Jonah',
    'micah':'Mic','nahum':'Nah','habakkuk':'Hab','zephaniah':'Zeph',
    'haggai':'Hag','zechariah':'Zech','malachi':'Mal',
    'matthew':'Matt','mark':'Mark','luke':'Luke','john':'John','acts':'Acts',
    'romans':'Rom','1 corinthians':'1Cor','2 corinthians':'2Cor',
    'galatians':'Gal','ephesians':'Eph','philippians':'Phil',
    'colossians':'Col','1 thessalonians':'1Thess','2 thessalonians':'2Thess',
    '1 timothy':'1Tim','2 timothy':'2Tim','titus':'Titus','philemon':'Phlm',
    'hebrews':'Heb','james':'Jas','1 peter':'1Pet','2 peter':'2Pet',
    '1 john':'1John','2 john':'2John','3 john':'3John','jude':'Jude',
    'revelation':'Rev',
}

def normalize_book(book_name):
    b = book_name.strip()
    if b.lower() == 'psalm': return 'Psalms'
    return b

def get_osis_ref(book, chapter, verse_start):
    osis = BOOK_TO_OSIS.get(book.lower(), book.replace(' ',''))
    return f'{osis}.{chapter}.{verse_start}'

# ═══ CLAUDE PHASE 1: METADATA ════════════════════════════════════════════════
PHASE1_SYSTEM = """Analyze this sermon and return ONLY a valid JSON object.
ASCII characters only. No smart quotes. No backslash before apostrophes.
Keep all text fields concise.

Return exactly this structure:
{"title":"sermon title","author_detected":null,"date_detected":null,"summary":"2-3 sentence summary","main_theme":"3-6 word theme","series_name":null,"structure":{"has_introduction":true,"main_points":["point 1","point 2"],"has_conclusion":true,"has_altar_call":false},"keywords":["faith","salvation","grace"],"estimated_length":"medium","notes":null}

estimated_length options: short, medium, long, extended"""

def analyze_phase1(client, text, filename):
    if len(text.strip()) < 80:
        return None, 'text_too_short'
    safe = sanitize(text[:MAX_TEXT_PHASE1])
    msg  = f'Filename: {filename}\n\nSermon text:\n{safe}'
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.messages.create(
                model='claude-haiku-4-5-20251001',
                max_tokens=600,
                system=PHASE1_SYSTEM,
                messages=[{'role':'user','content':msg}],
            )
            raw   = resp.content[0].text.strip()
            start = raw.find('{')
            end   = raw.rfind('}')
            if start != -1 and end > start:
                raw = raw[start:end+1]
            raw    = raw.replace("\\'",'\'')
            parsed = json.loads(raw)
            return parsed, 'success'
        except json.JSONDecodeError as e:
            log.warning(f'Phase1 JSON error attempt {attempt+1} for {filename}: {e}')
            time.sleep(attempt+1)
        except anthropic.RateLimitError:
            time.sleep(60*(attempt+1))
        except Exception as e:
            log.warning(f'Phase1 error attempt {attempt+1} for {filename}: {e}')
            time.sleep(2*(attempt+1))
    return None, 'analysis_failed'

# ═══ CLAUDE PHASE 2: SCRIPTURE REFERENCES ════════════════════════════════════
PHASE2_SYSTEM = """Extract ALL Bible scripture references from this sermon.
Return ONLY a valid JSON array. ASCII only. No smart quotes. No backslash apostrophes.
Keep context under 8 words. If no references found return: []

Return exactly this structure:
[{"reference":"John 3:16","book":"John","chapter":3,"verse_start":16,"verse_end":16,"context":"God loved the world"}]"""

def analyze_phase2(client, text, filename):
    if len(text.strip()) < 80:
        return [], 'text_too_short'
    safe = sanitize(text[:MAX_TEXT_PHASE2])
    msg  = f'Filename: {filename}\n\nSermon text:\n{safe}'
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.messages.create(
                model='claude-haiku-4-5-20251001',
                max_tokens=2000,
                system=PHASE2_SYSTEM,
                messages=[{'role':'user','content':msg}],
            )
            raw   = resp.content[0].text.strip()
            start = raw.find('[')
            end   = raw.rfind(']')
            if start != -1 and end > start:
                raw = raw[start:end+1]
            raw    = raw.replace("\\'",'\'')
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed, 'success'
            return [], 'invalid_format'
        except json.JSONDecodeError as e:
            log.warning(f'Phase2 JSON error attempt {attempt+1} for {filename}: {e}')
            time.sleep(attempt+1)
        except anthropic.RateLimitError:
            time.sleep(60*(attempt+1))
        except Exception as e:
            log.warning(f'Phase2 error attempt {attempt+1} for {filename}: {e}')
            time.sleep(2*(attempt+1))
    return [], 'analysis_failed'

# ═══ AUTHOR RESOLUTION ═══════════════════════════════════════════════════════
def is_hawley_name(name):
    if not name: return False
    return any(v in name.lower() for v in HAWLEY_NAME_VARIANTS)

def resolve_author(file_meta, analysis, primary_pastor_name):
    detected = (analysis or {}).get('author_detected')
    folder   = (file_meta.get('folder') or '').lower()
    if detected and 3 < len(detected.strip()) < 60:
        return detected.strip(), is_hawley_name(detected)
    if folder in OTHER_PREACHER_FOLDERS:
        author = OTHER_PREACHER_FOLDERS[folder]
        return (author or 'Unknown'), False
    if folder in PRIMARY_PASTOR_FOLDERS or file_meta.get('folder') is None:
        return primary_pastor_name, True
    return f'Unknown ({file_meta.get("folder","root")})', False

# ═══ FOLDER CRAWLER ═══════════════════════════════════════════════════════════
def crawl_local_folder(folder_path, folder_name=None, depth=0):
    results = []
    try:
        items = sorted(Path(folder_path).iterdir())
    except PermissionError:
        return results
    for item in items:
        name_lower = item.name.lower()
        if item.is_dir():
            if name_lower in OTHER_PREACHER_FOLDERS and OTHER_PREACHER_FOLDERS[name_lower] is None:
                log.info(f'{'  '*depth}Skipping: {item.name}')
                continue
            log.info(f'{'  '*depth}Folder: {item.name}')
            results.extend(crawl_local_folder(str(item), item.name, depth+1))
        elif item.is_file() and item.suffix.lower() in SERMON_EXTENSIONS:
            parsed = parse_filename(item.name)
            results.append({
                'local_path': str(item),
                'filename':   item.name,
                'folder':     folder_name,
                'web_url':    '',
                'size_bytes': item.stat().st_size,
                'ext':        item.suffix.lower(),
                **parsed,
            })
    return results

# ═══ MICROSOFT GRAPH ══════════════════════════════════════════════════════════
class GraphClient:
    BASE = 'https://graph.microsoft.com/v1.0'
    def __init__(self):
        self._app   = msal.PublicClientApplication(MS_CLIENT_ID, authority=MS_AUTHORITY)
        self._token = None
        self._authenticate()
    def _authenticate(self):
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(MS_SCOPES, account=accounts[0])
            if result and 'access_token' in result:
                self._token = result['access_token']
                log.info('Using cached Microsoft token')
                return
        flow = self._app.initiate_device_flow(scopes=MS_SCOPES)
        print(f'\n{"="*50}\nMICROSOFT LOGIN\n1. Open: {flow["verification_uri"]}\n2. Enter: {flow["user_code"]}\n{"="*50}\n')
        result = self._app.acquire_token_by_device_flow(flow)
        if 'access_token' not in result:
            raise RuntimeError(f'Auth failed: {result.get("error_description")}')
        self._token = result['access_token']
        log.info('Microsoft login successful')
    @property
    def _headers(self): return {'Authorization': f'Bearer {self._token}'}
    def _refresh(self):
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(MS_SCOPES, account=accounts[0])
            if result and 'access_token' in result:
                self._token = result['access_token']
                return True
        return False
    def get(self, path):
        for attempt in range(2):
            r = requests.get(f'{self.BASE}{path}', headers=self._headers)
            if r.status_code == 401 and attempt == 0 and self._refresh(): continue
            r.raise_for_status()
            return r.json()
    def list_children(self, item_id):
        items = []
        url   = f'{self.BASE}/me/drive/items/{item_id}/children'
        while url:
            for attempt in range(2):
                r = requests.get(url, headers=self._headers)
                if r.status_code == 401 and attempt == 0 and self._refresh(): continue
                r.raise_for_status()
                data = r.json()
                break
            items.extend(data.get('value',[]))
            url = data.get('@odata.nextLink')
        return items
    def find_folder(self, path):
        encoded = requests.utils.quote(path, safe='/')
        item = self.get(f'/me/drive/root:/{encoded}')
        return item if item.get('folder') else None

def fetch_web_urls(graph):
    log.info('Fetching OneDrive web URLs...')
    folder = graph.find_folder(ONEDRIVE_FOLDER)
    if not folder:
        log.warning('Could not find OneDrive folder')
        return {}
    url_map = {}
    _crawl_urls(graph, folder['id'], url_map)
    log.info(f'Found {len(url_map)} web URLs')
    return url_map

def _crawl_urls(graph, folder_id, url_map):
    for item in graph.list_children(folder_id):
        name = item.get('name','')
        if item.get('folder'):
            if name.lower() == 'illustrations': continue
            _crawl_urls(graph, item['id'], url_map)
        elif item.get('file'):
            if Path(name).suffix.lower() in SERMON_EXTENSIONS:
                web_url = item.get('webUrl','')
                if web_url: url_map[name] = web_url

# ═══ SERIES DETECTION ════════════════════════════════════════════════════════
def detect_and_write_series(db, pastor_id, all_docs):
    log.info('Detecting sermon series...')
    groups = defaultdict(list)
    for doc in all_docs:
        if doc.get('series_number') is not None:
            key = f"{doc.get('folder','root')}::{doc.get('series_name') or doc.get('folder','root')}"
            groups[key].append(doc)
        elif doc.get('series_name'):
            groups[f'named::{doc["series_name"]}'].append(doc)
    written = 0
    for key, sermons in groups.items():
        if len(sermons) < 2: continue
        sermons_sorted = sorted(sermons, key=lambda s: s.get('series_number') or 0)
        dates      = [s.get('date') for s in sermons if s.get('date')]
        sermon_ids = [s.get('_firestore_id') for s in sermons if s.get('_firestore_id')]
        series_name = sermons[0].get('series_name') or key.split('::')[-1]
        ref = db.collection('series').document()
        ref.set({
            'pastor_id':    pastor_id,
            'name':         series_name,
            'sermon_ids':   sermon_ids,
            'sermon_count': len(sermons),
            'folder':       sermons[0].get('folder'),
            'date_start':   min(dates) if dates else None,
            'date_end':     max(dates) if dates else None,
            'created_at':   datetime.now().isoformat(),
        })
        series_id = ref.id
        for s in sermons:
            fid = s.get('_firestore_id')
            if fid:
                db.collection('sermons').document(fid).update({'series_id': series_id})
        written += 1
    log.info(f'Wrote {written} series')

# ═══ ALGOLIA ══════════════════════════════════════════════════════════════════
def init_algolia():
    """Initialize Algolia via REST API - no client library needed."""
    # Configure index settings
    url = f"https://{ALGOLIA_APP_ID}.algolia.net/1/indexes/{ALGOLIA_INDEX_NAME}/settings"
    headers = {
        "X-Algolia-Application-Id": ALGOLIA_APP_ID,
        "X-Algolia-API-Key": ALGOLIA_WRITE_KEY,
        "Content-Type": "application/json",
    }
    settings = {
        "searchableAttributes": ["title","summary","main_theme","keywords","author","full_text_snippet"],
        "attributesForFaceting": ["author","is_primary_pastor","folder","decade","keywords","bible_books"],
        "customRanking": ["desc(word_count)"],
    }
    try:
        r = requests.put(url, headers=headers, json=settings, timeout=10)
        r.raise_for_status()
        log.info("Algolia index configured")
    except Exception as e:
        log.warning(f"Algolia settings failed: {e}")
    return headers  # return headers for use in save_objects

def algolia_save_objects(headers, records):
    """Save objects to Algolia via REST API batch endpoint."""
    if not records: return
    url = f"https://{ALGOLIA_APP_ID}.algolia.net/1/indexes/{ALGOLIA_INDEX_NAME}/batch"
    requests_body = {
        "requests": [
            {"action": "updateObject", "body": rec}
            for rec in records
        ]
    }
    try:
        r = requests.post(url, headers=headers, json=requests_body, timeout=30)
        r.raise_for_status()
    except Exception as e:
        log.warning(f"Algolia batch save failed: {e}")

def algolia_clear_index(headers):
    """Clear all objects from Algolia index."""
    url = f"https://{ALGOLIA_APP_ID}.algolia.net/1/indexes/{ALGOLIA_INDEX_NAME}/clear"
    try:
        r = requests.post(url, headers=headers, timeout=10)
        r.raise_for_status()
        log.info("Algolia index cleared")
    except Exception as e:
        log.warning(f"Algolia clear failed: {e}")

def build_algolia_record(doc, sermon_id):
    full_text = doc.get('full_text_raw','') or ''
    return {
        'objectID':          sermon_id,
        'pastor_id':         doc.get('pastor_id',''),
        'title':             doc.get('title',''),
        'author':            doc.get('author',''),
        'is_primary_pastor': doc.get('is_primary_pastor',False),
        'summary':           doc.get('summary',''),
        'main_theme':        doc.get('main_theme',''),
        'keywords':          doc.get('keywords',[]),
        'bible_books':       doc.get('bible_books',[]),
        'folder':            doc.get('folder',''),
        'date':              doc.get('date',''),
        'decade':            doc.get('decade',''),
        'estimated_length':  doc.get('estimated_length',''),
        'word_count':        doc.get('word_count',0),
        'web_url':           doc.get('web_url',''),
        'full_text_snippet': full_text[:8000],
    }

# ═══ STATS ════════════════════════════════════════════════════════════════════
def compute_and_write_stats(db, pastor_id):
    log.info('Computing stats...')
    sermons = [d.to_dict() for d in db.collection('sermons').where('pastor_id','==',pastor_id).stream()]
    refs    = [d.to_dict() for d in db.collection('scripture_references').where('pastor_id','==',pastor_id).stream()]
    keywords = []
    primary = other = 0
    decades = defaultdict(int)
    for s in sermons:
        if s.get('is_primary_pastor'): primary += 1
        else: other += 1
        keywords.extend(s.get('keywords') or [])
        if s.get('decade'): decades[s['decade']] += 1
    books  = [normalize_book(r.get('book','')) for r in refs if r.get('book')]
    verses = [r.get('reference','') for r in refs if r.get('reference')]
    stats = {
        'pastor_id':             pastor_id,
        'total_sermons':         len(sermons),
        'william_hawley_count':  primary,
        'other_preachers_count': other,
        'total_references':      len(refs),
        'top_keywords':    [{'word':w,'count':c} for w,c in Counter(keywords).most_common(30)],
        'top_bible_books': [{'book':b,'count':c} for b,c in Counter(books).most_common(66)],
        'top_verses':      [{'reference':v,'count':c} for v,c in Counter(verses).most_common(20)],
        'sermons_by_decade': dict(decades),
        'computed_at':     datetime.now().isoformat(),
    }
    db.collection('stats').document(pastor_id).set(stats)
    db.collection('stats').document('global').set(stats, merge=True)
    log.info(f'Stats: {len(sermons)} sermons, {len(refs)} refs, {len(set(books))} books')

# ═══ FIRESTORE HELPERS ═══════════════════════════════════════════════════════
def ensure_pastor(db, name, desc):
    existing = list(db.collection('pastors').where('name','==',name).limit(1).stream())
    if existing: return existing[0].id
    ref = db.collection('pastors').document()
    ref.set({'name':name,'description':desc,'created_at':firestore.SERVER_TIMESTAMP})
    log.info(f'Created pastor: {name} (id: {ref.id})')
    return ref.id

def get_existing_filenames(db, pastor_id):
    docs = db.collection('sermons').where('pastor_id','==',pastor_id).stream()
    return {d.to_dict().get('filename') for d in docs if d.to_dict().get('filename')}

def flush_batch(db, algolia_index, pastor_id, batch):
    wb = db.batch()
    algolia_records = []
    written_docs    = []
    for doc, refs in batch:
        ref = db.collection('sermons').document()
        doc['_firestore_id'] = ref.id
        clean_doc = {k:v for k,v in doc.items() if k != '_firestore_id'}
        wb.set(ref, clean_doc)
        algolia_records.append(build_algolia_record(doc, ref.id))
        written_docs.append(doc)
    wb.commit()
    # Write scripture references
    ref_batch  = db.batch()
    ref_count  = 0
    for doc, refs in batch:
        sermon_id = doc.get('_firestore_id')
        for r in refs:
            book = normalize_book(r.get('book',''))
            rref = db.collection('scripture_references').document()
            ref_batch.set(rref, {
                'sermon_id':   sermon_id,
                'pastor_id':   pastor_id,
                'reference':   r.get('reference',''),
                'book':        book,
                'chapter':     r.get('chapter',0),
                'verse_start': r.get('verse_start',0),
                'verse_end':   r.get('verse_end',0),
                'context':     r.get('context',''),
                'osis_ref':    get_osis_ref(book, r.get('chapter',0), r.get('verse_start',0)),
            })
            ref_count += 1
            if ref_count % 400 == 0:
                ref_batch.commit()
                ref_batch = db.batch()
    if ref_count % 400 != 0 or ref_count == 0:
        ref_batch.commit()
    if algolia_records:
        try: algolia_save_objects(algolia_index, algolia_records)
        except Exception as e: log.warning(f'Algolia batch failed: {e}')
    log.info(f'Wrote {len(batch)} sermons, {ref_count} references')
    return written_docs, ref_count

# ═══ MAIN ════════════════════════════════════════════════════════════════════
def run_ingestion(args):
    pastor_name = args.pastor or DEFAULT_PASTOR_NAME
    pastor_desc = args.desc   or DEFAULT_PASTOR_DESC
    local_path  = args.local  or LOCAL_BASE_PATH
    print('\n'+'='*60)
    print(f'  SERMON LIBRARY INGESTION v3')
    print(f'  Pastor: {pastor_name}')
    print(f'  Source: {local_path}')
    print('='*60+'\n')
    if not ANTHROPIC_API_KEY:
        print('ERROR: Anthropic API key not found.')
        sys.exit(1)
    if not Path(local_path).exists():
        print(f'ERROR: Source folder not found: {local_path}')
        sys.exit(1)
    log.info('Initializing Firebase...')
    db = init_firebase()
    log.info('Initializing Algolia...')
    algolia_index = init_algolia()
    if not args.resume and not args.no_wipe:
        answer = input('Wipe Firestore + Algolia and start fresh? (YES to confirm): ').strip()
        if answer == 'YES':
            wipe_firestore(db)
            try:
                algolia_clear_index(algolia_index)
                log.info('Algolia index cleared')
            except Exception as e:
                log.warning(f'Algolia clear failed: {e}')
    log.info('Initializing Anthropic...')
    ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    pastor_id = ensure_pastor(db, pastor_name, pastor_desc)
    log.info(f'Pastor ID: {pastor_id}')
    web_urls = {}
    try:
        graph    = GraphClient()
        web_urls = fetch_web_urls(graph)
    except Exception as e:
        log.warning(f'Could not fetch web URLs: {e}')
    log.info('Scanning local files...')
    all_files = crawl_local_folder(local_path)
    log.info(f'Found {len(all_files)} sermon files')
    if args.resume:
        existing  = get_existing_filenames(db, pastor_id)
        all_files = [f for f in all_files if f['filename'] not in existing]
        log.info(f'Resuming: {len(all_files)} files remaining')
    if not all_files:
        log.info('Nothing to process.')
        compute_and_write_stats(db, pastor_id)
        return
    batch      = []
    errors     = []
    all_docs   = []
    converted_count = 0
    total_refs = 0
    for file_meta in tqdm(all_files, desc='Ingesting sermons', unit='sermon'):
        filename = file_meta['filename']
        ext      = file_meta['ext']
        try:
            using_converted = False
            if ext == '.doc':
                converted = get_converted_path(Path(file_meta['local_path']))
                if converted and converted.exists():
                    using_converted = True
                    converted_count += 1
            raw_text, quality = extract_text(file_meta['local_path'])
            if using_converted: quality = 'high'
            meta, status1 = analyze_phase1(ai, raw_text, filename)
            time.sleep(REQUEST_DELAY)
            refs, status2 = analyze_phase2(ai, raw_text, filename)
            time.sleep(REQUEST_DELAY)
            author, is_primary = resolve_author(file_meta, meta, pastor_name)
            for r in refs:
                r['book'] = normalize_book(r.get('book',''))
            bible_books = list({r['book'] for r in refs if r.get('book')})
            date_str = (meta or {}).get('date_detected') or file_meta.get('date')
            year     = file_meta.get('year')
            decade   = file_meta.get('decade')
            if date_str and not year:
                try:
                    dt     = datetime.strptime(date_str,'%Y-%m-%d')
                    year   = dt.year
                    decade = f'{(year//10)*10}s'
                except Exception:
                    pass
            title = (meta or {}).get('title') or file_meta['clean_name']
            doc = {
                'pastor_id':            pastor_id,
                'filename':             filename,
                'folder':               file_meta.get('folder'),
                'web_url':              web_urls.get(filename,''),
                'author':               author,
                'is_primary_pastor':    is_primary,
                'date':                 date_str,
                'year':                 year,
                'decade':               decade,
                'series_name':          (meta or {}).get('series_name') or file_meta.get('series_name'),
                'series_number':        file_meta.get('series_number'),
                'series_id':            None,
                'title':                title,
                'title_lower':          title.lower(),
                'summary':              (meta or {}).get('summary',''),
                'main_theme':           (meta or {}).get('main_theme',''),
                'structure':            (meta or {}).get('structure',{}),
                'keywords':             (meta or {}).get('keywords',[]),
                'bible_books':          bible_books,
                'word_count':           len(raw_text.split()) if raw_text else 0,
                'estimated_length':     (meta or {}).get('estimated_length','unknown'),
                'extraction_quality':   quality,
                'processing_status':    status1,
                'scripture_ref_count':  len(refs),
                'notes':                (meta or {}).get('notes'),
                'processed_at':         datetime.now().isoformat(),
                'file_size_bytes':      file_meta.get('size_bytes',0),
                'full_text_raw':        raw_text[:50000] if raw_text else '',
            }
            batch.append((doc, refs))
            if len(batch) >= BATCH_SIZE:
                written, ref_count = flush_batch(db, algolia_index, pastor_id, batch)
                all_docs.extend(written)
                total_refs += ref_count
                batch = []
        except Exception as e:
            log.error(f'FAILED: {filename} -- {e}', exc_info=True)
            errors.append({'filename': filename, 'error': str(e)})
    if batch:
        written, ref_count = flush_batch(db, algolia_index, pastor_id, batch)
        all_docs.extend(written)
        total_refs += ref_count
    detect_and_write_series(db, pastor_id, all_docs)
    compute_and_write_stats(db, pastor_id)
    print(f'\n{"="*60}')
    print(f'  COMPLETE')
    print(f'  Sermons:    {len(all_files) - len(errors)}')
    print(f'  LibreOffice:{converted_count}')
    print(f'  References: {total_refs}')
    print(f'  Errors:     {len(errors)}')
    print(f'{"="*60}\n')
    if errors:
        with open('failed_files.json','w') as f: json.dump(errors, f, indent=2)
        print('Failed: failed_files.json')
        print('Retry: python ingest.py --resume --no-wipe')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Ingest sermons v3')
    parser.add_argument('--pastor',     help='Pastor name')
    parser.add_argument('--desc',       help='Description')
    parser.add_argument('--local',      help='Local folder path')
    parser.add_argument('--resume',     action='store_true')
    parser.add_argument('--no-wipe',    action='store_true', dest='no_wipe')
    parser.add_argument('--stats-only', action='store_true', dest='stats_only')
    args = parser.parse_args()
    if args.stats_only:
        db = init_firebase()
        pastor_name = args.pastor or DEFAULT_PASTOR_NAME
        existing = list(db.collection('pastors').where('name','==',pastor_name).limit(1).stream())
        if existing: compute_and_write_stats(db, existing[0].id)
        else: print(f'Pastor not found: {pastor_name}')
    else:
        run_ingestion(args)
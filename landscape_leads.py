#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════════════════
LUXURY HOME LANDSCAPE LIGHTING LEAD GENERATOR v2.0
For Landscape Lighting Businesses – Long Island, NY
════════════════════════════════════════════════════════════════════
Finds homes sold $1.3M+ in Northern Nassau + all of Suffolk County.
Uses Redfin county-level API (2 requests vs 107 per-town searches).
Downloads exterior photos. Generates AI landscape lighting renders.

Usage:
  python landscape_leads.py
  python landscape_leads.py --min-price=1300000 --max-age=730 --max-total=50

Setup:
  pip install requests beautifulsoup4 lxml openai Pillow
  export OPENAI_API_KEY="sk-..."
"""
import argparse, os, re, sys, json, time, base64, logging, traceback, csv, io
import requests
from io import BytesIO
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from bs4 import BeautifulSoup
from PIL import Image
import openai

# ─────────────────────────────────────────────────────────────────
# CLI ARGUMENTS
# ─────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="Landscape Lighting Lead Generator")
    p.add_argument("--min-price",       type=int, default=1_300_000)
    p.add_argument("--max-age",         type=int, default=730, help="Max days since sale")
    p.add_argument("--max-total",       type=int, default=50)
    p.add_argument("--max-per-town",    type=int, default=25)
    p.add_argument("--output-dir",      type=str, default="")
    p.add_argument("--street-view-key", type=str, default="")
    return p.parse_args()

args = parse_args()

OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "")
MIN_SALE_PRICE  = args.min_price
MAX_AGE_DAYS    = args.max_age
MAX_TOTAL       = args.max_total
MAX_PER_TOWN    = args.max_per_town
REQUEST_DELAY   = 2.5  # seconds between requests
STREET_VIEW_KEY = os.environ.get("STREET_VIEW_KEY", args.street_view_key)
OUTPUT_DIR      = Path(args.output_dir) if args.output_dir else Path(__file__).parent / "leads_output"

# ─────────────────────────────────────────────────────────────────
# TARGET TOWNS (fallback if county search fails)
# ─────────────────────────────────────────────────────────────────
NORTHERN_NASSAU = [
    "Great Neck","Port Washington","Manhasset","Roslyn","Glen Cove",
    "Oyster Bay","Locust Valley","Brookville","Old Westbury","Muttontown",
    "East Hills","Kings Point","Lake Success","North Hills","Sea Cliff",
]
SUFFOLK_TOWNS = [
    "Huntington","Cold Spring Harbor","Lloyd Harbor","Northport",
    "Smithtown","Head of the Harbor","Nissequogue","St James",
    "Stony Brook","Port Jefferson","East Setauket",
    "East Hampton","Southampton","Bridgehampton","Sag Harbor",
    "Water Mill","Quogue","Shelter Island","Melville","Dix Hills","Woodbury",
]

# ─────────────────────────────────────────────────────────────────
# LOGGING (FlushingHandler so Streamlit sees output immediately)
# ─────────────────────────────────────────────────────────────────
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
log_file = OUTPUT_DIR / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

class FlushHandler(logging.StreamHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        FlushHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
)
log = logging.getLogger("leads")

# ─────────────────────────────────────────────────────────────────
# REDFIN SCRAPER (county-level – 2 searches instead of 107)
# ─────────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.redfin.com/",
}

# Known Redfin county region IDs for Long Island
REDFIN_COUNTIES = [
    {"name": "Nassau County, NY",  "region_id": "1974", "region_type": "5"},
    {"name": "Suffolk County, NY", "region_id": "1996", "region_type": "5"},
]

class RedfinScraper:
    BASE = "https://www.redfin.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    # ── internal GET with delay ────────────────────────────────────
    def _get(self, url: str, **kwargs) -> Optional[requests.Response]:
        time.sleep(REQUEST_DELAY)
        try:
            r = self.session.get(url, timeout=30, **kwargs)
            log.info(f"  HTTP {r.status_code} <- {url[:80]}")
            if r.status_code == 200 and r.text[:9].lstrip().startswith("<!"):
                log.warning(f"  Got HTML instead of data (bot-detection?)")
                return None
            r.raise_for_status()
            return r
        except Exception as e:
            log.warning(f"  Request failed ({type(e).__name__}): {e}")
            return None

    # ── dynamic region ID lookup via autocomplete ──────────────────
    def get_region_id(self, location: str) -> Optional[Tuple[str, str]]:
        url = f"{self.BASE}/stingray/do/location-autocomplete"
        r = self._get(url, params={"location": location, "v": "2"})
        if not r: return None
        try:
            text = r.text
            if text.startswith("{}&&"): text = text[4:]
            data = json.loads(text)
            for section in data.get("payload", {}).get("sections", []):
                for row in section.get("rows", []):
                    path = row.get("url", "")
                    m = re.search(r"/county/(\d+)/", path)
                    if m: return (m.group(1), "5")
                    m = re.search(r"/city/(\d+)/", path)
                    if m: return (m.group(1), "6")
        except Exception as e:
            log.debug(f"  Autocomplete parse error: {e}")
        return None

    # ── county-level CSV download ──────────────────────────────────
    def search_county_csv(self, region_id: str, min_price: int, max_age_days: int) -> List[Dict]:
        url = f"{self.BASE}/stingray/api/gis-csv"
        params = {
            "al": 1, "market": "newyork", "v": 8,
            "min_price": min_price, "sold_within_days": max_age_days,
            "status": 9, "uipt": "1,2,3,4,7,8",
            "region_type": 5, "region_id": region_id,
            "num_homes": 350, "sf": "1,2,3,5,6,7",
        }
        log.info(f"  Fetching sold listings CSV (region_id={region_id})...")
        r = self._get(url, params=params)
        if not r:
            log.warning("  CSV request returned no response")
            return []
        try:
            reader = csv.DictReader(io.StringIO(r.text))
            results = []
            for row in reader:
                try:
                    price_str = next((row[k] for k in row if "PRICE" in k.upper()), "0")
                    price     = int(re.sub(r"[^0-9]", "", str(price_str)) or "0")
                    if price < min_price: continue
                    address  = next((row[k] for k in row if "ADDRESS" in k.upper()), "")
                    city     = next((row[k] for k in row if "CITY" in k.upper() or "TOWN" in k.upper() or "LOCATION" in k.upper()), "")
                    state    = next((row[k] for k in row if "STATE" in k.upper()), "NY")
                    zipcode  = next((row[k] for k in row if "ZIP" in k.upper()), "")
                    sold     = next((row[k] for k in row if "SOLD" in k.upper() and "DATE" in k.upper()), "")
                    beds     = next((row[k] for k in row if "BED" in k.upper()), "")
                    baths    = next((row[k] for k in row if "BATH" in k.upper()), "")
                    sqft     = next((row[k] for k in row if "SQUARE" in k.upper() or "SQFT" in k.upper() or "SQ FT" in k.upper()), "")
                    url_col  = next((row[k] for k in row if k.upper().startswith("URL")), "")
                    detail_url = url_col if url_col.startswith("http") else (self.BASE + url_col if url_col else "")
                    # If city not found in columns, try to extract town from Redfin URL
                    # Redfin URLs look like: /NY/Huntington/123-Main-St-11743/home/...
                    if not city and detail_url:
                        m_town = re.search(r'/NY/([^/]+)/', detail_url)
                        if m_town:
                            city = m_town.group(1).replace("-", " ").title()
                    # Build full address — always include city/town so the display shows the location
                    city_str = city.strip() if city else ""
                    zip_str = zipcode.strip() if zipcode else ""
                    state_str = (state or "NY").strip()
                    parts = [p for p in [address.strip(), city_str, f"{state_str} {zip_str}".strip()] if p and p != "NY"]
                    full_address = ", ".join(parts)
                    if address:
                        results.append({
                            "address":    full_address,
                            "price":      price, "sold_date": sold,
                            "zillow_url": detail_url, "redfin_url": detail_url,
                            "thumbnail":  "", "beds": beds, "baths": baths, "sqft": sqft,
                            "source":     "redfin_csv",
                        })
                except Exception: continue
            log.info(f"  {len(results)} homes found in CSV")
            return results
        except Exception as e:
            log.warning(f"  CSV parse error: {e}")
            return []

    # ── county-level GIS JSON (fallback) ──────────────────────────
    def search_county_gis(self, region_id: str, min_price: int, max_age_days: int) -> List[Dict]:
        url = f"{self.BASE}/stingray/api/gis"
        params = {
            "al": 1, "market": "newyork", "v": 8,
            "min_price": min_price, "sold_within_days": max_age_days,
            "status": 9, "uipt": "1,2,3,4,7,8",
            "region_type": 5, "region_id": region_id,
            "num_homes": 350, "sf": "1,2,3,5,6,7",
        }
        log.info(f"  Trying GIS JSON fallback (region_id={region_id})...")
        r = self._get(url, params=params)
        if not r: return []
        try:
            text = r.text
            if text.startswith("{}&&"): text = text[4:]
            data  = json.loads(text)
            homes = data.get("payload", {}).get("homes", [])
            results = []
            for h in homes:
                try:
                    price_info = h.get("price", {})
                    price = price_info.get("value", 0) if isinstance(price_info, dict) else int(re.sub(r"[^0-9]","",str(price_info)) or "0")
                    if price < min_price: continue
                    sl  = h.get("streetLine", {})
                    address = sl.get("value","") if isinstance(sl, dict) else str(sl)
                    csz = h.get("cityStateZip",{})
                    city_state_zip = csz.get("value","") if isinstance(csz, dict) else str(csz)
                    path = h.get("url","")
                    detail_url = (self.BASE + path) if path and not path.startswith("http") else path
                    beds = h.get("beds","")
                    sqft_info = h.get("sqFt",{})
                    sqft = sqft_info.get("value","") if isinstance(sqft_info,dict) else str(sqft_info)
                    if address:
                        results.append({
                            "address":    f"{address}, {city_state_zip}".strip(", "),
                            "price":      price, "sold_date": "",
                            "zillow_url": detail_url, "redfin_url": detail_url,
                            "thumbnail":  "", "beds": beds, "baths": "", "sqft": sqft,
                            "source":     "redfin_gis",
                        })
                except Exception: continue
            log.info(f"  {len(results)} homes found via GIS")
            return results
        except Exception as e:
            log.warning(f"  GIS parse error: {e}")
            return []

    # ── per-town fallback ──────────────────────────────────────────
    def search_town(self, town: str, min_price: int, max_age_days: int) -> List[Dict]:
        years = max(1, max_age_days // 365)
        slug  = town.replace(" ", "-")
        url   = (
            f"{self.BASE}/NY/{slug}/"
            f"filter/min-price={min_price},include=sold-{years}yr,property-type=house"
        )
        log.info(f"  Redfin town search: {town}, NY...")
        r = self._get(url)
        if not r: return []
        results = []
        try:
            soup = BeautifulSoup(r.text, "lxml")
            for script in soup.find_all("script"):
                raw = script.string or ""
                if "lastSoldPrice" not in raw and "soldDate" not in raw: continue
                for m in re.finditer(r'\{[^{}]{30,2000}\}', raw):
                    try:
                        obj = json.loads(m.group())
                        price_raw = obj.get("lastSoldPrice", obj.get("price", 0))
                        price = int(re.sub(r"[^0-9]","",str(price_raw)) or "0")
                        if price < min_price: continue
                        sl      = obj.get("streetLine", {})
                        address = sl.get("value","") if isinstance(sl,dict) else str(sl)
                        path    = obj.get("url","")
                        detail_url = (self.BASE+path) if path and not path.startswith("http") else path
                        if address:
                            results.append({
                                "address":    f"{address}, {town}, NY",
                                "price":      price, "sold_date": "",
                                "zillow_url": detail_url, "redfin_url": detail_url,
                                "thumbnail":  "", "source": "redfin_html",
                            })
                    except Exception: continue
                if results: break
        except Exception as e:
            log.debug(f"  HTML parse error: {e}")
        log.info(f"  {len(results)} homes in {town}")
        return results

    # ── get exterior photo URL from detail page ────────────────────
    def get_exterior_photo(self, redfin_url: str) -> Optional[str]:
        if not redfin_url: return None
        r = self._get(redfin_url)
        if not r: return None
        try:
            soup = BeautifulSoup(r.text, "lxml")
            og = soup.find("meta", {"property": "og:image"})
            if og and og.get("content"): return og["content"]
            imgs = soup.select("img[src*='cdn-redfin.com']")
            if imgs: return max(imgs, key=lambda i: len(i.get("src",""))).get("src","")
            for script in soup.find_all("script"):
                raw = script.string or ""
                m = re.search(r'""url"\s:+\s*"(https://[^"]*cdn-redfin[[^"]*)"', raw)
                if m: return m.group(1)
        except Exception as e:
            log.debug(f"  Photo extraction error: {e}")
        return None

    def download_image(self, url: str) -> Optional[bytes]:
        if not url: return None
        try:
            r = self.session.get(url, timeout=30)
            r.raise_for_status()
            return r.content if len(r.content) > 5_000 else None
        except Exception as e:
            log.warning(f"  Image download failed: {e}")
            return None

    def search_bing_image(self, addr\�Έ��HO��[ۘ[���N������X\���[��[XY�\��܈[�^\�[܈��وH��\�K�����]Y\�HH���Y�\��H^\�[܈�\�H��۝��\�H�΋����˘�[�˘��K�[XY�\���X\����\�[\�HȜH��]Y\�K��ܛH�����̈���\����K��Ȏ��[XY�Rݙ\�]H�B�XY\��H�\�\�PY�[����[ޚ[K�K�
�[�����L���[���
�
H\U�X��]�L�ˌ͈
�SZ�H�X���H���YK�L������Y�\�K�L�ˌ͈���X��\���^�[\X�][ۋ�[
�[
�ʎ�OL����X��\S[��XY�H���[�UT�[��OL�H����Y�\�\����΋����˘�[�˘��Kȋ�B��N��[YK��Y\
JB��H�\]Y\�˙�]
\�\�[\�\\�[\�XY\��ZXY\��[Y[�]LMJB�Y����]\����HOH����]\���ۙB�X]�\�H�K��[�[
�ț]\����΋��׈�J��Κ���Y���JΖ׈�^�
LJO�H����^
B�Y�X]�\΂��˚[������[��[XY�H��[���X]�\��VΎ_H�B��]\��X]�\��B�^�\^�\[ۈ\�N���˙X�Y����[��[XY�H�X\��\��܎��_H�B��]\���ۙB��Y��X\��ܙX[ܗ����[�Y�\�Έ��HO��[ۘ[���N������X\���X[܋���H�܈[�^\�[܈���HY�\�ˈ����\�H�΋����˜�X[܋���K�\K݌Kܙ���X\���ܜ��Y[��Y\��\�X\��Y�܋\�[K\�X\��	���[XO]�\�H��XY\��H�\�\�PY�[����[ޚ[K�K�
�[�����L���[���
�
H\U�X��]�L�ˌ͈
�SZ�H�X���H���YK�L������Y�\�K�L�ˌ͈���X��\���\X�][ۋڜ�ۈ����۝[�U\H���\X�][ۋڜ�ۈ���ܚY�[����΋����˜�X[܋���H����Y�\�\����΋����˜�X[܋���Kȋ�B���HH�]Y\�H������]Y\�H�ۜ�[Y\��X\��]Y\�J	]Y\�N��X\��]Y\�HK	[Z]�[�
H�YW��X\��
]Y\�N�	]Y\�K[Z]�	[Z]
H�\�[�������Y�H�[X\�W�����Y�HB�B�H������\�XX�\Ȏ��]Y\�H��Ȝ�X\�����][ۈ��ț��][ۈ��Y�\��_K��[Z]��B�B��N��[YK��Y\
JB��H�\]Y\�˜��
\���ۏX��KXY\��ZXY\��[Y[�]LMJB�Y����]\����HOH���]HH����ۊ
B��\�[�H]K��]
	�]I��JK��]
	��YW��X\��	��JK��]
	ܙ\�[���JB��܈�\�[��\�[΂��[X\�HH�\˙�]
	��[X\�W�����JH܈�B��Y�H�[X\�K��]
	��Y��	��B�Y��Y����˚[�����X[܋���H����[��B��]\���Y�����H�\˙�]
	������JH܈�B�Y����[�����K��]
	��Y��N���˚[�����X[܋���H����[��B��]\������V���Y��B���[�X�Έ�ܘ\HY�B��X\���\�H��΋����˜�X[܋���KܙX[\�]X[��Y\�\�X\����Y�\�˜�\X�J	�	�	�I�K��\X�J	�	�	��_H����H�[����]
�X\���\�
B�Y�����X]�\�H�K��[�[
�Ȝ�[X\�W��ȗʎ�ʗ�ןWJ���Y��ʎ�ʈ�΋��\���^���K�׈�J�H�����^
B�Y�X]�\΂��˚[�����X[܋���H����[��XHY�H�ܘ\H�B��]\��X]�\��B�^�\^�\[ۈ\�N���˙X�Y����X[܋���H��\��܎��_H�B��]\���ۙB��Y��X\�����Y]ݚY]��[�Y�\�Έ��\W��^N���HO��[ۘ[؞]\�N������]�^\�[܈���XH����H��Y]�Y]��]X�TK����]\���[XY�H�]\�\�X�H
��HT�
K��\�\��]\���\��ܗ���O]�YH��H

\��]\��Y
[��XYوHܘ^B�X�Z�\�H�[�����Y]�Y]�[XY�\�H^\���܈HY�\�˂�����Y���\W��^N���]\���ۙB��N��\�H�΋��X\˙����X\\˘��K�X\��\K���Y]�Y]Ȃ�\�[\�H��^�H����
�����][ۈ��Y�\�����^H��\W��^K���݈���L���]����L����]\���\��ܗ���H����YH��B��H�[���\��[ۋ��]
\�\�[\�\\�[\�[Y[�]LMJB�Y����]\����HOH�[��[XY�H�[���XY\�˙�]
��۝[�]\H���N��Y�[����۝[�
H�
W����X[���\�H\��N�[�HH\��܈[XY�B��˚[������Y]�Y]���؝Z[�YH�B��]\�����۝[���˙X�Y����Y]�Y]Έ�\�ۜ�H���X[��\[�ȊB��]\���ۙB��˙X�Y�����Y]�Y]Έ܋��]\����_H
��[XY�\�H]�Z[X�JH�B��]\���ۙB�^�\^�\[ۈ\�N���˝�\��[������Y]�Y]�TH\��܎��_H�B��]\���ۙB����8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� ��RHS���THQ�S���S�T�T���8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� ��\��[���\T�[�\�\���Y���[�]���[�\W��^N���N��Y���\W��^N���Z\�H�[YQ\��܊��[�RHTH�^H�\]Z\�Y��B��[���Y[�H�[�ZK��[�RJ\W��^OX\W��^JB��Y�\�ܚX�W��YJ�[�[XY�W؞]\Έ�]\�HO�������H�\�M����[���J[XY�W؞]\�K�X��J
B��N���\�H�[���Y[���]���\][ۜ˘ܙX]J�[�[H��Mȋ�Y\��Y�\�V�Ȝ��H���\�\����۝[���ȝ\H���[XY�W�\���[XY�W�\���ȝ\�����]N�[XY�KڜY�ؘ\�M�؍�H��]Z[���Y��_K�ȝ\H���^��^����\�ܚX�H\��YH^\�[܈�܈H[���\HY�[��\�Yۙ\�[���[�[��\Η����H\��]X�\�[�[H
��ۚX[�۝[\ܘ\�KY܋�\�Z�\�K]ˊW����H^\�[܈X]\�X[�[���ܜ�����H�^H�X]\�\Έ��[[��ܛY\���[����ܝX���\�Y�K�Y\��]�]�^W�����H�X�Y�X�8�%\��[�H\�Y��[�\�]HH[���\HY�[���[�\�[�ˈ��
_B�_WK�X^���[��L��
B��]\���\����X�\��K�Y\��Y�K��۝[��^�\^�\[ۈ\�N���˝�\��[�����M�[�[\�\��Z[Y��_H�B��]\���H\��H^\�H�[��KY�[Z[H�YH�]�ٙ\��[ۘ[[���\[��[�H]�Y�]�]�^K����Y��[�\�]Wܙ[�\�[���[��\�W�\�ܚ\[ێ���HO��[ۘ[؞]\�N����\H
����ܙX[\�X�[���\HY�[��\�Yۈ�[�\�[��وH^\�H�YH]�[Y�������QN���\�W�\�ܚ\[۟H���Q�S�Έ�\�H���Q\Y��ۈ�X�YK[X�\�]Y��[ۙ��]�]�^K���\��]X�\�[��Y��ۈ��[[��[�ܛY\���YH\Y�[��Y�Z[��Y\�YH�[Y���K����\Y�[���\�[�X��[�Y���\�H������H�[���ˈ����ܙX[\�X�XY�^�[�K\]X[]K�[Y��\��][��\�K���
B��N���\�H�[���Y[��[XY�\˙�[�\�]J�[�[H�[YKLȋ��\\��\��^�OH�M�L�L��]X[]OH���LK�[OH��]\�[��
B�[Y�܈H�\]Y\�˙�]
�\��]V�K�\�[Y[�]M�
B�[Y�܋��Z\�Wٛܗ��]\�
B��]\��[Y�܋��۝[��^�\�[�ZK��Y�\]Y\�\��܎���N���\�H�[���Y[��[XY�\˙�[�\�]J�[�[H�[YKLȋ���\J���^\�H�YH]\���]�ٙ\��[ۘ[[���\HY�[�ˈ������\�W�\�ܚ\[ۖΌML_H����\�HQ\Y�[��[X�\�]Y���YH\Y�[���[Y��YH��K�����ܙX[\�X��[�\�[�ˈ��
K��^�OH�M�L�L��]X[]OH���LK�
B�[Y�܈H�\]Y\�˙�]
�\��]V�K�\�[Y[�]M�
B��]\��[Y�܋��۝[��^�\^�\[ۈ\�L����˙\��܊���[�\�[���]�H�Z[Y��L�H�B��]\���ۙB�^�\^�\[ۈ\�N���˙\��܊���[�\�[���Z[Y��_H�B��]\���ۙB����8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� ��PQ�S�T�UԈ8�$�PRS�Ԑ�T��UԂ��8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� ��\��XY�[�\�]܎��Y���[�]���[�N��Y����S�RW�TW��VN���˙\��܊��S�RW�TW��VH\����]��B��\˙^]
JB��[���Y�[�H�Y�[��ܘ\\�
B��[���[�\�\�H[���\T�[�\�\��S�RW�TW��VJB��[���]�Hș��[������Ȏ���[�\�[��Ȏ����\Y���\��ܜȎ�B��[��ۙWٚ[HH�UU�T������\]Y�Y�\��\˚��ۈ���[��ۙN��]H�]

B�Y��[��ۙWٚ[K�^\��
N���N���]�[��[��ۙWٚ[JH\�����[��ۙHH�]
��ۋ��Y
�JB��˚[������\�[Z[��H�[��[��ۙJ_H�Y\�[�XYHۙH���H�[܈�[�ȊB�^�\^�\[ێ��\��Y���Y�Wۘ[YJ�[�Y�\�Έ��HO������[YHH�K��X��������ʗI���Y�\��B��]\���K��X����ȋ���[YJK���\

VΌL�B��Y���]�J�[�Y�\�Έ��ܚYΈ�]\��[�\�[�Έ�[ۘ[؞]\�KY]N�X�
N����\�H�UU�T���[����Y�Wۘ[YJY�\��B���\��Z�\�\�[��U�YK^\����U�YJB�Y�ܚY΂��]�[���\���ܚY�[�[��ȋ�؈�H\�����ܚ]JܚY�B�Y��[�\�[�΂��]�[���\����]�[���\W�Y�[�˚�ȋ�؈�H\�����ܚ]J�[�\�[��B��]�[���\�����\�W�[��˝��ȊH\������ܚ]J��Y�\�Έ�Y�\��W��B���ܚ]J���[H�X�N�	�Y]K��]
	��X�I�
N�W��B���ܚ]J����]N��Y]K��]
	����]I�	�[�ۛ�ۉ�_W��B���ܚ]J���Y���\Έ�Y]K��]
	ؙY��	Ӌ�I�_W��B���ܚ]J���]���\Έ�Y]K��]
	ؘ]��	Ӌ�I�_W��B���ܚ]J���H���Y]K��]
	��Y�	�	Ӌ�I�_W��B���ܚ]J���Y�[�T���Y]K��]
	ܙY�[��\�	�	Ӌ�I�_W��B���ܚ]J���[�\�]Y��]][YK����
K����[YJ	�VKI[KIY	R�SI�_W��B��]\����\���Y��X\���ۙJ�[�Y�\�Έ��N���[��ۙK�Y
Y�\��B��N���]�[��[��ۙWٚ[K�ȊH\������ۋ�[\
\�
�[��ۙJK�B�^�\^�\[ێ��\��Y����\����YJ�[����X�
HO������Y�\��H����]
�Y�\�ȋ�[�ۛ�ۈ�B�Y�Y�\��[��[��ۙH܈Y�\��OH�[�ۛ�ۈ����[���]�Ȝ��\Y�H
�HB��]\���[�B���˚[��������� 	ʍ�H�B��˚[������YN��Y�\��H�B��˚[������X�N�	�����]
	��X�I�
N�H��������]
	����]I�	�[�ۛ�ۉ�_H�B���8� 8� ��X�]Z\�][ێ��HXX���\��H[�ܙ\�8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� ��˚[�����]�[��^\�[܈�ˋ���B����\�H����]
�[X��Z[���H܈�[���Y�[���]�^\�[ܗ�������]
��Y�[��\����JB��Y������\����˚[�����Y�[���[�]�Z[X�HH�Z[���[��[XY�H�X\������B����\�H�[���Y�[���X\��ؚ[���[XY�JY�\��B��Y������\����˚[�����Z[���X[܋���K����B����\�H�[���Y�[���X\��ܙX[ܗ���Y�\��B��[Y�؞]\�H�ۙB�Y����\���[Y�؞]\�H�[���Y�[���ۛ�Y�[XY�J���\�
B�Y�[Y�؞]\΂��N��[Y�H[XY�K��[��]\�S�[Y�؞]\�JB��H[Y˜�^�B�Y���܈����˝�\��[����[XY�H���X[
��^�JHH�Z[����Y]�Y]ȊB�[Y�؞]\�H�ۙB�[Y�[Y˙�ܛX]��[�
��Qȋ��ȊN���Y�H�]\�S�
B�[Y˘�۝�\�
��Ј�K��]�J�Y��ܛX]H��Qȋ]X[]ONL
B�[Y�؞]\�H�Y���]�[YJ
B�^�\^�\[ۈ\�N���˝�\��[����[��[Y[XY�N��_HH�Z[����Y]�Y]ȊB�[Y�؞]\�H�ۙB�[�N���˝�\��[�����[���ۛ�Y��H�Z[����Y]�Y]ȊB���8� 8� ����H��Y]�Y]��[�X��8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� �Y���[Y�؞]\΂�Y���QUՒQU���VN���˚[�����Z[������H��Y]�Y]��]X�TK����B�[Y�؞]\�H�[���Y�[���X\�����Y]ݚY]�Y�\����QUՒQU���VJB�Y���[Y�؞]\΂��˚[������Y]�Y]��]\��Y��[XY�\�HH�[�\�][�����H��\�H]H�B�[�N���˚[��������Y]�Y]��^HH�[�\�][�����H��\�H]H�B���8� 8� �Z[\�ܚ\[ێ��M����H��܈^���H]H8� 8� �Y�[Y�؞]\΂��[���]�Ȝ��ȗH
�HB��˚[������؝Z[�YH[�[^�[���]�Mˋ���B�\�ܚ\[ۈH�[���[�\�\��\�ܚX�W��YJ[Y�؞]\�B��˚[�����\�ܚ\[ێ��\�ܚ\[ۖΌL_K����B�[�N���˚[��������H�Z[[��\�ܚ\[ۈ���H��\�H]K����B��X�HH����]
	��X�I�
B��Y�H����]
	ؙY��	��B��Y�H����]
	��Y�	�	��B��[HH�ܘ[�\�]H�Y��X�H�
[�H�^\�H���Y���H��ؙY�KX�Y���K�Y��Y�[�H����Y����H����Y�H�H��Y��Y�[�H���\�ܚ\[ۈH
���H��[_H�[��KY�[Z[H�YH[�ۙ�\�[��K�����ؙY���^��Y����\��\�H�]�ٙ\��[ۘ[[���\[������X[�X�\�YY�\�X]\�H�Y\�H�YH]�Y�]�]�^K����[�[Y�[�\��]X�\�[]Z[�\X�[وY�Y[��\��]K��Y������[�H�Y\ˈ��
B��˚[�����\�ܚ\[ێ��\�ܚ\[ۖΌL_K����B���8� 8� SQH��[�\�[��8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� ��˚[�����[�\�][��[���\HY�[���[�\�[���]SQHˋ���B��[�\�[��H�[���[�\�\���[�\�]Wܙ[�\�[��\�ܚ\[ۊB�Y��[�\�[�΂��[���]�Ȝ�[�\�[��ȗH
�HB��˚[�����[�\�[��ܙX]YH�B�[�N���˝�\��[����[�\�[���Z[Y�B��[���]�ș\��ܜȗH
�HB��]\���[�B����\�H�[����]�JY�\��[Y�؞]\�܈����[�\�[����
B��˚[������]�Y�ٛ�\���[Y_KȊB��[���X\���ۙJY�\��B��]\���YB��Y���X����\�Y\��[�HO�\��X�N��[���Έ\��X�HH�B��Y[���]H�]

B���˚[��������Iʍ�H�B��˚[����T�HN��PT��S���Ԉ	K��J����QTȊB��˚[������]Y�N���[�K[]�[�X\��
�\�
HO�\�]�ۈ�[�X�ȊB��˚[�������Iʍ�H�B���܈��[�H[��Q�S����S�QT΂�Y�[�[����H�HPV��S���XZ�[YHH��[�Vț�[YH�B��Y�[ۗ�YH��[�VȜ�Y�[ۗ�Y�B��˚[�������X\��[��ۘ[Y_H�B�[�[ZX�H�[���Y�[���]ܙY�[ۗ�Y
�[YJB�Y�[�[ZX΂��Y�[ۗ�Y�H[�[ZX�˚[������Y�[ۈQ�ۙ�\�YY�ܙY�[ۗ�YH�B�[�N���˚[�����\�[��Y�][�Y�[ۈQ�ܙY�[ۗ�YH�B����H�[���Y�[���X\�����[�W��݊�Y�[ۗ�YRS���SW��P�KPV�Q�W�VT�B�Y�����΂����H�[���Y�[���X\�����[�W��\��Y�[ۗ�YRS���SW��P�KPV�Q�W�VT�B�YYH��܈[���΂�Y�[�[����H�HPV��S���XZY�H��]
�Y�\�ȋ��K���\

B�Y�Y�[�Y���[��Y[����Y[��Y
Y�B�[���˘\[�

B��[���]�ș��[��H
�HB�YY
�HB��˚[�����YY�YYH�Y\����Hۘ[Y_H�B��Y���[���΂��˝�\��[������[�H�X\���]\��Y�\�[�H�[[���X���\�]�ۈ�X\���B�[�\�X\�H
����ܝ\���\��]H�H�܈[��ԕT��ӐT��UWH
���Y������[�H�H�܈[��Q������Ӕ�B�
B��܈�ۋ�Y�[ۈ[�[�\�X\΂�Y�[�[����H�HPV��S���XZ���H�[���Y�[���X\����ۊ�ۋRS���SW��P�KPV�Q�W�VT�B�YYH��܈[����ΓPV�T���ӗN��Y�H��]
�Y�\�ȋ��K���\

B�Y�Y�[�Y���[��Y[����Y[��Y
Y�B�[���˘\[�

B��[���]�ș��[��H
�HB�YY
�HB�Y�YY���˚[������ܙY�[۟WH��۟N��YYH�Y\�YY�B���˚[�������[]X[Y�Z[���Y\���[���[�[����_H�B��]�[��UU�T���[�XY˚��ۈ��ȊH\������ۋ�[\
[�����[�[�L�B��˚[�����]�Y[�XY˚��ۈ�B��]\��[����Y��[��[�N���\�H]][YK����
B��˚[��������Iʍ�H�B��˚[����VT�H�QHS���THQ�S��PQ�S�T�UԈ����B��˚[�����Z[��X�N�	�RS���SW��P�N�HX^Y�N��PV�Q�W�VT�H^\ȊB��˚[�����X^�Y\Έ�PV��SH�]]���UU�T�H�B�Y���QUՒQU���VN���˚[������Y]�Y]ΈTH�^H�ݚYYH�X[�YH���[�X�YH�B�[�N���˚[������Y]�Y]Έ���^H�]HY��QUՒQU���VH�܈�X[��ȊB��˚[�������Iʍ�H�B��^\�[���XY�ٚ[HH�UU�T���[�XY˚��ۈ��Y�^\�[���XY�ٚ[K�^\��
N���N���]�[�^\�[���XY�ٚ[JH\����^\�[��H��ۋ��Y
�B�Y�^\�[�΂��˚[������YY�[�^\�[��_H^\�[��XY�H��\[���X\���B���\�Y\�H^\�[�[�N����\�Y\�H�[����X����\�Y\�
B�^�\^�\[ێ����\�Y\�H�[����X����\�Y\�
B�[�N����\�Y\�H�[����X����\�Y\�
B��Y�����\�Y\΂��˝�\��[������]X[Y�Z[���Y\���[���Y�[�X^H�H����[���\]Y\�ˈ�HY�Z[�[�
KLLZ[�]\ˈ�B��]\�����˚[��������Iʍ�H�B��˚[�����T�H�����T��S���[���\�Y\�_H�QTȊB��˚[�����\�[X]Y[YN��[���\�Y\�H
�

H��
�K^�[���\�Y\�H
�L��
�HZ[�]\ȊB��˚[�������Iʍ�H�B���܈K��[�[�[Y\�]J��\�Y\�JN���˚[��������_K��[���\�Y\�_WH�B��N���[�����\����YJ��
B�^�\�^X��\�[�\��\���˚[�������Y�H\�\��B���XZ^�\^�\[ۈ\�N���˙\��܊��\��܎��_H�B��˙X�Y��X�X�X�˙�ܛX]�^�
JB��[���]�ș\��ܜȗH
�HB�Y��[���]�Ȝ�[�\�[��ȗH
��[���]�ș\��ܜȗH�HPV��S����XZ�[\�YH]][YK����
HH�\���˚[��������Iʍ�H�B��˚[�����S���TUH�B��˚[�����[YN����[\�Y
K��]
	ˉ�V�_H�B��˚[�������[����[���]��ٛ�[�	�_H�B��˚[�������Έ��[���]�������_H�B��˚[������[�\�[��Έ��[���]��ܙ[�\�[����_H�B��˚[�����\��ܜΈ��[���]���\��ܜ��_H�B��˚[������]]���UU�T�H�B��˚[�������Iʍ�W��B����8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� 8� �Y��ۘ[YW��OH���XZ[��Ȏ��XY�[�\�]܊
K��[�
B

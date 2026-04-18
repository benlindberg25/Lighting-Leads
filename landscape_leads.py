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
import sys as _sys; print("DIAG:0 script_start", flush=True, file=_sys.stdout)
import argparse, os, re, sys, json, time, base64, logging, traceback, csv, io
import requests
from io import BytesIO
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from bs4 import BeautifulSoup
from PIL import Image
import openai
print("DIAG:1 imports_done", flush=True, file=_sys.stdout)
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
print("DIAG:2 args_parsed", flush=True, file=_sys.stdout)
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
                    address  = next((row[k] for k in row if k.upper() in ("ADDRESS",)), "")
                    city     = next((row[k] for k in row if k.upper() in ("CITY",)), "")
                    state    = next((row[k] for k in row if "STATE" in k.upper()), "NY")
                    zipcode  = next((row[k] for k in row if "ZIP" in k.upper()), "")
                    sold     = next((row[k] for k in row if "SOLD" in k.upper() and "DATE" in k.upper()), "")
                    beds     = next((row[k] for k in row if k.upper() in ("BEDS",)), "")
                    baths    = next((row[k] for k in row if k.upper() in ("BATHS",)), "")
                    sqft     = next((row[k] for k in row if "SQUARE" in k.upper()), "")
                    url_col  = next((row[k] for k in row if k.upper().startswith("URL")), "")
                    detail_url = url_col if url_col.startswith("http") else (self.BASE + url_col if url_col else "")
                    if address:
                        results.append({
                            "address":    f"{address}, {city}, {state} {zipcode}".strip(", "),
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
        except Exception as e:
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
                m = re.search(r'"url"\s*:\s*"(https://[^"]*cdn-redfin[^"]*)"', raw)
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

    def search_bing_image(self, address: str) -> Optional[str]:
        """Search Bing Images for an exterior photo of the property."""
        query  = f"{address} exterior house front"
        url    = "https://www.bing.com/images/search"
        params = {"q": query, "form": "HDRSC2", "first": 1, "tsc": "ImageHoverTitle"}
        headers = {
            "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept":          "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer":         "https://www.bing.com/",
        }
        try:
            time.sleep(1)
            r = requests.get(url, params=params, headers=headers, timeout=15)
            if r.status_code != 200:
                return None
            matches = re.findall(r'"murl":"(https://[^"]+\.(?:jpg|jpeg|png)(?:[^"]{0,50})?)"', r.text)
            if matches:
                log.info(f"  Bing image found: {matches[0][:80]}")
                return matches[0]
        except Exception as e:
            log.debug(f"  Bing image search error: {e}")
        return None

    def search_realtor_photo(self, address: str) -> Optional[str]:
        """Search Realtor.com for an exterior photo by address."""
        url = "https://www.realtor.com/api/v1/rdc_search_srp?client_id=rdc-search-for-sale-search&schema=vesta"
        headers = {
            "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept":       "application/json",
            "Content-Type": "application/json",
            "Origin":       "https://www.realtor.com",
            "Referer":      "https://www.realtor.com/",
        }
        body = {
            "query": """
            query ConsumerSearchQuery($query: SearchQuery!, $limit: Int) {
              home_search(query: $query, limit: $limit) {
                results { photos { href } primary_photo { href } }
              }
            }""",
            "variables": {
                "query": {"search_location": {"location": address}},
                "limit": 3
            }
        }
        try:
            time.sleep(1)
            r = requests.post(url, json=body, headers=headers, timeout=15)
            if r.status_code == 200:
                data    = r.json()
                results = data.get('data', {}).get('home_search', {}).get('results', [])
                for res in results:
                    primary = res.get('primary_photo', {}) or {}
                    href    = primary.get('href', '')
                    if href:
                        log.info("  Realtor.com photo found")
                        return href
                    photos = res.get('photos', []) or []
                    if photos and photos[0].get('href'):
                        log.info("  Realtor.com photo found")
                        return photos[0]['href']
            # Fallback: scrape page
            search_url = f"https://www.realtor.com/realestateandhomes-search/{address.replace(' ', '-').replace(',', '')}"
            r2 = self._get(search_url)
            if r2:
                matches = re.findall(r'"primary_photo"\s*:\s*\{[^}]*"href"\s*:\s*"(https://ap\.rdcpix\.com/[^"]+)"', r2.text)
                if matches:
                    log.info("  Realtor.com photo found via page scrape")
                    return matches[0]
        except Exception as e:
            log.debug(f"  Realtor.com photo error: {e}")
        return None

    def search_street_view(self, address: str, api_key: str) -> Optional[bytes]:
        """Fetch exterior photo via Google Street View Static API.

        Returns image bytes directly (not a URL).
        Uses return_error_code=true so a 404 is returned (instead of a gray
        placeholder) when no Street View imagery exists for the address.
        """
        if not api_key:
            return None
        try:
            url    = "https://maps.googleapis.com/maps/api/streetview"
            params = {
                "size":              "640x480",
                "location":          address,
                "key":               api_key,
                "fov":               "90",
                "pitch":             "10",
                "return_error_code": "true",
            }
            r = self.session.get(url, params=params, timeout=15)
            if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
                if len(r.content) > 5_000:  # real photos are large; tiny = error image
                    log.info("  Street View photo obtained!")
                    return r.content
                log.debug("  Street View: response too small, skipping")
                return None
            log.debug(f"  Street View: HTTP {r.status_code} (no imagery available)")
            return None
        except Exception as e:
            log.warning(f"  Street View API error: {e}")
            return None


# ─────────────────────────────────────────────────────────────────
# AI LANDSCAPE LIGHTING RENDERER
# ─────────────────────────────────────────────────────────────────
class LandscapeRenderer:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("OpenAI API key required.")
        self.client = openai.OpenAI(api_key=api_key)

    def describe_home(self, image_bytes: bytes) -> str:
        b64 = base64.b64encode(image_bytes).decode()
        try:
            resp = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role":"user","content":[
                    {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}","detail":"high"}},
                    {"type":"text","text":(
                        "Describe this home exterior for a landscape lighting designer in 3 sentences:\n"
                        "- Architectural style (colonial, contemporary, Tudor, farmhouse, etc.)\n"
                        "- Exterior materials and colors\n"
                        "- Key features: columns, dormers, windows, portico, garage, trees, driveway\n"
                        "Be specific — this will be used to generate a landscape lighting rendering."
                    )}
                ]}],
                max_tokens=300
            )
            return resp.choices[0].message.content
        except Exception as e:
            log.warning(f"  GPT-4o analysis failed: {e}")
            return "A large luxury single-family home with professional landscaping and a paved driveway."

    def generate_rendering(self, house_description: str) -> Optional[bytes]:
        prompt = (
            f"Photorealistic landscape lighting design rendering of a luxury home at twilight. "
            f"HOME: {house_description} "
            "LIGHTING: warm 2700K LED uplights on facade, amber path lights along driveway, "
            "architectural spotlights on columns and dormers, tree uplighting against deep blue twilight sky, "
            "step lighting, garden accent lights, warm glow from windows. "
            "Photorealistic, magazine-quality, twilight/dusk atmosphere."
        )
        try:
            resp = self.client.images.generate(
                model="dall-e-3", prompt=prompt,
                size="1792x1024", quality="hd", n=1, style="natural"
            )
            img_r = requests.get(resp.data[0].url, timeout=60)
            img_r.raise_for_status()
            return img_r.content
        except openai.BadRequestError:
            try:
                resp = self.client.images.generate(
                    model="dall-e-3",
                    prompt=(
                        f"Luxury home at dusk with professional landscape lighting. "
                        f"{house_description[:150]} "
                        "Warm LED uplighting, amber path lights, tree uplighting, twilight blue sky. "
                        "Photorealistic rendering."
                    ),
                    size="1792x1024", quality="hd", n=1,
                )
                img_r = requests.get(resp.data[0].url, timeout=60)
                return img_r.content
            except Exception as e2:
                log.error(f"  Rendering retry failed: {e2}")
                return None
        except Exception as e:
            log.error(f"  Rendering failed: {e}")
            return None


# ─────────────────────────────────────────────────────────────────
# LEAD GENERATOR – MAIN ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────
class LeadGenerator:
    def __init__(self):
        if not OPENAI_API_KEY:
            log.error("OPENAI_API_KEY is not set.")
            sys.exit(1)
        self.redfin   = RedfinScraper()
        self.renderer = LandscapeRenderer(OPENAI_API_KEY)
        self.stats    = {"found":0,"photos":0,"renderings":0,"skipped":0,"errors":0}
        self.done_file = OUTPUT_DIR / ".completed_addresses.json"
        self.done: set = set()
        if self.done_file.exists():
            try:
                with open(self.done_file) as f:
                    self.done = set(json.load(f))
                log.info(f"Resuming - {len(self.done)} homes already done from prior runs")
            except Exception:
                pass

    def _safe_name(self, address: str) -> str:
        name = re.sub(r'[<>:"/\\|?*]', "", address)
        return re.sub(r"\s+", " ", name).strip()[:120]

    def _save(self, address: str, orig: bytes, rendering: Optional[bytes], meta: Dict):
        folder = OUTPUT_DIR / self._safe_name(address)
        folder.mkdir(parents=True, exist_ok=True)
        if orig:
            with open(folder / "original.jpg", "wb") as f: f.write(orig)
        if rendering:
            with open(folder / "with_landscape_lighting.jpg", "wb") as f: f.write(rendering)
        with open(folder / "property_info.txt", "w") as f:
            f.write(f"Address: {address}\n")
            f.write(f"Sale Price: ${meta.get('price',0):,}\n")
            f.write(f"Sold Date: {meta.get('sold_date','Unknown')}\n")
            f.write(f"Bedrooms: {meta.get('beds','N/A')}\n")
            f.write(f"Bathrooms: {meta.get('baths','N/A')}\n")
            f.write(f"Sq Ft: {meta.get('sqft','N/A')}\n")
            f.write(f"Redfin URL: {meta.get('redfin_url','N/A')}\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        return folder

    def _mark_done(self, address: str):
        self.done.add(address)
        try:
            with open(self.done_file, "w") as f:
                json.dump(list(self.done), f)
        except Exception:
            pass

    def process_home(self, prop: Dict) -> bool:
        address = prop.get("address","Unknown")
        if address in self.done or address == "Unknown":
            self.stats["skipped"] += 1
            return False

        log.info(f"\n{'─'*60}")
        log.info(f"Home: {address}")
        log.info(f"Price: ${prop.get('price',0):,} | Sold: {prop.get('sold_date','Unknown')}")

        # ── Photo acquisition: try each source in order ────────────
        log.info("  Fetching exterior photo...")
        photo_url = prop.get("thumbnail","") or self.redfin.get_exterior_photo(prop.get("redfin_url",""))

        if not photo_url:
            log.info("  Redfin photo unavailable - trying Bing image search...")
            photo_url = self.redfin.search_bing_image(address)

        if not photo_url:
            log.info("  Trying Realtor.com...")
            photo_url = self.redfin.search_realtor_photo(address)

        img_bytes = None
        if photo_url:
            img_bytes = self.redfin.download_image(photo_url)
            if img_bytes:
                try:
                    img = Image.open(BytesIN(img_bytes))
                    w, h = img.size
                    if w < 300 or h < 200:
                        log.warning(f"  Image too small ({w}x{h}) - trying Street View")
                        img_bytes = None
                    elif img.format not in ("JPEG","JPG"):
                        buf = BytesIO()
                        img.convert("RGB").save(buf, format="JPEG", quality=90)
                        img_bytes = buf.getvalue()
                except Exception as e:
                    log.warning(f"  Invalid image: {e} - trying Street View")
                    img_bytes = None
            else:
                log.warning("  Could not download photo - trying Street View")

        # ── Google Street View fallback ────────────────────────────
        if not img_bytes:
            if STREET_VIEW_KEY:
                log.info("  Trying Google Street View Static API...")
                img_bytes = self.redfin.search_street_view(address, STREET_VIEW_KEY)
                if not img_bytes:
                    log.info("  Street View returned no imagery - generating from property data")
            else:
                log.info("  No Street View key - generating from property data")

        # ── Build description: GPT-4o from photo, or text from data ──
        if img_bytes:
            self.stats["photos"] += 1
            log.info("  Photo obtained - analyzing with GPT-4o...")
            description = self.renderer.describe_home(img_bytes)
            log.info(f"  Description: {description[:100]}...")
        else:
            log.info("  No photo - building description from property data...")
            price    = prop.get('price', 0)
            beds     = prop.get('beds', '')
            sqft     = prop.get('sqft', '')
            style    = "grand estate" if price > 4000000 else "luxury"
            bed_str  = f"{beds}-bedroom, " if beds else ""
            sqft_str = f"{sqft} sq ft " if sqft else ""
            description = (
                f"A {style} single-family home in Long Island, NY. "
                f"{bed_str}{sqft_str}property with professional landscaping, "
                f"manicured hedges, mature trees, a wide paved driveway, "
                f"and elegant architectural details typical of high-end Nassau/Suffolk County homes."
            )
            log.info(f"  Description: {description[:100]}...")

        # ── DALL-E 3 rendering ─────────────────────────────────────
        log.info("  Generating landscape lighting rendering with DALL-E 3...")
        rendering = self.renderer.generate_rendering(description)
        if rendering:
            self.stats["renderings"] += 1
            log.info("  Rendering created!")
        else:
            log.warning("  Rendering failed")
            self.stats["errors"] += 1
            return False

        folder = self._save(address, img_bytes or b"", rendering, prop)
        log.info(f"  Saved to {folder.name}/")
        self._mark_done(address)
        return True

    def collect_properties(self) -> List[Dict]:
        all_props: List[Dict] = []
        seen: set = set()

        log.info(f"\n{'='*60}")
        log.info("PHASE 1: SEARCHING FOR $1.3M+ SOLD HOMES")
        log.info("Strategy: county-level search (fast) -> per-town fallback")
        log.info(f"{'='*60}")

        for county in REDFIN_COUNTIES:
            if len(all_props) >= MAX_TOTAL: break
            name      = county["name"]
            region_id = county["region_id"]
            log.info(f"\nSearching {name}")
            dynamic = self.redfin.get_region_id(name)
            if dynamic:
                region_id, _ = dynamic
                log.info(f"  Region ID confirmed: {region_id}")
            else:
                log.info(f"  Using default region ID: {region_id}")
            props = self.redfin.search_county_csv(region_id, MIN_SALE_PRICE, MAX_AGE_DAYS)
            if not props:
                props = self.redfin.search_county_gis(region_id, MIN_SALE_PRICE, MAX_AGE_DAYS)
            added = 0
            for p in props:
                if len(all_props) >= MAX_TOTAL: break
                addr = p.get("address","").strip()
                if addr and addr not in seen:
                    seen.add(addr)
                    all_props.append(p)
                    self.stats["found"] += 1
                    added += 1
            log.info(f"  Added {added} homes from {name}")

        if not all_props:
            log.warning("\nCounty search returned 0 results - falling back to per-town search")
            all_areas = (
                [(t, "Northern Nassau") for t in NORTHERN_NASSAU] +
                [(t, "Suffolk County")  for t in SUFFOLK_TOWNS]
            )
            for town, region in all_areas:
                if len(all_props) >= MAX_TOTAL: break
                props = self.redfin.search_town(town, MIN_SALE_PRICE, MAX_AGE_DAYS)
                added = 0
                for p in props[:MAX_PER_TOWN]:
                    addr = p.get("address","").strip()
                    if addr and addr not in seen:
                        seen.add(addr)
                        all_props.append(p)
                        self.stats["found"] += 1
                        added += 1
                if added:
                    log.info(f"  [{region}] {town}: {added} homes added")

        log.info(f"\nTotal qualifying homes found: {len(all_props)}")
        with open(OUTPUT_DIR / "all_leads.json", "w") as f:
            json.dump(all_props, f, indent=2)
        log.info("Saved all_leads.json")
        return all_props

    def run(self):
        start = datetime.now()
        log.info(f"\n{'='*60}")
        log.info(" LUXURY HOME LANDSCAPE LIGHTING LEAD GENERATOR v2.0")
        log.info(f" Min price: ${MIN_SALE_PRICE:,} | Max age: {MAX_AGE_DAYS} days")
        log.info(f" Max homes: {MAX_TOTAL} | Output: {OUTPUT_DIR}")
        if STREET_VIEW_KEY:
            log.info(" Street View: API key provided - real home photos enabled!")
        else:
            log.info(" Street View: No key set - add STREET_VIEW_KEY for real photos")
        log.info(f"{'='*60}")

        existing_leads_file = OUTPUT_DIR / "all_leads.json"
        if existing_leads_file.exists():
            try:
                with open(existing_leads_file) as f:
                    existing = json.load(f)
                if existing:
                    log.info(f"Loaded {len(existing)} existing leads - skipping search")
                    properties = existing
                else:
                    properties = self.collect_properties()
            except Exception:
                properties = self.collect_properties()
        else:
            properties = self.collect_properties()

        if not properties:
            log.warning("\nNo qualifying homes found. Redfin may be blocking requests. Try again in 5-10 minutes.")
            return

        log.info(f"\n{'='*60}")
        log.info(f"PHASE 2: PROCESSING {len(properties)} HOMES")
        log.info(f"Estimated time: {len(properties) * 45 // 60}-{len(properties) * 90 // 60} minutes")
        log.info(f"{'='*60}")

        for i, prop in enumerate(properties, 1):
            log.info(f"\n[{i}/{len(properties)}]")
            try:
                self.process_home(prop)
            except KeyboardInterrupt:
                log.info("\nStopped by user")
                break
            except Exception as e:
                log.error(f"Error: {e}")
                log.debug(traceback.format_exc())
                self.stats["errors"] += 1
            if self.stats["renderings"] + self.stats["errors"] >= MAX_TOTAL:
                break

        elapsed = datetime.now() - start
        log.info(f"\n{'='*60}")
        log.info(" RUN COMPLETE")
        log.info(f" Time:       {str(elapsed).split('.')[0]}")
        log.info(f" Found:      {self.stats['found']}")
        log.info(f" Photos:     {self.stats['photos']}")
        log.info(f" Renderings: {self.stats['renderings']}")
        log.info(f" Errors:     {self.stats['errors']}")
        log.info(f" Output:     {OUTPUT_DIR}")
        log.info(f"{'='*60}\n")


# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    LeadGenerator().run()

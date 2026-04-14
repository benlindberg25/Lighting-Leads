#!/usr/bin/env python3
"""
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
  LUXURY HOME LANDSCAPE LIGHTING LEAD GENERATOR  v2.0
  For Landscape Lighting Businesses â Long Island, NY
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
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

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# CLI ARGUMENTS
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
def parse_args():
    p = argparse.ArgumentParser(description="Landscape Lighting Lead Generator")
    p.add_argument("--min-price",   type=int, default=1_300_000)
    p.add_argument("--max-age",     type=int, default=730,  help="Max days since sale")
    p.add_argument("--max-total",   type=int, default=50)
    p.add_argument("--max-per-town",type=int, default=25)
    p.add_argument("--output-dir",  type=str, default="")
    return p.parse_args()

args             = parse_args()
OPENAI_API_KEY   = os.environ.get("OPENAI_API_KEY", "")
MIN_SALE_PRICE   = args.min_price
MAX_AGE_DAYS     = args.max_age
MAX_TOTAL        = args.max_total
MAX_PER_TOWN     = args.max_per_town
REQUEST_DELAY    = 2.5   # seconds between requests

OUTPUT_DIR = Path(args.output_dir) if args.output_dir else Path(__file__).parent / "leads_output"

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# TARGET TOWNS (fallback if county search fails)
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
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

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# LOGGING  (FlushingHandler so Streamlit sees output immediately)
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
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

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# REDFIN SCRAPER  (county-level â 2 searches instead of 107)
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
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
    {"name": "Nassau County, NY",  "region_id": "1329", "region_type": "5"},
    {"name": "Suffolk County, NY", "region_id": "1330", "region_type": "5"},
]


class RedfinScraper:
    BASE = "https://www.redfin.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    # ââ internal GET with delay ââââââââââââââââââââââââââââââââââ
    def _get(self, url: str, **kwargs) -> Optional[requests.Response]:
        time.sleep(REQUEST_DELAY)
        try:
            r = self.session.get(url, timeout=30, **kwargs)
            r.raise_for_status()
            return r
        except Exception as e:
            log.warning(f"  â  Request failed: {e}")
            return None

    # ââ dynamic region ID lookup via autocomplete ââââââââââââââââ
    def get_region_id(self, location: str) -> Optional[Tuple[str, str]]:
        """Returns (region_id, region_type) for a county or city name."""
        url = f"{self.BASE}/stingray/do/location-autocomplete"
        r = self._get(url, params={"location": location, "v": "2"})
        if not r:
            return None
        try:
            text = r.text
            if text.startswith("{}&&"):
                text = text[4:]
            data = json.loads(text)
            for section in data.get("payload", {}).get("sections", []):
                for row in section.get("rows", []):
                    path = row.get("url", "")
                    m = re.search(r"/county/(\d+)/", path)
                    if m:
                        return (m.group(1), "5")
                    m = re.search(r"/city/(\d+)/", path)
                    if m:
                        return (m.group(1), "6")
        except Exception as e:
            log.debug(f"  Autocomplete parse error: {e}")
        return None

    # ââ county-level CSV download ââââââââââââââââââââââââââââââââ
    def search_county_csv(self, region_id: str, min_price: int, max_age_days: int) -> List[Dict]:
        """Redfin's GIS-CSV endpoint â returns up to 350 sold listings."""
        url = f"{self.BASE}/stingray/api/gis-csv"
        params = {
            "al": 1, "market": "newyork", "v": 8,
            "min_price": min_price,
            "sold_within_days": max_age_days,
            "status": 9,           # sold
            "uipt": "1,2,3,4,7,8", # all property types
            "region_type": 5,
            "region_id": region_id,
            "num_homes": 350,
            "sf": "1,2,3,5,6,7",
        }
        log.info(f"  â³ Fetching sold listings CSV (region_id={region_id})â¦")
        r = self._get(url, params=params)
        if not r:
            return []
        try:
            reader = csv.DictReader(io.StringIO(r.text))
            results = []
            for row in reader:
                try:
                    price_str = next((row[k] for k in row if "PRICE" in k.upper()), "0")
                    price = int(re.sub(r"[^0-9]", "", str(price_str)) or "0")
                    if price < min_price:
                        continue

                    address = next((row[k] for k in row if k.upper() in ("ADDRESS",)), "")
                    city    = next((row[k] for k in row if k.upper() in ("CITY",)), "")
                    state   = next((row[k] for k in row if "STATE" in k.upper()), "NY")
                    zipcode = next((row[k] for k in row if "ZIP" in k.upper()), "")
                    sold    = next((row[k] for k in row if "SOLD" in k.upper() and "DATE" in k.upper()), "")
                    beds    = next((row[k] for k in row if k.upper() in ("BEDS",)), "")
                    baths   = next((row[k] for k in row if k.upper() in ("BATHS",)), "")
                    sqft    = next((row[k] for k in row if "SQUARE" in k.upper()), "")
                    url_col = next((row[k] for k in row if k.upper().startswith("URL")), "")
                    detail_url = url_col if url_col.startswith("http") else (self.BASE + url_col if url_col else "")

                    if address:
                        results.append({
                            "address":    f"{address}, {city}, {state} {zipcode}".strip(", "),
                            "price":      price,
                            "sold_date":  sold,
                            "zillow_url": detail_url,
                            "redfin_url": detail_url,
                            "thumbnail":  "",
                            "beds": beds, "baths": baths, "sqft": sqft,
                            "source": "redfin_csv",
                        })
                except Exception:
                    continue
            log.info(f"  â {len(results)} homes found in CSV")
            return results
        except Exception as e:
            log.warning(f"  CSV parse error: {e}")
            return []

    # ââ county-level GIS JSON (fallback) ââââââââââââââââââââââââ
    def search_county_gis(self, region_id: str, min_price: int, max_age_days: int) -> List[Dict]:
        url = f"{self.BASE}/stingray/api/gis"
        params = {
            "al": 1, "market": "newyork", "v": 8,
            "min_price": min_price,
            "sold_within_days": max_age_days,
            "status": 9,
            "uipt": "1,2,3,4,7,8",
            "region_type": 5,
            "region_id": region_id,
            "num_homes": 350,
            "sf": "1,2,3,5,6,7",
        }
        log.info(f"  â³ Trying GIS JSON fallback (region_id={region_id})â¦")
        r = self._get(url, params=params)
        if not r:
            return []
        try:
            text = r.text
            if text.startswith("{}&&"):
                text = text[4:]
            data  = json.loads(text)
            homes = data.get("payload", {}).get("homes", [])
            results = []
            for h in homes:
                try:
                    price_info = h.get("price", {})
                    price = price_info.get("value", 0) if isinstance(price_info, dict) else int(re.sub(r"[^0-9]","",str(price_info)) or "0")
                    if price < min_price:
                        continue
                    sl = h.get("streetLine", {})
                    address = sl.get("value","") if isinstance(sl, dict) else str(sl)
                    csz = h.get("cityStateZip",{})
                    city_state_zip = csz.get("value","") if isinstance(csz, dict) else str(csz)
                    path = h.get("url","")
                    detail_url = (self.BASE + path) if path and not path.startswith("http") else path
                    beds  = h.get("beds","")
                    sqft_info = h.get("sqFt",{})
                    sqft  = sqft_info.get("value","") if isinstance(sqft_info,dict) else str(sqft_info)
                    if address:
                        results.append({
                            "address":    f"{address}, {city_state_zip}".strip(", "),
                            "price":      price,
                            "sold_date":  "",
                            "zillow_url": detail_url,
                            "redfin_url": detail_url,
                            "thumbnail":  "",
                            "beds": beds, "baths": "", "sqft": sqft,
                            "source": "redfin_gis",
                        })
                except Exception:
                    continue
            log.info(f"  â {len(results)} homes found via GIS")
            return results
        except Exception as e:
            log.warning(f"  GIS parse error: {e}")
            return []

    # ââ per-town fallback âââââââââââââââââââââââââââââââââââââââââ
    def search_town(self, town: str, min_price: int, max_age_days: int) -> List[Dict]:
        years = max(1, max_age_days // 365)
        slug  = town.replace(" ", "-")
        url   = (
            f"{self.BASE}/NY/{slug}/"
            f"filter/min-price={min_price},include=sold-{years}yr,property-type=house"
        )
        log.info(f"  â³ Redfin town search: {town}, NYâ¦")
        r = self._get(url)
        if not r:
            return []

        results = []
        try:
            soup = BeautifulSoup(r.text, "lxml")
            # Try og:description for count indicator
            for script in soup.find_all("script"):
                raw = script.string or ""
                if "lastSoldPrice" not in raw and "soldDate" not in raw:
                    continue
                # Grab individual JSON objects
                for m in re.finditer(r'\{[^{}]{30,2000}\}', raw):
                    try:
                        obj = json.loads(m.group())
                        price_raw = obj.get("lastSoldPrice", obj.get("price", 0))
                        price = int(re.sub(r"[^0-9]","",str(price_raw)) or "0")
                        if price < min_price:
                            continue
                        sl = obj.get("streetLine", {})
                        address = sl.get("value","") if isinstance(sl,dict) else str(sl)
                        path = obj.get("url","")
                        detail_url = (self.BASE+path) if path and not path.startswith("http") else path
                        if address:
                            results.append({
                                "address": f"{address}, {town}, NY",
                                "price": price, "sold_date": "",
                                "zillow_url": detail_url,
                                "redfin_url": detail_url,
                                "thumbnail": "", "source": "redfin_html",
                            })
                    except Exception:
                        continue
                if results:
                    break
        except Exception as e:
            log.debug(f"  HTML parse error: {e}")

        log.info(f"  â {len(results)} homes in {town}")
        return results

    # ââ get exterior photo URL from detail page ââââââââââââââââââ
    def get_exterior_photo(self, redfin_url: str) -> Optional[str]:
        if not redfin_url:
            return None
        r = self._get(redfin_url)
        if not r:
            return None
        try:
            soup = BeautifulSoup(r.text, "lxml")
            # og:image is usually the exterior front photo
            og = soup.find("meta", {"property": "og:image"})
            if og and og.get("content"):
                return og["content"]
            # Try CDN image tags
            imgs = soup.select("img[src*='cdn-redfin.com']")
            if imgs:
                return max(imgs, key=lambda i: len(i.get("src",""))).get("src","")
            # Try embedded JSON
            for script in soup.find_all("script"):
                raw = script.string or ""
                m = re.search(r'"url"\s*:\s*"(https://[^"]*cdn-redfin[^"]*)"', raw)
                if m:
                    return m.group(1)
        except Exception as e:
            log.debug(f"  Photo extraction error: {e}")
        return None

    def download_image(self, url: str) -> Optional[bytes]:
        if not url:
            return None
        try:
            r = self.session.get(url, timeout=30)
            r.raise_for_status()
            return r.content if len(r.content) > 5_000 else None
        except Exception as e:
            log.warning(f"  Image download failed: {e}")
            return None


# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# AI LANDSCAPE LIGHTING RENDERER
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
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
                        "Be specific â this will be used to generate a landscape lighting rendering."
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


# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# LEAD GENERATOR â MAIN ORCHESTRATOR
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
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
                log.info(f"Resuming â {len(self.done)} homes already done from prior runs")
            except Exception:
                pass

    def _safe_name(self, address: str) -> str:
        name = re.sub(r'[<>:"/\\|?*]', "", address)
        return re.sub(r"\s+", " ", name).strip()[:120]

    def _save(self, address: str, orig: bytes, rendering: Optional[bytes], meta: Dict):
        folder = OUTPUT_DIR / self._safe_name(address)
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / "original.jpg", "wb") as f:
            f.write(orig)
        if rendering:
            with open(folder / "with_landscape_lighting.jpg", "wb") as f:
                f.write(rendering)
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

        log.info(f"\n{'â'*60}")
        log.info(f"ð  {address}")
        log.info(f"ð° ${prop.get('price',0):,} | Sold: {prop.get('sold_date','Unknown')}")

        # Get photo
        log.info("  ð¸ Fetching exterior photoâ¦")
        photo_url = prop.get("thumbnail","") or self.redfin.get_exterior_photo(prop.get("redfin_url",""))
        if not photo_url:
            log.warning("  No exterior photo â skipping")
            self.stats["errors"] += 1
            return False

        img_bytes = self.redfin.download_image(photo_url)
        if not img_bytes:
            log.warning("  Could not download photo â skipping")
            self.stats["errors"] += 1
            return False

        # Validate image
        try:
            img = Image.open(BytesIO(img_bytes))
            w, h = img.size
            if w < 300 or h < 200:
                log.warning(f"  Image too small ({w}Ã{h}) â skipping")
                self.stats["errors"] += 1
                return False
            if img.format not in ("JPEG","JPG"):
                buf = BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=90)
                img_bytes = buf.getvalue()
        except Exception as e:
            log.warning(f"  Invalid image: {e}")
            self.stats["errors"] += 1
            return False

        self.stats["photos"] += 1
        log.info(f"  â Photo downloaded ({w}Ã{h} px)")

        # GPT-4o description
        log.info("  ð¤ Analyzing architecture with GPT-4oâ¦")
        description = self.renderer.describe_home(img_bytes)
        log.info(f"  â {description[:100]}â¦")

        # DALL-E 3 rendering
        log.info("  ð¨ Generating landscape lighting rendering with DALL-E 3â¦")
        rendering = self.renderer.generate_rendering(description)
        if rendering:
            self.stats["renderings"] += 1
            log.info("  â Rendering created!")
        else:
            log.warning("  â ï¸  Rendering failed â saving original only")

        folder = self._save(address, img_bytes, rendering, prop)
        log.info(f"  ð¾ Saved â {folder.name}/")
        self._mark_done(address)
        return True

    def collect_properties(self) -> List[Dict]:
        all_props: List[Dict] = []
        seen: set = set()

        log.info(f"\n{'â'*60}")
        log.info("PHASE 1: SEARCHING FOR $1.3M+ SOLD HOMES")
        log.info("Strategy: county-level search (fast) â per-town fallback")
        log.info(f"{'â'*60}")

        # ââ Try county-level search first (2 API calls total) âââ
        for county in REDFIN_COUNTIES:
            if len(all_props) >= MAX_TOTAL:
                break
            name      = county["name"]
            region_id = county["region_id"]

            log.info(f"\nð Searching {name}â¦")

            # Try to confirm/update region ID via autocomplete
            dynamic = self.redfin.get_region_id(name)
            if dynamic:
                region_id, _ = dynamic
                log.info(f"  â Region ID confirmed: {region_id}")
            else:
                log.info(f"  Using default region ID: {region_id}")

            props = self.redfin.search_county_csv(region_id, MIN_SALE_PRICE, MAX_AGE_DAYS)
            if not props:
                props = self.redfin.search_county_gis(region_id, MIN_SALE_PRICE, MAX_AGE_DAYS)

            added = 0
            for p in props:
                if len(all_props) >= MAX_TOTAL:
                    break
                addr = p.get("address","").strip()
                if addr and addr not in seen:
                    seen.add(addr)
                    all_props.append(p)
                    self.stats["found"] += 1
                    added += 1
            log.info(f"  â Added {added} homes from {name}")

        # ââ Fall back to per-town if county search returned nothing ââ
        if not all_props:
            log.warning("\nâ ï¸  County search returned 0 results â falling back to per-town search")
            all_areas = (
                [(t, "Northern Nassau") for t in NORTHERN_NASSAU] +
                [(t, "Suffolk County")  for t in SUFFOLK_TOWNS]
            )
            for town, region in all_areas:
                if len(all_props) >= MAX_TOTAL:
                    break
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

        log.info(f"\n{'â'*60}")
        log.info(f"Total qualifying homes found: {len(all_props)}")

        # Save lead list
        with open(OUTPUT_DIR / "all_leads.json", "w") as f:
            json.dump(all_props, f, indent=2)
        log.info("Saved all_leads.json")

        return all_props

    def run(self):
        start = datetime.now()
        log.info(f"\n{'â'*60}")
        log.info("  LUXURY HOME LANDSCAPE LIGHTING LEAD GENERATOR v2.0")
        log.info(f"  Min price: ${MIN_SALE_PRICE:,}  |  Max age: {MAX_AGE_DAYS} days")
        log.info(f"  Max homes: {MAX_TOTAL}  |  Output: {OUTPUT_DIR}")
        log.info(f"{'â'*60}")

        properties = self.collect_properties()

        if not properties:
            log.warning(
                "\nâ No qualifying homes found.\n"
                "Redfin may be temporarily blocking requests.\n"
                "Please wait 5â10 minutes and try again."
            )
            return

        log.info(f"\n{'â'*60}")
        log.info(f"PHASE 2: PROCESSING {len(properties)} HOMES")
        log.info(f"Estimated time: {len(properties) * 45 // 60}â{len(properties) * 90 // 60} minutes")
        log.info(f"{'â'*60}")

        for i, prop in enumerate(properties, 1):
            log.info(f"\n[{i}/{len(properties)}]")
            try:
                self.process_home(prop)
            except KeyboardInterrupt:
                log.info("\nâ¹ Stopped by user")
                break
            except Exception as e:
                log.error(f"Error: {e}")
                log.debug(traceback.format_exc())
                self.stats["errors"] += 1
            if sel

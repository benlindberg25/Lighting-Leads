#!/usr/bin/env python3
"""
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
â     LUXURY HOME LANDSCAPE LIGHTING LEAD GENERATOR v1.1           â
â     For Landscape Lighting Businesses â Long Island, NY           â
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

Finds homes sold 2+ years, $1.3M+ in Northern Nassau + Suffolk County, NY.
Downloads Zillow exterior photos. Generates AI landscape lighting renderings.

Usage (terminal):
    python landscape_leads.py

Usage (web app passes settings via CLI):
    python landscape_leads.py --min-price=1300000 --max-age=730 --max-total=50

Setup:
    pip install requests beautifulsoup4 lxml openai Pillow
    export OPENAI_API_KEY="sk-..."
"""

import argparse
import os
import re
import sys
import json
import time
import base64
import logging
import traceback
import requests

from io import BytesIO
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from bs4 import BeautifulSoup
from PIL import Image
import openai

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# CLI ARGUMENT PARSING  (allows the web app to control settings)
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def parse_args():
    parser = argparse.ArgumentParser(description="Landscape Lighting Lead Generator")
    parser.add_argument("--min-price",  type=int, default=1_300_000,
                        help="Minimum home sale price (default: 1300000)")
    parser.add_argument("--max-age",    type=int, default=730,
                        help="Maximum days since sale (default: 730 = 2 years)")
    parser.add_argument("--max-total",  type=int, default=300,
                        help="Maximum total homes to process (default: 300)")
    parser.add_argument("--max-per-town", type=int, default=25,
                        help="Max homes per town (default: 25)")
    parser.add_argument("--output-dir", type=str, default="",
                        help="Output directory path (default: ./leads_output/)")
    return parser.parse_args()

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# CONFIGURATION
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

args = parse_args()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
MIN_SALE_PRICE = args.min_price
MAX_AGE_DAYS   = args.max_age
MAX_TOTAL      = args.max_total
MAX_PER_TOWN   = args.max_per_town
REQUEST_DELAY  = 3.5  # seconds between web requests

if args.output_dir:
    OUTPUT_DIR = Path(args.output_dir)
else:
    OUTPUT_DIR = Path(__file__).parent / "leads_output"

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# TARGET AREAS
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

NORTHERN_NASSAU = [
    "Great Neck", "Port Washington", "Manhasset", "Roslyn",
    "Roslyn Heights", "Roslyn Estates", "Roslyn Harbor",
    "Glen Cove", "Sea Cliff", "Glen Head",
    "Oyster Bay", "Cove Neck", "Centre Island", "Bayville",
    "Locust Valley", "Lattingtown", "Matinecock", "Brookville",
    "Old Westbury", "Upper Brookville", "Mill Neck", "Muttontown",
    "Old Brookville", "East Hills", "Flower Hill",
    "North Hills", "Plandome", "Plandome Heights", "Plandome Manor",
    "Munsey Park", "Saddle Rock", "Kings Point",
    "Russell Gardens", "Lake Success", "Kensington",
    "Great Neck Plaza", "Great Neck Estates",
]

SUFFOLK_COUNTY = [
    # Huntington
    "Huntington", "Huntington Bay", "Centerport", "Cold Spring Harbor",
    "Lloyd Harbor", "Northport", "East Northport", "Asharoken",
    "Greenlawn", "Halesite", "Lloyd Neck",
    # Smithtown
    "Smithtown", "Kings Park", "St James", "Nesconset", "Hauppauge",
    "Head of the Harbor", "Nissequogue",
    # Islip
    "Bay Shore", "Brightwaters", "West Islip", "Islip", "East Islip",
    "Oakdale", "Sayville", "West Sayville", "Great River", "Bohemia",
    # Babylon
    "Babylon", "West Babylon", "Amityville", "Copiague", "Lindenhurst",
    # Brookhaven
    "Stony Brook", "Setauket", "East Setauket", "Port Jefferson",
    "Port Jefferson Station", "Mount Sinai", "Miller Place",
    "Rocky Point", "Shoreham", "Wading River",
    "Mastic Beach", "Center Moriches", "East Moriches", "Bellport",
    # Riverhead / North Fork
    "Riverhead", "Jamesport", "Aquebogue",
    "Southold", "Cutchogue", "Mattituck", "Orient", "East Marion",
    "Greenport", "Peconic", "Laurel", "New Suffolk",
    # East Hampton
    "East Hampton", "Amagansett", "Montauk", "Springs",
    "Wainscott", "Sagaponack",
    # Southampton
    "Southampton", "Bridgehampton", "Water Mill", "Quogue",
    "Westhampton", "Westhampton Beach", "Remsenburg", "East Quogue",
    "Hampton Bays", "North Sea", "Flanders",
    # Shelter Island / Sag Harbor
    "Shelter Island", "Shelter Island Heights", "Sag Harbor",
    # Other
    "Melville", "Dix Hills", "Woodbury", "Commack",
    "Brentwood", "Central Islip",
]

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# LOGGING
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
log_file = OUTPUT_DIR / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
)
log = logging.getLogger("leads")

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# ZILLOW SCRAPER
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

class ZillowScraper:
    BASE = "https://www.zillow.com"
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "no-cache",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def _slug(self, town: str) -> str:
        return town.strip().replace(" ", "-") + "-NY"

    def _get(self, url: str, **kwargs) -> Optional[requests.Response]:
        time.sleep(REQUEST_DELAY)
        try:
            resp = self.session.get(url, timeout=20, **kwargs)
            if resp.status_code == 403:
                log.warning(f"  403 Blocked by Zillow â will try Redfin")
                return None
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            log.warning(f"  Network error: {e}")
            return None

    def _next_data(self, html: str) -> dict:
        soup = BeautifulSoup(html, "lxml")
        tag = soup.find("script", {"id": "__NEXT_DATA__"})
        if tag and tag.string:
            try:
                return json.loads(tag.string)
            except json.JSONDecodeError:
                pass
        return {}

    def search_sold(self, town: str, min_price: int, max_age_days: int) -> List[Dict]:
        slug = self._slug(town)
        cutoff = datetime.now() - timedelta(days=max_age_days)

        filter_state = {
            "price": {"min": min_price},
            "doz":   {"value": str(min(max_age_days // 30, 36))},
            "rs":    {"value": True},
            "fsba":  {"value": False},
            "fsbo":  {"value": False},
            "nc":    {"value": False},
            "cmsn":  {"value": False},
            "auc":   {"value": False},
            "fore":  {"value": False},
        }
        search_state = json.dumps({"filterState": filter_state}, separators=(",", ":"))
        url = f"{self.BASE}/homes/recently_sold/{slug}_rb/"

        log.info(f"Zillow: {town}, NY â¦")
        resp = self._get(url, params={"searchQueryState": search_state})
        if resp is None:
            return []

        data = self._next_data(resp.text)
        results = self._extract_results(data)
        if not results:
            results = self._html_fallback(resp.text)

        return [r for r in results if self._qualifies(r, min_price, cutoff)]

    def _qualifies(self, r: dict, min_price: int, cutoff: datetime) -> bool:
        if r.get("price", 0) < min_price:
            return False
        sold_str = r.get("sold_date", "")
        if sold_str:
            try:
                if datetime.strptime(sold_str[:10], "%Y-%m-%d") < cutoff:
                    return False
            except ValueError:
                pass
        return True

    def _extract_results(self, data: dict) -> List[Dict]:
        items = []
        try:
            cat1 = (data.get("props", {})
                        .get("pageProps", {})
                        .get("searchPageState", {})
                        .get("cat1", {}))
            list_results = cat1.get("searchResults", {}).get("listResults", [])
            if not list_results:
                list_results = (data.get("props", {})
                                    .get("pageProps", {})
                                    .get("searchPageState", {})
                                    .get("searchResults", {})
                                    .get("listResults", []))
            for item in list_results:
                p = self._parse_item(item)
                if p:
                    items.append(p)
        except Exception as e:
            log.debug(f"JSON parse error: {e}")
        return items

    def _parse_item(self, item: dict) -> Optional[Dict]:
        price_raw = item.get("price", item.get("unformattedPrice", 0))
        price = int(re.sub(r"[^0-9]", "", str(price_raw)) or "0")

        address  = item.get("address") or item.get("streetAddress", "")
        city     = item.get("addressCity") or item.get("city", "")
        state    = item.get("addressState") or "NY"
        zipcode  = item.get("addressZipcode") or item.get("zipcode", "")
        full_addr = f"{address}, {city}, {state} {zipcode}".strip(", ")

        sold_date = (item.get("soldDate") or item.get("lastSoldDate")
                     or item.get("dateSold", ""))

        detail_url = item.get("detailUrl", "")
        if detail_url and not detail_url.startswith("http"):
            detail_url = self.BASE + detail_url

        thumb = item.get("imgSrc", "")
        if not thumb:
            mini = item.get("miniCardPhotos", [])
            thumb = mini[0].get("url", "") if mini else ""

        return {
            "zpid":       item.get("zpid"),
            "address":    full_addr,
            "price":      price,
            "sold_date":  sold_date,
            "zillow_url": detail_url,
            "thumbnail":  thumb,
            "beds":       item.get("beds", ""),
            "baths":      item.get("baths", ""),
            "sqft":       item.get("area", ""),
        }

    def _html_fallback(self, html: str) -> List[Dict]:
        results = []
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select('[data-test="property-card"]')
        for card in cards:
            try:
                price_el = card.select_one('[data-test="property-card-price"]')
                price = int(re.sub(r"[^0-9]", "", price_el.text or "0")) if price_el else 0
                addr_el = card.select_one('[data-test="property-card-addr"]')
                address = addr_el.text.strip() if addr_el else ""
                link_el = card.select_one("a[href*='/homedetails/']")
                url = (self.BASE + link_el["href"]) if link_el else ""
                img_el = card.select_one("img")
                thumb = img_el.get("src", "") if img_el else ""
                if address:
                    results.append({"address": address, "price": price,
                                    "zillow_url": url, "thumbnail": thumb})
            except Exception:
                continue
        return results

    def get_exterior_photo_url(self, prop: Dict) -> Optional[str]:
        thumb = prop.get("thumbnail", "")
        if thumb and "zillowstatic.com" in thumb:
            return re.sub(r"_\d+x\d+", "_1920x1080", thumb)

        detail_url = prop.get("zillow_url", "")
        if not detail_url:
            return thumb or None

        resp = self._get(detail_url)
        if resp is None:
            return thumb or None

        data = self._next_data(resp.text)
        photo_url = self._photo_from_data(data)
        if photo_url:
            return photo_url

        soup = BeautifulSoup(resp.text, "lxml")
        og = soup.find("meta", {"property": "og:image"})
        if og and og.get("content"):
            return og["content"]

        imgs = soup.select("img[src*='photos.zillowstatic.com']")
        if imgs:
            return re.sub(r"_\d+x\d+", "_1920x1080", imgs[0].get("src", ""))

        return thumb or None

    def _photo_from_data(self, data: dict) -> Optional[str]:
        try:
            gdp_cache = (data.get("props", {})
                             .get("pageProps", {})
                             .get("componentProps", {})
                             .get("gdpClientCache", {}))
            for val in gdp_cache.values():
                if not isinstance(val, dict):
                    continue
                photos = val.get("property", {}).get("photos", [])
                if photos and isinstance(photos[0], dict):
                    sources = photos[0].get("mixedSources", {}).get("jpeg", [])
                    if sources:
                        return max(sources, key=lambda x: x.get("width", 0)).get("url", "")
        except Exception:
            pass
        return None

    def download_image(self, url: str) -> Optional[bytes]:
        if not url:
            return None
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.content if len(resp.content) > 5_000 else None
        except Exception as e:
            log.warning(f"  Image download failed: {e}")
            return None


# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# REDFIN FALLBACK SCRAPER
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

class RedfinScraper:
    BASE = "https://www.redfin.com"
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.redfin.com/",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def _get(self, url: str, **kwargs) -> Optional[requests.Response]:
        time.sleep(REQUEST_DELAY)
        try:
            resp = self.session.get(url, timeout=20, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception as e:
            log.warning(f"  Redfin error: {e}")
            return None

    def search_sold(self, town: str, min_price: int, max_age_days: int) -> List[Dict]:
        cutoff = datetime.now() - timedelta(days=max_age_days)
        years = max(1, max_age_days // 365)
        town_slug = town.replace(" ", "-")
        url = (f"{self.BASE}/NY/{town_slug}/"
               f"filter/min-price={min_price},include=sold-{years}yr")

       log.info(f"Redfin: {town}, NY (fallback) â¦")
        resp = self._get(url)
        if resp is None:
            return []

        results = self._parse(resp.text, min_price, cutoff)
        log.info(f"  â {len(results)} qualifying homes (Redfin)")
        return results

    def _parse(self, html: str, min_price: int, cutoff: datetime) -> List[Dict]:
        soup = BeautifulSoup(html, "lxml")
        results = []
        for s in soup.find_all("script", {"type": "application/json"}):
            try:
                data = json.loads(s.string or "{}")
                homes = data.get("homes", data.get("properties", []))
                for h in homes:
                    p = self._parse_home(h, min_price, cutoff)
                    if p:
                        results.append(p)
                if results:
                    break
            except Exception:
                continue
        return results

    def _parse_home(self, h: dict, min_price: int, cutoff: datetime) -> Optional[Dict]:
        price_raw = h.get("price", h.get("soldPrice", 0))
        price = int(re.sub(r"[^0-9]", "", str(price_raw)) or "0")
        if price < min_price:
            return None
        sold_date = h.get("soldDate", h.get("lastSoldDate", ""))
        if sold_date:
            try:
                if datetime.strptime(sold_date[:10], "%Y-%m-%d") < cutoff:
                    return None
            except ValueError:
                pass
        address = h.get("streetLine", h.get("address", ""))
        city = h.get("city", "")
        state = h.get("state", "NY")
        zipcode = h.get("zip", "")
        url = h.get("url", "")
        if url and not url.startswith("http"):
            url = self.BASE + url
        thumb = h.get("photoURL", h.get("primaryPhotoDisplayUrl", ""))
        return {
            "address":   f"{address}, {city}, {state} {zipcode}".strip(", "),
            "price":     price,
            "sold_date": sold_date,
            "zillow_url": url,
            "thumbnail":  thumb,
            "source":    "redfin",
        }


# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# AI LANDSCAPE LIGHTING RENDERER
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

class LandscapeRenderer:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY.")
        self.client = openai.OpenAI(api_key=api_key)

    def describe_home(self, image_bytes: bytes) -> str:
        b64 = base64.b64encode(image_bytes).decode()
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}",
                                "detail": "high"
                            }
                        },
                        {
                            "type": "text",
                            "text": (
                                "You are helping a landscape lighting designer prepare a "
                                "client presentation. Describe this home exterior in 3 sentences:\n"
                                "- Architectural style (colonial, contemporary, Tudor, farmhouse, etc.)\n"
                                "- Exterior materials and colors\n"
                                "- Key features: columns, dormers, windows, portico, garage\n"
                                "- Trees, shrubs, driveway material\n"
                                "Be specific â this will be used to generate a landscape lighting rendering."
                            )
                        }
                    ]
                }],
                max_tokens=300
            )
            return response.choices[0].message.content
        except Exception as e:
            log.warning(f"  GPT-4o analysis failed: {e}")
            return "A large luxury single-family home with professional landscaping and a paved driveway."

    def generate_rendering(self, house_description: str) -> Optional[bytes]:
        prompt = f"""Photorealistic landscape lighting design rendering of a luxury home at twilight.

HOME: {house_description}

LIGHTING to show:
- Warm 2700K LED uplights on the home facade
- Path lights along the driveway and walkway with amber pools of light
- Architectural spotlights on columns, dormers, and features
- Tree uplighting creating dramatic silhouettes against deep blue twilight sky
- Step/riser lighting on front steps
- Subtle garden bed accent lights
- Soft warm glow from windows inside
- Professional landscape lighting portfolio photo quality
- Photorealistic, magazine-worthy image, twilight/dusk atmosphere"""

        try:
            response = self.client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1792x1024",
                quality="hd",
                n=1,
                style="natural"
            )
            img_resp = requests.get(response.data[0].url, timeout=60)
            img_resp.raise_for_status()
            return img_resp.content
        except openai.BadRequestError:
            # Retry with shorter prompt
            try:
                response = self.client.images.generate(
                    model="dall-e-3",
                    prompt=(
                        f"A luxury home at dusk with professional landscape lighting. "
                       f"{house_description[:150]} "
                        "Warm LED uplighting on facade, amber path lights along driveway, "
                        "tree uplighting, twilight blue sky. Photorealistic rendering."
                    ),
                    size="1792x1024",
                    quality="hd",
                    n=1,
                )
                img_resp = requests.get(response.data[0].url, timeout=60)
                return img_resp.content
            except Exception as e2:
                log.error(f"  Rendering failed after retry: {e2}")
                return None
        except Exception as e:
            log.error(f"  Rendering generation failed: {e}")
            return None


# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# LEAD GENERATOR â MAIN ORCHESTRATOR
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

class LeadGenerator:
    def __init__(self):
        if not OPENAI_API_KEY:
            log.error("OPENAI_API_KEY is not set. Set it and try again.")
            sys.exit(1)

        self.zillow   = ZillowScraper()
        self.redfin   = RedfinScraper()
        self.renderer = LandscapeRenderer(OPENAI_API_KEY)
        self.stats    = {"found": 0, "photos": 0, "renderings": 0,
                         "skipped": 0, "errors": 0}

        self.done_file = OUTPUT_DIR / ".completed_addresses.json"
        self.done: set = set()
        if self.done_file.exists():
            try:
                with open(self.done_file) as f:
                    self.done = set(json.load(f))
                log.info(f"Resuming â {len(self.done)} homes already done from prior runs")
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
            f.write(f"Address:    {address}\n")
            f.write(f"Sale Price: ${meta.get('price', 0):,}\n")
            f.write(f"Sold Date:  {meta.get('sold_date', 'Unknown')}\n")
            f.write(f"Bedrooms:   {meta.get('beds', 'N/A')}\n")
            f.write(f"Bathrooms:  {meta.get('baths', 'N/A')}\n")
            f.write(f"Sq Ft:      {meta.get('sqft', 'N/A')}\n")
            f.write(f"Zillow URL: {meta.get('zillow_url', 'N/A')}\n")
            f.write(f"Generated:  {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

        return folder

    def _mark_done(self, address: str):
        self.done.add(address)
        try:
            with open(self.done_file, "w") as f:
                json.dump(list(self.done), f)
        except Exception:
            pass

    def process_home(self, prop: Dict) -> bool:
        address = prop.get("address", "Unknown")
        if address in self.done or address == "Unknown":
            self.stats["skipped"] += 1
            return False

        log.info(f"\n{'â'*60}")
        log.info(f"ð  {address}")
        log.info(f"ð°  ${prop.get('price', 0):,}  |  Sold: {prop.get('sold_date', 'Unknown')}")

        # Get photo URL
        photo_url = self.zillow.get_exterior_photo_url(prop)
        if not photo_url:
            log.warning("  No exterior photo â skipping")
            self.stats["errors"] += 1
            return False

        # Download photo
        log.info("  Downloading exterior photo â¦")
        img_bytes = self.zillow.download_image(photo_url)
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
            if img.format not in ("JPEG", "JPG"):
                buf = BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=90)
                img_bytes = buf.getvalue()
        except Exception as e:
            log.warning(f"  Invalid image: {e}")
            self.stats["errors"] += 1
            return False

        self.stats["photos"] += 1
        log.info(f"  Photo downloaded ({w}Ã{h} px)")

        # Analyze with GPT-4o
        log.info("  Analyzing home architecture with GPT-4o â¦")
        description = self.renderer.describe_home(img_bytes)
        log.info(f"  â {description[:100]}â¦")

        # Generate rendering
        log.info("  Generating landscape lighting rendering with DALL-E 3 â¦")
        rendering = self.renderer.generate_rendering(description)
        if rendering:
            self.stats["renderings"] += 1
            log.info("  â Rendering created!")
        else:
            log.warning("  â ï¸  Rendering failed â saving original only")

        # Save to folder
        folder = self._save(address, img_bytes, rendering, prop)
        log.info(f"  ð  Saved â {folder.name}/")

        self._mark_done(address)
        return True

    def collect_properties(self) -> List[Dict]:
        all_props: List[Dict] = []
        seen: set = set()

        areas = (
            [(t, "Northern Nassau") for t in NORTHERN_NASSAU] +
            [(t, "Suffolk County")  for t in SUFFOLK_COUNTY]
        )

        log.info(f"\n{'â'*60}")
        log.info(f"PHASE 1: SEARCHING {len(areas)} AREAS")
        log.info(f"{'â'*60}")

        for town, region in areas:
            if len(all_props) >= MAX_TOTAL:
                break

            props = self.zillow.search_sold(town, MIN_SALE_PRICE, MAX_AGE_DAYS)
            if not props:
                props = self.redfin.search_sold(town, MIN_SALE_PRICE, MAX_AGE_DAYS)

            added = 0
            for p in props[:MAX_PER_TOWN]:
                addr = p.get("address", "").strip()
                if addr and addr not in seen:
                    seen.add(addr)
                    all_props.append(p)
                    self.stats["found"] += 1
                    added += 1
                    log.info(f"  [{region}] {addr} â ${p.get('price', 0):,}")

        log.info(f"\nTotal qualifying homes: {len(all_props)}")

        with open(OUTPUT_DIR / "all_leads.json", "w") as f:
            json.dump(all_props, f, indent=2)
        log.info("Saved all_leads.json")
        return all_props

    def run(self):
        start = datetime.now()
        log.info(f"\n{'â'*60}")
        log.info("  LUXURY HOME LANDSCAPE LIGHTING LEAD GENERATOR")
        log.info(f"  Min price:  ${MIN_SALE_PRICE:,}")
        log.info(f"  Max age:    {MAX_AGE_DAYS} days  |  Max total: {MAX_TOTAL}")
        log.info(f"  Output:     {OUTPUT_DIR}")
        log.info(f"{'â'*60}")

        properties = self.collect_properties()
        if not properties:
            log.warning("No qualifying homes found. Zillow/Redfin may be rate-limiting. "
                        "Try again in 30 minutes.")
            return

        log.info(f"\n{'â'*60}")
        log.info(f"PHASE 2: PROCESSING {len(properties)} HOMES")
        log.info(f"{'â'*60}")

        for i, prop in enumerate(properties, 1):
            log.info(f"\n[{i}/{len(properties)}]")
            try:
                self.process_home(prop)
            except KeyboardInterrupt:
                log.info("\nâ¹  Stopped by user")
                break
            except Exception as e:
                log.error(f"Error: {e}")
                log.debug(traceback.format_exc())
                self.stats["errors"] += 1

            if self.stats["renderings"] + self.stats["errors"] >= MAX_TOTAL:
                break

        elapsed = datetime.now() - start
        log.info(f"\n{'â'*60}")
        log.info("  RUN COMPLETE")
        log.info(f"  Time: {str(elapsed).split('.')[0]}")
        log.info(f"  Found: {self.stats['found']}  |  Photos: {self.stats['photos']}"
                 f"  |  Renderings: {self.stats['renderings']}"
                 f"  |  Errors: {self.stats['errors']}")
        log.info(f"  Output: {OUTPUT_DIR}")
        log.info(f"{'â'*60}\n")


# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# ENTRY POINT
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

if __name__ == "__main__":
    LeadGenerator().run()

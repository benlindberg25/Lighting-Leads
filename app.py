#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║  Landscape Lighting Lead Generator  —  Web Dashboard      ║
║  Built with Streamlit • Deploy free at streamlit.io       ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import time
import base64
import subprocess
import threading
import requests
from pathlib import Path
from datetime import datetime, timedelta
from io import BytesIO

import streamlit as st
from PIL import Image
import openai

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Landscape Lighting Leads",
    page_icon="💡",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "Luxury Home Landscape Lighting Lead Generator — finds recently sold $1.3M+ homes and creates AI lighting renderings."
    }
)

# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM CSS  (dark professional theme with warm gold accents)
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* ── Base & Background ─────────────────────────────────── */
.stApp {
    background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
    color: #e6edf3;
}

/* ── Sidebar ──────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1f2e 0%, #141820 100%);
    border-right: 1px solid #2a3040;
}
[data-testid="stSidebar"] .stMarkdown h1,
[data-testid="stSidebar"] .stMarkdown h2,
[data-testid="stSidebar"] .stMarkdown h3 {
    color: #f0b429;
}

/* ── Buttons ──────────────────────────────────────────── */
.stButton > button {
    background: linear-gradient(135deg, #c8922a 0%, #f0b429 100%);
    color: #0d1117;
    font-weight: 700;
    font-size: 15px;
    border: none;
    border-radius: 8px;
    padding: 0.6rem 1.5rem;
    transition: all 0.2s ease;
    box-shadow: 0 4px 15px rgba(240, 180, 41, 0.25);
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 20px rgba(240, 180, 41, 0.40);
    color: #0d1117;
}

/* ── Metric Cards ─────────────────────────────────────── */
[data-testid="metric-container"] {
    background: #1c2132;
    border: 1px solid #2a3040;
    border-radius: 10px;
    padding: 16px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: #f0b429;
    font-size: 2rem !important;
    font-weight: 700;
}
[data-testid="metric-container"] [data-testid="stMetricLabel"] {
    color: #8b949e;
}

/* ── Property Cards ───────────────────────────────────── */
.property-card {
    background: #1c2132;
    border: 1px solid #2a3040;
    border-radius: 12px;
    padding: 0;
    margin-bottom: 24px;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    transition: box-shadow 0.2s ease;
}
.property-card:hover {
    box-shadow: 0 8px 30px rgba(240, 180, 41, 0.15);
    border-color: #f0b429;
}
.property-card-header {
    background: linear-gradient(135deg, #1a2035 0%, #1c2132 100%);
    padding: 14px 18px;
    border-bottom: 1px solid #2a3040;
}
.property-address {
    font-size: 15px;
    font-weight: 600;
    color: #e6edf3;
    margin: 0 0 4px 0;
}
.property-meta {
    font-size: 13px;
    color: #8b949e;
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
}
.price-badge {
    display: inline-block;
    background: rgba(240, 180, 41, 0.15);
    color: #f0b429;
    border: 1px solid rgba(240, 180, 41, 0.3);
    border-radius: 6px;
    padding: 2px 10px;
    font-size: 13px;
    font-weight: 600;
}

/* ── Photo Labels ─────────────────────────────────────── */
.photo-label {
    text-align: center;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 8px 0 4px 0;
}
.label-before { color: #8b949e; }
.label-after  { color: #f0b429; }

/* ── Section Headers ──────────────────────────────────── */
.section-title {
    font-size: 22px;
    font-weight: 700;
    color: #e6edf3;
    border-left: 4px solid #f0b429;
    padding-left: 12px;
    margin: 8px 0 20px 0;
}

/* ── Log output ───────────────────────────────────────── */
.stCode, code, pre {
    background: #0d1117 !important;
    border: 1px solid #2a3040 !important;
    border-radius: 8px !important;
    color: #7ee787 !important;
    font-size: 12px !important;
}

/* ── Inputs & Sliders ─────────────────────────────────── */
.stNumberInput input, .stTextInput input {
    background: #1c2132 !important;
    border: 1px solid #2a3040 !important;
    color: #e6edf3 !important;
    border-radius: 8px !important;
}
.stSlider [data-testid="stThumbValue"] {
    color: #f0b429 !important;
}

/* ── Tabs ─────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    border-bottom: 1px solid #2a3040;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    border-radius: 8px 8px 0 0;
    color: #8b949e;
    padding: 8px 16px;
}
.stTabs [aria-selected="true"] {
    background: rgba(240, 180, 41, 0.1) !important;
    color: #f0b429 !important;
    border-bottom: 2px solid #f0b429 !important;
}

/* ── Dividers ─────────────────────────────────────────── */
hr { border-color: #2a3040; }

/* ── Alert/Info boxes ─────────────────────────────────── */
.stAlert {
    background: #1c2132 !important;
    border: 1px solid #2a3040 !important;
    border-radius: 8px !important;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS & PATHS
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR  = Path(__file__).parent
LEADS_DIR   = SCRIPT_DIR / "leads_output"
AGENT_SCRIPT = SCRIPT_DIR / "landscape_leads.py"
MANIFEST    = LEADS_DIR / "all_leads.json"
DONE_FILE   = LEADS_DIR / ".completed_addresses.json"

LEADS_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────

defaults = {
    "running":           False,
    "run_logs":          [],
    "process":           None,
    "run_complete":      False,
    "last_run":          None,
    "upload_rendering":  None,   # bytes of the generated rendering
    "upload_original":   None,   # bytes of the uploaded photo
    "upload_description": "",    # GPT-4o description
    "upload_generating": False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def get_api_key() -> str:
    """Get OpenAI API key from Streamlit secrets or environment."""
    try:
        return st.secrets.get("OPENAI_API_KEY", "")
    except Exception:
        return os.environ.get("OPENAI_API_KEY", "")


def generate_rendering(client: "openai.OpenAI", image_bytes: bytes) -> bytes | None:
    """
    Edit the actual uploaded home photo to add professional landscape lighting.
    Uses gpt-image-1 image editing so the home's architecture is preserved exactly.
    Falls back to DALL-E 2 image edit if gpt-image-1 is unavailable.
    """
    prompt = (
        "Edit this real photo of a home to add professional landscape lighting, making it look "
        "like a photograph taken at twilight/dusk. The home's architecture, structure, colors, "
        "materials, and all physical features must remain EXACTLY the same — do not change the "
        "house at all, only add lighting effects around and on it. "
        "Add: warm 2700K LED uplights washing the facade, amber path lights lining the driveway, "
        "architectural spotlights highlighting columns and architectural details, dramatic tree "
        "uplighting silhouetted against a deep blue twilight sky, step lighting, garden accent "
        "lights, warm golden glow from interior windows. "
        "The result should look like a real twilight photograph of the exact same house with "
        "professional landscape lighting installed. Magazine-quality real estate photography."
    )
    try:
        # Primary: gpt-image-1 image editing (preserves the actual house)
        buf = BytesIO(image_bytes)
        buf.name = "home.jpg"
        resp = client.images.edit(
            model="gpt-image-1",
            image=buf,
            prompt=prompt,
            n=1,
            size="auto",
        )
        return base64.b64decode(resp.data[0].b64_json)
    except Exception:
        pass

    try:
        # Fallback: DALL-E 2 image edit (requires PNG, max 4MB)
        pil_img = Image.open(BytesIO(image_bytes)).convert("RGBA")
        # Resize if too large (DALL-E 2 limit)
        pil_img.thumbnail((1024, 1024), Image.LANCZOS)
        png_buf = BytesIO()
        pil_img.save(png_buf, format="PNG")
        png_buf.seek(0)
        png_buf.name = "home.png"
        resp = client.images.edit(
            image=png_buf,
            prompt=prompt,
            n=1,
            size="1024x1024",
        )
        img_r = requests.get(resp.data[0].url, timeout=60)
        img_r.raise_for_status()
        return img_r.content
    except Exception:
        return None


def load_leads() -> list[dict]:
    """Load all leads from the manifest file."""
    if not MANIFEST.exists():
        return []
    try:
        with open(MANIFEST) as f:
            return json.load(f)
    except Exception:
        return []


def get_completed_addresses() -> set:
    """Get set of already-processed addresses."""
    if not DONE_FILE.exists():
        return set()
    try:
        with open(DONE_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def get_result_folders() -> list[Path]:
    """Return all address folders that contain images, sorted newest first."""
    folders = []
    for item in LEADS_DIR.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            if (item / "original.jpg").exists():
                folders.append(item)
    folders.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return folders


def read_property_info(folder: Path) -> dict:
    """Parse property_info.txt into a dict."""
    info = {}
    info_file = folder / "property_info.txt"
    if info_file.exists():
        for line in info_file.read_text().splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                info[key.strip()] = val.strip()
    return info


def format_price(price_str: str) -> str:
    """Format price string nicely."""
    try:
        price = int(price_str.replace(",", "").replace("$", "").strip())
        return f"${price:,}"
    except Exception:
        return price_str


def run_agent(api_key: str, min_price: int, max_age_days: int, max_total: int):
    """
    Run landscape_leads.py as a subprocess and stream output to session state.
    Called in a background thread.
    """
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = api_key
    env["PYTHONUNBUFFERED"] = "1"  # Force unbuffered output

    cmd = [
        sys.executable, str(AGENT_SCRIPT),
        f"--min-price={min_price}",
        f"--max-age={max_age_days}",
        f"--max-total={max_total}",
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        st.session_state.process = proc

        for line in proc.stdout:
            line = line.rstrip()
            if line:
                st.session_state.run_logs.append(line)

        proc.wait()
        st.session_state.run_complete = True
        st.session_state.last_run = datetime.now().strftime("%Y-%m-%d %H:%M")

    except Exception as e:
        st.session_state.run_logs.append(f"ERROR: {e}")
        st.session_state.run_complete = True
    finally:
        st.session_state.running = False


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 💡 Landscape Lighting\n### Lead Generator")
    st.markdown("---")

    # API Key
    st.markdown("**OpenAI API Key**")
    api_key_input = st.text_input(
        "OpenAI API Key",
        value=get_api_key(),
        type="password",
        placeholder="sk-...",
        label_visibility="collapsed",
        help="Get your key at platform.openai.com/api-keys"
    )
    if not api_key_input:
        st.warning("⚠️ API key required to run")

    st.markdown("---")
    st.markdown("**Search Settings**")

    min_price = st.number_input(
        "Minimum Sale Price ($)",
        min_value=500_000,
        max_value=10_000_000,
        value=1_300_000,
        step=50_000,
        format="%d",
    )

    max_age_years = st.slider(
        "Sold within (years)",
        min_value=1,
        max_value=5,
        value=2,
        step=1,
    )
    max_age_days = max_age_years * 365

    max_total = st.slider(
        "Max homes per run",
        min_value=10,
        max_value=300,
        value=50,
        step=10,
        help="Lower = faster & cheaper. Each home costs ~$0.085 in OpenAI fees."
    )

    st.markdown(
        f"<small style='color:#8b949e'>Estimated cost: "
        f"<span style='color:#f0b429'>${max_total * 0.085:.2f}</span> max</small>",
        unsafe_allow_html=True
    )

    st.markdown("---")

    # Run / Stop buttons
    if not st.session_state.running:
        run_clicked = st.button(
            "🚀  Run Agent",
            use_container_width=True,
            disabled=not api_key_input,
        )
        if run_clicked:
            if not api_key_input:
                st.error("Please enter your OpenAI API key above.")
            elif not AGENT_SCRIPT.exists():
                st.error(f"Agent script not found: {AGENT_SCRIPT}")
            else:
                st.session_state.running = True
                st.session_state.run_complete = False
                st.session_state.run_logs = ["🚀 Starting agent…"]
                thread = threading.Thread(
                    target=run_agent,
                    args=(api_key_input, min_price, max_age_days, max_total),
                    daemon=True,
                )
                thread.start()
                st.rerun()
    else:
        st.button("⏹  Stop", use_container_width=True, type="secondary",
                  on_click=lambda: (
                      st.session_state.process.terminate()
                      if st.session_state.process else None
                  ))
        st.info("Agent is running…")

    # Stats summary
    st.markdown("---")
    completed = get_completed_addresses()
    folders   = get_result_folders()
    st.markdown("**Results Summary**")
    col_a, col_b = st.columns(2)
    col_a.metric("Leads Found", len(folders))
    col_b.metric("Renderings", sum(1 for f in folders if (f / "with_landscape_lighting.jpg").exists()))

    if st.session_state.last_run:
        st.markdown(f"<small style='color:#8b949e'>Last run: {st.session_state.last_run}</small>",
                    unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CONTENT
# ─────────────────────────────────────────────────────────────────────────────

# Page header
st.markdown("""
<div style='padding: 8px 0 24px 0;'>
    <h1 style='font-size:32px; font-weight:800; color:#e6edf3; margin:0;'>
        💡 Landscape Lighting Lead Generator
    </h1>
    <p style='color:#8b949e; font-size:15px; margin:6px 0 0 0;'>
        Northern Nassau County &amp; Suffolk County, NY — Homes sold $1.3M+ in the last 2 years
    </p>
</div>
""", unsafe_allow_html=True)

# Tabs
tab_gallery, tab_upload, tab_progress, tab_leads = st.tabs([
    "📸  Before / After Gallery",
    "🏠  Upload & Render",
    "⚙️  Run Progress",
    "📋  All Leads",
])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — GALLERY
# ─────────────────────────────────────────────────────────────────────────────

with tab_gallery:
    folders = get_result_folders()

    if not folders:
        st.markdown("""
        <div style='text-align:center; padding:60px 0;'>
            <div style='font-size:48px; margin-bottom:16px;'>🏡</div>
            <h3 style='color:#8b949e;'>No results yet</h3>
            <p style='color:#4a5568;'>Click <strong style='color:#f0b429;'>Run Agent</strong>
               in the sidebar to start finding homes and generating renderings.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Filter bar
        with st.expander("🔍 Filter results", expanded=False):
            search_text = st.text_input("Search by address", placeholder="e.g. Huntington, East Hampton…")
            show_only_rendered = st.checkbox("Show only homes with AI renderings", value=False)

        # Apply filters
        filtered = folders
        if search_text:
            filtered = [f for f in filtered if search_text.lower() in f.name.lower()]
        if show_only_rendered:
            filtered = [f for f in filtered if (f / "with_landscape_lighting.jpg").exists()]

        st.markdown(
            f"<p style='color:#8b949e; font-size:13px;'>Showing {len(filtered)} of {len(folders)} properties</p>",
            unsafe_allow_html=True
        )

        # Display property cards
        for folder in filtered:
            info = read_property_info(folder)
            address   = info.get("Address",    folder.name)
            price     = info.get("Sale Price", "N/A")
            sold_date = info.get("Sold Date",  "")
            zillow_url = info.get("Zillow URL", "")
            beds   = info.get("Bedrooms",  "")
            baths  = info.get("Bathrooms", "")
            sqft   = info.get("Sq Ft",     "")

            # Card header
            meta_parts = []
            if beds and beds != "N/A":   meta_parts.append(f"🛏  {beds} bd")
            if baths and baths != "N/A": meta_parts.append(f"🚿  {baths} ba")
            if sqft and sqft != "N/A":   meta_parts.append(f"📐  {sqft} sq ft")
            if sold_date:                meta_parts.append(f"📅  Sold {sold_date}")

            meta_html = "  ·  ".join(meta_parts) if meta_parts else ""
            zillow_link = (f"<a href='{zillow_url}' target='_blank' "
                           f"style='color:#f0b429; font-size:12px;'>View on Zillow ↗</a>"
                           if zillow_url and zillow_url != "N/A" else "")

            st.markdown(f"""
            <div class='property-card'>
                <div class='property-card-header'>
                    <div style='display:flex; justify-content:space-between; align-items:start;'>
                        <p class='property-address'>{address}</p>
                        <span class='price-badge'>{price}</span>
                    </div>
                    <div class='property-meta'>
                        {meta_html}
                        {("· " + zillow_link) if zillow_link else ""}
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Photos
            orig_path   = folder / "original.jpg"
            render_path = folder / "with_landscape_lighting.jpg"

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("<p class='photo-label label-before'>📷 Original Photo</p>",
                            unsafe_allow_html=True)
                if orig_path.exists():
                    st.image(str(orig_path), use_container_width=True)
                else:
                    st.markdown(
                        "<div style='background:#1c2132; height:200px; border-radius:8px; "
                        "display:flex; align-items:center; justify-content:center; "
                        "color:#4a5568;'>No photo</div>",
                        unsafe_allow_html=True
                    )

            with col2:
                st.markdown("<p class='photo-label label-after'>💡 With Landscape Lighting (AI)</p>",
                            unsafe_allow_html=True)
                if render_path.exists():
                    st.image(str(render_path), use_container_width=True)
                else:
                    st.markdown(
                        "<div style='background:#1c2132; height:200px; border-radius:8px; "
                        "display:flex; align-items:center; justify-content:center; "
                        "color:#4a5568; border: 1px dashed #2a3040;'>⏳ Rendering pending</div>",
                        unsafe_allow_html=True
                    )

            # Download buttons
            dl_col1, dl_col2, _ = st.columns([1, 1, 3])
            if orig_path.exists():
                with open(orig_path, "rb") as f:
                    dl_col1.download_button(
                        "⬇ Original",
                        data=f.read(),
                        file_name=f"{folder.name}_original.jpg",
                        mime="image/jpeg",
                        key=f"dl_orig_{folder.name}",
                    )
            if render_path.exists():
                with open(render_path, "rb") as f:
                    dl_col2.download_button(
                        "⬇ Rendering",
                        data=f.read(),
                        file_name=f"{folder.name}_landscape_lighting.jpg",
                        mime="image/jpeg",
                        key=f"dl_render_{folder.name}",
                    )

            st.markdown("<hr style='margin: 8px 0 20px 0; border-color:#2a3040;'>",
                        unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — UPLOAD & RENDER
# ─────────────────────────────────────────────────────────────────────────────

with tab_upload:
    st.markdown("""
    <div style='padding: 4px 0 20px 0;'>
      <h2 style='font-size:22px; font-weight:700; color:#e6edf3; margin:0;'>
        Upload a Home Photo
      </h2>
      <p style='color:#8b949e; font-size:14px; margin:6px 0 0 0;'>
        Upload any exterior photo of a home and we'll generate a professional
        landscape lighting rendering using DALL-E 3.
      </p>
    </div>
    """, unsafe_allow_html=True)

    if not api_key_input:
        st.warning("⚠️ Enter your OpenAI API key in the sidebar to use this feature.")
    else:
        uploaded_file = st.file_uploader(
            "Choose a home exterior photo",
            type=["jpg", "jpeg", "png", "webp"],
            help="Upload a front-facing exterior photo for best results. JPG, PNG, or WebP."
        )

        if uploaded_file:
            # Read and normalise to JPEG
            raw = uploaded_file.read()
            try:
                pil_img = Image.open(BytesIO(raw)).convert("RGB")
                buf = BytesIO()
                pil_img.save(buf, format="JPEG", quality=92)
                img_bytes = buf.getvalue()
            except Exception as e:
                st.error(f"Could not read image: {e}")
                img_bytes = None

            if img_bytes:
                # Show the uploaded photo
                col_orig, col_render = st.columns(2)
                with col_orig:
                    st.markdown("<p class='photo-label label-before'>📷 Original Photo</p>",
                                unsafe_allow_html=True)
                    st.image(img_bytes, use_container_width=True)

                with col_render:
                    st.markdown("<p class='photo-label label-after'>💡 With Landscape Lighting (AI)</p>",
                                unsafe_allow_html=True)

                    # Show existing rendering if same file was already processed
                    if st.session_state.upload_rendering and st.session_state.upload_original == img_bytes:
                        st.image(st.session_state.upload_rendering, use_container_width=True)
                    else:
                        st.markdown(
                            "<div style='background:#1c2132; height:320px; border-radius:8px; "
                            "display:flex; align-items:center; justify-content:center; "
                            "color:#4a5568; border:1px dashed #2a3040; font-size:14px;'>"
                            "⏳ Click Generate to create rendering</div>",
                            unsafe_allow_html=True
                        )

                # Generate button
                gen_col, _ = st.columns([1, 3])
                with gen_col:
                    if st.button("✨  Generate Rendering", use_container_width=True,
                                 disabled=st.session_state.upload_generating):
                        st.session_state.upload_generating = True
                        st.session_state.upload_original = img_bytes
                        st.session_state.upload_rendering = None
                        st.rerun()

                # Run the generation (triggered after rerun)
                if st.session_state.upload_generating and st.session_state.upload_original == img_bytes:
                    with col_render:
                        with st.spinner("Editing your photo to add landscape lighting…  (~30–60 sec)"):
                            try:
                                client = openai.OpenAI(api_key=api_key_input)

                                # Directly edit the uploaded photo — preserves the actual house
                                rendering = generate_rendering(client, img_bytes)

                                if rendering:
                                    st.session_state.upload_rendering = rendering
                                    st.session_state.upload_generating = False
                                    st.rerun()
                                else:
                                    st.error("Rendering generation failed. Please try again.")
                                    st.session_state.upload_generating = False
                            except Exception as e:
                                st.error(f"Error: {e}")
                                st.session_state.upload_generating = False

                # Show rendering result + download
                if st.session_state.upload_rendering and st.session_state.upload_original == img_bytes:
                    with col_render:
                        st.image(st.session_state.upload_rendering, use_container_width=True)

                    # Download buttons
                    dl1, dl2, _ = st.columns([1, 1, 3])
                    with dl1:
                        st.download_button(
                            "⬇ Original",
                            data=img_bytes,
                            file_name="home_original.jpg",
                            mime="image/jpeg",
                            key="dl_upload_orig"
                        )
                    with dl2:
                        st.download_button(
                            "⬇ Rendering",
                            data=st.session_state.upload_rendering,
                            file_name="home_landscape_lighting.jpg",
                            mime="image/jpeg",
                            key="dl_upload_render"
                        )

                    st.success("✅ Rendering complete! Use the download button to save your image.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — RUN PROGRESS
# ─────────────────────────────────────────────────────────────────────────────

with tab_progress:
    if st.session_state.running:
        st.markdown(
            "<div style='display:flex; align-items:center; gap:10px; margin-bottom:16px;'>"
            "<div style='width:12px; height:12px; background:#f0b429; border-radius:50%; "
            "animation:pulse 1.5s infinite;'></div>"
            "<span style='color:#f0b429; font-weight:600;'>Agent is running…</span></div>"
            "<style>@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }</style>",
            unsafe_allow_html=True
        )
        # Auto-refresh while running
        time.sleep(2)
        st.rerun()

    elif st.session_state.run_complete:
        st.success("✅ Agent run complete!")
    elif not st.session_state.run_logs:
        st.markdown("""
        <div style='text-align:center; padding:60px 0;'>
            <div style='font-size:48px; margin-bottom:16px;'>⚙️</div>
            <h3 style='color:#8b949e;'>No runs yet</h3>
            <p style='color:#4a5568;'>Click <strong style='color:#f0b429;'>Run Agent</strong>
               in the sidebar to start.</p>
        </div>
        """, unsafe_allow_html=True)

    if st.session_state.run_logs:
        log_text = "\n".join(st.session_state.run_logs[-200:])  # Last 200 lines
        st.code(log_text, language=None)

        if st.button("🗑  Clear Log"):
            st.session_state.run_logs = []
            st.rerun()

    # Show run log files if they exist
    log_files = sorted(LEADS_DIR.glob("run_*.log"), reverse=True)
    if log_files:
        st.markdown("---")
        st.markdown("**Previous Run Logs**")
        selected_log = st.selectbox(
            "Select a log file",
            options=log_files,
            format_func=lambda p: p.name,
            label_visibility="collapsed"
        )
        if selected_log:
            with st.expander(f"📄 {selected_log.name}", expanded=False):
                try:
                    st.code(selected_log.read_text()[-5000:], language=None)
                except Exception:
                    st.warning("Could not read log file")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — ALL LEADS TABLE
# ─────────────────────────────────────────────────────────────────────────────

with tab_leads:
    leads = load_leads()
    folders = get_result_folders()
    completed = get_completed_addresses()

    # Summary metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Leads Found",    len(leads))
    m2.metric("Renderings Created",   sum(1 for f in folders if (f / "with_landscape_lighting.jpg").exists()))
    m3.metric("Photos Downloaded",    len(folders))
    m4.metric("Pending Processing",   max(0, len(leads) - len(completed)))

    st.markdown("---")

    if not leads:
        st.info("No lead data yet. Run the agent to start collecting properties.")
    else:
        # Build display table
        import pandas as pd

        rows = []
        for lead in leads:
            addr = lead.get("address", "")
            folder = LEADS_DIR / addr[:120]
            has_photo    = (folder / "original.jpg").exists() if folder.exists() else False
            has_rendering = (folder / "with_landscape_lighting.jpg").exists() if folder.exists() else False
            rows.append({
                "Address":   addr,
                "Sale Price": f"${lead.get('price', 0):,}",
                "Sold Date":  lead.get("sold_date", ""),
                "Beds":       lead.get("beds", ""),
                "Baths":      lead.get("baths", ""),
                "Sq Ft":      lead.get("sqft", ""),
                "Photo":      "✅" if has_photo else "⏳",
                "Rendering":  "✅" if has_rendering else "⏳",
                "Zillow":     lead.get("zillow_url", ""),
            })

        df = pd.DataFrame(rows)

        # Filter
        price_filter = st.text_input("Filter by address or area", placeholder="e.g. Huntington…")
        if price_filter:
            df = df[df["Address"].str.contains(price_filter, case=False)]

        st.dataframe(
            df.drop(columns=["Zillow"]),
            use_container_width=True,
            hide_index=True,
        )

        # CSV download
        csv = df.to_csv(index=False)
        st.download_button(
            "⬇ Download as CSV",
            data=csv,
            file_name=f"landscape_leads_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )


# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown(
    "<p style='text-align:center; color:#4a5568; font-size:12px;'>"
    "💡 Landscape Lighting Lead Generator • "
    "Northern Nassau &amp; Suffolk County, NY • "
    "Powered by Zillow, Redfin, OpenAI GPT-4o &amp; DALL-E 3"
    "</p>",
    unsafe_allow_html=True
)

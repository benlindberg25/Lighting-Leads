#!/usr/bin/env python3
"""
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
â  Landscape Lighting Lead Generator  â  Web Dashboard    â
â  Built with Streamlit â¢ Deploy free at streamlit.io     â
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
"""
import os
import sys
import json
import time
import queue
import subprocess
import threading
from pathlib import Path
from datetime import datetime, timedelta
from io import BytesIO

import streamlit as st
from PIL import Image

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# PAGE CONFIGURATION
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
st.set_page_config(
    page_title="Landscape Lighting Leads",
    page_icon="ð¡",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "Luxury Home Landscape Lighting Lead Generator â finds recently sold $1.3M+ homes and creates AI lighting renderings."
    }
)

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# CUSTOM CSS (dark professional theme with warm gold accents)
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
st.markdown("""
<style>
/* ââ Base & Background âââââââââââââââââââââââââââââââââ */
.stApp {
    background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
    color: #e6edf3;
}
/* ââ Sidebar âââââââââââââââââââââââââââââââââââââââââââ */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1f2e 0%, #141820 100%);
    border-right: 1px solid #2a3040;
}
[data-testid="stSidebar"] .stMarkdown h1,
[data-testid="stSidebar"] .stMarkdown h2,
[data-testid="stSidebar"] .stMarkdown h3 {
    color: #f0b429;
}
/* ââ Buttons âââââââââââââââââââââââââââââââââââââââââââ */
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
/* ââ Metric Cards ââââââââââââââââââââââââââââââââââââââââ */
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
/* ââ Property Cards ââââââââââââââââââââââââââââââââââââ */
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
/* ââ Photo Labels ââââââââââââââââââââââââââââââââââââââââ */
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
/* ââ Section Headers âââââââââââââââââââââââââââââââââââ */
.section-title {
    font-size: 22px;
    font-weight: 700;
    color: #e6edf3;
    border-left: 4px solid #f0b429;
    padding-left: 12px;
    margin: 8px 0 20px 0;
}
/* ââ Log output ââââââââââââââââââââââââââââââââââââââââ */
.stCode, code, pre {
    background: #0d1117 !important;
    border: 1px solid #2a3040 !important;
    border-radius: 8px !important;
    color: #7ee787 !important;
    font-size: 12px !important;
}
/* ââ Inputs & Sliders ââââââââââââââââââââââââââââââââââ */
.stNumberInput input, .stTextInput input {
    background: #1c2132 !important;
    border: 1px solid #2a3040 !important;
    color: #e6edf3 !important;
    border-radius: 8px !important;
}
.stSlider [data-testid="stThumbValue"] { color: #f0b429 !important; }
/* ââ Tabs ââââââââââââââââââââââââââââââââââââââââââââââââ */
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
/* ââ Dividers ââââââââââââââââââââââââââââââââââââââââââ */
hr { border-color: #2a3040; }
/* ââ Alert/Info boxes ââââââââââââââââââââââââââââââââââ */
.stAlert {
    background: #1c2132 !important;
    border: 1px solid #2a3040 !important;
    border-radius: 8px !important;
}
</style>
""", unsafe_allow_html=True)

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# CONSTANTS & PATHS
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
SCRIPT_DIR   = Path(__file__).parent
LEADS_DIR    = SCRIPT_DIR / "leads_output"
AGENT_SCRIPT = SCRIPT_DIR / "landscape_leads.py"
MANIFEST     = LEADS_DIR / "all_leads.json"
DONE_FILE    = LEADS_DIR / ".completed_addresses.json"
LEADS_DIR.mkdir(parents=True, exist_ok=True)

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# THREAD-SAFE COMMUNICATION
# Background thread writes to these; main thread reads them on each rerun.
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
_output_queue: queue.Queue = queue.Queue() if "_output_queue" not in globals() else _output_queue
_process_ref: list = [None]           # _process_ref[0] holds the Popen object
_SENTINEL = "__AGENT_DONE__"          # signals thread finished

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# SESSION STATE INITIALIZATION
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
defaults = {
    "running":      False,
    "run_logs":     [],
    "run_complete": False,
    "last_run":     None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# DRAIN QUEUE  (runs every Streamlit rerun while agent is active)
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
while not _output_queue.empty():
    try:
        item = _output_queue.get_nowait()
        if item == _SENTINEL:
            st.session_state.running      = False
            st.session_state.run_complete = True
            st.session_state.last_run     = datetime.now().strftime("%Y-%m-%d %H:%M")
        else:
            st.session_state.run_logs.append(item)
    except queue.Empty:
        break

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# HELPER FUNCTIONS
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
def get_api_key() -> str:
    """Get OpenAI API key from Streamlit secrets or environment."""
    try:
        return st.secrets.get("OPENAI_API_KEY", "")
    except Exception:
        return os.environ.get("OPENAI_API_KEY", "")

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
    """Return all address folders that have been processed, sorted newest first."""
    folders = []
    if not LEADS_DIR.exists():
        return folders
    for item in LEADS_DIR.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            if (item / "property_info.txt").exists():
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
    Run landscape_leads.py as a subprocess and push output to _output_queue.
    Runs in a background thread â NEVER touches st.session_state directly.
    """
    env = os.environ.copy()
    env["OPENAI_API_KEY"]    = api_key
    env["STREET_VIEW_KEY"]   = globals().get("street_view_key_input", "")
    env["PYTHONUNBUFFERED"]  = "1"

    cmd = [
        sys.executable, "-u", str(AGENT_SCRIPT),
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
        _process_ref[0] = proc
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                _output_queue.put(line)
        proc.wait()
    except Exception as e:
        _output_queue.put(f"ERROR: {e}")
    finally:
        _output_queue.put(_SENTINEL)   # always signal completion

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# SIDEBAR
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
with st.sidebar:
    st.markdown("## ð¡ Landscape Lighting\n### Lead Generator")
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

    st.markdown("---")
    st.markdown("**Google Street View API Key** *(optional)*")
    street_view_key_input = st.text_input(
        "Street View API Key",
        value=os.environ.get("STREET_VIEW_KEY", ""),
        type="password",
        placeholder="AIza...",
        label_visibility="collapsed",
        help="Enables real home photos. Get a free key at console.cloud.google.com"
    )
    if not api_key_input:
        st.warning("â ï¸ API key required to run")

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
        min_value=1, max_value=5, value=2, step=1,
    )
    max_age_days = max_age_years * 365

    max_total = st.slider(
        "Max homes per run",
        min_value=10, max_value=300, value=50, step=10,
        help="Lower = faster & cheaper. Each home costs ~$0.085 in OpenAI fees."
    )
    st.markdown(
        f"<small style='color:#8b949e'>Estimated cost: "
        f"<span style='color:#f0b429'>${max_total * 0.085:.2f}</span> max</small>",
        unsafe_allow_html=True
    )

    st.markdown("---")

    # Clear cache option
    done_file = LEADS_DIR / ".completed_addresses.json"
    if not st.session_state.running and done_file.exists():
        if st.button("ðï¸ Clear cache (re-run all homes)", use_container_width=True):
            done_file.unlink(missing_ok=True)
            leads_file = LEADS_DIR / "all_leads.json"
            leads_file.unlink(missing_ok=True)
            for folder in LEADS_DIR.iterdir():
                if folder.is_dir() and not folder.name.startswith("."):
                    import shutil
                    shutil.rmtree(folder, ignore_errors=True)
            st.success("Cache cleared! Click Run Agent to start fresh.")
            st.rerun()

    # Run / Stop buttons
    if not st.session_state.running:
        run_clicked = st.button(
            "ð Run Agent",
            use_container_width=True,
            disabled=not api_key_input,
        )
        if run_clicked:
            if not api_key_input:
                st.error("Please enter your OpenAI API key above.")
            elif not AGENT_SCRIPT.exists():
                st.error(f"Agent script not found: {AGENT_SCRIPT}")
            else:
                st.session_state.running      = True
                st.session_state.run_complete = False
                st.session_state.run_logs     = ["ð Starting agentâ¦"]
                thread = threading.Thread(
                    target=run_agent,
                    args=(api_key_input, min_price, max_age_days, max_total),
                    daemon=True,
                )
                thread.start()
                st.rerun()
    else:
        def _stop():
            proc = _process_ref[0]
            if proc:
                proc.terminate()

        st.button("â¹ Stop", use_container_width=True, type="secondary", on_click=_stop)
        st.info("Agent is runningâ¦")

    # Stats summary
    st.markdown("---")
    folders = get_result_folders()
    st.markdown("**Results Summary**")
    col_a, col_b = st.columns(2)
    col_a.metric("Leads Found", len(folders))
    col_b.metric("Renderings", sum(1 for f in folders if (f / "with_landscape_lighting.jpg").exists()))
    if st.session_state.last_run:
        st.markdown(
            f"<small style='color:#8b949e'>Last run: {st.session_state.last_run}</small>",
            unsafe_allow_html=True
        )

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# MAIN CONTENT
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
st.markdown("""
<div style='padding: 8px 0 24px 0;'>
  <h1 style='font-size:32px; font-weight:800; color:#e6edf3; margin:0;'>
    ð¡ Landscape Lighting Lead Generator
  </h1>
  <p style='color:#8b949e; font-size:15px; margin:6px 0 0 0;'>
    Northern Nassau County &amp; Suffolk County, NY &mdash; Homes sold $1.3M+ in the last 2 years
  </p>
</div>
""", unsafe_allow_html=True)

tab_gallery, tab_progress, tab_leads = st.tabs([
    "ð¸ Before / After Gallery",
    "âï¸ Run Progress",
    "ð All Leads",
])

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# TAB 1 â GALLERY
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
with tab_gallery:
    folders = get_result_folders()
    if not folders:
        st.markdown("""
        <div style='text-align:center; padding:60px 0;'>
            <div style='font-size:48px; margin-bottom:16px;'>ð¡</div>
            <h3 style='color:#8b949e;'>No results yet</h3>
            <p style='color:#4a5568;'>Click <strong style='color:#f0b429;'>Run Agent</strong> in the sidebar to start finding homes and generating renderings.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        with st.expander("ð Filter results", expanded=False):
            search_text = st.text_input("Search by address", placeholder="e.g. Huntington, East Hamptonâ¦")
            show_only_rendered = st.checkbox("Show only homes with AI renderings", value=False)

        filtered = folders
        if search_text:
            filtered = [f for f in filtered if search_text.lower() in f.name.lower()]
        if show_only_rendered:
            filtered = [f for f in filtered if (f / "with_landscape_lighting.jpg").exists()]

        st.markdown(
            f"<p style='color:#8b949e; font-size:13px;'>Showing {len(filtered)} of {len(folders)} properties</p>",
            unsafe_allow_html=True
        )

        for folder in filtered:
            info        = read_property_info(folder)
            address     = info.get("Address",   folder.name)
            price       = info.get("Sale Price","N/A")
            sold_date   = info.get("Sold Date", "")
            redfin_url  = info.get("Redfin URL", info.get("Zillow URL", ""))
            beds        = info.get("Bedrooms",  "")
            baths       = info.get("Bathrooms", "")
            sqft        = info.get("Sq Ft",     "")

            meta_parts = []
            if beds  and beds  != "NA": meta_parts.append(f"ð {beds} bd")
            if baths and baths != "NA": meta_parts.append(f"ð¿ {baths} ba")
            if sqft  and sqft  != "NA": meta_parts.append(f"ð {sqft} sq ft")
            if sold_date:               meta_parts.append(f"ð Sold {sold_date}")
            meta_html  = " Â· ".join(meta_parts)

            listing_link = (
                f"<a href='{redfin_url}' target='_blank' style='color:#f0b429; font-size:12px;'>View listing â</a>"
                if redfin_url and redfin_url != "N/A" else ""
            )

            st.markdown(f"""
            <div class='property-card'>
              <div class='property-card-header'>
                <div style='display:flex; justify-content:space-between; align-items:start;'>
                  <p class='property-address'>{address}</p>
                  <span class='price-badge'>{price}</span>
                </div>
                <div class='property-meta'>
                  {meta_html}
                  {("Â· " + listing_link) if listing_link else ""}
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            orig_path   = folder / "original.jpg"
            render_path = folder / "with_landscape_lighting.jpg"
            col1, col2  = st.columns(2)

            with col1:
                st.markdown("<p class='photo-label label-before'>ð· Original Photo</p>", unsafe_allow_html=True)
                if orig_path.exists():
                    st.image(str(orig_path), use_container_width=True)
                else:
                    st.markdown("<div style='background:#1c2132; height:200px; border-radius:8px; display:flex; align-items:center; justify-content:center; color:#4a5568;'>No photo</div>", unsafe_allow_html=True)

            with col2:
                st.markdown("<p class='photo-label label-after'>ð¡ With Landscape Lighting (AI)</p>", unsafe_allow_html=True)
                if render_path.exists():
                    st.image(str(render_path), use_container_width=True)
                else:
                    st.markdown("<div style='background:#1c2132; height:200px; border-radius:8px; display:flex; align-items:center; justify-content:center; color:#4a5568; border: 1px dashed #2a3040;'>â³ Rendering pending</div>", unsafe_allow_html=True)

            dl_col1, dl_col2, _ = st.columns([1, 1, 3])
            if orig_path.exists():
                with open(orig_path, "rb") as f:
                    dl_col1.download_button("â¬ Original", data=f.read(),
                        file_name=f"{folder.name}_original.jpg", mime="image/jpeg",
                        key=f"dl_orig_{folder.name}")
            if render_path.exists():
                with open(render_path, "rb") as f:
                    dl_col2.download_button("â¬ Rendering", data=f.read(),
                        file_name=f"{folder.name}_landscape_lighting.jpg", mime="image/jpeg",
                        key=f"dl_render_{folder.name}")

            st.markdown("<hr style='margin: 8px 0 20px 0; border-color:#2a3040;'>", unsafe_allow_html=True)

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# TAB 2 â RUN PROGRESS
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
with tab_progress:
    if st.session_state.running:
        st.markdown(
            "<div style='display:flex; align-items:center; gap:10px; margin-bottom:16px;'>"
            "<div style='width:12px; height:12px; background:#f0b429; border-radius:50%; "
            "animation:pulse 1.5s infinite;'></div>"
            "<span style='color:#f0b429; font-weight:600;'>Agent is runningâ¦</span></div>"
            "<style>@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }</style>",
            unsafe_allow_html=True
        )
        # Auto-refresh every 2 seconds while running
        time.sleep(2)
        st.rerun()
    elif st.session_state.run_complete:
        st.success("â Agent run complete!")
    elif not st.session_state.run_logs:
        st.markdown("""
        <div style='text-align:center; padding:60px 0;'>
            <div style='font-size:48px; margin-bottom:16px;'>âï¸</div>
            <h3 style='color:#8b949e;'>No runs yet</h3>
            <p style='color:#4a5568;'>Click <strong style='color:#f0b429;'>Run Agent</strong> in the sidebar to start.</p>
        </div>
        """, unsafe_allow_html=True)

    if st.session_state.run_logs:
        log_text = "\n".join(st.session_state.run_logs[-200:])
        st.code(log_text, language=None)
        if st.button("ð Clear Log"):
            st.session_state.run_logs = []
            st.rerun()

    log_files = sorted(LEADS_DIR.glob("run_*.log"), reverse=True)
    if log_files:
        st.markdown("---")
        st.markdown("**Previous Run Logs**")
        selected_log = st.selectbox("Select a log file", options=log_files,
            format_func=lambda p: p.name, label_visibility="collapsed")
        if selected_log:
            with st.expander(f"ð {selected_log.name}", expanded=False):
                try:
                    st.code(selected_log.read_text()[-5000:], language=None)
                except Exception:
                    st.warning("Could not read log file")

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# TAB 3 â ALL LEADS TABLE
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
with tab_leads:
    leads   = load_leads()
    folders = get_result_folders()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Leads Found",   len(leads))
    m2.metric("Renderings Created",  sum(1 for f in folders if (f / "with_landscape_lighting.jpg").exists()))
    m3.metric("Photos Downloaded",   len(folders))
    m4.metric("Pending Processing",  max(0, len(leads) - len(get_completed_addresses())))
    st.markdown("---")

    if not leads:
        st.info("No lead data yet. Run the agent to start collecting properties.")
    else:
        import pandas as pd
        rows = []
        for lead in leads:
            addr   = lead.get("address", "")
            folder = LEADS_DIR / addr[:120]
            has_photo     = (folder / "original.jpg").exists()              if folder.exists() else False
            has_rendering = (folder / "with_landscape_lighting.jpg").exists() if folder.exists() else False
            rows.append({
                "Address":    addr,
                "Sale Price": f"${lead.get('price', 0):,}",
                "Sold Date":  lead.get("sold_date", ""),
                "Beds":       lead.get("beds",  ""),
                "Baths":      lead.get("baths", ""),
                "Sq Ft":      lead.get("sqft",  ""),
                "Photo":      "â" if has_photo     else "â³",
                "Rendering":  "â" if has_rendering else "â³",
            })
        df = pd.DataFrame(rows)

        price_filter = st.text_input("Filter by address or area", placeholder="e.g. Huntingtonâ¦")
        if price_filter:
            df = df[df["Address"].str.contains(price_filter, case=False)]

        st.dataframe(df, use_container_width=True, hide_index=True)

        csv = df.to_csv(index=False)
        st.download_button(
            "â¬ Download as CSV",
            data=csv,
            file_name=f"landscape_leads_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# FOOTER
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
st.markdown("---")
st.markdown(
    "<p style='text-align:center; color:#4a5568; font-size:12px;'>"
    "ð¡ Landscape Lighting Lead Generator &bull; "
    "Northern Nassau &amp; Suffolk County, NY &bull; "
    "Powered by Redfin, OpenAI GPT-4o &amp; DALL-E 3"
    "</p>",
    unsafe_allow_html=True
)

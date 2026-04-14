"""
app.py — MathMind 2.0 · Final Ship Build
==========================================
Zero raw-HTML artifacts. Zero text-color leakage. Zero spatial drift.

Architecture:
  1. box-sizing: border-box on * — absolute containment
  2. [35:65] rigid flex split with align-items: flex-start
  3. Dual-axis rulers (Top + Left) on every bento card
  4. Breathing LED (opacity 0.4→1.0) for pipeline status
  5. X/Y axis labels on the blueprint grid background
  6. Layered-opacity CSS variables with hardcoded contrast:
     • Light: grid #E2E8F0, text #0F172A, card #FFFFFF
     • Dark: bg #0B0E14, code-bg rgba(0,0,0,0.3), grid 8%
  7. All solution blocks built as single atomic HTML strings
  8. ENGINE_SPECS expander with padding isolation
  9. File uploader in a dashed blueprint input zone
 10. 100% text-color compliance — no element escapes --text-main
"""

import streamlit as st
import requests
import base64
import io
from PIL import Image

# ── Page Config (MUST be first st call) ───────────────────────────────────────
st.set_page_config(
    page_title="MathMind 2.0",
    page_icon="⊿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Session State ─────────────────────────────────────────────────────────────
for _k, _d in {
    "theme": "dark",
    "api_data": None,
    "image_cache": None,
    "last_processed": None,
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _d


def toggle_theme():
    st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"


# ══════════════════════════════════════════════════════════════════════════════
# THEME ENGINE
# ══════════════════════════════════════════════════════════════════════════════

THEMES = {
    "dark": {
        "--bg-color":       "#0B0E14",
        "--bg-elevated":    "#161B22",
        "--grid-color":     "rgba(88, 166, 255, 0.08)",
        "--card-bg":        "rgba(22, 27, 34, 0.82)",
        "--card-bg-solid":  "#161B22",
        "--border-color":   "#30363D",
        "--border-hover":   "#484F58",
        "--text-main":      "#E6EDF3",
        "--text-secondary": "#B1BAC4",
        "--text-muted":     "#8B949E",
        "--text-dim":       "#484F58",
        "--accent":         "#58A6FF",
        "--accent-glow":    "rgba(88, 166, 255, 0.20)",
        "--accent-subtle":  "rgba(88, 166, 255, 0.08)",
        "--success":        "#3FB950",
        "--warning":        "#D29922",
        "--error":          "#F85149",
        "--ruler-opacity":  "0.45",
        "--img-well-bg":    "rgba(0, 0, 0, 0.25)",
        "--code-bg":        "rgba(0, 0, 0, 0.3)",
        "--shadow":         "0 8px 24px rgba(0, 0, 0, 0.45)",
        "--glow-ring":      "0 0 0 1px rgba(88, 166, 255, 0.06)",
        "--axis-label":     "rgba(88, 166, 255, 0.18)",
    },
    "light": {
        "--bg-color":       "#F0F3F6",
        "--bg-elevated":    "#FFFFFF",
        "--grid-color":     "#E2E8F0",
        "--card-bg":        "rgba(255, 255, 255, 0.96)",
        "--card-bg-solid":  "#FFFFFF",
        "--border-color":   "#D0D7DE",
        "--border-hover":   "#AFB8C1",
        "--text-main":      "#0F172A",
        "--text-secondary": "#334155",
        "--text-muted":     "#64748B",
        "--text-dim":       "#94A3B8",
        "--accent":         "#0969DA",
        "--accent-glow":    "rgba(9, 105, 218, 0.12)",
        "--accent-subtle":  "rgba(9, 105, 218, 0.05)",
        "--success":        "#1A7F37",
        "--warning":        "#9A6700",
        "--error":          "#CF222E",
        "--ruler-opacity":  "0.30",
        "--img-well-bg":    "rgba(0, 0, 0, 0.025)",
        "--code-bg":        "rgba(175, 184, 193, 0.15)",
        "--shadow":         "0 4px 16px rgba(140, 149, 159, 0.12)",
        "--glow-ring":      "0 0 0 1px rgba(9, 105, 218, 0.04)",
        "--axis-label":     "rgba(9, 105, 218, 0.15)",
    },
}

_palette = THEMES[st.session_state.theme]
_css_vars = "\n".join(f"    {k}: {v};" for k, v in _palette.items())


# ══════════════════════════════════════════════════════════════════════════════
# SINGLE <style> BLOCK — Zero hardcoded colors in any HTML below.
# ══════════════════════════════════════════════════════════════════════════════

st.markdown(f"""
<style>
/* ═══ FONTS ═══════════════════════════════════════════════════════════════ */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:ital,wght@0,400;0,500;0,600;1,400&display=swap');

/* ═══ CSS VARIABLES ═══════════════════════════════════════════════════════ */
:root {{
{_css_vars}
    --font-ui: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --font-mono: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;
    --radius: 14px;
    --radius-sm: 8px;
    --ease-fluid: cubic-bezier(0.22, 1, 0.36, 1);
    --morph: all 0.6s cubic-bezier(0.22, 1, 0.36, 1);
    --card-gap: 20px;
}}

/* ═══ GLOBAL RESET ════════════════════════════════════════════════════════ */
*, *::before, *::after {{ box-sizing: border-box !important; }}

/* ═══ APP SHELL + BLUEPRINT GRID ══════════════════════════════════════════ */
.stApp {{
    background-color: var(--bg-color) !important;
    background-image:
        linear-gradient(var(--grid-color) 1px, transparent 1px),
        linear-gradient(90deg, var(--grid-color) 1px, transparent 1px);
    background-size: 50px 50px;
    background-attachment: fixed;
    font-family: var(--font-ui);
    transition: background-color 0.6s var(--ease-fluid),
                background-image 0.6s var(--ease-fluid);
}}

/* ═══ 100% TEXT-COLOR COMPLIANCE ══════════════════════════════════════════ */
html, body,
h1, h2, h3, h4, h5, h6,
p, span, label, li, td, th, div, a, strong, em, b, i, small,
.stMarkdown, .stMarkdown p, .stMarkdown span, .stMarkdown li,
.stMarkdown div, .stMarkdown strong, .stMarkdown em,
.stTextInput label, .stSelectbox label,
.stFileUploader label, .stFileUploader span, .stFileUploader p,
.stFileUploader small, .stFileUploader div,
[data-testid="stMetricValue"],
[data-testid="stMetricLabel"],
[data-testid="stMetricDelta"],
[data-testid="stExpanderToggleIcon"],
[data-testid="stWidgetLabel"],
[data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] span,
.stExpander summary, .stExpander summary span,
.stExpander summary p, .stExpander summary div,
.stAlert p, .stAlert div {{
    color: var(--text-main) !important;
    font-family: var(--font-ui);
    transition: color 0.3s ease;
}}

/* ═══ HIDE STREAMLIT CHROME ═══════════════════════════════════════════════ */
#MainMenu, footer, header, [data-testid="stToolbar"] {{
    visibility: hidden !important; height: 0 !important; overflow: hidden !important;
}}
.block-container {{
    padding: 1.5rem 3.5rem 4rem 3.5rem;
    max-width: 1640px;
}}

/* ═══ SCROLLBAR ═══════════════════════════════════════════════════════════ */
::-webkit-scrollbar {{ width: 5px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: var(--border-color); border-radius: 3px; }}

/* ═════════════════════════════════════════════════════════════════════════
   BENTO CARD — Glassmorphism + Dual-Axis Rulers (Top + Left)
   ═════════════════════════════════════════════════════════════════════════ */
.bento {{
    background: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: 24px 28px;
    backdrop-filter: blur(18px);
    -webkit-backdrop-filter: blur(18px);
    box-shadow: var(--shadow);
    position: relative;
    margin-bottom: var(--card-gap);
    overflow: hidden;
    transition: border-color 0.6s var(--ease-fluid),
                box-shadow 0.6s var(--ease-fluid),
                transform 0.6s var(--ease-fluid),
                background-image 0.6s var(--ease-fluid),
                background-color 0.6s var(--ease-fluid);
}}
/* HOVER: Corner Glow (blooms slowly) + Ruler Brighten + Lift */
.bento:hover {{
    border-color: var(--border-hover);
    box-shadow: var(--shadow), var(--glow-ring);
    transform: scale(1.01);
    background-image: radial-gradient(
        ellipse 140px 140px at 0% 0%,
        var(--accent-glow), transparent 70%
    );
}}
.bento:hover::before,
.bento:hover::after {{
    opacity: 1.0;
}}

/* RULER: Y-axis (vertical, top-left) */
.bento::before {{
    content: "";
    position: absolute; top: 0; left: 0;
    width: 2px; height: 80px;
    opacity: 0.3;
    background: repeating-linear-gradient(180deg,
        var(--accent) 0px, var(--accent) 1px,
        transparent 1px, transparent 6px);
    pointer-events: none;
    transition: opacity 0.8s var(--ease-fluid);
}}
/* RULER: X-axis (horizontal, top-left) */
.bento::after {{
    content: "";
    position: absolute; top: 0; left: 0;
    width: 80px; height: 2px;
    opacity: 0.3;
    background: repeating-linear-gradient(90deg,
        var(--accent) 0px, var(--accent) 1px,
        transparent 1px, transparent 6px);
    pointer-events: none;
    transition: opacity 0.8s var(--ease-fluid);
}}

/* ═══ CARD LABEL ══════════════════════════════════════════════════════════ */
.lbl {{
    font-family: var(--font-mono);
    font-size: 0.62rem;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--accent) !important;
    margin: 0 0 14px 0;
    padding-left: 14px;
    border-left: 2px solid var(--accent);
    line-height: 1;
}}

/* ═══ IMAGE WELL ══════════════════════════════════════════════════════════ */
.img-well {{
    display: flex; justify-content: center; align-items: center;
    background: var(--img-well-bg);
    border: 1px dashed var(--border-color);
    border-radius: var(--radius-sm);
    padding: 14px;
    min-height: 200px;
    overflow: hidden;
}}
.img-well img {{
    max-width: 100%; max-height: 380px;
    width: auto; height: auto;
    border-radius: 6px;
    border: 1px solid var(--border-color);
    object-fit: contain;
    display: block;
}}

/* ═══ LATEX CENTER ════════════════════════════════════════════════════════ */
.latex-wrap {{
    display: flex; justify-content: center; align-items: flex-start;
    overflow-x: auto;
    margin-top: -24px;
    padding: 0 4px 4px 4px;
}}
.latex-wrap .katex-display {{ margin: 0 !important; }}
.latex-wrap .katex {{ color: var(--text-main) !important; }}

/* ═══ TELEMETRY ═══════════════════════════════════════════════════════════ */
.t-row {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid var(--border-color);
}}
.t-row:last-of-type {{ border-bottom: none; }}
.t-key {{
    font-family: var(--font-mono); font-size: 0.70rem;
    font-weight: 500; letter-spacing: 0.08em;
    color: var(--text-muted) !important;
}}
.t-val {{
    font-family: var(--font-mono); font-size: 0.82rem;
    font-weight: 600; color: var(--text-main) !important;
}}
.t-val.hi {{ color: var(--accent) !important; }}

/* ═══ CONFIDENCE BAR ══════════════════════════════════════════════════════ */
.conf-track {{
    width: 100%; height: 4px;
    background: var(--border-color);
    border-radius: 2px; margin-top: 8px; overflow: hidden;
}}
.conf-fill {{
    height: 100%; border-radius: 2px;
    transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
}}

/* ═══ SOLUTION BLOCK ══════════════════════════════════════════════════════ */
.sol-block {{
    margin-top: 12px; padding: 18px 22px;
    border-left: 3px solid var(--accent);
    background: var(--accent-subtle);
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}}
.sol-block.identity-block {{
    border-left-color: var(--success);
    background: rgba(63, 185, 80, 0.05);
}}
.sol-target {{
    font-family: var(--font-mono); font-size: 0.62rem;
    letter-spacing: 0.06em; color: var(--text-dim) !important;
    margin: 0 0 6px 0; word-break: break-all;
}}
.sol-val {{
    font-family: var(--font-mono); font-size: 1.9rem;
    font-weight: 700; color: var(--text-main) !important;
    line-height: 1.25; margin: 4px 0;
}}

/* Status pills — used in both Resolution cards and ENGINE_SPECS */
.pill {{
    display: inline-block;
    padding: 3px 12px; border-radius: 12px;
    font-family: var(--font-mono); font-size: 0.60rem;
    font-weight: 600; letter-spacing: 0.05em;
    vertical-align: middle;
}}
.pill-solved   {{ background: rgba(88,166,255,0.12); color: var(--accent) !important; }}
.pill-identity {{ background: rgba(63,185,80,0.10);  color: var(--success) !important; }}
.pill-parsed   {{ background: rgba(210,153,34,0.10); color: var(--warning) !important; }}
.pill-error    {{ background: rgba(248,81,73,0.10);  color: var(--error) !important; }}
.pill-failed   {{ background: rgba(110,118,129,0.10); color: var(--text-dim) !important; }}

/* ═══ IDENTITY BADGE ══════════════════════════════════════════════════════ */
.id-badge {{
    display: inline-flex; align-items: center; gap: 6px;
    padding: 5px 14px;
    background: rgba(63, 185, 80, 0.08);
    border: 1px solid rgba(63, 185, 80, 0.25);
    border-radius: 20px;
    font-family: var(--font-mono); font-size: 0.68rem;
    font-weight: 600; color: var(--success) !important;
    margin-top: 6px;
}}

/* ═══ TIMEOUT BANNER ══════════════════════════════════════════════════════ */
.t-warn {{
    padding: 12px 18px;
    background: rgba(210, 153, 34, 0.07);
    border: 1px solid rgba(210, 153, 34, 0.25);
    border-radius: var(--radius-sm);
    font-family: var(--font-mono); font-size: 0.75rem;
    color: var(--warning) !important;
    margin-top: 10px;
    display: flex; align-items: center; gap: 10px;
}}

/* ═══ EMPTY STATE ═════════════════════════════════════════════════════════ */
.void {{ text-align: center; padding: 50px 16px; }}
.void-icon {{ font-size: 2.5rem; margin-bottom: 14px; opacity: 0.25; }}
.void-text {{
    font-family: var(--font-mono); font-size: 0.78rem;
    color: var(--text-dim) !important; letter-spacing: 0.08em;
}}

/* ═══ STATUS LED — Organic Breathing (Opacity + Scale) ══════════════════════ */
@keyframes breathe {{
    0%, 100% {{
        opacity: 0.4;
        transform: scale(0.95);
        box-shadow: 0 0 0 0 rgba(16,185,129, 0.45);
    }}
    50% {{
        opacity: 1.0;
        transform: scale(1.05);
        box-shadow: 0 0 0 6px rgba(16,185,129, 0);
    }}
}}
.led {{
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    margin-right: 8px;
    vertical-align: middle;
    flex-shrink: 0;
    will-change: transform, opacity;
}}
.led.on  {{ background: #10B981; animation: breathe 2.4s ease-in-out infinite; }}
.led.off {{ background: var(--text-dim); opacity: 0.5; }}

/* ═══ NAV BAR ═════════════════════════════════════════════════════════════ */
.nav-bar {{
    display: flex; align-items: center; justify-content: space-between;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 14px;
}}

/* ── "Titan" Signature Title: 3.2rem Stencil + Sinusoidal Pulse ───────── */
@keyframes title-scan {{
    0%   {{ left: -30%; opacity: 0; }}
    15%  {{ opacity: 1; }}
    85%  {{ opacity: 1; }}
    100% {{ left: 130%; opacity: 0; }}
}}
.nav-title {{
    font-size: 2.5rem !important;
    font-weight: 700;
    letter-spacing: 2px;
    margin: 0;
    line-height: 1.15;
    position: relative;
    display: inline-block;
    background: linear-gradient(135deg, var(--accent), var(--text-main), var(--accent));
    background-size: 200% 200%;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    transition: var(--morph);
    cursor: default;
}}
/* Hover: accent wash + deep diffused glow */
.nav-title:hover {{
    background: var(--accent);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 24px var(--accent-glow))
            drop-shadow(0 0 48px var(--accent-glow));
}}
/* Scanning pulse: sinusoidal fade in/out */
.nav-title::before {{
    content: "";
    position: absolute;
    top: 0; left: -30%;
    width: 20%; height: 100%;
    background: linear-gradient(90deg, transparent, var(--accent-glow), transparent);
    animation: title-scan 5s cubic-bezier(0.45, 0.05, 0.55, 0.95) infinite;
    pointer-events: none;
}}

.nav-sub {{
    font-family: var(--font-mono); font-size: 0.68rem;
    letter-spacing: 0.12em; color: var(--text-dim) !important;
    margin: 2px 0 0 0;
}}
.nav-led-group {{
    display: flex; align-items: center;
    font-family: var(--font-mono); font-size: 0.65rem;
    letter-spacing: 0.08em; color: var(--text-muted) !important;
    white-space: nowrap;
}}

/* ═══ X / Y AXIS LABELS (Blueprint Background Embellishment) ═════════════ */
.axis-labels {{
    position: fixed; top: 0; left: 0;
    width: 100%; height: 100%;
    pointer-events: none;
    z-index: 0;
}}
.axis-y {{
    position: absolute; top: 60px; left: 12px;
    font-family: var(--font-mono); font-size: 0.55rem;
    letter-spacing: 0.15em;
    color: var(--axis-label); transform: rotate(-90deg);
    transform-origin: top left;
}}
.axis-x {{
    position: absolute; bottom: 12px; left: 60px;
    font-family: var(--font-mono); font-size: 0.55rem;
    letter-spacing: 0.15em;
    color: var(--axis-label);
}}

/* ═══ FILE UPLOADER ═══════════════════════════════════════════════════════ */
[data-testid="stFileUploader"] {{
    border: 2px dashed var(--border-color) !important;
    border-radius: var(--radius) !important;
    background: var(--card-bg-solid) !important;
    padding: 16px !important;
    transition: var(--morph);
}}
[data-testid="stFileUploader"]:hover {{
    border-color: var(--accent) !important;
}}
/* FIX: Eradicate Light Mode black box — every nested layer forced transparent */
[data-testid="stFileUploader"] section,
[data-testid="stFileUploader"] section > div,
[data-testid="stFileUploader"] section > div > div {{
    background: transparent !important;
    background-color: transparent !important;
    color: var(--text-main) !important;
}}
[data-testid="stFileUploader"] div,
[data-testid="stFileUploader"] section div,
[data-testid="stFileUploader"] section span,
[data-testid="stFileUploader"] section p,
[data-testid="stFileUploader"] section small,
[data-testid="stFileUploader"] section label,
[data-testid="stFileUploader"] section input {{
    color: var(--text-main) !important;
    background-color: transparent !important;
}}
[data-testid="stFileUploader"] button {{
    color: var(--accent) !important;
    background-color: transparent !important;
}}

/* ═══ THEME TOGGLE ════════════════════════════════════════════════════════ */
.stButton > button {{
    background: var(--card-bg) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text-main) !important;
    font-size: 1.15rem; padding: 6px 10px !important;
    transition: var(--morph); cursor: pointer;
    min-height: unset !important;
}}
.stButton > button:hover {{
    border-color: var(--accent) !important;
    box-shadow: 0 0 14px var(--accent-glow);
}}
.stButton > button:active, .stButton > button:focus {{
    border-color: var(--accent) !important;
    box-shadow: none !important; outline: none !important;
}}

/* ═══ EXPANDER — ENGINE_SPECS (Color-Bleed Purge) ════════════════════════ */
/* Outer wrapper: solid bg in both themes, never inherits dark fallback */
.stExpander,
[data-testid="stExpander"] {{
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius) !important;
    background: var(--card-bg-solid) !important;
    background-color: var(--card-bg-solid) !important;
    transition: var(--morph);
}}
/* Details container: also pinned to solid bg */
.stExpander > details,
[data-testid="stExpander"] > details {{
    padding: 0 !important;
    background: var(--card-bg-solid) !important;
    background-color: var(--card-bg-solid) !important;
    color: var(--text-main) !important;
}}
/* ICON ERADICATION: Only text remains */
.stExpander summary span[data-testid="stIconMaterial"],
.stExpander details summary svg,
.stExpander details summary [data-testid="stExpanderToggleIcon"] {{
    display: none !important;
}}
/* Summary bar: explicit bg, color, font — no inheritance from Streamlit */
.stExpander details summary,
[data-testid="stExpander"] details summary {{
    font-family: var(--font-mono) !important;
    font-size: 0.76rem !important;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-main) !important;
    background-color: var(--card-bg-solid) !important;
    padding: 12px 20px !important;
    margin: 0 !important;
}}
/* Contrast guardrail: every text node in summary */
.stExpander summary p,
.stExpander summary span,
.stExpander summary div {{
    color: var(--text-main) !important;
    font-family: var(--font-mono) !important;
    background-color: transparent !important;
}}
/* Inner content area */
.stExpander > details > div {{
    padding: 10px 20px 16px 20px !important;
    background-color: var(--card-bg-solid) !important;
    color: var(--text-main) !important;
}}
/* All text inside expander body */
.stExpander > details > div p,
.stExpander > details > div span,
.stExpander > details > div div,
.stExpander > details > div label,
.stExpander > details > div li {{
    color: var(--text-main) !important;
}}
/* Open state */
.stExpander[open], .stExpander > details[open],
[data-testid="stExpander"][open] {{
    border-color: var(--border-hover) !important;
}}
.stCodeBlock {{
    background: var(--code-bg) !important;
    border-radius: var(--radius-sm) !important;
    border: 1px solid var(--border-color) !important;
    margin-bottom: 12px !important;
}}
pre, code, .stCodeBlock code {{
    font-family: var(--font-mono) !important;
    font-size: 0.74rem !important;
    color: var(--text-main) !important;
    background: transparent !important;
}}

/* ═══ COLUMNS — Top-Aligned, Fixed Gap ════════════════════════════════════ */
[data-testid="stHorizontalBlock"] {{
    align-items: flex-start !important;
    gap: var(--card-gap) !important;
}}

/* ═══ GLOBAL WIDGET CONTRAST GUARDRAIL ════════════════════════════════════ */
/* Prevents color-leakage: widgets always use the solid card background.   */
.stExpander,
[data-testid="stFileUploader"],
.stMarkdown {{
    background-color: transparent !important;
}}
.stExpander > details,
[data-testid="stFileUploader"] > div {{
    background-color: var(--card-bg-solid) !important;
}}

/* ═══ SPINNER ═════════════════════════════════════════════════════════════ */
.stSpinner > div {{ border-top-color: var(--accent) !important; }}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# X / Y AXIS LABELS — Blueprint grid annotation
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("""
    <div class='axis-labels'>
        <span class='axis-y'>Y — AXIS</span>
        <span class='axis-x'>X — AXIS</span>
    </div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — NAVIGATION
# ══════════════════════════════════════════════════════════════════════════════

_resolved = st.session_state.api_data is not None
_led = "on" if _resolved else "off"
_status = "PIPELINE RESOLVED" if _resolved else "AWAITING INPUT"

_nav_l, _nav_r = st.columns([9, 1])
with _nav_l:
    st.markdown(f"""
        <div class='nav-bar'>
            <div>
                <p class='nav-title'>MathMind <span style='color:var(--accent);'>2.0</span></p>
                <p class='nav-sub'>// NEURO-SYMBOLIC RESOLUTION ENGINE</p>
            </div>
            <div class='nav-led-group'>
                <span class='led {_led}'></span>
                {_status}
            </div>
        </div>
    """, unsafe_allow_html=True)
with _nav_r:
    st.button(
        "☀️" if st.session_state.theme == "dark" else "🌙",
        on_click=toggle_theme,
        use_container_width=True,
        key="theme_toggle",
    )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — FILE UPLOAD
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
uploaded_file = st.file_uploader(
    "DROP MATHEMATICAL INPUT — PNG / JPG / WEBP",
    type=["png", "jpg", "jpeg", "webp"],
    label_visibility="collapsed",
    key="uploader",
)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — API DISPATCH (fires ONCE per unique filename)
# ══════════════════════════════════════════════════════════════════════════════

if uploaded_file is not None:
    _fname = uploaded_file.name
    if st.session_state.last_processed != _fname:
        with st.spinner("⟳  Dispatching to MathMind pipeline …"):
            try:
                _raw = uploaded_file.getvalue()
                _resp = requests.post(
                    "http://localhost:8000/api/v1/solve",
                    files={"file": (_fname, _raw, uploaded_file.type)},
                    data={"input_type": "auto", "verify": "true"},
                    timeout=90,
                )
                _resp.raise_for_status()
                _payload = _resp.json()

                if _payload.get("success"):
                    st.session_state.api_data = _payload
                    st.session_state.last_processed = _fname
                    _img = Image.open(io.BytesIO(_raw))
                    _buf = io.BytesIO()
                    _img.save(_buf, format="PNG")
                    st.session_state.image_cache = base64.b64encode(
                        _buf.getvalue()
                    ).decode()
                    st.rerun()
                else:
                    st.error(f"Pipeline error: {_payload.get('error', 'Unknown')}")
            except requests.ConnectionError:
                st.error("⚠  Backend offline — run FastAPI on :8000")
            except requests.Timeout:
                st.error("⚠  Request timed out (90 s limit)")
            except Exception as _exc:
                st.error(f"⚠  {_exc}")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — BENTO GRID (Results)
# ══════════════════════════════════════════════════════════════════════════════

_show = (
    st.session_state.api_data is not None
    and st.session_state.last_processed is not None
    and st.session_state.last_processed == getattr(uploaded_file, "name", None)
)

if _show:
    data = st.session_state.api_data
    v = data.get("verification")
    api_err = data.get("error")

    # ── Helper: escape LaTeX for safe HTML embedding ──────────────────────
    def _esc(s: str) -> str:
        return (s or "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # ── Helper: map status → pill class ───────────────────────────────────
    def _pill(status: str) -> str:
        s = status.lower()
        cls = {"solved": "pill-solved", "identity": "pill-identity",
               "parsed": "pill-parsed", "error": "pill-error"}.get(s, "pill-failed")
        return f"<span class='pill {cls}'>{status.upper()}</span>"

    # ── [35 : 65] RIGID SPLIT ─────────────────────────────────────────────
    col_L, col_R = st.columns([35, 65], gap="medium")

    # ══════════════════════════════════════════════════════════════════════
    # LEFT COLUMN
    # ══════════════════════════════════════════════════════════════════════
    with col_L:

        # ── CARD 1: FRAGMENT ─────────────────────────────────────────────
        _img_html = ""
        if st.session_state.image_cache:
            _img_html = (
                "<div class='img-well'>"
                f"<img src='data:image/png;base64,{st.session_state.image_cache}'"
                " alt='Source document' />"
                "</div>"
            )
        st.markdown(
            f"<div class='bento' style='min-height:250px;'>"
            f"<div class='lbl'>FRAGMENT_01 · SOURCE DOCUMENT</div>"
            f"{_img_html}"
            f"</div>",
            unsafe_allow_html=True,
        )

        # ── CARD 2: TELEMETRY ────────────────────────────────────────────
        _tok = data.get("tokens_generated", 0)
        _inp = data.get("input_type", "auto").upper()
        _cf  = v["overall_confidence"] if v else 0.0
        _pok = v["parsed_ok"]          if v else 0
        _tot = v["total_equations"]    if v else 0
        _vok = v["verified_ok"]        if v else 0

        if _cf >= 0.75:
            _cc = "var(--success)"
        elif _cf >= 0.4:
            _cc = "var(--warning)"
        else:
            _cc = "var(--error)"

        st.markdown(
            "<div class='bento'>"
            "<div class='lbl'>TELEMETRY_02 · PIPELINE DIAGNOSTICS</div>"
            "<div class='t-row'>"
              "<span class='t-key'>TOKENS_GEN</span>"
              f"<span class='t-val'>{_tok}</span>"
            "</div>"
            "<div class='t-row'>"
              "<span class='t-key'>INPUT_CLASS</span>"
              f"<span class='t-val'>{_inp}</span>"
            "</div>"
            "<div class='t-row'>"
              "<span class='t-key'>EQUATIONS</span>"
              f"<span class='t-val'>{_pok} / {_tot}</span>"
            "</div>"
            "<div class='t-row'>"
              "<span class='t-key'>VERIFIED</span>"
              f"<span class='t-val hi'>{_vok}</span>"
            "</div>"
            "<div class='t-row'>"
              "<span class='t-key'>CONFIDENCE</span>"
              f"<span class='t-val' style='color:{_cc} !important;'>{_cf:.1%}</span>"
            "</div>"
            "<div class='conf-track'>"
              f"<div class='conf-fill' style='width:{_cf*100:.0f}%; background:{_cc};'></div>"
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )

        # ── TIMEOUT BANNER ───────────────────────────────────────────────
        if api_err:
            st.markdown(
                f"<div class='t-warn'><span>⏱️</span> <span>{_esc(api_err)}</span></div>",
                unsafe_allow_html=True,
            )

    # ══════════════════════════════════════════════════════════════════════
    # RIGHT COLUMN
    # ══════════════════════════════════════════════════════════════════════
    with col_R:

        # ── CARD 3: SEMANTICS ────────────────────────────────────────────
        st.markdown(
            "<div class='bento'>"
            "<div class='lbl'>SEMANTICS_03 · SYMBOLIC TRANSCRIPTION</div>",
            unsafe_allow_html=True,
        )
        st.markdown("<div class='latex-wrap'>", unsafe_allow_html=True)
        st.latex(data.get("latex", "\\text{No output}"))
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        # ── CARD 4: RESOLUTION ───────────────────────────────────────────
        st.markdown(
            "<div class='bento'>"
            "<div class='lbl'>RESOLUTION_04 · SYMBOLIC OUTPUT</div>",
            unsafe_allow_html=True,
        )

        _any = False

        if v and v.get("details"):
            for eq in v["details"]:
                _st = eq.get("status", "Failed")
                _raw = _esc(eq.get("raw_latex", ""))

                # ── SOLVED equations ─────────────────────────────────────
                if _st == "Solved" and eq.get("solutions"):
                    _any = True
                    _vals = ""
                    for s in eq["solutions"]:
                        _var  = _esc(s.get("variable", "?"))
                        _vstr = ", ".join(_esc(x) for x in s.get("values", []))
                        _vals += f"<p class='sol-val'>{_var} = {_vstr}</p>"

                    st.markdown(
                        "<div class='sol-block'>"
                        f"<p class='sol-target'>TARGET: {_raw}</p>"
                        f"{_vals}"
                        f"<span class='pill pill-solved' style='margin-top:10px;'>SOLVED</span>"
                        "</div>",
                        unsafe_allow_html=True,
                    )

                # ── IDENTITY equations ───────────────────────────────────
                elif _st == "Identity":
                    _any = True
                    st.markdown(
                        "<div class='sol-block identity-block'>"
                        f"<p class='sol-target'>IDENTITY: {_raw}</p>"
                        "<div class='id-badge'>✓ ALWAYS TRUE</div>"
                        "</div>",
                        unsafe_allow_html=True,
                    )

        if not _any:
            if api_err:
                _void_icon, _void_txt = "⊘", "VERIFICATION TIMED OUT"
            elif v:
                _void_icon, _void_txt = "∅", "NO SOLVABLE EQUATIONS DETECTED"
            else:
                _void_icon, _void_txt = "⊘", "VERIFICATION DATA UNAVAILABLE"

            st.markdown(
                "<div class='void'>"
                f"<div class='void-icon'>{_void_icon}</div>"
                f"<div class='void-text'>{_void_txt}</div>"
                "</div>",
                unsafe_allow_html=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 5 — ENGINE_SPECS EXPANDER
    # ══════════════════════════════════════════════════════════════════════

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    with st.expander("// ENGINE_SPECS — PER-EQUATION AST LOG", expanded=False):
        if v and v.get("details"):
            for i, eq in enumerate(v["details"], 1):
                _s   = eq.get("status", "Failed")
                _raw = eq.get("raw_latex", "—")
                _sym = eq.get("sympy_form") or "—"
                _c   = eq.get("confidence", 0.0)

                # Pill rendered as its own st.markdown call — 100% safe
                st.markdown(_pill(_s), unsafe_allow_html=True)

                st.code(
                    f"EQ_{i:02d}\n"
                    f"├─ INPUT_LATEX  : {_raw}\n"
                    f"├─ SYMPY_AST    : {_sym}\n"
                    f"├─ STATUS       : {_s}\n"
                    f"└─ CONFIDENCE   : {_c:.0%}",
                    language="text",
                )
        else:
            st.markdown(
                "<p style='font-family:var(--font-mono); font-size:0.74rem;"
                " color:var(--text-dim) !important; padding:8px 0;'>"
                "No equation diagnostics available.</p>",
                unsafe_allow_html=True,
            )

else:
    # ══════════════════════════════════════════════════════════════════════
    # EMPTY STATE
    # ══════════════════════════════════════════════════════════════════════
    st.markdown(
        "<div style='text-align:center; padding:100px 20px 60px 20px;'>"
        "<div style='font-size:3.5rem; margin-bottom:20px; opacity:0.15;'>⊿</div>"
        "<p style='font-family:var(--font-mono); font-size:0.85rem;"
        " color:var(--text-dim) !important; letter-spacing:0.12em;'>"
        "UPLOAD A MATHEMATICAL IMAGE TO BEGIN ANALYSIS</p>"
        "<p style='font-family:var(--font-mono); font-size:0.65rem;"
        " color:var(--text-dim) !important; opacity:0.4; margin-top:8px;"
        " letter-spacing:0.10em;'>"
        "FORMATS: PNG · JPG · JPEG · WEBP</p>"
        "</div>",
        unsafe_allow_html=True,
    )
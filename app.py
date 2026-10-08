"""
Exercise Database Selector — Streamlit version
--------------------------------------------------------
- Exercise library stored in a Google Sheet, so it survives app restarts
  and redeploys (e.g. on Streamlit Community Cloud) and is shared by
  everyone using this deployment.
- Anyone can browse, search, filter, tick exercises, set reps, copy the
  final list as text, and add/edit/remove exercises from the sidebar.

Setup (one-time):
    1. Create a Google Sheet. Add a header row to its first worksheet
       (default name "Sheet1") with exactly these columns:
       id | name | category | pattern | regression | progression | equipment | image
       (the "image" column is new — if your Sheet predates it, the app adds
       it automatically the next time it saves.)
    2. Create a Google Cloud service account with Sheets API access,
       download its JSON key.
    3. Share the Google Sheet with the service account's email (found as
       "client_email" inside the downloaded JSON key) — give it Editor access.
    4. Set SPREADSHEET_URL below to your Sheet's URL.
    5. Provide the credentials one of two ways, depending on where you run
       this:

       LOCAL development:
           Save the downloaded JSON key file as service_account.json,
           directly in this same folder, right next to app.py. No
           .streamlit folder needed.

       STREAMLIT COMMUNITY CLOUD:
           Local files aren't available on Streamlit Cloud, so instead go
           to your deployed app → Settings → Secrets, and paste in a
           [gcp_service_account] section with the same fields as the JSON
           key file, e.g.:

               [gcp_service_account]
               type = "service_account"
               project_id = "your-project-id"
               private_key_id = "..."
               private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
               client_email = "your-service-account@your-project.iam.gserviceaccount.com"
               client_id = "..."
               auth_uri = "https://accounts.google.com/o/oauth2/auth"
               token_uri = "https://oauth2.googleapis.com/token"
               auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
               client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com"

           The app checks for this Streamlit secret first, and only falls
           back to the local service_account.json file if it isn't found
           — so the same app.py works in both places unchanged.

Images & QR codes:
    - Exercise photos are shrunk to a small JPEG and stored as text inside
      the Sheet's "image" column (Google Sheets cells hold at most 50,000
      characters, so images are compressed to fit).
    - The Selected panel can export the chosen exercises (text + photos) as
      a PDF, and generate a QR code for it. A QR code can't hold a whole PDF
      (it fits only a few KB), so the QR holds a link instead: set APP_URL
      below (or type it into the QR box in the app) to your deployed app's
      public address. Scanning opens a read-only page listing the exercises
      with a "Download as PDF" button. Without a URL, the QR simply contains
      the plain-text list.

Run locally:
    pip install -r requirements.txt
    streamlit run app.py
"""

import base64
import uuid
from datetime import date
from io import BytesIO
from pathlib import Path

import gspread
import pandas as pd
import qrcode
import streamlit as st
from fpdf import FPDF
from PIL import Image, ImageOps

# --- Fill in your own Google Sheet URL here ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1zDZgeY77XMCTqIAtStlzJwsy_AU_LJO-K4bO-QUe9Ag/edit"
SERVICE_ACCOUNT_FILE = Path(__file__).parent / "service_account.json"
WORKSHEET = "Sheet1"
COLUMNS = ["id", "name", "category", "pattern", "regression", "progression", "equipment", "image"]

# Public address of your deployed app, e.g. "https://your-app.streamlit.app".
# Used to build the QR code link. Leave blank to type it in inside the app.
APP_URL = ""

# Google Sheets cells max out at 50,000 characters; stay safely under that.
MAX_IMAGE_CHARS = 45000

CATEGORY_LABELS = {
    "upper": "Upper Body",
    "lower": "Lower Body",
    "core": "Core",
    "carry": "Carry",
    "full_body": "Full Body Compound",
}
CATEGORY_ICONS = {
    "upper": "💪",
    "lower": "🦵",
    "core": "🧍",
    "carry": "🎒",
    "full_body": "🔥",
}

EQUIPMENT_OPTIONS = ["Bodyweight", "Resistance Band", "Dumbbell", "Kettlebell", "Barbell", "Machine", "Cable"]
EQUIPMENT_COLORS = {
    "Bodyweight": "#6b6b66",
    "Resistance Band": "#2e8b57",
    "Dumbbell": "#3465a4",
    "Kettlebell": "#7b4fa0",
    "Barbell": "#b5651d",
    "Machine": "#1f7a7a",
    "Cable": "#a63b6b",
}

DEFAULT_SEED = [
    ("Push-up", "upper", "Push", "Wall / incline push-up", "Weighted / deficit push-up", "Bodyweight"),
    ("Overhead press (dumbbell)", "upper", "Push", "Seated overhead press", "Standing barbell press", "Dumbbell"),
    ("Seated row (band/machine)", "upper", "Pull", "Band row, light resistance", "Bent-over barbell row", "Resistance Band"),
    ("Assisted pull-up", "upper", "Pull", "Lat pulldown", "Strict pull-up", "Bodyweight"),
    ("Romanian deadlift (dumbbell)", "lower", "Hinge", "Hip hinge with dowel (bodyweight)", "Single-leg RDL", "Dumbbell"),
    ("Split squat", "lower", "Single Leg", "Assisted split squat (hold support)", "Bulgarian split squat / pistol squat", "Bodyweight"),
    ("Squat jump", "lower", "Triple Extension", "Box step-up with arm drive", "Broad jump / hang clean", "Bodyweight"),
    ("Plank", "core", "Core", "Dead bug", "Pallof press / hanging leg raise", "Bodyweight"),
    ("Farmer's carry", "carry", "Carry", "Suitcase carry (single side, light load)", "Overhead carry / uneven load carry", "Dumbbell"),
    ("Dumbbell thruster", "full_body", "Squat-to-Press", "Bodyweight squat to overhead reach (no load)", "Barbell thruster", "Dumbbell"),
    ("Kettlebell swing", "full_body", "Hinge-to-Pull", "Two-hand swing, lighter load", "Single-arm swing / snatch", "Kettlebell"),
    ("Clean and press", "full_body", "Pull-to-Press", "Dumbbell clean and press, light load", "Barbell clean and jerk", "Barbell"),
]


# --------------------------------------------------------------- helpers --
def compress_image(file_bytes):
    """Shrink an uploaded photo into a small JPEG and return it as a base64
    string short enough to fit in a single Google Sheets cell."""
    img = Image.open(BytesIO(file_bytes))
    img = ImageOps.exif_transpose(img)  # respect phone-camera rotation
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, "white")
        background.paste(img, mask=img.split()[-1])
        img = background
    else:
        img = img.convert("RGB")

    max_side = 420
    while max_side >= 120:
        work = img.copy()
        work.thumbnail((max_side, max_side))
        for quality in (80, 70, 60, 50, 40, 30):
            buf = BytesIO()
            work.save(buf, format="JPEG", quality=quality, optimize=True)
            encoded = base64.b64encode(buf.getvalue()).decode("ascii")
            if len(encoded) <= MAX_IMAGE_CHARS:
                return encoded
        max_side = int(max_side * 0.8)
    return ""


def image_bytes(encoded):
    """Decode a stored base64 image, or return None if there isn't one."""
    if not encoded:
        return None
    try:
        return base64.b64decode(encoded)
    except Exception:
        return None


def build_plan_token(selections):
    """Compact, URL-safe description of the current selection.
    Each item is  <first 8 chars of exercise id>.<kind>.<reps>  where kind is
    m (main exercise), r (regression) or p (progression); items joined by '-'."""
    parts = []
    for key, sel in selections.items():
        ex_id, _, suffix = key.partition("::")
        kind = {"": "m", "reg": "r", "prog": "p"}.get(suffix, "m")
        parts.append(f"{ex_id[:8]}.{kind}.{int(sel['reps'])}")
    return "-".join(parts)


def parse_plan_token(token):
    items = []
    for part in token.split("-"):
        short, kind, reps = part.split(".")
        if kind not in ("m", "r", "p"):
            raise ValueError("bad kind")
        items.append((short, kind, int(reps)))
    return items


def make_qr_png(payload):
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def resolve_plan(df, items):
    """Turn parsed plan items into display-ready entries (title, note, reps,
    photo bytes). Returns (entries, number_of_missing_exercises)."""
    entries, missing = [], 0
    for short, kind, reps in items:
        match = df[df["id"].astype(str).str.startswith(short)]
        if match.empty:
            missing += 1
            continue
        row = match.iloc[0]
        if kind == "m":
            title, note, pic = row["name"], "", image_bytes(row["image"])
        elif kind == "r":
            title, note, pic = row["regression"], f"Easier option for {row['name']}", None
        else:
            title, note, pic = row["progression"], f"Harder option for {row['name']}", None
        entries.append({"title": title, "note": note, "reps": reps, "image": pic})
    return entries, missing


def _pdf_text(text):
    """PDF's built-in fonts only cover Latin-1; swap common punctuation for
    plain equivalents and replace anything else so nothing crashes."""
    for old, new in {
        "\u2014": "-", "\u2013": "-", "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"', "\u2022": "-", "\u00b7": "-", "\u2026": "...",
    }.items():
        text = text.replace(old, new)
    return str(text).encode("latin-1", "replace").decode("latin-1")


def build_plan_pdf(entries, title="Exercise plan"):
    """Build a simple PDF: one row per exercise with its photo (if any),
    name, optional note, and reps. Returns the PDF as bytes."""
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 11, _pdf_text(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(130, 130, 130)
    pdf.cell(0, 6, date.today().strftime("%d %b %Y"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    box_w, box_h, gap = 40, 32, 6
    page_w = pdf.w - pdf.l_margin - pdf.r_margin

    for n, e in enumerate(entries, 1):
        img_w = img_h = 0
        if e["image"]:
            try:
                w_px, h_px = Image.open(BytesIO(e["image"])).size
                scale = min(box_w / w_px, box_h / h_px)
                img_w, img_h = w_px * scale, h_px * scale
            except Exception:
                img_w = img_h = 0

        row_h = max(img_h, 22)
        if pdf.get_y() + row_h > pdf.h - pdf.b_margin:
            pdf.add_page()
        y = pdf.get_y()

        text_x = pdf.l_margin
        if img_w:
            pdf.image(BytesIO(e["image"]), x=pdf.l_margin, y=y, w=img_w, h=img_h)
            text_x = pdf.l_margin + box_w + gap
        text_w = pdf.w - pdf.r_margin - text_x

        pdf.set_xy(text_x, y)
        pdf.set_text_color(30, 30, 30)
        pdf.set_font("Helvetica", "B", 13)
        pdf.multi_cell(text_w, 7, _pdf_text(f"{n}. {e['title']}"), new_x="LEFT", new_y="NEXT", align="L")
        if e["note"]:
            pdf.set_x(text_x)
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(130, 130, 130)
            pdf.multi_cell(text_w, 5, _pdf_text(e["note"]), new_x="LEFT", new_y="NEXT", align="L")
        pdf.set_x(text_x)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(138, 109, 59)
        pdf.cell(text_w, 7, _pdf_text(f"{e['reps']} reps"), new_x="LEFT", new_y="NEXT")

        y_end = max(pdf.get_y(), y + img_h) + 4
        pdf.set_draw_color(228, 217, 195)
        pdf.line(pdf.l_margin, y_end, pdf.l_margin + page_w, y_end)
        pdf.set_y(y_end + 4)

    return bytes(pdf.output())


def render_plan_view(df, token):
    """Read-only page that opens when someone scans the QR code."""
    st.title("🏋️ Your exercise plan")
    try:
        items = parse_plan_token(token)
    except Exception:
        st.error("This link doesn't look valid. Ask for a fresh QR code.")
        return
    entries, missing = resolve_plan(df, items)
    if missing:
        st.warning(
            f"{missing} exercise{'s' if missing != 1 else ''} in this plan "
            "no longer exist and were left out."
        )
    if not entries:
        st.info("This plan is empty.")
        return

    st.download_button(
        "📄 Download as PDF", data=build_plan_pdf(entries),
        file_name="exercise-plan.pdf", mime="application/pdf",
        type="primary", use_container_width=True,
    )

    for e in entries:
        with st.container(border=True):
            if e["image"]:
                c_img, c_txt = st.columns([1, 2])
                c_img.image(e["image"], use_container_width=True)
            else:
                c_txt = st.container()
            with c_txt:
                st.markdown(f"### {e['title']}")
                if e["note"]:
                    st.caption(e["note"])
                st.markdown(f"**{e['reps']} reps**")


# ---------------------------------------------------------------- storage --
def _cloud_credentials():
    """Return the [gcp_service_account] secret as a dict, or None if it
    isn't configured. Safe to call even when no secrets.toml exists at all
    (e.g. pure local-file setups) — that case is not an error here."""
    try:
        if "gcp_service_account" in st.secrets:
            return dict(st.secrets["gcp_service_account"])
    except Exception:
        pass
    return None


@st.cache_resource
def get_client():
    creds = _cloud_credentials()
    if creds:
        return gspread.service_account_from_dict(creds)

    if SERVICE_ACCOUNT_FILE.exists():
        return gspread.service_account(filename=str(SERVICE_ACCOUNT_FILE))

    st.error(
        "No Google service account credentials found.\n\n"
        "- **Running locally:** save your service account's JSON key as "
        f"`{SERVICE_ACCOUNT_FILE.name}` next to app.py.\n"
        "- **Running on Streamlit Community Cloud:** add the credentials "
        "under your app's Settings → Secrets as a `[gcp_service_account]` "
        "section (see the setup notes at the top of app.py)."
    )
    st.stop()


@st.cache_resource
def get_worksheet():
    gc = get_client()
    try:
        sh = gc.open_by_url(SPREADSHEET_URL)
    except gspread.exceptions.APIError as e:
        st.error(
            "Couldn't open the Google Sheet. Make sure you've shared it with "
            "the service account's email (the 'client_email' field in your "
            "JSON key or [gcp_service_account] secret) with Editor access.\n\n"
            f"{e}"
        )
        st.stop()
    try:
        return sh.worksheet(WORKSHEET)
    except gspread.exceptions.WorksheetNotFound:
        return sh.sheet1


@st.cache_data(ttl=60, show_spinner=False)
def _read_records():
    """Cached for a minute: every checkbox click re-runs the script, and
    reading the Sheet each time would quickly hit Google's rate limit.
    save_df() clears this cache so your own changes show up immediately."""
    ws = get_worksheet()
    return ws.get_all_records(numericise_ignore=["all"])


def load_df(force=False):
    """Read the exercise sheet as a DataFrame."""
    if force:
        _read_records.clear()
    records = _read_records()
    if not records:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.DataFrame(records)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[COLUMNS].fillna("")
    df["id"] = df["id"].astype(str)
    return df.reset_index(drop=True)


def save_df(df):
    ws = get_worksheet()
    ws.clear()
    values = [COLUMNS] + df[COLUMNS].astype(str).values.tolist()
    ws.update(values)
    _read_records.clear()


def seed_if_empty():
    df = load_df()
    if df.empty:
        seed_rows = [
            {
                "id": str(uuid.uuid4()),
                "name": name, "category": category, "pattern": pattern,
                "regression": regression, "progression": progression, "equipment": equipment,
                "image": "",
            }
            for name, category, pattern, regression, progression, equipment in DEFAULT_SEED
        ]
        df = pd.DataFrame(seed_rows, columns=COLUMNS)
        save_df(df)
    return df


def fetch_exercises(df):
    """Return rows as plain tuples, same shape the rest of the app expects."""
    return list(df[COLUMNS].itertuples(index=False, name=None))


def add_exercise(df, name, category, pattern, regression, progression, equipment, image=""):
    new_row = {
        "id": str(uuid.uuid4()), "name": name, "category": category, "pattern": pattern,
        "regression": regression, "progression": progression, "equipment": equipment,
        "image": image,
    }
    updated = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_df(updated)
    return updated


def update_exercise(df, ex_id, name, category, pattern, regression, progression, equipment, image=None):
    """image=None leaves the stored photo untouched; pass a base64 string to replace it."""
    idx = df.index[df["id"] == ex_id]
    df.loc[idx, ["name", "category", "pattern", "regression", "progression", "equipment"]] = [
        name, category, pattern, regression, progression, equipment,
    ]
    if image:
        df.loc[idx, "image"] = image
    save_df(df)
    return df


def delete_exercise(df, ex_id):
    df = df[df["id"] != ex_id].reset_index(drop=True)
    save_df(df)
    return df


# --------------------------------------------------------------- dialogs --
@st.dialog("Exercise details")
def view_dialog(name, category, pattern, regression, progression, equipment, image=""):
    st.markdown(f"### {name}")
    pic = image_bytes(image)
    if pic:
        st.image(pic, use_container_width=True)
    st.markdown(f"**Category:** {CATEGORY_LABELS.get(category, category)}")
    st.markdown(f"**Movement pattern:** {pattern}")
    st.markdown(f"**Equipment:** {equipment}")
    st.divider()
    st.markdown(f"**Regression:** {regression}")
    st.markdown(f"**Progression:** {progression}")
    if st.button("Close", use_container_width=True):
        st.rerun()


@st.dialog("Edit exercise")
def edit_dialog(df, ex_id, name, category, pattern, regression, progression, equipment, image=""):
    new_name = st.text_input("Exercise name", value=name)
    new_category = st.selectbox(
        "Category",
        options=list(CATEGORY_LABELS.keys()),
        format_func=lambda c: CATEGORY_LABELS[c],
        index=list(CATEGORY_LABELS.keys()).index(category),
    )
    new_pattern = st.text_input("Movement pattern", value=pattern)
    new_equipment = st.selectbox(
        "Equipment",
        options=EQUIPMENT_OPTIONS,
        index=EQUIPMENT_OPTIONS.index(equipment) if equipment in EQUIPMENT_OPTIONS else 0,
    )
    new_regression = st.text_input("Regression", value=regression)
    new_progression = st.text_input("Progression", value=progression)

    current_pic = image_bytes(image)
    if current_pic:
        st.image(current_pic, caption="Current image", width=160)
    new_image_file = st.file_uploader(
        "Replace image (optional)" if current_pic else "Add an image (optional)",
        type=["png", "jpg", "jpeg", "webp"], key=f"edit_img_{ex_id}",
    )

    col1, col2 = st.columns(2)
    if col1.button("Save changes", use_container_width=True):
        if not new_name.strip():
            st.error("Exercise name is required.")
        else:
            new_image_b64 = None
            image_ok = True
            if new_image_file is not None:
                try:
                    new_image_b64 = compress_image(new_image_file.getvalue())
                    if not new_image_b64:
                        raise ValueError("image too large to compress")
                except Exception:
                    image_ok = False
                    st.error("Couldn't process that image. Try a different photo (PNG or JPG).")
            if image_ok:
                update_exercise(
                    df, ex_id, new_name.strip(), new_category,
                    new_pattern.strip() or "—", new_regression.strip() or "—",
                    new_progression.strip() or "—", new_equipment, image=new_image_b64,
                )
                st.session_state.selections.pop(ex_id, None)
                st.rerun()
    if col2.button("Cancel", use_container_width=True):
        st.rerun()


# -------------------------------------------------------------------- app --
st.set_page_config(page_title="Exercise Database Selector", page_icon="🏋️", layout="wide")

all_df = seed_if_empty()

if "selections" not in st.session_state:
    st.session_state.selections = {}  # id -> {"name": str, "reps": int}
if "reset_token" not in st.session_state:
    st.session_state.reset_token = 0  # bumped on "Clear all" to force fresh checkbox widgets

# Someone scanned a QR code: show the read-only plan page instead of the editor.
_plan_token = st.query_params.get("plan")
if _plan_token:
    render_plan_view(all_df, _plan_token)
    st.stop()

st.markdown(
    """
    <style>
    div[data-testid="stHorizontalBlock"] { align-items: center; }
    div.stButton > button {
        display: flex; justify-content: center; align-items: center;
        padding-left: 0; padding-right: 0; border-radius: 8px;
    }
    .cat-header { font-size: 1.05rem; font-weight: 700; color: #8a6d3b;
        border-bottom: 2px solid #e4d9c3; padding-bottom: 6px; margin: 18px 0 14px; }
    .card-title { font-weight: 700; font-size: 1rem; margin-bottom: 0; }
    .card-sub { color: #8a837a; font-size: 0.8rem; margin-bottom: 6px; }
    .card-label { color: #8a837a; font-weight: 600; }
    .card-line { font-size: 0.85rem; margin: 2px 0; }
    .badge {
        display: inline-block; padding: 2px 9px; border-radius: 999px;
        font-size: 0.72rem; font-weight: 700; margin-left: 6px;
    }
    .progress-banner {
        background: #f1e9db; border-radius: 10px; padding: 10px 16px;
        font-weight: 700; color: #8a6d3b; margin: 10px 0 18px; font-size: 0.95rem;
    }
    .rep-value { text-align: center; font-weight: 700; font-size: 0.95rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Exercise Database Selector")
st.caption("Search, filter, and tick exercises for the session. Your picks appear on the right as you go.")

# ------------------------------------------------------------- sidebar --
with st.sidebar:
    st.subheader("Filter by equipment")
    equipment_filter = st.multiselect(
        "Equipment", options=EQUIPMENT_OPTIONS, default=[],
        label_visibility="collapsed", help="Leave empty to show all equipment types.",
    )

    st.divider()
    with st.expander("➕ Add a new exercise", expanded=False):
        with st.form("add_exercise_form", clear_on_submit=True):
            name_in = st.text_input("Exercise name")
            category_in = st.selectbox(
                "Category", options=list(CATEGORY_LABELS.keys()),
                format_func=lambda c: CATEGORY_LABELS[c],
            )
            pattern_in = st.text_input("Movement pattern (e.g. Hinge, Push, Carry)")
            equipment_in = st.selectbox("Equipment", options=EQUIPMENT_OPTIONS)
            regression_in = st.text_input("Regression (easier variation)")
            progression_in = st.text_input("Progression (harder variation)")
            image_in = st.file_uploader(
                "Exercise image (optional)", type=["png", "jpg", "jpeg", "webp"],
            )
            submitted = st.form_submit_button("Add to list", use_container_width=True)
            if submitted:
                if not name_in.strip():
                    st.error("Exercise name is required.")
                else:
                    image_b64 = ""
                    image_ok = True
                    if image_in is not None:
                        try:
                            image_b64 = compress_image(image_in.getvalue())
                            if not image_b64:
                                raise ValueError("image too large to compress")
                        except Exception:
                            image_ok = False
                            st.error("Couldn't process that image. Try a different photo (PNG or JPG).")
                    if image_ok:
                        add_exercise(
                            all_df, name_in.strip(), category_in,
                            pattern_in.strip() or "—", regression_in.strip() or "—",
                            progression_in.strip() or "—", equipment_in, image_b64,
                        )
                        st.success(f"Added '{name_in}'.")
                        st.rerun()

# ------------------------------------------------------------- main area --
all_rows = fetch_exercises(all_df)

PANE_HEIGHT = 640

browse_col, selected_col = st.columns([2, 1])

with browse_col:
    search_term = st.text_input("🔍 Search exercises by name", placeholder="e.g. squat, press, carry")

    if st.button("Clear all selected", use_container_width=False):
        st.session_state.selections = {}
        st.session_state.reset_token += 1
        st.rerun()

    rows = all_rows
    if equipment_filter:
        rows = [r for r in rows if r[6] in equipment_filter]
    if search_term.strip():
        term = search_term.strip().lower()
        rows = [r for r in rows if term in r[1].lower()]

    grouped = {cat: [] for cat in CATEGORY_LABELS}
    for r in rows:
        grouped.setdefault(r[2], []).append(r)

    with st.container(height=PANE_HEIGHT, border=True):
        if not rows:
            st.info("No exercises match your search/filter.")

        CARD_COLS = 2
        for cat, label in CATEGORY_LABELS.items():
            items = grouped.get(cat, [])
            if not items:
                continue
            icon = CATEGORY_ICONS.get(cat, "")
            with st.expander(f"{icon} {label} ({len(items)})", expanded=True):
                for i in range(0, len(items), CARD_COLS):
                    row_items = items[i : i + CARD_COLS]
                    grid = st.columns(CARD_COLS)
                    for col, item in zip(grid, row_items):
                        ex_id, name, category, pattern, regression, progression, equipment, image = item
                        with col:
                            with st.container(border=True):
                                top = st.columns([0.5, 4])
                                chk_key = f"chk_{st.session_state.reset_token}_{ex_id}"
                                checked = top[0].checkbox("", key=chk_key, value=ex_id in st.session_state.selections)
                                color = EQUIPMENT_COLORS.get(equipment, "#6b6b66")
                                with top[1]:
                                    st.markdown(
                                        f'<div class="card-title">{name}{" 📷" if image else ""}</div>',
                                        unsafe_allow_html=True,
                                    )
                                    st.markdown(
                                        f'<div class="card-sub">{pattern}'
                                        f'<span class="badge" style="background:{color}20;color:{color};">{equipment}</span>'
                                        f'</div>',
                                        unsafe_allow_html=True,
                                    )
                                reg_key = f"{ex_id}::reg"
                                prog_key = f"{ex_id}::prog"

                                reg_row = st.columns([0.4, 4])
                                reg_chk_key = f"chkreg_{st.session_state.reset_token}_{ex_id}"
                                reg_checked = reg_row[0].checkbox(
                                    "", key=reg_chk_key, value=reg_key in st.session_state.selections,
                                )
                                reg_row[1].markdown(
                                    f'<div class="card-line"><span class="card-label">Regression:</span> {regression}</div>',
                                    unsafe_allow_html=True,
                                )

                                prog_row = st.columns([0.4, 4])
                                prog_chk_key = f"chkprog_{st.session_state.reset_token}_{ex_id}"
                                prog_checked = prog_row[0].checkbox(
                                    "", key=prog_chk_key, value=prog_key in st.session_state.selections,
                                )
                                prog_row[1].markdown(
                                    f'<div class="card-line"><span class="card-label">Progression:</span> {progression}</div>',
                                    unsafe_allow_html=True,
                                )

                                if reg_checked and reg_key not in st.session_state.selections:
                                    st.session_state.selections[reg_key] = {"name": regression, "reps": 10}
                                elif not reg_checked and reg_key in st.session_state.selections:
                                    st.session_state.selections.pop(reg_key, None)

                                if prog_checked and prog_key not in st.session_state.selections:
                                    st.session_state.selections[prog_key] = {"name": progression, "reps": 10}
                                elif not prog_checked and prog_key in st.session_state.selections:
                                    st.session_state.selections.pop(prog_key, None)

                                btns = st.columns(3)
                                if btns[0].button("👁", key=f"view_{ex_id}", help="View exercise", use_container_width=True):
                                    view_dialog(name, category, pattern, regression, progression, equipment, image)
                                if btns[1].button("✎", key=f"edit_{ex_id}", help="Edit exercise", use_container_width=True):
                                    edit_dialog(all_df, ex_id, name, category, pattern, regression, progression, equipment, image)
                                if btns[2].button("✕", key=f"del_{ex_id}", help="Remove exercise", use_container_width=True):
                                    delete_exercise(all_df, ex_id)
                                    st.session_state.selections.pop(ex_id, None)
                                    st.session_state.selections.pop(reg_key, None)
                                    st.session_state.selections.pop(prog_key, None)
                                    st.rerun()

                                if checked and ex_id not in st.session_state.selections:
                                    st.session_state.selections[ex_id] = {"name": name, "reps": 10}
                                elif not checked and ex_id in st.session_state.selections:
                                    st.session_state.selections.pop(ex_id, None)

with selected_col:
    st.markdown('<div class="cat-header" style="margin-top:0;">Selected exercises</div>', unsafe_allow_html=True)
    n_selected = len(st.session_state.selections)
    st.markdown(
        f'<div class="progress-banner" style="margin-top:0;">✅ {n_selected} exercise{"s" if n_selected != 1 else ""} selected</div>',
        unsafe_allow_html=True,
    )
    with st.container(height=PANE_HEIGHT, border=True):
        if not st.session_state.selections:
            st.caption("None selected yet — tick items on the left.")
        else:
            # Only main exercises (not their regression/progression variants) carry a photo.
            image_by_id = dict(zip(all_df["id"].astype(str), all_df["image"]))

            for sel_key, sel in list(st.session_state.selections.items()):
                pic = None if "::" in sel_key else image_bytes(image_by_id.get(sel_key, ""))
                if pic:
                    r0, r1, r2 = st.columns([1, 2.2, 1.3])
                    r0.image(pic, use_container_width=True)
                else:
                    r1, r2 = st.columns([3.2, 1.3])
                r1.markdown(f"**{sel['name']}**")
                new_reps = r2.number_input(
                    "Reps", min_value=1, step=1, value=int(sel["reps"]),
                    key=f"repnum_{sel_key}", label_visibility="collapsed",
                )
                st.session_state.selections[sel_key]["reps"] = new_reps
                st.markdown("<hr style='margin:6px 0;'>", unsafe_allow_html=True)

            list_text = "\n".join(
                f"{sel['name']} — {sel['reps']} reps" for sel in st.session_state.selections.values()
            )
            st.markdown("**Copy list**")
            st.code(list_text, language=None)

            

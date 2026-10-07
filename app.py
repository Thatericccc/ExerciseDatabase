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
       id | name | category | pattern | regression | progression | equipment
    2. Create a Google Cloud service account with Sheets API access,
       download its JSON key.
    3. Save that downloaded file as service_account.json directly in this
       same folder, right next to app.py. No .streamlit folder needed.
    4. Share the Google Sheet with the service account's email (found as
       "client_email" inside service_account.json) — give it Editor access.
    5. Set SPREADSHEET_URL below to your Sheet's URL.

Run locally:
    pip install -r requirements.txt
    streamlit run app.py
"""

import uuid
from pathlib import Path
import os
import json
import gspread
from google.oauth2 import service_account
import pandas as pd
import streamlit as st

# --- Fill in your own Google Sheet URL here ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1zDZgeY77XMCTqIAtStlzJwsy_AU_LJO-K4bO-QUe9Ag/edit"
SERVICE_ACCOUNT_FILE = os.getenv("GS_SERVICEACC_JSON")
WORKSHEET = "Sheet1"
COLUMNS = ["id", "name", "category", "pattern", "regression", "progression", "equipment"]

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


# ---------------------------------------------------------------- storage --
@st.cache_resource
def get_client():
    if not SERVICE_ACCOUNT_FILE():
          raise ValueError("Environment variable 'GS_SERVICEACC_JSON' is missing or empty.")

    try:
      credentials_info = json.loads (SERVICE_ACCOUNT_FILE)
    except json.JSONDecoderError as e:
      raise ValueError("GS_SERVICEACC_JSON contains JSON format.") from e

    credentials =  service_account.Credentials.from_service_account_info(credentials_info)

    scoped_credentials = credentials.with_scopes([
        "https://googleapis.com",
        "https://googleapis.com"
    ])
        st.stop()
    return gspread.service_account(filename=str(SERVICE_ACCOUNT_FILE))


@st.cache_resource
def get_worksheet():
    gc = get_client()
    try:
        sh = gc.open_by_url(SPREADSHEET_URL)
    except gspread.exceptions.APIError as e:
        st.error(
            "Couldn't open the Google Sheet. Make sure you've shared it with "
            "the service account's email (found as 'client_email' in "
            f"{SERVICE_ACCOUNT_FILE.name}) with Editor access.\n\n{e}"
        )
        st.stop()
    try:
        return sh.worksheet(WORKSHEET)
    except gspread.exceptions.WorksheetNotFound:
        return sh.sheet1


def load_df(force=False):
    """Read the exercise sheet as a DataFrame."""
    ws = get_worksheet()
    records = ws.get_all_records()
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


def seed_if_empty():
    df = load_df(force=True)
    if df.empty:
        seed_rows = [
            {
                "id": str(uuid.uuid4()),
                "name": name, "category": category, "pattern": pattern,
                "regression": regression, "progression": progression, "equipment": equipment,
            }
            for name, category, pattern, regression, progression, equipment in DEFAULT_SEED
        ]
        df = pd.DataFrame(seed_rows, columns=COLUMNS)
        save_df(df)
    return df


def fetch_exercises(df):
    """Return rows as plain tuples, same shape the rest of the app expects."""
    return list(df[COLUMNS].itertuples(index=False, name=None))


def add_exercise(df, name, category, pattern, regression, progression, equipment):
    new_row = {
        "id": str(uuid.uuid4()), "name": name, "category": category, "pattern": pattern,
        "regression": regression, "progression": progression, "equipment": equipment,
    }
    updated = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_df(updated)
    return updated


def update_exercise(df, ex_id, name, category, pattern, regression, progression, equipment):
    idx = df.index[df["id"] == ex_id]
    df.loc[idx, ["name", "category", "pattern", "regression", "progression", "equipment"]] = [
        name, category, pattern, regression, progression, equipment,
    ]
    save_df(df)
    return df


def delete_exercise(df, ex_id):
    df = df[df["id"] != ex_id].reset_index(drop=True)
    save_df(df)
    return df


# --------------------------------------------------------------- dialogs --
@st.dialog("Exercise details")
def view_dialog(name, category, pattern, regression, progression, equipment):
    st.markdown(f"### {name}")
    st.markdown(f"**Category:** {CATEGORY_LABELS.get(category, category)}")
    st.markdown(f"**Movement pattern:** {pattern}")
    st.markdown(f"**Equipment:** {equipment}")
    st.divider()
    st.markdown(f"**Regression:** {regression}")
    st.markdown(f"**Progression:** {progression}")
    if st.button("Close", use_container_width=True):
        st.rerun()


@st.dialog("Edit exercise")
def edit_dialog(df, ex_id, name, category, pattern, regression, progression, equipment):
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

    col1, col2 = st.columns(2)
    if col1.button("Save changes", use_container_width=True):
        if not new_name.strip():
            st.error("Exercise name is required.")
        else:
            update_exercise(
                df, ex_id, new_name.strip(), new_category,
                new_pattern.strip() or "—", new_regression.strip() or "—",
                new_progression.strip() or "—", new_equipment,
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
            submitted = st.form_submit_button("Add to list", use_container_width=True)
            if submitted:
                if not name_in.strip():
                    st.error("Exercise name is required.")
                else:
                    add_exercise(
                        all_df, name_in.strip(), category_in,
                        pattern_in.strip() or "—", regression_in.strip() or "—",
                        progression_in.strip() or "—", equipment_in,
                    )
                    st.success(f"Added '{name_in}'.")
                    st.rerun()

# ------------------------------------------------------------- main area --
all_rows = fetch_exercises(all_df)

# Progress indicator
n_selected = len(st.session_state.selections)
st.markdown(
    f'<div class="progress-banner">✅ {n_selected} exercise{"s" if n_selected != 1 else ""} selected</div>',
    unsafe_allow_html=True,
)

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
                        ex_id, name, category, pattern, regression, progression, equipment = item
                        with col:
                            with st.container(border=True):
                                top = st.columns([0.5, 4])
                                chk_key = f"chk_{st.session_state.reset_token}_{ex_id}"
                                checked = top[0].checkbox("", key=chk_key, value=ex_id in st.session_state.selections)
                                color = EQUIPMENT_COLORS.get(equipment, "#6b6b66")
                                with top[1]:
                                    st.markdown(f'<div class="card-title">{name}</div>', unsafe_allow_html=True)
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
                                    view_dialog(name, category, pattern, regression, progression, equipment)
                                if btns[1].button("✎", key=f"edit_{ex_id}", help="Edit exercise", use_container_width=True):
                                    edit_dialog(all_df, ex_id, name, category, pattern, regression, progression, equipment)
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
    with st.container(height=PANE_HEIGHT, border=True):
        if not st.session_state.selections:
            st.caption("None selected yet — tick items on the left.")
        else:
            for sel_key, sel in list(st.session_state.selections.items()):
                r1, r2 = st.columns([3, 1.2])
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

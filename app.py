"""
Exercise Database Selector — Streamlit version
--------------------------------------------------------
- Exercise library stored in a local SQLite file (exercises.db), so it
  persists across restarts and is shared by everyone using this deployment.
- Anyone can browse, search, filter, tick exercises, set reps, copy the
  final list as text, and add/edit/remove exercises from the sidebar.

Run locally:
    pip install -r requirements.txt
    streamlit run app.py
"""

import sqlite3
from pathlib import Path

import streamlit as st

DB_PATH = Path(__file__).parent / "exercises.db"

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
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            pattern TEXT,
            regression TEXT,
            progression TEXT,
            equipment TEXT DEFAULT 'Bodyweight'
        )
        """
    )
    cols = [row[1] for row in conn.execute("PRAGMA table_info(exercises)").fetchall()]
    if "equipment" not in cols:
        conn.execute("ALTER TABLE exercises ADD COLUMN equipment TEXT DEFAULT 'Bodyweight'")
    conn.commit()
    return conn


def seed_if_empty(conn):
    count = conn.execute("SELECT COUNT(*) FROM exercises").fetchone()[0]
    if count == 0:
        conn.executemany(
            "INSERT INTO exercises (name, category, pattern, regression, progression, equipment) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            DEFAULT_SEED,
        )
        conn.commit()


def fetch_exercises(conn):
    return conn.execute(
        "SELECT id, name, category, pattern, regression, progression, equipment "
        "FROM exercises ORDER BY category, name"
    ).fetchall()


def add_exercise(conn, name, category, pattern, regression, progression, equipment):
    conn.execute(
        "INSERT INTO exercises (name, category, pattern, regression, progression, equipment) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, category, pattern, regression, progression, equipment),
    )
    conn.commit()


def update_exercise(conn, ex_id, name, category, pattern, regression, progression, equipment):
    conn.execute(
        "UPDATE exercises SET name = ?, category = ?, pattern = ?, regression = ?, progression = ?, "
        "equipment = ? WHERE id = ?",
        (name, category, pattern, regression, progression, equipment, ex_id),
    )
    conn.commit()


def delete_exercise(conn, ex_id):
    conn.execute("DELETE FROM exercises WHERE id = ?", (ex_id,))
    conn.commit()


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
def edit_dialog(conn, ex_id, name, category, pattern, regression, progression, equipment):
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
                conn, ex_id, new_name.strip(), new_category,
                new_pattern.strip() or "—", new_regression.strip() or "—",
                new_progression.strip() or "—", new_equipment,
            )
            st.session_state.selections.pop(ex_id, None)
            st.rerun()
    if col2.button("Cancel", use_container_width=True):
        st.rerun()


# -------------------------------------------------------------------- app --
st.set_page_config(page_title="Exercise Database Selector", page_icon="🏋️", layout="wide")

conn = get_conn()
seed_if_empty(conn)

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
                        conn, name_in.strip(), category_in,
                        pattern_in.strip() or "—", regression_in.strip() or "—",
                        progression_in.strip() or "—", equipment_in,
                    )
                    st.success(f"Added '{name_in}'.")
                    st.rerun()

# ------------------------------------------------------------- main area --
all_rows = fetch_exercises(conn)

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
                                st.markdown(
                                    f'<div class="card-line"><span class="card-label">Regression:</span> {regression}</div>',
                                    unsafe_allow_html=True,
                                )
                                st.markdown(
                                    f'<div class="card-line"><span class="card-label">Progression:</span> {progression}</div>',
                                    unsafe_allow_html=True,
                                )
                                btns = st.columns(3)
                                if btns[0].button("👁", key=f"view_{ex_id}", help="View exercise", use_container_width=True):
                                    view_dialog(name, category, pattern, regression, progression, equipment)
                                if btns[1].button("✎", key=f"edit_{ex_id}", help="Edit exercise", use_container_width=True):
                                    edit_dialog(conn, ex_id, name, category, pattern, regression, progression, equipment)
                                if btns[2].button("✕", key=f"del_{ex_id}", help="Remove exercise", use_container_width=True):
                                    delete_exercise(conn, ex_id)
                                    st.session_state.selections.pop(ex_id, None)
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
            for ex_id, sel in list(st.session_state.selections.items()):
                st.markdown(f"**{sel['name']}**")
                r1, r2, r3 = st.columns([1, 1, 1])
                if r1.button("−", key=f"minus_{ex_id}", use_container_width=True):
                    st.session_state.selections[ex_id]["reps"] = max(1, sel["reps"] - 1)
                    st.rerun()
                r2.markdown(f'<div class="rep-value">{sel["reps"]}</div>', unsafe_allow_html=True)
                if r3.button("+", key=f"plus_{ex_id}", use_container_width=True):
                    st.session_state.selections[ex_id]["reps"] = sel["reps"] + 1
                    st.rerun()
                st.markdown("<hr style='margin:6px 0;'>", unsafe_allow_html=True)

            list_text = "\n".join(
                f"{sel['name']} — {sel['reps']} reps" for sel in st.session_state.selections.values()
            )
            st.markdown("**Copy list**")
            st.code(list_text, language=None)

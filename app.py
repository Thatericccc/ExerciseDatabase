"""
Exercise Database Selector — Streamlit version
--------------------------------------------------------
- Exercise library stored in a local SQLite file (exercises.db), so it
  persists across restarts and is shared by everyone using this deployment.
- Anyone can browse, tick exercises, set reps, copy the final list as
  text, and add new exercises to the shared library.

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
}

EQUIPMENT_OPTIONS = ["Bodyweight", "Resistance Band", "Dumbbell", "Kettlebell", "Barbell"]

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
    # Migration for databases created before the equipment column existed.
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
                conn,
                ex_id,
                new_name.strip(),
                new_category,
                new_pattern.strip() or "—",
                new_regression.strip() or "—",
                new_progression.strip() or "—",
                new_equipment,
            )
            st.session_state.selections.pop(ex_id, None)
            st.rerun()
    if col2.button("Cancel", use_container_width=True):
        st.rerun()


# -------------------------------------------------------------------- app --
st.set_page_config(page_title="Exercise Database Selector", page_icon="🏋️", layout="centered")

conn = get_conn()
seed_if_empty(conn)

if "selections" not in st.session_state:
    st.session_state.selections = {}  # id -> {"name": str, "reps": int}

st.title("Exercise Database Selector")
st.caption("Tick exercises for the session. Your picks build a final rep list you can copy below.")

st.markdown(
    """
    <style>
    div[data-testid="stHorizontalBlock"] { align-items: center; }
    div.stButton > button {
        display: flex;
        justify-content: center;
        align-items: center;
        padding-left: 0;
        padding-right: 0;
        border-radius: 8px;
    }
    .cat-header {
        font-size: 1.05rem;
        font-weight: 700;
        color: #8a6d3b;
        border-bottom: 2px solid #e4d9c3;
        padding-bottom: 6px;
        margin: 22px 0 14px;
    }
    .card-title {
        font-weight: 700;
        font-size: 1rem;
        margin-bottom: 0;
    }
    .card-sub {
        color: #8a837a;
        font-size: 0.8rem;
        margin-bottom: 6px;
    }
    .card-label {
        color: #8a837a;
        font-weight: 600;
    }
    .card-line {
        font-size: 0.85rem;
        margin: 2px 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

tab_browse, tab_add = st.tabs(["Browse list", "Add exercise"])

# --- Browse / tick list ---
with tab_browse:
    st.subheader("Filter by equipment")
    equipment_filter = st.multiselect(
        "Equipment",
        options=EQUIPMENT_OPTIONS,
        default=[],
        label_visibility="collapsed",
        help="Leave empty to show all equipment types.",
    )

    rows = fetch_exercises(conn)
    if equipment_filter:
        rows = [r for r in rows if r[6] in equipment_filter]
    grouped = {cat: [] for cat in CATEGORY_LABELS}
    for r in rows:
        grouped.setdefault(r[2], []).append(r)

    CARD_COLS = 2
    for cat, label in CATEGORY_LABELS.items():
        items = grouped.get(cat, [])
        if not items:
            continue
        st.markdown(f'<div class="cat-header">{label}</div>', unsafe_allow_html=True)
        for i in range(0, len(items), CARD_COLS):
            row_items = items[i : i + CARD_COLS]
            grid = st.columns(CARD_COLS)
            for col, item in zip(grid, row_items):
                ex_id, name, category, pattern, regression, progression, equipment = item
                with col:
                    with st.container(border=True):
                        top = st.columns([0.5, 4])
                        checked = top[0].checkbox("", key=f"chk_{ex_id}", value=ex_id in st.session_state.selections)
                        with top[1]:
                            st.markdown(f'<div class="card-title">{name}</div>', unsafe_allow_html=True)
                            st.markdown(f'<div class="card-sub">{pattern} · {equipment}</div>', unsafe_allow_html=True)
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

    # --- Selected exercises + reps ---
    st.markdown('<div class="cat-header">Selected exercises</div>', unsafe_allow_html=True)
    if not st.session_state.selections:
        st.info("No exercises selected yet — tick items above.")
    else:
        for ex_id, sel in list(st.session_state.selections.items()):
            c1, c2 = st.columns([3, 1])
            c1.write(sel["name"])
            new_reps = c2.number_input(
                "Reps", min_value=1, value=sel["reps"], key=f"reps_{ex_id}", label_visibility="collapsed"
            )
            st.session_state.selections[ex_id]["reps"] = new_reps

        list_text = "\n".join(
            f"{sel['name']} — {sel['reps']} reps" for sel in st.session_state.selections.values()
        )
        st.markdown('<div class="cat-header">Copy list</div>', unsafe_allow_html=True)
        st.code(list_text, language=None)

# --- Add exercise (open to anyone) ---
with tab_add:
    st.subheader("Add a new exercise")
    with st.form("add_exercise_form", clear_on_submit=True):
        name = st.text_input("Exercise name")
        category = st.selectbox("Category", options=list(CATEGORY_LABELS.keys()), format_func=lambda c: CATEGORY_LABELS[c])
        pattern = st.text_input("Movement pattern (e.g. Hinge, Push, Carry)")
        equipment = st.selectbox("Equipment", options=EQUIPMENT_OPTIONS)
        regression = st.text_input("Regression (easier variation)")
        progression = st.text_input("Progression (harder variation)")
        submitted = st.form_submit_button("Add to list")
        if submitted:
            if not name.strip():
                st.error("Exercise name is required.")
            else:
                add_exercise(
                    conn,
                    name.strip(),
                    category,
                    pattern.strip() or "—",
                    regression.strip() or "—",
                    progression.strip() or "—",
                    equipment,
                )
                st.success(f"Added '{name}' to the shared list.")
                st.rerun()

import json
import os
import tempfile
import threading
import time

from flask import Flask, render_template, request, jsonify
import pandas as pd

app = Flask(__name__)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.config["current_file"] = None  # No file loaded initially

TEMP_FILE = tempfile.NamedTemporaryFile(
    suffix=".xlsx", delete=False, prefix="kanban_"
).name

LAST_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_file.txt")
COLUMN_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "column_config.json")

DEFAULT_COLUMN_CONFIG = {
    "board_column": "Role",
    "swimlane_column": "New JG",
    "card_header": "Name",
    "card_fields": ["Proposed new Role for Manager Review", "Comment"],
    "dropdown_fields": ["Proposed new Role for Manager Review"],
}


def load_column_config():
    """Load column mapping configuration from disk."""
    if os.path.exists(COLUMN_CONFIG_PATH):
        with open(COLUMN_CONFIG_PATH, "r") as f:
            return json.load(f)
    return dict(DEFAULT_COLUMN_CONFIG)


def save_column_config(config):
    """Save column mapping configuration to disk."""
    with open(COLUMN_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


app.config["column_config"] = load_column_config()


def load_last_file():
    """Load the last used file from disk if it exists."""
    if os.path.exists(LAST_FILE_PATH):
        with open(LAST_FILE_PATH, "r") as f:
            file_path = f.read().strip()
        if os.path.exists(file_path):
            app.config["current_file"] = file_path
            return True
    return False


# Load the last used file on startup
load_last_file()


def load_data():
    df = pd.read_excel(app.config["current_file"], sheet_name=0)
    df = df.fillna("")
    return df


def get_config():
    return app.config["column_config"]


@app.route("/")
def index():
    if not app.config["current_file"]:
        return render_template("upload.html")
    cfg = get_config()
    df = load_data()
    board_col = cfg["board_column"]
    swim_col = cfg["swimlane_column"]
    roles = sorted(df[board_col].unique())
    jgs = sorted(df[swim_col].dropna().unique(), key=lambda v: (isinstance(v, str), v))
    filename = app.config["current_file"]
    return render_template("index.html", roles=roles, jgs=jgs, filename=filename,
                           board_col_name=board_col, swim_col_name=swim_col)


@app.route("/api/upload", methods=["POST"])
def api_upload():
    f = request.files.get("file")
    if not f or not f.filename.endswith(".xlsx"):
        return jsonify({"error": "Please select an .xlsx file"}), 400
    dest = os.path.join(UPLOAD_DIR, f.filename)
    f.save(dest)
    app.config["current_file"] = dest
    # Save the filename for next startup
    with open(LAST_FILE_PATH, "w") as lf:
        lf.write(dest)
    return jsonify({"ok": True, "filename": f.filename})


@app.route("/api/columns", methods=["GET"])
def api_get_columns():
    """Return available Excel columns and current mapping config."""
    if not app.config["current_file"]:
        return jsonify({"error": "No file loaded"}), 400
    df = load_data()
    columns = list(df.columns)
    return jsonify({"columns": columns, "config": get_config()})


@app.route("/api/columns", methods=["POST"])
def api_save_columns():
    """Save column mapping configuration."""
    data = request.get_json()
    cfg = get_config()
    if "board_column" in data:
        cfg["board_column"] = data["board_column"]
    if "swimlane_column" in data:
        cfg["swimlane_column"] = data["swimlane_column"]
    if "card_header" in data:
        cfg["card_header"] = data["card_header"]
    if "card_fields" in data:
        cfg["card_fields"] = data["card_fields"]
    if "dropdown_fields" in data:
        cfg["dropdown_fields"] = data["dropdown_fields"]
    app.config["column_config"] = cfg
    save_column_config(cfg)
    return jsonify({"ok": True, "config": cfg})


@app.route("/api/board")
def api_board():
    cfg = get_config()
    board_col = cfg["board_column"]
    swim_col = cfg["swimlane_column"]
    header_col = cfg["card_header"]
    card_fields = cfg["card_fields"]

    df = load_data()

    col_filter = request.args.get("role", "")
    if col_filter:
        df = df[df[board_col] == col_filter]

    swim_filter = request.args.get("jg", "")
    if swim_filter:
        df = df[df[swim_col].astype(str) == swim_filter]

    all_roles = sorted(df[board_col].unique())
    all_jgs = sorted(df[swim_col].dropna().unique(), key=lambda v: (isinstance(v, str), v))

    swimlanes = {}
    for jg in all_jgs:
        swimlanes[str(jg)] = {role: [] for role in all_roles}

    for _, row in df.iterrows():
        jg_val = row[swim_col]
        if jg_val == "":
            continue
        jg_key = str(int(jg_val)) if isinstance(jg_val, (int, float)) else str(jg_val)
        col_val = row[board_col]
        if not col_val:
            continue

        person = {"name": row[header_col]}
        for field in card_fields:
            if field in row.index:
                person[field] = row[field]

        if jg_key in swimlanes and col_val in swimlanes[jg_key]:
            swimlanes[jg_key][col_val].append(person)

    # Collect unique values only for fields configured as dropdowns
    dropdown_fields = cfg.get("dropdown_fields", [])
    full_df = load_data()
    field_options = {}
    for field in card_fields:
        if field in dropdown_fields and field in full_df.columns:
            vals = sorted(v for v in full_df[field].unique() if v != "")
            field_options[field] = [str(v) for v in vals]

    return jsonify({
        "roles": all_roles,
        "jgs": [str(int(j)) if isinstance(j, (int, float)) else str(j) for j in all_jgs],
        "swimlanes": swimlanes,
        "card_fields": card_fields,
        "field_options": field_options,
    })


@app.route("/api/move", methods=["POST"])
def api_move():
    cfg = get_config()
    board_col = cfg["board_column"]
    swim_col = cfg["swimlane_column"]
    header_col = cfg["card_header"]

    data = request.get_json()
    name = data.get("name", "")
    new_role = data.get("new_role", "")
    new_jg = data.get("new_jg", "")
    if not name:
        return jsonify({"error": "name required"}), 400

    df = pd.read_excel(app.config["current_file"], sheet_name=0)
    mask = df[header_col] == name
    if not mask.any():
        return jsonify({"error": f"Name '{name}' not found"}), 404

    if new_role:
        df.loc[mask, board_col] = new_role
    if new_jg:
        try:
            df.loc[mask, swim_col] = int(new_jg)
        except ValueError:
            df.loc[mask, swim_col] = new_jg
    df.to_excel(app.config["current_file"], index=False)
    return jsonify({"ok": True, "name": name, "new_role": new_role, "new_jg": new_jg})


@app.route("/api/edit", methods=["POST"])
def api_edit():
    cfg = get_config()
    header_col = cfg["card_header"]
    card_fields = cfg["card_fields"]

    data = request.get_json()
    name = data.get("name", "")
    if not name:
        return jsonify({"error": "name required"}), 400

    df = pd.read_excel(app.config["current_file"], sheet_name=0)
    mask = df[header_col] == name
    if not mask.any():
        return jsonify({"error": f"Name '{name}' not found"}), 404

    # Update all configured card fields, casting to match column dtype
    for field in card_fields:
        if field in data and field in df.columns:
            value = data[field]
            col_dtype = df[field].dtype
            if pd.api.types.is_integer_dtype(col_dtype):
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    pass
            elif pd.api.types.is_float_dtype(col_dtype):
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    pass
            df.loc[mask, field] = value

    df.to_excel(app.config["current_file"], index=False)
    return jsonify({"ok": True, "name": name})


if __name__ == "__main__":
    app.run(debug=True)

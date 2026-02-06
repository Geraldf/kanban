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


def load_data():
    df = pd.read_excel(app.config["current_file"], sheet_name=0)
    df = df.fillna("")
    return df


@app.route("/")
def index():
    if not app.config["current_file"]:
        return render_template("upload.html")
    df = load_data()
    roles = sorted(df["Role"].unique())
    jgs = sorted(int(v) for v in df["New JG"].dropna().unique())
    filename = os.path.basename(app.config["current_file"])
    return render_template("index.html", roles=roles, jgs=jgs, filename=filename)


@app.route("/api/upload", methods=["POST"])
def api_upload():
    f = request.files.get("file")
    if not f or not f.filename.endswith(".xlsx"):
        return jsonify({"error": "Please select an .xlsx file"}), 400
    dest = os.path.join(UPLOAD_DIR, f.filename)
    f.save(dest)
    app.config["current_file"] = dest
    return jsonify({"ok": True, "filename": f.filename})


@app.route("/api/board")
def api_board():
    df = load_data()
    role_filter = request.args.get("role", "")
    if role_filter:
        df = df[df["Role"] == role_filter]

    jg_filter = request.args.get("jg", "")
    if jg_filter:
        df = df[df["New JG"].astype(str) == jg_filter]

    all_roles = sorted(df["Role"].unique())
    all_jgs = sorted(int(v) for v in df["New JG"].dropna().unique())

    swimlanes = {}
    for jg in all_jgs:
        swimlanes[str(jg)] = {role: [] for role in all_roles}

    for _, row in df.iterrows():
        jg = str(int(row["New JG"])) if row["New JG"] != "" else None
        role = row["Role"]
        if jg and role:
            swimlanes[jg][role].append(
                {
                    "name": row["Name"],
                    "proposed_role": row["Proposed new Role for Manager Review"],
                    "comment": row["Comment"],
                }
            )

    return jsonify({"roles": all_roles, "jgs": all_jgs, "swimlanes": swimlanes})


@app.route("/api/move", methods=["POST"])
def api_move():
    data = request.get_json()
    name = data.get("name", "")
    new_role = data.get("new_role", "")
    new_jg = data.get("new_jg", "")
    if not name:
        return jsonify({"error": "name required"}), 400

    df = pd.read_excel(app.config["current_file"], sheet_name=0)
    mask = df["Name"] == name
    if not mask.any():
        return jsonify({"error": f"Name '{name}' not found"}), 404

    if new_role:
        df.loc[mask, "Role"] = new_role
    if new_jg:
        df.loc[mask, "New JG"] = int(new_jg)
    df.to_excel(app.config["current_file"], index=False)
    return jsonify({"ok": True, "name": name, "new_role": new_role, "new_jg": new_jg})


if __name__ == "__main__":
    app.run(debug=True)

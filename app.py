import os
import json
import logging
from datetime import datetime
from pathlib import Path
import shutil

from flask import Flask, render_template, request, jsonify
import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('kanban.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
BASE_DIR = Path(__file__).parent.absolute()
UPLOAD_DIR = BASE_DIR / "uploads"
BACKUP_DIR = BASE_DIR / "backups"
UPLOAD_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)

app.config["current_file"] = None  # No file loaded initially
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size

# Column config
CONFIG_FILE = BASE_DIR / "column_config.json"
LAST_FILE = BASE_DIR / "last_file.txt"

DEFAULT_CONFIG = {
    "board_column": "Role",
    "swimlane_column": "New JG",
    "card_header": "Name",
    "card_fields": ["Proposed new Role for Manager Review", "Comment"],
    "dropdown_fields": []
}


def load_column_config():
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading column config: {e}")
    return dict(DEFAULT_CONFIG)


def save_column_config(config):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        logger.info("Column config saved")
    except Exception as e:
        logger.error(f"Error saving column config: {e}")


def load_last_file():
    try:
        if LAST_FILE.exists():
            file_path = LAST_FILE.read_text().strip()
            if file_path and os.path.exists(file_path):
                app.config["current_file"] = file_path
                logger.info(f"Loaded last file: {file_path}")
    except Exception as e:
        logger.error(f"Error loading last file: {e}")


def save_last_file(file_path):
    try:
        LAST_FILE.write_text(str(file_path))
    except Exception as e:
        logger.error(f"Error saving last file: {e}")


load_last_file()


def create_backup(file_path):
    """Create a timestamped backup of the current file."""
    try:
        if not os.path.exists(file_path):
            logger.warning(f"Cannot backup non-existent file: {file_path}")
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{Path(file_path).stem}_backup_{timestamp}.xlsx"
        backup_path = BACKUP_DIR / backup_name
        
        shutil.copy2(file_path, backup_path)
        logger.info(f"Backup created: {backup_path}")
        
        # Keep only last 10 backups per file
        cleanup_old_backups(Path(file_path).stem)
        
        return str(backup_path)
    except Exception as e:
        logger.error(f"Backup creation failed: {e}")
        return None


def cleanup_old_backups(file_stem, keep_count=10):
    """Keep only the most recent backups."""
    try:
        backups = sorted(
            BACKUP_DIR.glob(f"{file_stem}_backup_*.xlsx"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        for old_backup in backups[keep_count:]:
            old_backup.unlink()
            logger.info(f"Deleted old backup: {old_backup}")
    except Exception as e:
        logger.error(f"Backup cleanup failed: {e}")


def validate_excel_structure(df):
    """Validate that the Excel file has a Name column at minimum."""
    if "Name" not in df.columns:
        raise ValueError("Missing required column: Name")
    return True


def load_data():
    """Load and validate Excel data with error handling."""
    if not app.config["current_file"]:
        raise ValueError("No file currently loaded")

    if not os.path.exists(app.config["current_file"]):
        raise FileNotFoundError(f"File not found: {app.config['current_file']}")

    df = pd.read_excel(app.config["current_file"], sheet_name=0)
    validate_excel_structure(df)
    df = df.fillna("")
    return df


@app.route("/")
def index():
    """Main board view with error handling."""
    try:
        if not app.config["current_file"]:
            return render_template("upload.html")

        df = load_data()
        config = load_column_config()
        board_col = config.get("board_column", "Role")
        swim_col = config.get("swimlane_column", "New JG")

        roles = sorted(df[board_col].unique()) if board_col in df.columns else []
        jgs = sorted(int(v) for v in df[swim_col].dropna().unique() if v != "") if swim_col in df.columns else []
        filename = os.path.basename(app.config["current_file"])

        return render_template(
            "index.html",
            roles=roles,
            jgs=jgs,
            filename=filename,
            board_col_name=board_col,
            swim_col_name=swim_col,
        )
    except Exception as e:
        logger.error(f"Error loading board: {e}")
        return render_template("upload.html", error=f"Error loading file: {str(e)}")


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """Upload and validate Excel file with comprehensive error handling."""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file part in request"}), 400
        
        f = request.files.get("file")
        if not f or f.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not f.filename.endswith(".xlsx"):
            return jsonify({"error": "Only .xlsx files are supported"}), 400
        
        # Secure filename
        filename = Path(f.filename).name
        dest = UPLOAD_DIR / filename
        
        # Save file temporarily
        f.save(dest)
        logger.info(f"File uploaded: {filename}")
        
        # Validate structure before accepting
        try:
            df = pd.read_excel(dest, sheet_name=0)
            validate_excel_structure(df)
        except Exception as e:
            os.remove(dest)
            logger.error(f"Invalid file structure: {e}")
            return jsonify({"error": f"Invalid file structure: {str(e)}"}), 400
        
        # If we had a previous file, create backup
        if app.config["current_file"] and os.path.exists(app.config["current_file"]):
            create_backup(app.config["current_file"])
        
        app.config["current_file"] = str(dest)
        save_last_file(dest)
        logger.info(f"File activated: {filename}, {len(df)} entries")

        return jsonify({
            "ok": True,
            "filename": filename,
            "entries": len(df),
        })
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500


@app.route("/api/board")
def api_board():
    """Get board data with filtering and error handling."""
    try:
        df = load_data()
        config = load_column_config()
        board_col = config.get("board_column", "Role")
        swim_col = config.get("swimlane_column", "New JG")
        card_header = config.get("card_header", "Name")
        card_fields = config.get("card_fields", [])
        dropdown_fields = config.get("dropdown_fields", [])

        # Apply filters
        role_filter = request.args.get("role", "").strip()
        if role_filter and board_col in df.columns:
            df = df[df[board_col] == role_filter]

        jg_filter = request.args.get("jg", "").strip()
        if jg_filter and swim_col in df.columns:
            df = df[df[swim_col].astype(str) == jg_filter]

        all_roles = sorted(df[board_col].unique()) if board_col in df.columns else []
        all_jgs = sorted(int(v) for v in df[swim_col].dropna().unique() if v != "") if swim_col in df.columns else []

        # Build field_options for dropdown fields
        full_df = load_data()
        field_options = {}
        for field in card_fields:
            if field in dropdown_fields and field in full_df.columns:
                vals = full_df[field].dropna().unique()
                field_options[field] = sorted([str(v) for v in vals if str(v).strip()])

        # Build swimlanes
        swimlanes = {}
        for jg in all_jgs:
            swimlanes[str(jg)] = {role: [] for role in all_roles}

        for _, row in df.iterrows():
            jg_val = row.get(swim_col, "")
            if pd.notna(jg_val) and jg_val != "":
                jg = str(int(jg_val))
                role = row.get(board_col, "")
                if jg and role:
                    person = {"name": row.get(card_header, "")}
                    for field in card_fields:
                        person[field] = str(row.get(field, ""))
                    swimlanes[jg][role].append(person)

        return jsonify({
            "roles": all_roles,
            "jgs": all_jgs,
            "swimlanes": swimlanes,
            "card_fields": card_fields,
            "field_options": field_options,
            "total_entries": len(df),
        })
    except Exception as e:
        logger.error(f"Error getting board data: {e}")
        return jsonify({"error": f"Failed to load board: {str(e)}"}), 500


@app.route("/api/move", methods=["POST"])
def api_move():
    """Move entry with backup and comprehensive validation."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        config = load_column_config()
        board_col = config.get("board_column", "Role")
        swim_col = config.get("swimlane_column", "New JG")

        name = data.get("name", "").strip()
        new_role = data.get("new_role", "").strip()
        new_jg = data.get("new_jg", "").strip()

        if not name:
            return jsonify({"error": "Name is required"}), 400

        if not new_role and not new_jg:
            return jsonify({"error": "Either new_role or new_jg must be provided"}), 400

        # Create backup before modification
        backup_path = create_backup(app.config["current_file"])

        # Load and modify data
        df = pd.read_excel(app.config["current_file"], sheet_name=0)
        mask = df["Name"] == name

        if not mask.any():
            return jsonify({"error": f"Name '{name}' not found"}), 404

        changes = {}
        if new_role and board_col in df.columns:
            old_role = df.loc[mask, board_col].iloc[0]
            df.loc[mask, board_col] = new_role
            changes["role"] = {"old": str(old_role), "new": new_role}

        if new_jg and swim_col in df.columns:
            old_jg = df.loc[mask, swim_col].iloc[0]
            col_dtype = df[swim_col].dtype
            value = new_jg
            if pd.api.types.is_integer_dtype(col_dtype):
                value = int(new_jg)
            elif pd.api.types.is_float_dtype(col_dtype):
                value = float(new_jg)
            df.loc[mask, swim_col] = value
            changes["jg"] = {"old": str(old_jg), "new": new_jg}

        df.to_excel(app.config["current_file"], index=False)
        logger.info(f"Entry moved: {name} - {changes}")

        return jsonify({
            "ok": True,
            "name": name,
            "new_role": new_role,
            "new_jg": new_jg,
            "backup": os.path.basename(backup_path) if backup_path else None,
            "changes": changes,
        })
    except Exception as e:
        logger.error(f"Move error: {e}")
        return jsonify({"error": f"Move failed: {str(e)}"}), 500


@app.route("/api/columns", methods=["GET"])
def api_columns_get():
    """Get available columns and current config."""
    try:
        df = load_data()
        config = load_column_config()
        return jsonify({
            "columns": list(df.columns),
            "config": config,
        })
    except Exception as e:
        logger.error(f"Error getting columns: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/columns", methods=["POST"])
def api_columns_post():
    """Save column mapping configuration."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        config = load_column_config()
        if "board_column" in data:
            config["board_column"] = data["board_column"]
        if "swimlane_column" in data:
            config["swimlane_column"] = data["swimlane_column"]
        if "card_fields" in data:
            config["card_fields"] = data["card_fields"]
        if "dropdown_fields" in data:
            config["dropdown_fields"] = data["dropdown_fields"]

        save_column_config(config)
        return jsonify({"ok": True, "config": config})
    except Exception as e:
        logger.error(f"Error saving columns config: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/edit", methods=["POST"])
def api_edit():
    """Edit a person's fields."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Name is required"}), 400

        backup_path = create_backup(app.config["current_file"])

        df = pd.read_excel(app.config["current_file"], sheet_name=0)
        mask = df["Name"] == name

        if not mask.any():
            return jsonify({"error": f"Name '{name}' not found"}), 404

        config = load_column_config()
        card_fields = config.get("card_fields", [])

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
        logger.info(f"Entry edited: {name}")

        return jsonify({"ok": True, "name": name})
    except Exception as e:
        logger.error(f"Edit error: {e}")
        return jsonify({"error": f"Edit failed: {str(e)}"}), 500


@app.route("/api/backups")
def api_backups():
    """List available backups."""
    try:
        backups = []
        for backup_file in sorted(BACKUP_DIR.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True):
            backups.append({
                "filename": backup_file.name,
                "size": backup_file.stat().st_size,
                "created": datetime.fromtimestamp(backup_file.stat().st_mtime).isoformat()
            })
        return jsonify({"backups": backups, "count": len(backups)})
    except Exception as e:
        logger.error(f"Error listing backups: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/restore/<backup_name>", methods=["POST"])
def api_restore(backup_name):
    """Restore from a backup."""
    try:
        backup_path = BACKUP_DIR / backup_name
        if not backup_path.exists():
            return jsonify({"error": "Backup not found"}), 404
        
        # Create backup of current state before restoring
        if app.config["current_file"]:
            create_backup(app.config["current_file"])
        
        # Restore
        dest = UPLOAD_DIR / f"restored_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        shutil.copy2(backup_path, dest)
        app.config["current_file"] = str(dest)
        
        logger.info(f"Restored from backup: {backup_name}")
        return jsonify({"ok": True, "filename": dest.name})
    except Exception as e:
        logger.error(f"Restore error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    logger.info("Starting Kanban Board application")
    app.run(debug=True)

import os
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

# Required Excel columns
REQUIRED_COLUMNS = ["Name", "Role", "New JG", "Proposed new Role for Manager Review", "Comment"]


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
    """Validate that the Excel file has required columns."""
    missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")
    return True


def load_data():
    """Load and validate Excel data with error handling."""
    try:
        if not app.config["current_file"]:
            raise ValueError("No file currently loaded")
        
        if not os.path.exists(app.config["current_file"]):
            raise FileNotFoundError(f"File not found: {app.config['current_file']}")
        
        df = pd.read_excel(app.config["current_file"], sheet_name=0)
        validate_excel_structure(df)
        df = df.fillna("")
        
        logger.info(f"Successfully loaded data from {app.config['current_file']}")
        return df
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        raise


@app.route("/")
def index():
    """Main board view with error handling."""
    try:
        if not app.config["current_file"]:
            return render_template("upload.html")
        
        df = load_data()
        roles = sorted(df["Role"].unique())
        jgs = sorted(int(v) for v in df["New JG"].dropna().unique() if v != "")
        filename = os.path.basename(app.config["current_file"])
        
        logger.info(f"Board loaded: {filename}, {len(df)} entries")
        return render_template("index.html", roles=roles, jgs=jgs, filename=filename)
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
        logger.info(f"File activated: {filename}, {len(df)} entries")
        
        return jsonify({
            "ok": True, 
            "filename": filename,
            "entries": len(df),
            "roles": len(df["Role"].unique()),
            "jgs": len(df["New JG"].dropna().unique())
        })
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500


@app.route("/api/board")
def api_board():
    """Get board data with filtering and error handling."""
    try:
        df = load_data()
        
        # Apply filters
        role_filter = request.args.get("role", "").strip()
        if role_filter:
            df = df[df["Role"] == role_filter]
            logger.debug(f"Filtered by role: {role_filter}")

        jg_filter = request.args.get("jg", "").strip()
        if jg_filter:
            df = df[df["New JG"].astype(str) == jg_filter]
            logger.debug(f"Filtered by JG: {jg_filter}")

        all_roles = sorted(df["Role"].unique())
        all_jgs = sorted(int(v) for v in df["New JG"].dropna().unique() if v != "")

        # Build swimlanes
        swimlanes = {}
        for jg in all_jgs:
            swimlanes[str(jg)] = {role: [] for role in all_roles}

        for _, row in df.iterrows():
            jg_val = row["New JG"]
            if pd.notna(jg_val) and jg_val != "":
                jg = str(int(jg_val))
                role = row["Role"]
                if jg and role:
                    swimlanes[jg][role].append({
                        "name": row["Name"],
                        "proposed_role": row["Proposed new Role for Manager Review"],
                        "comment": row["Comment"],
                    })

        return jsonify({
            "roles": all_roles, 
            "jgs": all_jgs, 
            "swimlanes": swimlanes,
            "total_entries": len(df)
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
        
        name = data.get("name", "").strip()
        new_role = data.get("new_role", "").strip()
        new_jg = data.get("new_jg", "").strip()
        
        if not name:
            return jsonify({"error": "Name is required"}), 400
        
        if not new_role and not new_jg:
            return jsonify({"error": "Either new_role or new_jg must be provided"}), 400

        # Create backup before modification
        backup_path = create_backup(app.config["current_file"])
        if not backup_path:
            logger.warning("Proceeding without backup")

        # Load and modify data
        df = pd.read_excel(app.config["current_file"], sheet_name=0)
        mask = df["Name"] == name
        
        if not mask.any():
            return jsonify({"error": f"Name '{name}' not found"}), 404

        # Track changes for logging
        changes = {}
        if new_role:
            old_role = df.loc[mask, "Role"].iloc[0]
            df.loc[mask, "Role"] = new_role
            changes["role"] = {"old": old_role, "new": new_role}
            
        if new_jg:
            old_jg = df.loc[mask, "New JG"].iloc[0]
            df.loc[mask, "New JG"] = int(new_jg)
            changes["jg"] = {"old": str(old_jg), "new": new_jg}

        # Save changes
        df.to_excel(app.config["current_file"], index=False)
        
        logger.info(f"Entry moved: {name} - {changes}")
        
        return jsonify({
            "ok": True, 
            "name": name, 
            "new_role": new_role, 
            "new_jg": new_jg,
            "backup": os.path.basename(backup_path) if backup_path else None,
            "changes": changes
        })
    except Exception as e:
        logger.error(f"Move error: {e}")
        return jsonify({"error": f"Move failed: {str(e)}"}), 500


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

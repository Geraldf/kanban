# Kanban Board - Role Review Application

A Flask-based web application for managing role reviews using Excel files with a visual Kanban board interface.

## Features

- 📊 **Excel-based Data Management**: Upload and manage .xlsx files
- 🎯 **Kanban Board View**: Visual swimlane organization by Job Groups and Roles
- 🔄 **Drag & Drop**: Move employees between roles and job groups
- 💾 **Automatic Backups**: Every change creates a timestamped backup
- 🔍 **Filtering**: Filter board by role and job group
- 📝 **Comprehensive Logging**: Track all operations and changes
- ✅ **Data Validation**: Ensures Excel files have required structure

## Installation

### Requirements
- Python 3.8+
- pip

### Setup

1. Clone the repository:
```bash
git clone https://github.com/Geraldf/kanban.git
cd kanban
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Starting the Application

```bash
python app.py
```

The application will start on `http://localhost:5000`

### Excel File Structure

Your Excel file must contain these columns:
- `Name`: Employee name
- `Role`: Current role
- `New JG`: New job group (numeric)
- `Proposed new Role for Manager Review`: Suggested new role
- `Comment`: Additional comments

### API Endpoints

#### Upload File
```http
POST /api/upload
Content-Type: multipart/form-data

file: <xlsx file>
```

#### Get Board Data
```http
GET /api/board?role=<role>&jg=<job_group>
```

#### Move Entry
```http
POST /api/move
Content-Type: application/json

{
  "name": "John Doe",
  "new_role": "Senior Developer",
  "new_jg": "5"
}
```

#### List Backups
```http
GET /api/backups
```

#### Restore Backup
```http
POST /api/restore/<backup_name>
```

## Backup System

- Automatic backup before each data modification
- Timestamped backup files in `backups/` directory
- Keeps last 10 backups per file
- Manual restore capability via API

## Logging

All operations are logged to:
- `kanban.log` (file)
- Console output

Log levels:
- INFO: Normal operations
- ERROR: Failures and exceptions
- WARNING: Non-critical issues

## Directory Structure

```
kanban/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── templates/            # HTML templates
│   ├── index.html       # Main board view
│   └── upload.html      # File upload page
├── uploads/             # Uploaded Excel files
├── backups/             # Automatic backups
└── kanban.log          # Application log
```

## Error Handling

The application includes comprehensive error handling:
- Invalid file format detection
- Missing column validation
- File not found handling
- Backup failure recovery
- Detailed error messages in API responses

## Security Considerations

- File size limited to 16MB
- Only .xlsx files accepted
- Filename sanitization
- Input validation on all endpoints

## Development

### Running in Debug Mode
```bash
python app.py
```

### Production Deployment

For production, use a WSGI server like Gunicorn:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

## Changelog

### Version 2.0 (Enhanced)
- ✅ Added comprehensive error handling
- ✅ Implemented automatic backup system
- ✅ Added logging throughout application
- ✅ Input validation and sanitization
- ✅ Backup management API
- ✅ Improved data validation
- ✅ File size limits
- ✅ Better error messages

### Version 1.0 (Original)
- Basic Kanban board functionality
- Excel file upload
- Drag & drop interface

## License

[Add your license here]

## Author

Gerald Fuchs

## Support

For issues or questions, please open an issue on GitHub.

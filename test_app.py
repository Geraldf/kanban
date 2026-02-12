"""
Unit tests for Kanban Board application.
"""

import unittest
import os
import tempfile
from pathlib import Path
import pandas as pd
from app import app, validate_excel_structure, create_backup, REQUIRED_COLUMNS


class KanbanTestCase(unittest.TestCase):
    """Test cases for Kanban Board application."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        
        # Create temporary test file
        self.test_data = pd.DataFrame({
            'Name': ['Alice', 'Bob', 'Charlie'],
            'Role': ['Developer', 'Manager', 'Developer'],
            'New JG': [3, 5, 3],
            'Proposed new Role for Manager Review': ['Senior Developer', 'Director', 'Senior Developer'],
            'Comment': ['Great work', 'Promotion ready', 'Needs training']
        })
        
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = Path(self.temp_dir) / 'test.xlsx'
        self.test_data.to_excel(self.test_file, index=False)
    
    def tearDown(self):
        """Clean up test fixtures."""
        if self.test_file.exists():
            self.test_file.unlink()
        Path(self.temp_dir).rmdir()
    
    def test_index_without_file(self):
        """Test index route without uploaded file."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'upload', response.data.lower())
    
    def test_validate_excel_structure_valid(self):
        """Test Excel validation with valid structure."""
        try:
            validate_excel_structure(self.test_data)
        except ValueError:
            self.fail("validate_excel_structure raised ValueError unexpectedly")
    
    def test_validate_excel_structure_invalid(self):
        """Test Excel validation with invalid structure."""
        invalid_data = pd.DataFrame({'Wrong': ['Column']})
        with self.assertRaises(ValueError):
            validate_excel_structure(invalid_data)
    
    def test_upload_valid_file(self):
        """Test uploading valid Excel file."""
        with open(self.test_file, 'rb') as f:
            response = self.client.post(
                '/api/upload',
                data={'file': (f, 'test.xlsx')},
                content_type='multipart/form-data'
            )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(data.get('entries'), 3)
    
    def test_upload_invalid_extension(self):
        """Test uploading file with wrong extension."""
        response = self.client.post(
            '/api/upload',
            data={'file': (tempfile.NamedTemporaryFile(suffix='.txt'), 'test.txt')},
            content_type='multipart/form-data'
        )
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn('error', data)
    
    def test_upload_no_file(self):
        """Test upload endpoint without file."""
        response = self.client.post('/api/upload')
        self.assertEqual(response.status_code, 400)
    
    def test_api_board_without_file(self):
        """Test board API without uploaded file."""
        response = self.client.get('/api/board')
        self.assertEqual(response.status_code, 500)
    
    def test_backup_creation(self):
        """Test backup file creation."""
        backup_path = create_backup(str(self.test_file))
        self.assertIsNotNone(backup_path)
        self.assertTrue(Path(backup_path).exists())
        # Cleanup
        if backup_path:
            Path(backup_path).unlink()
    
    def test_backup_nonexistent_file(self):
        """Test backup of non-existent file."""
        backup_path = create_backup('/nonexistent/file.xlsx')
        self.assertIsNone(backup_path)
    
    def test_api_move_no_data(self):
        """Test move API without JSON data."""
        response = self.client.post('/api/move')
        self.assertEqual(response.status_code, 400)
    
    def test_api_move_missing_name(self):
        """Test move API with missing name."""
        response = self.client.post(
            '/api/move',
            json={'new_role': 'Developer'}
        )
        self.assertEqual(response.status_code, 400)
    
    def test_list_backups(self):
        """Test listing backups."""
        response = self.client.get('/api/backups')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('backups', data)
        self.assertIn('count', data)


class DataIntegrityTestCase(unittest.TestCase):
    """Test data integrity and validation."""
    
    def test_required_columns_defined(self):
        """Test that required columns are properly defined."""
        self.assertIsInstance(REQUIRED_COLUMNS, list)
        self.assertGreater(len(REQUIRED_COLUMNS), 0)
        self.assertIn('Name', REQUIRED_COLUMNS)
        self.assertIn('Role', REQUIRED_COLUMNS)


if __name__ == '__main__':
    unittest.main()

"""
Configuration settings for Kanban Board application.
"""

import os
from pathlib import Path

class Config:
    """Base configuration."""
    
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    DEBUG = False
    TESTING = False
    
    # File upload settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    ALLOWED_EXTENSIONS = {'xlsx'}
    
    # Directory settings
    BASE_DIR = Path(__file__).parent.absolute()
    UPLOAD_DIR = BASE_DIR / "uploads"
    BACKUP_DIR = BASE_DIR / "backups"
    
    # Backup settings
    MAX_BACKUPS_PER_FILE = 10
    AUTO_BACKUP = True
    
    # Logging settings
    LOG_FILE = 'kanban.log'
    LOG_LEVEL = 'INFO'
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Excel column requirements
    REQUIRED_COLUMNS = [
        "Name",
        "Role",
        "New JG",
        "Proposed new Role for Manager Review",
        "Comment"
    ]


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    LOG_LEVEL = 'WARNING'
    # In production, always set SECRET_KEY via environment variable
    

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    DEBUG = True


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

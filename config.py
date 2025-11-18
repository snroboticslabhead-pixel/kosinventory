import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-2024'
    
    # MySQL configuration for PythonAnywhere
    MYSQL_HOST = os.environ.get('MYSQL_HOST') or 'inventorykos.mysql.pythonanywhere-services.com'
    MYSQL_USER = os.environ.get('MYSQL_USER') or 'inventorykos'
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD') or 'Krishna@532'
    MYSQL_DB = os.environ.get('MYSQL_DB') or 'inventorykos$default'
    
    DEBUG = False
    TESTING = False

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig

}

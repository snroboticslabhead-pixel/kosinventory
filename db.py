import pymysql
from flask import current_app
import contextlib

def get_db_connection():
    """Get MySQL database connection"""
    return pymysql.connect(
        host=current_app.config['MYSQL_HOST'],
        user=current_app.config['MYSQL_USER'],
        password=current_app.config['MYSQL_PASSWORD'],
        database=current_app.config['MYSQL_DB'],
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

@contextlib.contextmanager
def get_cursor():
    """Context manager for database cursor"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

def init_db():
    """Initialize database tables"""
    with get_cursor() as cursor:
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(80) UNIQUE NOT NULL,
                email VARCHAR(120) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                role ENUM('admin', 'trainer') NOT NULL,
                lab_id INT,
                lab_name VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Labs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS labs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                lab_id VARCHAR(50) UNIQUE NOT NULL,
                location VARCHAR(255),
                device_count INT DEFAULT 0,
                status ENUM('active', 'maintenance') DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Component groups table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS component_groups (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                color VARCHAR(7) DEFAULT '#6B7280',
                lab_id INT,
                lab_name VARCHAR(255),
                auto_created BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Components table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS components (
                id INT AUTO_INCREMENT PRIMARY KEY,
                uid VARCHAR(50) UNIQUE,
                name VARCHAR(255) NOT NULL,
                category VARCHAR(255) NOT NULL,
                lab VARCHAR(255) NOT NULL,
                lab_id INT NOT NULL,
                group_id INT,
                group_name VARCHAR(255),
                initial_quantity INT NOT NULL,
                current_quantity INT NOT NULL,
                status ENUM('available', 'low_stock', 'out_of_stock') DEFAULT 'available',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (lab_id) REFERENCES labs(id),
                FOREIGN KEY (group_id) REFERENCES component_groups(id)
            )
        ''')
        
        # Transactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                component_name VARCHAR(255) NOT NULL,
                component_uid VARCHAR(50),
                lab VARCHAR(255) NOT NULL,
                lab_id INT NOT NULL,
                issued_to VARCHAR(255) NOT NULL,
                campus VARCHAR(255),
                quantity_issued INT NOT NULL,
                quantity_returned INT DEFAULT 0,
                pending_quantity INT DEFAULT 0,
                status ENUM('issued', 'partially_returned', 'returned') DEFAULT 'issued',
                issue_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                return_date TIMESTAMP NULL,
                purpose TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (lab_id) REFERENCES labs(id)
            )
        ''')
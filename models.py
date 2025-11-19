from datetime import datetime
from db import get_cursor
import pymysql
from typing import List, Dict, Tuple, Optional

class User:
    @staticmethod
    def create_user(data):
        with get_cursor() as cursor:
            cursor.execute('''
                INSERT INTO users (username, email, password, role, lab_id, lab_name, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (
                data['username'],
                data['email'],
                data['password'],
                data.get('role', 'user'),
                data.get('lab_id'),
                data.get('lab_name'),
                datetime.utcnow()
            ))
            return cursor.lastrowid

    @staticmethod
    def find_by_username(username):
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
            return cursor.fetchone()

    @staticmethod
    def find_by_email(email):
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
            return cursor.fetchone()

    @staticmethod
    def get_trainers():
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM users WHERE role = "trainer"')
            return cursor.fetchall()

    @staticmethod
    def update_trainer_lab(trainer_id, lab_id, lab_name):
        with get_cursor() as cursor:
            cursor.execute('''
                UPDATE users 
                SET lab_id = %s, lab_name = %s 
                WHERE id = %s AND role = "trainer"
            ''', (lab_id, lab_name, trainer_id))
            return cursor.rowcount

class Lab:
    @staticmethod
    def get_all():
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM labs')
            return cursor.fetchall()

    @staticmethod
    def get_by_id(lab_id):
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM labs WHERE id = %s', (lab_id,))
            return cursor.fetchone()

    @staticmethod
    def get_by_name(lab_name):
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM labs WHERE name = %s', (lab_name,))
            return cursor.fetchone()

    @staticmethod
    def create(data):
        with get_cursor() as cursor:
            cursor.execute('''
                INSERT INTO labs (name, lab_id, location, device_count, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (
                data['name'],
                data['lab_id'],
                data['location'],
                data.get('device_count', 0),
                data.get('status', 'active'),
                datetime.utcnow()
            ))
            return cursor.lastrowid

    @staticmethod
    def update(lab_id, data):
        with get_cursor() as cursor:
            set_clause = ', '.join([f"{key} = %s" for key in data.keys()])
            values = list(data.values())
            values.append(lab_id)
            cursor.execute(f'UPDATE labs SET {set_clause} WHERE id = %s', values)
            return cursor.rowcount

    @staticmethod
    def delete(lab_id):
        with get_cursor() as cursor:
            cursor.execute('DELETE FROM labs WHERE id = %s', (lab_id,))
            return cursor.rowcount

class Component:
    @staticmethod
    def get_all():
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM components')
            return cursor.fetchall()

    @staticmethod
    def get_by_lab(lab_id):
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM components WHERE lab_id = %s', (lab_id,))
            return cursor.fetchall()

    @staticmethod
    def get_by_lab_and_group(lab_id, group_id):
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM components WHERE lab_id = %s AND group_id = %s', (lab_id, group_id))
            return cursor.fetchall()

    @staticmethod
    def get_paginated_components(page: int = 1, per_page: int = 20, 
                                lab_id: Optional[str] = None, 
                                group_id: Optional[str] = None) -> Tuple[List[Dict], int]:
        
        skip = (page - 1) * per_page
        
        # Build WHERE clause
        where_clauses = []
        params = []
        
        if lab_id:
            where_clauses.append("lab_id = %s")
            params.append(lab_id)
        
        if group_id:
            where_clauses.append("group_id = %s")
            params.append(group_id)
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # Get total count
        with get_cursor() as cursor:
            cursor.execute(f'SELECT COUNT(*) as total FROM components WHERE {where_sql}', params)
            total = cursor.fetchone()['total']
        
        # Get paginated data
        with get_cursor() as cursor:
            cursor.execute(f'''
                SELECT * FROM components 
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            ''', params + [per_page, skip])
            data = cursor.fetchall()
        
        return data, total

    @staticmethod
    def create(data):
        with get_cursor() as cursor:
            cursor.execute('''
                INSERT INTO components (uid, name, category, lab, lab_id, group_id, group_name, 
                                      initial_quantity, current_quantity, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                data.get('uid'),
                data['name'],
                data['category'],
                data['lab'],
                data['lab_id'],
                data.get('group_id'),
                data.get('group_name'),
                data['initial_quantity'],
                data['current_quantity'],
                data.get('status', 'available'),
                datetime.utcnow()
            ))
            return cursor.lastrowid

    @staticmethod
    def update(component_id, data):
        with get_cursor() as cursor:
            set_clause = ', '.join([f"{key} = %s" for key in data.keys()])
            values = list(data.values())
            values.append(component_id)
            cursor.execute(f'UPDATE components SET {set_clause} WHERE id = %s', values)
            return cursor.rowcount

    @staticmethod
    def delete(component_id):
        with get_cursor() as cursor:
            cursor.execute('DELETE FROM components WHERE id = %s', (component_id,))
            return cursor.rowcount

class ComponentGroup:
    @staticmethod
    def get_all():
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM component_groups')
            return cursor.fetchall()

    @staticmethod
    def get_by_lab(lab_id):
        with get_cursor() as cursor:
            cursor.execute('''
                SELECT * FROM component_groups 
                WHERE lab_id = %s OR lab_id IS NULL
            ''', (lab_id,))
            return cursor.fetchall()

    @staticmethod
    def create(data):
        with get_cursor() as cursor:
            cursor.execute('''
                INSERT INTO component_groups (name, description, color, lab_id, lab_name, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (
                data['name'],
                data.get('description', ''),
                data.get('color', '#6B7280'),
                data.get('lab_id'),
                data.get('lab_name'),
                datetime.utcnow()
            ))
            return cursor.lastrowid

    @staticmethod
    def update(group_id, data):
        with get_cursor() as cursor:
            set_clause = ', '.join([f"{key} = %s" for key in data.keys()])
            values = list(data.values())
            values.append(group_id)
            cursor.execute(f'UPDATE component_groups SET {set_clause} WHERE id = %s', values)
            return cursor.rowcount

    @staticmethod
    def delete(group_id):
        with get_cursor() as cursor:
            cursor.execute('DELETE FROM component_groups WHERE id = %s', (group_id,))
            return cursor.rowcount

class Transaction:
    @staticmethod
    def get_all():
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM transactions ORDER BY issue_date DESC')
            return cursor.fetchall()

    @staticmethod
    def get_by_lab(lab_id):
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM transactions WHERE lab_id = %s ORDER BY issue_date DESC', (lab_id,))
            return cursor.fetchall()

    @staticmethod
    def create(data):
        with get_cursor() as cursor:
            cursor.execute('''
                INSERT INTO transactions (component_name, component_uid, lab, lab_id, issued_to, campus,
                                        quantity_issued, quantity_returned, pending_quantity, status, 
                                        issue_date, return_date, purpose)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                data['component_name'],
                data.get('component_uid', ''),
                data['lab'],
                data['lab_id'],
                data['issued_to'],
                data.get('campus', ''),
                data['quantity_issued'],
                data.get('quantity_returned', 0),
                data.get('pending_quantity', data['quantity_issued']),
                data.get('status', 'issued'),
                data.get('issue_date', datetime.utcnow()),
                data.get('return_date'),
                data.get('purpose', '')
            ))
            return cursor.lastrowid

    @staticmethod
    def update(transaction_id, data):
        with get_cursor() as cursor:
            set_clause = ', '.join([f"{key} = %s" for key in data.keys()])
            values = list(data.values())
            values.append(transaction_id)
            cursor.execute(f'UPDATE transactions SET {set_clause} WHERE id = %s', values)
            return cursor.rowcount

    @staticmethod
    def delete(transaction_id):
        with get_cursor() as cursor:
            cursor.execute('DELETE FROM transactions WHERE id = %s', (transaction_id,))
            return cursor.rowcount

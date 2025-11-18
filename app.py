from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from models import User, Lab, Component, Transaction, ComponentGroup
from config import config
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import pytz
import pandas as pd
import io
import csv
from werkzeug.utils import secure_filename
from functools import wraps
import re
from db import init_db, get_cursor

app = Flask(__name__)
app.config.from_object(config['development'])

# Initialize database
with app.app_context():
    init_db()

# Custom Jinja2 filters
@app.template_filter('timezone_filter')
def timezone_filter(dt, timezone='Asia/Kolkata'):
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(pytz.timezone(timezone))

@app.template_filter('datetime_format')
def datetime_format(dt, format='%Y-%m-%d %H:%M'):
    if dt is None:
        return None
    return dt.strftime(format)

@app.template_filter('date_format')
def date_format(dt, format='%Y-%m-%d'):
    if dt is None:
        return None
    return dt.strftime(format)

# Context processor to make current time available in all templates
@app.context_processor
def inject_now():
    return {'now': datetime.now(pytz.timezone('Asia/Kolkata'))}

# Helper functions for data normalization
def normalize_string(s):
    """Normalize string by trimming and converting to lowercase for comparison"""
    if not s or not isinstance(s, str):
        return ""
    return s.strip().lower()

def find_or_create_category(category_name, existing_categories):
    """Find existing category or create a new normalized one"""
    normalized_name = normalize_string(category_name)
    
    # Check if category exists (case-insensitive)
    for existing_category in existing_categories:
        if normalize_string(existing_category) == normalized_name:
            return existing_category
    
    # Return the original name with proper capitalization
    return category_name.strip().title()

def find_or_create_group(group_name, lab_id, lab_name, existing_groups):
    """Find existing group or create a new one"""
    if not group_name or not isinstance(group_name, str):
        return None
    
    normalized_name = normalize_string(group_name)
    
    # Check if group exists for this lab (case-insensitive)
    for group in existing_groups:
        if (normalize_string(group['name']) == normalized_name and 
            group.get('lab_id') == lab_id):
            return group['id']
    
    # Create new group
    group_data = {
        'name': group_name.strip().title(),
        'description': f'Auto-created group for {lab_name}',
        'color': '#6B7280',  # Default gray color
        'lab_id': lab_id,
        'lab_name': lab_name,
        'auto_created': True
    }
    
    group_id = ComponentGroup.create(group_data)
    return group_id

# UID Generation functions - FIXED VERSION
def generate_component_uid(lab_id, component_name, existing_components):
    """Generate unique UID for component based on lab and component type"""
    # Get lab details
    lab = Lab.get_by_id(lab_id)
    if not lab:
        return None
    
    # Extract lab number from lab_id (LAB-001 -> L1, LAB-002 -> L2, etc.)
    lab_number_match = re.search(r'(\d+)', lab['lab_id'])
    if lab_number_match:
        lab_number = lab_number_match.group(1).lstrip('0') or '1'
        lab_code = f"L{lab_number}"
    else:
        # Fallback: use first 2 letters of lab name
        lab_code = lab['name'][:2].upper()
    
    # Get existing UIDs to avoid duplicates
    existing_uids = set()
    for comp in existing_components:
        if comp.get('uid'):
            existing_uids.add(comp['uid'])
    
    # Find the next available sequence number
    sequence_number = 1
    while True:
        uid = f"COM{lab_code}-{sequence_number:03d}"
        if uid not in existing_uids:
            return uid
        sequence_number += 1
        if sequence_number > 999:  # Safety limit
            break
    
    # Fallback: use timestamp if all sequence numbers are taken
    timestamp = int(datetime.utcnow().timestamp())
    return f"COM{lab_code}-{timestamp}"

def assign_uids_to_existing_components():
    """Assign UIDs to all existing components that don't have them"""
    existing_components = Component.get_all()
    components_without_uid = [c for c in existing_components if not c.get('uid')]
    
    print(f"Found {len(components_without_uid)} components without UIDs")
    
    for component in components_without_uid:
        uid = generate_component_uid(
            component['lab_id'], 
            component['name'], 
            existing_components
        )
        if uid:
            try:
                Component.update(component['id'], {'uid': uid})
                print(f"Assigned UID {uid} to component {component['name']}")
                # Update our local list to avoid duplicates
                component['uid'] = uid
            except Exception as e:
                print(f"Error assigning UID to component {component['name']}: {str(e)}")

# Sample data initialization - FIXED VERSION
def init_sample_data():
    with get_cursor() as cursor:
        cursor.execute('SELECT COUNT(*) as count FROM users')
        user_count = cursor.fetchone()['count']
        
        if user_count == 0:
            print("Initializing sample data...")
            
            # Create admin user
            admin_user_id = User.create_user({
                'username': 'admin',
                'email': 'admin@lab.com',
                'password': generate_password_hash('admin123'),
                'role': 'admin'
            })
            print("Created admin user")
            
            # Create sample labs
            sample_labs = [
                {
                    'name': 'Robotics Lab A',
                    'lab_id': 'LAB-001',
                    'location': 'Room 101',
                    'device_count': 15,
                    'status': 'active'
                },
                {
                    'name': 'IoT Prototyping Zone',
                    'lab_id': 'LAB-002',
                    'location': 'Building C, Floor 2',
                    'device_count': 25,
                    'status': 'active'
                },
                {
                    'name': 'Automation Hub',
                    'lab_id': 'LAB-003',
                    'location': 'Room 105',
                    'device_count': 8,
                    'status': 'maintenance'
                }
            ]
            
            for lab_data in sample_labs:
                Lab.create(lab_data)
            
            labs = Lab.get_all()
            print(f"Created {len(labs)} labs")
            
            # Create sample trainer users with proper lab assignment
            trainer_users = [
                {
                    'username': 'trainer1',
                    'email': 'trainer1@lab.com',
                    'password': generate_password_hash('trainer123'),
                    'role': 'trainer',
                    'lab_id': labs[0]['id'],
                    'lab_name': labs[0]['name']
                },
                {
                    'username': 'trainer2',
                    'email': 'trainer2@lab.com',
                    'password': generate_password_hash('trainer123'),
                    'role': 'trainer',
                    'lab_id': labs[1]['id'],
                    'lab_name': labs[1]['name']
                }
            ]
            
            for trainer_data in trainer_users:
                User.create_user(trainer_data)
            print("Created trainer users")
            
            # Create sample component groups
            sample_groups = [
                {
                    'name': 'Project Design',
                    'description': 'Components used for project design and prototyping',
                    'color': '#3B82F6'
                },
                {
                    'name': 'Practical Implementation',
                    'description': 'Components used for hands-on practical sessions',
                    'color': '#10B981'
                }
            ]
            
            group_map = {}
            for group_data in sample_groups:
                group_id = ComponentGroup.create(group_data)
                group_map[group_data['name']] = group_id
            
            groups = ComponentGroup.get_all()
            print("Created component groups")
            
            # Create sample components for each lab - WITH PRE-ASSIGNED UIDs
            sample_components = [
                # Components for Robotics Lab A (LAB-001)
                {
                    'uid': 'COML1-001',
                    'name': 'Arduino Uno R3',
                    'category': 'Microcontrollers',
                    'lab': 'Robotics Lab A',
                    'lab_id': labs[0]['id'],
                    'group_id': group_map['Project Design'],
                    'group_name': 'Project Design',
                    'initial_quantity': 50,
                    'current_quantity': 42,
                    'status': 'available'
                },
                {
                    'uid': 'COML1-002',
                    'name': 'SG90 Micro Servo Motor',
                    'category': 'Actuators',
                    'lab': 'Robotics Lab A',
                    'lab_id': labs[0]['id'],
                    'group_id': group_map['Practical Implementation'],
                    'group_name': 'Practical Implementation',
                    'initial_quantity': 75,
                    'current_quantity': 61,
                    'status': 'available'
                },
                # Components for IoT Prototyping Zone (LAB-002)
                {
                    'uid': 'COML2-001',
                    'name': 'Raspberry Pi 4',
                    'category': 'Microcontrollers',
                    'lab': 'IoT Prototyping Zone',
                    'lab_id': labs[1]['id'],
                    'group_id': group_map['Project Design'],
                    'group_name': 'Project Design',
                    'initial_quantity': 25,
                    'current_quantity': 4,
                    'status': 'low_stock'
                },
                {
                    'uid': 'COML2-002',
                    'name': 'HC-SR04 Ultrasonic Sensor',
                    'category': 'Sensors',
                    'lab': 'IoT Prototyping Zone',
                    'lab_id': labs[1]['id'],
                    'group_id': group_map['Practical Implementation'],
                    'group_name': 'Practical Implementation',
                    'initial_quantity': 100,
                    'current_quantity': 89,
                    'status': 'available'
                },
                {
                    'uid': 'COML2-003',
                    'name': 'DHT22 Temperature Sensor',
                    'category': 'Sensors',
                    'lab': 'IoT Prototyping Zone',
                    'lab_id': labs[1]['id'],
                    'group_id': group_map['Practical Implementation'],
                    'group_name': 'Practical Implementation',
                    'initial_quantity': 60,
                    'current_quantity': 45,
                    'status': 'available'
                },
                # Components for Automation Hub (LAB-003) - No trainer assigned
                {
                    'uid': 'COML3-001',
                    'name': 'PLC Trainer Kit',
                    'category': 'Controllers',
                    'lab': 'Automation Hub',
                    'lab_id': labs[2]['id'],
                    'initial_quantity': 10,
                    'current_quantity': 10,
                    'status': 'available'
                }
            ]
            
            for component_data in sample_components:
                Component.create(component_data)
            print("Created sample components with pre-assigned UIDs")
            
            # Create sample transactions with pending_quantity field
            sample_transactions = [
                {
                    'component_name': 'Arduino Uno R3',
                    'component_uid': 'COML1-001',
                    'lab': 'Robotics Lab A',
                    'lab_id': labs[0]['id'],
                    'issued_to': 'John Doe',
                    'campus': 'Main Campus',
                    'quantity_issued': 5,
                    'quantity_returned': 5,
                    'pending_quantity': 0,
                    'status': 'returned',
                    'issue_date': datetime.utcnow() - timedelta(days=5),
                    'return_date': datetime.utcnow() - timedelta(days=2),
                    'purpose': 'Student project'
                },
                {
                    'component_name': 'Raspberry Pi 4',
                    'component_uid': 'COML2-001',
                    'lab': 'IoT Prototyping Zone',
                    'lab_id': labs[1]['id'],
                    'issued_to': 'Jane Smith',
                    'campus': 'North Campus',
                    'quantity_issued': 2,
                    'quantity_returned': 1,
                    'pending_quantity': 1,
                    'status': 'partially_returned',
                    'issue_date': datetime.utcnow() - timedelta(days=3),
                    'purpose': 'Research project'
                }
            ]
            
            for transaction_data in sample_transactions:
                Transaction.create(transaction_data)
            print("Created sample transactions")
            
            print("Sample data initialization completed!")
        else:
            print("Sample data already exists, skipping initialization.")
            # Still assign UIDs to any components that might be missing them
            assign_uids_to_existing_components()

# Role-based access control decorator
def requires_role(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if session.get('role') not in roles:
                flash('Access denied. Insufficient permissions.', 'error')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Trainer lab access restriction
def requires_trainer_lab_access(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') == 'trainer':
            trainer_lab_id = session.get('lab_id')
            if not trainer_lab_id:
                flash('No lab assigned. Please contact administrator.', 'error')
                return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'admin')
        
        user = User.find_by_username(username)
        if user and user['role'] == role and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            
            # Store lab info for trainers
            if user['role'] == 'trainer':
                session['lab_id'] = user.get('lab_id')
                session['lab_name'] = user.get('lab_name', '')
                print(f"Trainer {username} logged in with lab: {session['lab_name']} (ID: {session['lab_id']})")
            
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username, password, or role selection', 'error')
    
    return render_template('login.html', hide_sidebar=True)

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Get stats based on user role
    if session.get('role') == 'admin':
        # Admin sees all stats
        with get_cursor() as cursor:
            cursor.execute('SELECT COUNT(*) as count FROM labs')
            total_labs = cursor.fetchone()['count']
            
            cursor.execute('SELECT COUNT(*) as count FROM components')
            total_components = cursor.fetchone()['count']
            
            cursor.execute('SELECT COUNT(*) as count FROM users WHERE role = "trainer"')
            total_trainers = cursor.fetchone()['count']
            
            # Get transactions from today
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            cursor.execute('SELECT COUNT(*) as count FROM transactions WHERE issue_date >= %s', (today_start,))
            issued_today = cursor.fetchone()['count']
            
            # Get low stock components (less than 10)
            cursor.execute('SELECT COUNT(*) as count FROM components WHERE current_quantity < 10')
            low_stock = cursor.fetchone()['count']
            
            # Get pending returns (transactions with pending_quantity > 0)
            cursor.execute('SELECT COUNT(*) as count FROM transactions WHERE pending_quantity > 0')
            pending_returns = cursor.fetchone()['count']
            
            # Get overdue items
            overdue_threshold = datetime.utcnow() - timedelta(days=14)
            cursor.execute('SELECT COUNT(*) as count FROM transactions WHERE issue_date < %s AND pending_quantity > 0', 
                          (overdue_threshold,))
            overdue_count = cursor.fetchone()['count']
            
            # Get recent transactions
            cursor.execute('SELECT * FROM transactions ORDER BY issue_date DESC LIMIT 5')
            recent_transactions = cursor.fetchall()
        
        return render_template('dashboard.html',
                             total_labs=total_labs,
                             total_components=total_components,
                             total_trainers=total_trainers,
                             issued_today=issued_today,
                             low_stock=low_stock,
                             pending_returns=pending_returns,
                             overdue_count=overdue_count,
                             recent_transactions=recent_transactions,
                             user_role='admin')
    
    else:  # Trainer
        # Trainer sees only their lab stats
        lab_id = session.get('lab_id')
        lab_name = session.get('lab_name')
        
        if not lab_id:
            flash('No lab assigned. Please contact administrator.', 'error')
            return render_template('dashboard.html', user_role='trainer')
        
        print(f"Fetching data for trainer's lab: {lab_name} (ID: {lab_id})")
        
        with get_cursor() as cursor:
            # Get components count for trainer's lab
            cursor.execute('SELECT COUNT(*) as count FROM components WHERE lab_id = %s', (lab_id,))
            total_components = cursor.fetchone()['count']
            print(f"Total components in {lab_name}: {total_components}")
            
            # Get low stock components for trainer's lab
            cursor.execute('SELECT COUNT(*) as count FROM components WHERE lab_id = %s AND current_quantity < 10', (lab_id,))
            low_stock = cursor.fetchone()['count']
            
            # Get today's transactions for trainer's lab
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            cursor.execute('SELECT COUNT(*) as count FROM transactions WHERE lab_id = %s AND issue_date >= %s', 
                          (lab_id, today_start))
            issued_today = cursor.fetchone()['count']
            
            # Get pending returns for trainer's lab
            cursor.execute('SELECT COUNT(*) as count FROM transactions WHERE lab_id = %s AND pending_quantity > 0', (lab_id,))
            pending_returns = cursor.fetchone()['count']
            
            # Get overdue items for trainer's lab
            overdue_threshold = datetime.utcnow() - timedelta(days=14)
            cursor.execute('SELECT COUNT(*) as count FROM transactions WHERE lab_id = %s AND issue_date < %s AND pending_quantity > 0', 
                          (lab_id, overdue_threshold))
            overdue_count = cursor.fetchone()['count']
            
            # Get recent transactions for trainer's lab
            cursor.execute('SELECT * FROM transactions WHERE lab_id = %s ORDER BY issue_date DESC LIMIT 5', (lab_id,))
            recent_transactions = cursor.fetchall()
        
        return render_template('dashboard.html',
                             lab_name=lab_name,
                             total_components=total_components,
                             issued_today=issued_today,
                             low_stock=low_stock,
                             pending_returns=pending_returns,
                             overdue_count=overdue_count,
                             recent_transactions=recent_transactions,
                             user_role='trainer')

# Trainer Management Routes (Admin only)
@app.route('/trainers')
@requires_role(['admin'])
def trainers():
    trainers_list = User.get_trainers()
    labs_list = Lab.get_all()
    
    return render_template('trainers.html', trainers=trainers_list, labs=labs_list)

@app.route('/api/trainers', methods=['POST'])
@requires_role(['admin'])
def create_trainer():
    data = request.get_json()
    
    # Check if username already exists
    existing_user = User.find_by_username(data['username'])
    if existing_user:
        return jsonify({'error': 'Username already exists'}), 400
    
    # Get lab details
    lab = Lab.get_by_id(data['lab_id'])
    if not lab:
        return jsonify({'error': 'Lab not found'}), 404
    
    trainer_data = {
        'username': data['username'],
        'email': data['email'],
        'password': generate_password_hash(data['password']),
        'role': 'trainer',
        'lab_id': data['lab_id'],
        'lab_name': lab['name']
    }
    
    trainer_id = User.create_user(trainer_data)
    return jsonify({'message': 'Trainer created successfully', 'id': trainer_id}), 201

@app.route('/api/trainers/<trainer_id>', methods=['PUT'])
@requires_role(['admin'])
def update_trainer(trainer_id):
    data = request.get_json()
    
    update_data = {}
    if 'username' in data:
        update_data['username'] = data['username']
    if 'email' in data:
        update_data['email'] = data['email']
    if 'password' in data and data['password']:
        update_data['password'] = generate_password_hash(data['password'])
    if 'lab_id' in data:
        lab = Lab.get_by_id(data['lab_id'])
        if not lab:
            return jsonify({'error': 'Lab not found'}), 404
        update_data['lab_id'] = data['lab_id']
        update_data['lab_name'] = lab['name']
    
    with get_cursor() as cursor:
        set_clause = ', '.join([f"{key} = %s" for key in update_data.keys()])
        values = list(update_data.values())
        values.append(trainer_id)
        cursor.execute(f'UPDATE users SET {set_clause} WHERE id = %s AND role = "trainer"', values)
        
        if cursor.rowcount:
            return jsonify({'message': 'Trainer updated successfully'}), 200
        else:
            return jsonify({'error': 'Trainer not found'}), 404

@app.route('/api/trainers/<trainer_id>', methods=['DELETE'])
@requires_role(['admin'])
def delete_trainer(trainer_id):
    with get_cursor() as cursor:
        cursor.execute('DELETE FROM users WHERE id = %s AND role = "trainer"', (trainer_id,))
        
        if cursor.rowcount:
            return jsonify({'message': 'Trainer deleted successfully'}), 200
        else:
            return jsonify({'error': 'Trainer not found'}), 404

@app.route('/api/trainers/<trainer_id>', methods=['GET'])
@requires_role(['admin'])
def get_trainer(trainer_id):
    with get_cursor() as cursor:
        cursor.execute('SELECT * FROM users WHERE id = %s AND role = "trainer"', (trainer_id,))
        trainer = cursor.fetchone()
        
        if trainer:
            return jsonify(trainer)
        else:
            return jsonify({'error': 'Trainer not found'}), 404

# Labs Route (Admin only)
@app.route('/labs')
@requires_role(['admin'])
def labs():
    labs_list = Lab.get_all()
    
    # Calculate device counts for each lab
    for lab in labs_list:
        with get_cursor() as cursor:
            cursor.execute('SELECT COUNT(*) as count FROM components WHERE lab_id = %s', (lab['id'],))
            device_count = cursor.fetchone()['count']
        lab['device_count'] = device_count
    
    return render_template('labs.html', labs=labs_list)

# Components Route (Both Admin and Trainer)
@app.route('/components')
@requires_role(['admin', 'trainer'])
@requires_trainer_lab_access
def components():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Build query based on user role
    if session.get('role') == 'admin':
        components_list, total_components = Component.get_paginated_components(page=page, per_page=per_page)
        labs_list = Lab.get_all()
    else:  # Trainer
        lab_id = session.get('lab_id')
        lab_name = session.get('lab_name')
        components_list, total_components = Component.get_paginated_components(page=page, per_page=per_page, lab_id=lab_id)
        labs_list = [{'name': lab_name, 'id': lab_id}]
        print(f"Trainer viewing components for lab: {lab_name}, found {len(components_list)} components")
    
    groups_list = ComponentGroup.get_all()
    
    # Calculate pagination
    total_pages = (total_components + per_page - 1) // per_page
    
    return render_template('components.html', 
                         components=components_list,
                         labs=labs_list,
                         groups=groups_list,
                         current_page=page,
                         total_pages=total_pages,
                         total_components=total_components)

@app.route('/components/by-group/<group_id>')
@requires_role(['admin', 'trainer'])
@requires_trainer_lab_access
def components_by_group(group_id):
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Get the group details
    with get_cursor() as cursor:
        cursor.execute('SELECT * FROM component_groups WHERE id = %s', (group_id,))
        group = cursor.fetchone()
    
    if not group:
        flash('Component group not found', 'error')
        return redirect(url_for('component_groups'))
    
    # Build query based on user role
    if session.get('role') == 'admin':
        components_list, total_components = Component.get_paginated_components(page=page, per_page=per_page, group_id=group_id)
        labs_list = Lab.get_all()
    else:  # Trainer
        lab_id = session.get('lab_id')
        lab_name = session.get('lab_name')
        components_list, total_components = Component.get_paginated_components(page=page, per_page=per_page, lab_id=lab_id, group_id=group_id)
        labs_list = [{'name': lab_name, 'id': lab_id}]
    
    groups_list = ComponentGroup.get_all()
    
    # Calculate pagination
    total_pages = (total_components + per_page - 1) // per_page
    
    return render_template('components.html', 
                         components=components_list,
                         labs=labs_list,
                         groups=groups_list,
                         current_group=group,
                         show_group_filter=False,
                         current_page=page,
                         total_pages=total_pages,
                         total_components=total_components)

# Component Groups Route (Both Admin and Trainer)
@app.route('/component-groups')
@requires_role(['admin', 'trainer'])
@requires_trainer_lab_access
def component_groups():
    # Build query based on user role
    if session.get('role') == 'admin':
        groups_list = ComponentGroup.get_all()
    else:  # Trainer
        lab_id = session.get('lab_id')
        groups_list = ComponentGroup.get_by_lab(lab_id)
    
    # Calculate component counts for each group based on user role
    for group in groups_list:
        if session.get('role') == 'admin':
            with get_cursor() as cursor:
                cursor.execute('SELECT COUNT(*) as count FROM components WHERE group_id = %s', (group['id'],))
                component_count = cursor.fetchone()['count']
        else:  # Trainer
            lab_id = session.get('lab_id')
            with get_cursor() as cursor:
                cursor.execute('SELECT COUNT(*) as count FROM components WHERE group_id = %s AND lab_id = %s', 
                              (group['id'], lab_id))
                component_count = cursor.fetchone()['count']
        group['component_count'] = component_count
    
    return render_template('component_groups.html', groups=groups_list)

# Issue & Return Route (Both Admin and Trainer)
@app.route('/issue-return')
@requires_role(['admin', 'trainer'])
@requires_trainer_lab_access
def issue_return():
    # Build query based on user role
    if session.get('role') == 'admin':
        transactions = Transaction.get_all()
        labs_list = Lab.get_all()
        components_list = Component.get_all()
    else:  # Trainer
        lab_id = session.get('lab_id')
        lab_name = session.get('lab_name')
        transactions = Transaction.get_by_lab(lab_id)
        labs_list = [{'name': lab_name, 'id': lab_id}]
        components_list = Component.get_by_lab(lab_id)
        print(f"Trainer viewing transactions for lab: {lab_name}, found {len(transactions)} transactions")
    
    # Ensure all transactions have pending_quantity field
    for transaction in transactions:
        if 'pending_quantity' not in transaction:
            transaction['pending_quantity'] = transaction['quantity_issued'] - transaction.get('quantity_returned', 0)
    
    return render_template('issue_return.html', 
                         transactions=transactions,
                         labs=labs_list,
                         components=components_list)

# Overdue Items Route (Both Admin and Trainer)
@app.route('/overdue-items')
@requires_role(['admin', 'trainer'])
@requires_trainer_lab_access
def overdue_items():
    # Calculate overdue items (issued for more than 14 days and not fully returned)
    overdue_threshold = datetime.utcnow() - timedelta(days=14)
    
    # Build query based on user role
    if session.get('role') == 'admin':
        with get_cursor() as cursor:
            cursor.execute('''
                SELECT * FROM transactions 
                WHERE issue_date < %s AND pending_quantity > 0 
                ORDER BY issue_date ASC
            ''', (overdue_threshold,))
            overdue_transactions = cursor.fetchall()
    else:  # Trainer
        lab_id = session.get('lab_id')
        with get_cursor() as cursor:
            cursor.execute('''
                SELECT * FROM transactions 
                WHERE lab_id = %s AND issue_date < %s AND pending_quantity > 0 
                ORDER BY issue_date ASC
            ''', (lab_id, overdue_threshold))
            overdue_transactions = cursor.fetchall()
    
    # Calculate overdue stats
    total_overdue = len(overdue_transactions)
    total_overdue_value = 0
    
    return render_template('overdue_items.html', 
                         overdue_items=overdue_transactions,
                         total_overdue=total_overdue,
                         total_overdue_value=total_overdue_value)

# Reports Route (Both Admin and Trainer)
@app.route('/reports')
@requires_role(['admin', 'trainer'])
@requires_trainer_lab_access
def reports():
    # Build query based on user role
    if session.get('role') == 'admin':
        with get_cursor() as cursor:
            cursor.execute('SELECT COUNT(*) as count FROM components')
            total_components = cursor.fetchone()['count']
            cursor.execute('SELECT COUNT(*) as count FROM labs')
            total_labs = cursor.fetchone()['count']
        components = Component.get_all()
    else:  # Trainer
        lab_id = session.get('lab_id')
        with get_cursor() as cursor:
            cursor.execute('SELECT COUNT(*) as count FROM components WHERE lab_id = %s', (lab_id,))
            total_components = cursor.fetchone()['count']
        total_labs = 1  # Trainer only has one lab
        components = Component.get_by_lab(lab_id)
    
    # Component usage statistics
    usage_stats = []
    
    for component in components:
        if session.get('role') == 'admin':
            with get_cursor() as cursor:
                cursor.execute('SELECT * FROM transactions WHERE component_name = %s', (component['name'],))
                transactions = cursor.fetchall()
        else:  # Trainer
            with get_cursor() as cursor:
                cursor.execute('SELECT * FROM transactions WHERE component_name = %s AND lab_id = %s', 
                              (component['name'], session.get('lab_id')))
                transactions = cursor.fetchall()
        
        total_issued = sum(t['quantity_issued'] for t in transactions)
        usage_rate = (total_issued / component['initial_quantity']) * 100 if component['initial_quantity'] > 0 else 0
        
        usage_stats.append({
            'name': component['name'],
            'uid': component.get('uid', 'N/A'),
            'category': component['category'],
            'lab': component['lab'],
            'group': component.get('group_name', 'N/A'),
            'initial_quantity': component['initial_quantity'],
            'current_quantity': component['current_quantity'],
            'total_issued': total_issued,
            'usage_rate': usage_rate
        })
    
    # Monthly issue trends (last 6 months)
    monthly_trends = []
    for i in range(5, -1, -1):
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0) - relativedelta(months=i)
        month_end = month_start + relativedelta(months=1) - timedelta(days=1)
        
        # Build query based on user role
        if session.get('role') == 'admin':
            with get_cursor() as cursor:
                cursor.execute('SELECT COUNT(*) as count FROM transactions WHERE issue_date BETWEEN %s AND %s', 
                              (month_start, month_end))
                monthly_issues = cursor.fetchone()['count']
        else:  # Trainer
            with get_cursor() as cursor:
                cursor.execute('SELECT COUNT(*) as count FROM transactions WHERE lab_id = %s AND issue_date BETWEEN %s AND %s', 
                              (session.get('lab_id'), month_start, month_end))
                monthly_issues = cursor.fetchone()['count']
        
        monthly_trends.append({
            'month': month_start.strftime('%b %Y'),
            'issues': monthly_issues
        })
    
    return render_template('reports.html',
                         total_components=total_components,
                         total_labs=total_labs,
                         usage_stats=usage_stats,
                         monthly_trends=monthly_trends)

# Export Components Route (Both Admin and Trainer)
@app.route('/export-components')
@requires_role(['admin', 'trainer'])
@requires_trainer_lab_access
def export_components():
    # Build query based on user role
    if session.get('role') == 'admin':
        components = Component.get_all()
    else:  # Trainer
        lab_id = session.get('lab_id')
        components = Component.get_by_lab(lab_id)
    
    # Create a CSV string
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['UID', 'Name', 'Category', 'Lab', 'Group', 'Initial Quantity', 'Current Quantity', 'Status', 'Created At'])
    
    # Write data
    for component in components:
        created_at = component['created_at']
        if isinstance(created_at, datetime):
            if created_at.tzinfo is None:
                created_at = pytz.utc.localize(created_at)
            created_at = created_at.astimezone(pytz.timezone('Asia/Kolkata'))
            created_at_str = created_at.strftime('%Y-%m-%d %H:%M:%S')
        else:
            created_at_str = str(created_at)
        
        writer.writerow([
            component.get('uid', 'N/A'),
            component['name'],
            component['category'],
            component['lab'],
            component.get('group_name', 'N/A'),
            component['initial_quantity'],
            component['current_quantity'],
            component['status'],
            created_at_str
        ])
    
    # Create response
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=components_export.csv'
    response.headers['Content-type'] = 'text/csv'
    return response

# Import Components Route (Both Admin and Trainer)
@app.route('/import-components', methods=['POST'])
@requires_role(['admin', 'trainer'])
@requires_trainer_lab_access
def import_components():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    # Check file extension
    allowed_extensions = {'csv', 'xlsx', 'xls'}
    if not file.filename.split('.')[-1].lower() in allowed_extensions:
        return jsonify({'error': 'Invalid file type. Only CSV, XLSX, and XLS files are allowed.'}), 400
    
    try:
        # Read the file based on its extension
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        # Check required columns
        required_columns = ['name', 'category', 'lab', 'initial_quantity', 'current_quantity']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return jsonify({
                'error': f'Missing required columns: {", ".join(missing_columns)}',
                'required_columns': required_columns + ['group (optional)', 'uid (optional)']
            }), 400
        
        # Get existing data for normalization
        existing_labs = Lab.get_all()
        existing_groups = ComponentGroup.get_all()
        
        with get_cursor() as cursor:
            cursor.execute('SELECT DISTINCT category FROM components')
            existing_categories = [row['category'] for row in cursor.fetchall()]
        
        existing_components = Component.get_all()
        
        # Clean and validate data
        imported_count = 0
        errors = []
        
        for index, row in df.iterrows():
            try:
                # Validate required fields
                if pd.isna(row['name']) or pd.isna(row['category']) or pd.isna(row['lab']):
                    errors.append(f"Row {index + 1}: Missing required fields (name, category, or lab)")
                    continue
                
                # Validate quantities
                try:
                    initial_quantity = int(row['initial_quantity'])
                    current_quantity = int(row['current_quantity'])
                except (ValueError, TypeError):
                    errors.append(f"Row {index + 1}: Invalid quantity values")
                    continue
                
                if initial_quantity < 0 or current_quantity < 0:
                    errors.append(f"Row {index + 1}: Quantity values must be non-negative")
                    continue
                
                # Normalize and validate lab name
                lab_name = str(row['lab']).strip()
                lab = None
                
                # Find lab by name (case-insensitive)
                for existing_lab in existing_labs:
                    if normalize_string(existing_lab['name']) == normalize_string(lab_name):
                        lab = existing_lab
                        break
                
                if not lab:
                    errors.append(f"Row {index + 1}: Lab '{lab_name}' not found")
                    continue
                
                # For trainers, ensure they can only import to their assigned lab
                if session.get('role') == 'trainer':
                    trainer_lab_id = session.get('lab_id')
                    if lab['id'] != trainer_lab_id:
                        errors.append(f"Row {index + 1}: You can only import components for your assigned lab '{session.get('lab_name')}'")
                        continue
                
                # Normalize category
                category = find_or_create_category(row['category'], existing_categories)
                
                # Handle UID assignment
                uid = None
                if 'uid' in df.columns and not pd.isna(row['uid']):
                    uid = str(row['uid']).strip()
                    # Check if UID already exists
                    with get_cursor() as cursor:
                        cursor.execute('SELECT id FROM components WHERE uid = %s', (uid,))
                        existing_component_with_uid = cursor.fetchone()
                    if existing_component_with_uid:
                        errors.append(f"Row {index + 1}: UID '{uid}' already exists")
                        continue
                else:
                    # Generate UID if not provided
                    uid = generate_component_uid(lab['id'], str(row['name']).strip(), existing_components)
                
                # Handle group assignment with auto-creation
                group_data = {}
                if 'group' in df.columns and not pd.isna(row['group']):
                    group_name = str(row['group']).strip()
                    if group_name:  # Only process if group name is not empty
                        group_id = find_or_create_group(group_name, lab['id'], lab['name'], existing_groups)
                        if group_id:
                            with get_cursor() as cursor:
                                cursor.execute('SELECT * FROM component_groups WHERE id = %s', (group_id,))
                                group = cursor.fetchone()
                            group_data = {
                                'group_id': group_id,
                                'group_name': group['name']
                            }
                            # Update existing_groups for subsequent rows
                            existing_groups.append(group)
                
                # Determine status based on current quantity
                status = 'available' if current_quantity >= 10 else 'low_stock'
                if current_quantity == 0:
                    status = 'out_of_stock'
                
                # Check if component already exists
                with get_cursor() as cursor:
                    cursor.execute('SELECT id FROM components WHERE name = %s AND lab_id = %s', 
                                  (str(row['name']).strip(), lab['id']))
                    existing_component = cursor.fetchone()
                
                if existing_component:
                    # Update existing component
                    update_data = {
                        'category': category,
                        'initial_quantity': initial_quantity,
                        'current_quantity': current_quantity,
                        'status': status
                    }
                    if uid:
                        update_data['uid'] = uid
                    update_data.update(group_data)
                    
                    Component.update(existing_component['id'], update_data)
                    imported_count += 1
                    errors.append(f"Row {index + 1}: Component '{row['name']}' updated (already existed)")
                else:
                    # Insert new component
                    component_data = {
                        'uid': uid,
                        'name': str(row['name']).strip(),
                        'category': category,
                        'lab': lab['name'],
                        'lab_id': lab['id'],
                        'initial_quantity': initial_quantity,
                        'current_quantity': current_quantity,
                        'status': status
                    }
                    component_data.update(group_data)
                    
                    Component.create(component_data)
                    imported_count += 1
                    # Update existing_components for UID generation
                    existing_components.append(component_data)
                
            except Exception as e:
                errors.append(f"Row {index + 1}: {str(e)}")
        
        return jsonify({
            'message': f'Successfully processed {imported_count} components',
            'imported_count': imported_count,
            'errors': errors,
            'total_rows': len(df)
        })
        
    except Exception as e:
        return jsonify({'error': f'Error processing file: {str(e)}'}), 500

# API Routes for Component Groups
@app.route('/api/component-groups', methods=['POST'])
@requires_role(['admin', 'trainer'])
def create_component_group():
    data = request.get_json()
    
    # For trainers, automatically assign their lab
    if session.get('role') == 'trainer':
        lab_id = session.get('lab_id')
        lab_name = session.get('lab_name')
        data['lab_id'] = lab_id
        data['lab_name'] = lab_name
    
    group_data = {
        'name': data['name'],
        'description': data.get('description', ''),
        'color': data.get('color', '#6B7280')
    }
    
    # Add lab info if provided
    if 'lab_id' in data:
        group_data['lab_id'] = data['lab_id']
        group_data['lab_name'] = data.get('lab_name', '')
    
    group_id = ComponentGroup.create(group_data)
    return jsonify({'message': 'Component group created successfully', 'id': group_id}), 201

@app.route('/api/component-groups/<group_id>', methods=['PUT'])
@requires_role(['admin', 'trainer'])
def update_component_group(group_id):
    data = request.get_json()
    
    # For trainers, verify they own this group
    if session.get('role') == 'trainer':
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM component_groups WHERE id = %s', (group_id,))
            group = cursor.fetchone()
        if not group or (group.get('lab_id') and group['lab_id'] != session.get('lab_id')):
            return jsonify({'error': 'Group not found or access denied'}), 404
    
    result = ComponentGroup.update(group_id, data)
    
    if result:
        return jsonify({'message': 'Component group updated successfully'}), 200
    else:
        return jsonify({'error': 'Component group not found'}), 404

@app.route('/api/component-groups/<group_id>', methods=['DELETE'])
@requires_role(['admin', 'trainer'])
def delete_component_group(group_id):
    # Check if any components are using this group
    with get_cursor() as cursor:
        cursor.execute('SELECT COUNT(*) as count FROM components WHERE group_id = %s', (group_id,))
        components_count = cursor.fetchone()['count']
    
    if components_count > 0:
        return jsonify({'error': f'Cannot delete group. {components_count} components are using this group.'}), 400
    
    # For trainers, verify they own this group
    if session.get('role') == 'trainer':
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM component_groups WHERE id = %s', (group_id,))
            group = cursor.fetchone()
        if not group or (group.get('lab_id') and group['lab_id'] != session.get('lab_id')):
            return jsonify({'error': 'Group not found or access denied'}), 404
    
    result = ComponentGroup.delete(group_id)
    
    if result:
        return jsonify({'message': 'Component group deleted successfully'}), 200
    else:
        return jsonify({'error': 'Component group not found'}), 404

@app.route('/api/component-groups/<group_id>', methods=['GET'])
@requires_role(['admin', 'trainer'])
def get_component_group(group_id):
    try:
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM component_groups WHERE id = %s', (group_id,))
            group = cursor.fetchone()
        
        if group:
            # For trainers, verify access
            if session.get('role') == 'trainer' and group.get('lab_id') and group['lab_id'] != session.get('lab_id'):
                return jsonify({'error': 'Access denied'}), 403
            return jsonify(group)
        else:
            return jsonify({'error': 'Component group not found'}), 404
    except Exception as e:
        return jsonify({'error': f'Invalid group ID: {str(e)}'}), 400

# API Routes for Labs (Admin only)
@app.route('/api/labs', methods=['POST'])
@requires_role(['admin'])
def create_lab():
    data = request.get_json()
    lab_data = {
        'name': data['name'],
        'lab_id': data['lab_id'],
        'location': data['location'],
        'device_count': data.get('device_count', 0),
        'status': data.get('status', 'active')
    }
    
    lab_id = Lab.create(lab_data)
    return jsonify({'message': 'Lab created successfully', 'id': lab_id}), 201

@app.route('/api/labs/<lab_id>', methods=['PUT'])
@requires_role(['admin'])
def update_lab(lab_id):
    data = request.get_json()
    result = Lab.update(lab_id, data)
    
    if result:
        return jsonify({'message': 'Lab updated successfully'}), 200
    else:
        return jsonify({'error': 'Lab not found'}), 404

@app.route('/api/labs/<lab_id>', methods=['DELETE'])
@requires_role(['admin'])
def delete_lab(lab_id):
    result = Lab.delete(lab_id)
    
    if result:
        return jsonify({'message': 'Lab deleted successfully'}), 200
    else:
        return jsonify({'error': 'Lab not found'}), 404

@app.route('/api/labs/<lab_id>', methods=['GET'])
@requires_role(['admin'])
def get_lab(lab_id):
    lab = Lab.get_by_id(lab_id)
    if lab:
        return jsonify(lab)
    else:
        return jsonify({'error': 'Lab not found'}), 404

# API Routes for Components (Both Admin and Trainer)
@app.route('/api/components', methods=['POST'])
@requires_role(['admin', 'trainer'])
@requires_trainer_lab_access
def create_component():
    data = request.get_json()
    
    # For trainers, automatically assign their lab
    if session.get('role') == 'trainer':
        lab_id = session.get('lab_id')
        lab_name = session.get('lab_name')
        data['lab'] = lab_name
        data['lab_id'] = lab_id
        print(f"Trainer creating component for lab: {lab_name}")
    else:
        # For admin, get lab details
        lab = Lab.get_by_name(data['lab'])
        if not lab:
            return jsonify({'error': 'Lab not found'}), 404
        data['lab_id'] = lab['id']
    
    # Generate UID for new component
    existing_components = Component.get_all()
    uid = generate_component_uid(data['lab_id'], data['name'], existing_components)
    if not uid:
        return jsonify({'error': 'Error generating UID for component'}), 500
    
    # Handle group assignment
    group_data = {}
    if 'group_id' in data and data['group_id']:
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM component_groups WHERE id = %s', (data['group_id'],))
            group = cursor.fetchone()
        
        if group:
            # For trainers, verify group belongs to their lab
            if session.get('role') == 'trainer' and group.get('lab_id') and group['lab_id'] != session.get('lab_id'):
                return jsonify({'error': 'Invalid group selection'}), 400
            
            group_data = {
                'group_id': group['id'],
                'group_name': group['name']
            }
    
    component_data = {
        'uid': uid,
        'name': data['name'],
        'category': data['category'],
        'lab': data['lab'],
        'lab_id': data['lab_id'],
        'initial_quantity': data['initial_quantity'],
        'current_quantity': data['current_quantity'],
        'status': 'available' if data['current_quantity'] >= 10 else 'low_stock'
    }
    component_data.update(group_data)
    
    component_id = Component.create(component_data)
    return jsonify({'message': 'Component created successfully', 'id': component_id, 'uid': uid}), 201

@app.route('/api/components/<component_id>', methods=['PUT'])
@requires_role(['admin', 'trainer'])
@requires_trainer_lab_access
def update_component(component_id):
    data = request.get_json()
    
    # For trainers, verify they own this component
    if session.get('role') == 'trainer':
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM components WHERE id = %s', (component_id,))
            component = cursor.fetchone()
        if not component or component['lab_id'] != session.get('lab_id'):
            return jsonify({'error': 'Component not found or access denied'}), 404
    
    # Update status based on current quantity
    if 'current_quantity' in data:
        data['status'] = 'available' if data['current_quantity'] >= 10 else 'low_stock'
    
    # Handle group assignment
    if 'group_id' in data and data['group_id']:
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM component_groups WHERE id = %s', (data['group_id'],))
            group = cursor.fetchone()
        
        if group:
            # For trainers, verify group belongs to their lab
            if session.get('role') == 'trainer' and group.get('lab_id') and group['lab_id'] != session.get('lab_id'):
                return jsonify({'error': 'Invalid group selection'}), 400
            
            data['group_id'] = group['id']
            data['group_name'] = group['name']
        else:
            # Remove group if not found
            data.pop('group_id', None)
            data.pop('group_name', None)
    elif 'group_id' in data and not data['group_id']:
        # Remove group if empty
        data.pop('group_id', None)
        data.pop('group_name', None)
    
    result = Component.update(component_id, data)
    
    if result:
        return jsonify({'message': 'Component updated successfully'}), 200
    else:
        return jsonify({'error': 'Component not found'}), 404

@app.route('/api/components/<component_id>', methods=['DELETE'])
@requires_role(['admin', 'trainer'])
@requires_trainer_lab_access
def delete_component(component_id):
    # For trainers, verify they own this component
    if session.get('role') == 'trainer':
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM components WHERE id = %s', (component_id,))
            component = cursor.fetchone()
        if not component or component['lab_id'] != session.get('lab_id'):
            return jsonify({'error': 'Component not found or access denied'}), 404
    
    result = Component.delete(component_id)
    
    if result:
        return jsonify({'message': 'Component deleted successfully'}), 200
    else:
        return jsonify({'error': 'Component not found'}), 404

@app.route('/api/components/<component_id>', methods=['GET'])
@requires_role(['admin', 'trainer'])
@requires_trainer_lab_access
def get_component(component_id):
    try:
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM components WHERE id = %s', (component_id,))
            component = cursor.fetchone()
        
        if component:
            if session.get('role') == 'trainer' and component['lab_id'] != session.get('lab_id'):
                return jsonify({'error': 'Access denied'}), 403
            
            return jsonify(component)
        else:
            return jsonify({'error': 'Component not found'}), 404
    except Exception as e:
        return jsonify({'error': f'Invalid component ID: {str(e)}'}), 400

# API Routes for Transactions (Both Admin and Trainer)
@app.route('/api/transactions', methods=['POST'])
@requires_role(['admin', 'trainer'])
@requires_trainer_lab_access
def create_transaction():
    data = request.get_json()
    transaction_type = data.get('type', 'issue')
    
    # For trainers, automatically assign their lab
    if session.get('role') == 'trainer':
        lab_id = session.get('lab_id')
        lab_name = session.get('lab_name')
        data['lab'] = lab_name
        data['lab_id'] = lab_id
        print(f"Trainer creating transaction for lab: {lab_name}")
    
    # Get lab information for admin
    if session.get('role') == 'admin':
        lab = Lab.get_by_name(data['lab'])
        if not lab:
            return jsonify({'error': 'Lab not found'}), 404
        data['lab_id'] = lab['id']
    
    # Get component details including UID
    with get_cursor() as cursor:
        cursor.execute('SELECT * FROM components WHERE name = %s AND lab = %s', (data['component_name'], data['lab']))
        component = cursor.fetchone()
    
    if not component:
        return jsonify({'error': 'Component not found'}), 404
    
    # For trainers, verify they own this component
    if session.get('role') == 'trainer' and component['lab_id'] != session.get('lab_id'):
        return jsonify({'error': 'Component not found or access denied'}), 404
    
    if transaction_type == 'issue':
        if component['current_quantity'] < data['quantity_issued']:
            return jsonify({'error': 'Insufficient quantity available'}), 400
        
        # Reduce component quantity
        new_quantity = component['current_quantity'] - data['quantity_issued']
        Component.update(component['id'], {
            'current_quantity': new_quantity,
            'status': 'available' if new_quantity >= 10 else 'low_stock'
        })
        
        transaction_data = {
            'component_name': data['component_name'],
            'component_uid': component.get('uid', 'N/A'),
            'lab': data['lab'],
            'lab_id': data['lab_id'],
            'issued_to': data['issued_to'],
            'campus': data.get('campus', ''),
            'quantity_issued': data['quantity_issued'],
            'quantity_returned': 0,
            'pending_quantity': data['quantity_issued'],  # New field: initially all are pending
            'status': 'issued',
            'issue_date': datetime.utcnow(),
            'purpose': data.get('purpose', '')
        }
        
        transaction_id = Transaction.create(transaction_data)
        return jsonify({'message': 'Transaction created successfully', 'id': transaction_id}), 201
        
    else:  # return transaction
        # For return transactions, find active issued transactions for this component and recipient
        with get_cursor() as cursor:
            cursor.execute('''
                SELECT * FROM transactions 
                WHERE component_name = %s AND lab_id = %s AND issued_to = %s AND pending_quantity > 0 
                ORDER BY issue_date ASC
            ''', (data['component_name'], data['lab_id'], data['issued_to']))
            issued_transactions = cursor.fetchall()
        
        if not issued_transactions:
            return jsonify({'error': 'No active issued transactions found for return'}), 400
            
        # Use the oldest issued transaction for return
        issued_transaction = issued_transactions[0]
        
        if data['quantity_returned'] > issued_transaction['pending_quantity']:
            return jsonify({'error': f'Cannot return more than pending quantity ({issued_transaction["pending_quantity"]})'}), 400
        
        # Calculate new pending quantity
        new_pending_quantity = issued_transaction['pending_quantity'] - data['quantity_returned']
        new_quantity_returned = issued_transaction['quantity_returned'] + data['quantity_returned']
        
        # Update the original transaction
        new_status = 'returned' if new_pending_quantity == 0 else 'partially_returned'
        
        update_data = {
            'quantity_returned': new_quantity_returned,
            'pending_quantity': new_pending_quantity,
            'status': new_status
        }
        
        if new_status == 'returned':
            update_data['return_date'] = datetime.utcnow()
        
        Transaction.update(issued_transaction['id'], update_data)
        
        # Increase component quantity by the returned amount
        new_component_quantity = component['current_quantity'] + data['quantity_returned']
        if new_component_quantity > component['initial_quantity']:
            return jsonify({'error': 'Returned quantity would exceed initial stock'}), 400
            
        Component.update(component['id'], {
            'current_quantity': new_component_quantity,
            'status': 'available' if new_component_quantity >= 10 else 'low_stock'
        })
        
        return jsonify({'message': 'Component returned successfully'}), 200

@app.route('/api/transactions/<transaction_id>', methods=['PUT'])
@requires_role(['admin', 'trainer'])
@requires_trainer_lab_access
def update_transaction(transaction_id):
    data = request.get_json()
    
    # For trainers, verify they own this transaction
    if session.get('role') == 'trainer':
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM transactions WHERE id = %s', (transaction_id,))
            transaction = cursor.fetchone()
        if not transaction or transaction['lab_id'] != session.get('lab_id'):
            return jsonify({'error': 'Transaction not found or access denied'}), 404
    
    # Get the original transaction before update
    with get_cursor() as cursor:
        cursor.execute('SELECT * FROM transactions WHERE id = %s', (transaction_id,))
        original_transaction = cursor.fetchone()
    
    if not original_transaction:
        return jsonify({'error': 'Transaction not found'}), 404
    
    # Get the component associated with this transaction
    with get_cursor() as cursor:
        cursor.execute('SELECT * FROM components WHERE name = %s AND lab_id = %s', 
                      (original_transaction['component_name'], original_transaction['lab_id']))
        component = cursor.fetchone()
    
    if not component:
        return jsonify({'error': 'Component not found'}), 404
    
    # Handle quantity_returned changes
    if 'quantity_returned' in data:
        new_returned = data.get('quantity_returned', 0)
        old_returned = original_transaction.get('quantity_returned', 0)
        returned_delta = new_returned - old_returned
        
        # Validate the new returned quantity
        if new_returned < 0:
            return jsonify({'error': 'Returned quantity cannot be negative'}), 400
            
        if new_returned > original_transaction['quantity_issued']:
            return jsonify({'error': 'Returned quantity cannot exceed issued quantity'}), 400
        
        # Calculate new pending quantity
        new_pending_quantity = original_transaction['quantity_issued'] - new_returned
        
        # Update the component quantity based on the delta
        if returned_delta != 0:
            new_component_quantity = component['current_quantity'] + returned_delta
            
            # Validate that new quantity doesn't exceed initial quantity
            if new_component_quantity > component['initial_quantity']:
                return jsonify({
                    'error': f'Cannot return more than initial quantity. Component "{component["name"]}" has initial quantity of {component["initial_quantity"]}'
                }), 400
            
            # Validate that quantity doesn't go negative
            if new_component_quantity < 0:
                return jsonify({
                    'error': f'Insufficient quantity available. Component "{component["name"]}" would have negative quantity'
                }), 400
            
            # Update component quantity and status
            component_update_data = {
                'current_quantity': new_component_quantity,
                'status': 'available' if new_component_quantity >= 10 else 'low_stock'
            }
            if new_component_quantity == 0:
                component_update_data['status'] = 'out_of_stock'
            
            Component.update(component['id'], component_update_data)
        
        # Update transaction data
        data['pending_quantity'] = new_pending_quantity
        
        # Update status based on returned quantity
        if new_returned == 0:
            data['status'] = 'issued'
        elif new_returned == original_transaction['quantity_issued']:
            data['status'] = 'returned'
            if not original_transaction.get('return_date'):
                data['return_date'] = datetime.utcnow()
        else:
            data['status'] = 'partially_returned'
            # Don't set return date for partial returns
    
    # Update the transaction
    result = Transaction.update(transaction_id, data)
    
    if result:
        return jsonify({'message': 'Transaction updated successfully'}), 200
    else:
        return jsonify({'error': 'Transaction not found or no changes made'}), 404

@app.route('/api/transactions/<transaction_id>', methods=['DELETE'])
@requires_role(['admin', 'trainer'])
@requires_trainer_lab_access
def delete_transaction(transaction_id):
    # For trainers, verify they own this transaction
    if session.get('role') == 'trainer':
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM transactions WHERE id = %s', (transaction_id,))
            transaction = cursor.fetchone()
        if not transaction or transaction['lab_id'] != session.get('lab_id'):
            return jsonify({'error': 'Transaction not found or access denied'}), 404
    
    # Get the transaction before deletion to restore component quantity if needed
    with get_cursor() as cursor:
        cursor.execute('SELECT * FROM transactions WHERE id = %s', (transaction_id,))
        transaction = cursor.fetchone()
    
    if transaction and transaction.get('pending_quantity', 0) > 0:
        # Restore the pending quantity back to component
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM components WHERE name = %s AND lab_id = %s', 
                          (transaction['component_name'], transaction['lab_id']))
            component = cursor.fetchone()
        
        if component:
            new_quantity = component['current_quantity'] + transaction['pending_quantity']
            Component.update(component['id'], {
                'current_quantity': new_quantity,
                'status': 'available' if new_quantity >= 10 else 'low_stock'
            })
    
    result = Transaction.delete(transaction_id)
    
    if result:
        return jsonify({'message': 'Transaction deleted successfully'}), 200
    else:
        return jsonify({'error': 'Transaction not found'}), 404

@app.route('/api/transactions/<transaction_id>', methods=['GET'])
@requires_role(['admin', 'trainer'])
@requires_trainer_lab_access
def get_transaction(transaction_id):
    try:
        with get_cursor() as cursor:
            cursor.execute('SELECT * FROM transactions WHERE id = %s', (transaction_id,))
            transaction = cursor.fetchone()
        
        if transaction:
            # For trainers, verify they own this transaction
            if session.get('role') == 'trainer' and transaction['lab_id'] != session.get('lab_id'):
                return jsonify({'error': 'Access denied'}), 403
            
            return jsonify(transaction)
        else:
            return jsonify({'error': 'Transaction not found'}), 404
    except Exception as e:
        return jsonify({'error': f'Invalid transaction ID: {str(e)}'}), 400

@app.route('/api/components')
@requires_role(['admin', 'trainer'])
@requires_trainer_lab_access
def get_all_components():
    """Get all components for UID lookup"""
    # Build query based on user role
    if session.get('role') == 'admin':
        components = Component.get_all()
    else:  # Trainer
        lab_id = session.get('lab_id')
        components = Component.get_by_lab(lab_id)
    
    return jsonify(components)

# API Routes for Components by Lab
@app.route('/api/components/by-lab/<lab_name>')
@requires_role(['admin', 'trainer'])
def get_components_by_lab(lab_name):
    # For trainers, only allow access to their assigned lab
    if session.get('role') == 'trainer':
        if lab_name != session.get('lab_name'):
            return jsonify({'error': 'Access denied'}), 403
        lab_id = session.get('lab_id')
        components = Component.get_by_lab(lab_id)
    else:
        lab = Lab.get_by_name(lab_name)
        if not lab:
            return jsonify({'error': 'Lab not found'}), 404
        components = Component.get_by_lab(lab['id'])
    
    return jsonify(components)

# API Routes for Dashboard Stats
@app.route('/api/dashboard/stats')
@requires_role(['admin', 'trainer'])
def get_dashboard_stats():
    if session.get('role') == 'admin':
        # Admin dashboard stats
        with get_cursor() as cursor:
            cursor.execute('SELECT COUNT(*) as count FROM labs')
            total_labs = cursor.fetchone()['count']
            
            cursor.execute('SELECT COUNT(*) as count FROM components')
            total_components = cursor.fetchone()['count']
            
            cursor.execute('SELECT COUNT(*) as count FROM users WHERE role = "trainer"')
            total_trainers = cursor.fetchone()['count']
            
            # Today's transactions
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            cursor.execute('SELECT COUNT(*) as count FROM transactions WHERE issue_date >= %s', (today_start,))
            issued_today = cursor.fetchone()['count']
            
            # Low stock components
            cursor.execute('SELECT COUNT(*) as count FROM components WHERE current_quantity < 10')
            low_stock = cursor.fetchone()['count']
            
            # Overdue items
            overdue_threshold = datetime.utcnow() - timedelta(days=14)
            cursor.execute('SELECT COUNT(*) as count FROM transactions WHERE issue_date < %s AND pending_quantity > 0', 
                          (overdue_threshold,))
            overdue_count = cursor.fetchone()['count']
            
            # Pending returns
            cursor.execute('SELECT COUNT(*) as count FROM transactions WHERE pending_quantity > 0')
            pending_returns = cursor.fetchone()['count']
        
        return jsonify({
            'total_labs': total_labs,
            'total_components': total_components,
            'total_trainers': total_trainers,
            'issued_today': issued_today,
            'low_stock': low_stock,
            'overdue_count': overdue_count,
            'pending_returns': pending_returns
        })
    
    else:  # Trainer
        lab_id = session.get('lab_id')
        lab_name = session.get('lab_name')
        
        if not lab_id:
            return jsonify({'error': 'No lab assigned'}), 400
        
        # Trainer dashboard stats
        with get_cursor() as cursor:
            cursor.execute('SELECT COUNT(*) as count FROM components WHERE lab_id = %s', (lab_id,))
            total_components = cursor.fetchone()['count']
            
            # Low stock components for trainer's lab
            cursor.execute('SELECT COUNT(*) as count FROM components WHERE lab_id = %s AND current_quantity < 10', (lab_id,))
            low_stock = cursor.fetchone()['count']
            
            # Today's transactions for trainer's lab
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            cursor.execute('SELECT COUNT(*) as count FROM transactions WHERE lab_id = %s AND issue_date >= %s', 
                          (lab_id, today_start))
            issued_today = cursor.fetchone()['count']
            
            # Overdue items for trainer's lab
            overdue_threshold = datetime.utcnow() - timedelta(days=14)
            cursor.execute('SELECT COUNT(*) as count FROM transactions WHERE lab_id = %s AND issue_date < %s AND pending_quantity > 0', 
                          (lab_id, overdue_threshold))
            overdue_count = cursor.fetchone()['count']
            
            # Pending returns for trainer's lab
            cursor.execute('SELECT COUNT(*) as count FROM transactions WHERE lab_id = %s AND pending_quantity > 0', (lab_id,))
            pending_returns = cursor.fetchone()['count']
        
        return jsonify({
            'lab_name': lab_name,
            'total_components': total_components,
            'issued_today': issued_today,
            'low_stock': low_stock,
            'overdue_count': overdue_count,
            'pending_returns': pending_returns
        })

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

if __name__ == '__main__':
    with app.app_context():
        init_sample_data()
    app.run(debug=True, host='0.0.0.0', port=5000)

from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
import socket
import csv
from io import StringIO, BytesIO
from ops import DbOperations
import json
import getpass
import psycopg2
import os
from datetime import datetime, timedelta
import uuid
#from access_logger import log_site_access
# # =========================
# # DAILY TRACKER APIs
# # =========================
from psycopg2.extras import RealDictCursor
# Placeholder import for your existing PPT logic
try:
    from ppt_generator import generate_presentation, fetch_data, prepare_data_dictionary
except ImportError:
    generate_presentation = None
    fetch_data = None
    prepare_data_dictionary = None

app = Flask(__name__)
app.secret_key = 'internal_secret_key'

# --- Configuration ---
DB_CONFIG = {
    'dbname': 'DB_Name',  # Your DB Name
    'user': 'postgres',   # Your Superuser
    'password': 'DB_Password', # Your Password
    'host': 'localhost',
    'port': '5432'
}

def get_user_identity():
    """
    Determines user identity.
    1. Checks Flask Session (persists across tabs).
    2. Fallback: Uses nslookup on client IP to get system name.
    """
    # [SECURITY UPDATE] Removed request.args check so users cannot type ?username=X in URL
    # Login is now handled explicitly in the index() route via POST
    
    # 1. Retrieve from session
    username = session.get('username')
   
    # 2. Get IP / System Name (Fallback)
    if request.headers.getlist("X-Forwarded-For"):
        ip = request.headers.getlist("X-Forwarded-For")[0]
    else:
        ip = request.remote_addr
 
    system_name = "Unknown-System"
    try:
        if ip == '127.0.0.1':
            system_name = socket.gethostname()
        else:
            system_name = socket.gethostbyaddr(ip)[0]
    except:
        system_name = f"IP-{ip}"
 
    display_name = f"Hi, {username}" if username else f"System: {system_name}"
   
    return {
        'username': username,
        'system_name': system_name,
        'display_name': display_name,
        'ip_address' : ip
    }
 
 
# --- Template Filter ---
@app.template_filter('normalize_number')
def normalize_number(value):
    """Removes trailing zeros from floats/decimals."""
    return DbOperations.fmt_num(value)

# --- Routes ---

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Get username from the hidden form
        form_username = request.form.get('username')
        if form_username:
            session['username'] = form_username
            # Redirect to self (GET) to clear the browser history of the POST
            # This ensures the URL bar stays clean (e.g., http://10.193.96.41:5000/)
            
            return redirect(url_for('index'))

    # Standard Page Load (GET)
    user = get_user_identity()

    if request.method == 'GET':
        
        db = DbOperations(DB_CONFIG)
        db.log_access_db(user)

        #log_site_access(user)

    return render_template('metrics.html', user=user)

@app.route('/reporting')
def reporting():
    user = get_user_identity()
    return render_template('reporting.html', user=user)

# --- NEW: Download Access Logs (Hidden Admin Route) ---
@app.route('/download_access_logs')
def download_access_logs():
    db = DbOperations(DB_CONFIG)
    cols, rows = db.get_access_logs()
    
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(cols)
    cw.writerows(rows)
    output = BytesIO()
    output.write(si.getvalue().encode('utf-8'))
    output.seek(0)
    
    return send_file(output, mimetype='text/csv', download_name='user_access_logs.csv', as_attachment=True)

# --- API: Dropdowns ---
@app.route('/api/customers')
def api_customers():
    db = DbOperations(DB_CONFIG)
    return jsonify(db.get_customers())

@app.route('/api/months/<short_code>')
def api_months(short_code):
    db = DbOperations(DB_CONFIG)
    return jsonify(db.get_months(short_code))

# --- API: Load Data ---
@app.route('/load_metrics', methods=['POST'])
def load_metrics():
    short_code = request.form.get('short_code')
    month = request.form.get('month')
    
    if not short_code or not month:
        return jsonify({'success': False, 'message': 'Missing selection'})

    db = DbOperations(DB_CONFIG)
    data, config = db.load_metrics_data(short_code, month)
    
    if not data:
        return jsonify({'success': False, 'message': 'No data found for selection'})

    return jsonify({
        'success': True,
        'data': data,   # Rows from final_computed_table
        'config': config # Rows from customer_mapping_table
    })

# --- API: Updates ---
def build_audit_info(req):
    user = get_user_identity()
    return {
        'username': user['username'] or '',
        'system_name': user['system_name'],
        'comments': req.form.get('comment')
    }

@app.route('/save_availability', methods=['POST'])
def save_availability():
    try:
        db = DbOperations(DB_CONFIG)
        # Availability is stored as decimal 0.99 in DB, UI sends 99.00
        # Divide by 100 before saving
        avail = float(request.form.get('availability', 0)) / 100.0
        target = float(request.form.get('target', 0)) / 100.0
        
        db.update_availability(
            request.form.get('short_code'),
            request.form.get('month'),
            avail, target,
            build_audit_info(request)
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/save_users', methods=['POST'])
def save_users():
    try:
        db = DbOperations(DB_CONFIG)
        db.update_users(
            request.form.get('short_code'), request.form.get('month'),
            request.form.get('prod_limit'), request.form.get('test_limit'), request.form.get('dev_limit'),
            request.form.get('prod_used'), request.form.get('test_used'), request.form.get('dev_used'),
            build_audit_info(request)
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/save_storage', methods=['POST'])
def save_storage():
    try:
        db = DbOperations(DB_CONFIG)
        db.update_storage(
            request.form.get('short_code'), request.form.get('month'),
            request.form.get('prod_target'), request.form.get('test_target'), request.form.get('dev_target'),
            request.form.get('prod_actual'), request.form.get('test_actual'), request.form.get('dev_actual'),
            build_audit_info(request)
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/save_tickets', methods=['POST'])
def save_tickets():
    try:
        db = DbOperations(DB_CONFIG)
        db.update_tickets(
            request.form.get('short_code'), request.form.get('month'),
            request.form.get('opened'), request.form.get('closed'),
            request.form.get('current_backlog'), request.form.get('overall_backlog'),
            build_audit_info(request)
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/save_config', methods=['POST'])
def save_config():
    try:
        db = DbOperations(DB_CONFIG)
        # Parse UID list from comma string
        uid_str = request.form.get('customer_uid', '')
        uid_list = [x.strip() for x in uid_str.split(',') if x.strip()]
        
        db.update_config(
            request.form.get('short_code'),
            request.form.get('customer_name'),
            request.form.get('csm_primary'),
            request.form.get('csm_lead'),
            uid_list,
            request.form.get('no_of_environments'),
            request.form.get('no_of_months'),
            request.form.get('customer_note'),
            build_audit_info(request)
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


# --- API: Reporting Page ---
@app.route('/api/reporting/csm_list')
def api_csm_list():
    db = DbOperations(DB_CONFIG)
    return jsonify(db.get_csm_list())

@app.route('/api/reporting/months')
def api_reporting_months():
    # Accepts ?short_code=X or ?csm=Y
    sc = request.args.get('short_code')
    csm = request.args.get('csm')
    db = DbOperations(DB_CONFIG)
    return jsonify(db.get_reporting_months(short_code=sc, csm=csm))

@app.route('/load_report_data', methods=['POST'])
def load_report_data():
    sc = request.form.get('short_code')
    csm = request.form.get('csm')
    month = request.form.get('month')
    range_val = request.form.get('range', 6)
    
    db = DbOperations(DB_CONFIG)
    data = db.load_report(short_code=sc, csm=csm, month_year=month, no_of_months=range_val)
    return jsonify({'success': True, 'data': data})

@app.route('/download_report_csv', methods=['POST'])
def download_report_csv():
    sc = request.form.get('short_code')
    csm = request.form.get('csm')
    month = request.form.get('month')
    range_val = request.form.get('range', 6)
    
    db = DbOperations(DB_CONFIG)
    data = db.load_report(short_code=sc, csm=csm, month_year=month, no_of_months=range_val)
    
    # Generate CSV
    if not data:
        return "No Data"
    
    keys = data[0].keys()
    si = StringIO()
    cw = csv.DictWriter(si, fieldnames=keys)
    cw.writeheader()
    cw.writerows(data)
    
    output = BytesIO()
    output.write(si.getvalue().encode('utf-8'))
    output.seek(0)
    
    filename = f"Report_{sc or csm}_{month}.csv"
    return send_file(output, mimetype='text/csv', download_name=filename, as_attachment=True)

@app.route('/add_customer', methods=['POST'])
def add_customer():
    try:
        db = DbOperations(DB_CONFIG)
        audit_info = build_audit_info(request)
        if not audit_info.get('comments'):
            audit_info['comments'] = "New Customer Created via Admin Panel"
        db.insert_new_customer(
            request.form.get('short_code'),
            request.form.get('go_live_date'),
            request.form.get('csm_primary'),
            request.form.get('csm_lead'),
            request.form.get('no_of_months'),
            request.form.get('no_of_environments'),
            audit_info
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# --- Audit Logs ---
@app.route('/api/audits')
def api_audits():
    db = DbOperations(DB_CONFIG)
    rows = db.load_audits()
    return jsonify(rows)

@app.route('/download_audits')
def download_audits():
    db = DbOperations(DB_CONFIG)
    cols, rows = db.get_audit_csv_data()
    
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(cols)
    cw.writerows(rows)
    output = BytesIO()
    output.write(si.getvalue().encode('utf-8'))
    output.seek(0)
    
    return send_file(output, mimetype='text/csv', download_name='audit_logs.csv', as_attachment=True)

@app.route('/generate_ppt', methods=['POST'])
def generate_ppt_route():
    try:
        customer = request.form.get('customer')
        month = request.form.get('month')
        
        if not customer or not month:
            return jsonify({'success': False, 'message': 'Missing customer or month'}), 400

        # Create DB connection
        # Use DB_CONFIG credentials directly or specific PPT user
        conn = psycopg2.connect(**DB_CONFIG)
        
        try:
            # 1. Fetch Data
            customer_mapping_df, final_computed_df = fetch_data(conn, customer, month)
            
            if customer_mapping_df.empty or final_computed_df.empty:
                return jsonify({'success': False, 'message': 'No data found for this selection'}), 404

            # 2. Prepare Data Dictionary
            data_dict = prepare_data_dictionary(customer_mapping_df, final_computed_df, month)
            
            # 3. Generate PPT
            dt_obj = datetime.strptime(month, '%Y-%m-%d')
            year_str = dt_obj.strftime('%Y')
            month_str = dt_obj.strftime('%b')
            # Use short_code and month for filename
            output_filename = f"{customer}-{year_str}-{month_str}.pptx"
            generate_presentation(data_dict, output_filename)
            
            # 4. Send File
            # Use send_file with as_attachment=True
            return_data = send_file(output_filename, as_attachment=True, download_name=output_filename)
            
            # (Optional) Clean up file after sending is tricky in Flask without after_request hooks
            # but for low volume, overwriting same file is okay or use tempfile
            
            return return_data
            
        finally:
            conn.close()
            # Clean up file if it exists
            if 'output_filename' in locals() and os.path.exists(output_filename):
                # Small delay or separate cleanup might be needed, 
                # but sending file usually locks it until stream starts.
                # Ideally use: io.BytesIO buffer if generate_presentation supports it.
                pass 

    except Exception as e:
        print(f"PPT Error: {str(e)}") # Log it
        return jsonify({'success': False, 'message': f"Server Error: {str(e)}"}), 500


@app.route('/daily_tracker')
def daily_tracker():
    user = get_user_identity()
    db = DbOperations(DB_CONFIG)

    # customers_list (short_code + full name)
    customers = db.get_customers()
    customers_list = [{
        "name": c["short_code"],
        "label": c["display"]
    } for c in customers]

    # tasks_list
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT new_subtasks
                FROM task_details
                WHERE COALESCE(new_subtasks,'') <> ''
                ORDER BY new_subtasks
            """)
            tasks_list = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    from datetime import date, timedelta
    today = date.today()
    min_entry_date = (today - timedelta(days=365)).isoformat()
    max_entry_date = today.isoformat()

    return render_template(
        'daily_tracker.html',
        user=user,
        customers_list=customers_list,
        tasks_list=tasks_list,
        min_entry_date=min_entry_date,
        max_entry_date=max_entry_date
    )

@app.route('/daily_tracker/fetch_entries')
def daily_tracker_fetch_entries():
    date = request.args.get('date')
    user = get_user_identity()
    username = user['username']
    db = DbOperations(DB_CONFIG)
    return jsonify({'results': db.dt_fetch_entries(date, username)})


@app.route('/daily_tracker/aggregates')
def daily_tracker_aggregates():
    date = request.args.get('date')
    user = get_user_identity()
    username = user.get('username')

    if not username:
        return jsonify({'rows': []})

    db = DbOperations(DB_CONFIG)
    return jsonify({'rows': db.dt_aggregates(date, username)})



@app.route('/daily_tracker/add', methods=['POST'])
def daily_tracker_add():
    payload = request.get_json() or {}
    db = DbOperations(DB_CONFIG)
    audit = build_audit_info(request)
    return jsonify(db.dt_add_entry(payload, audit))


@app.route('/daily_tracker/delete', methods=['POST'])
def daily_tracker_delete():
    ids = (request.json or {}).get('ids', [])
    db = DbOperations(DB_CONFIG)
    return jsonify(db.dt_delete(ids))


@app.route('/daily_tracker/copy', methods=['POST'])
def daily_tracker_copy():
    payload = request.get_json() or {}
    db = DbOperations(DB_CONFIG)
    return jsonify(db.dt_copy(payload))


@app.route('/daily_tracker/download_csv')
def daily_tracker_download_csv():
    args = request.args
    user = get_user_identity()
    username = user.get('username')

    if not username:
        return jsonify({'success': False, 'message': 'User not identified'}), 401

    db = DbOperations(DB_CONFIG)
    return db.dt_download_csv(args, username)



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

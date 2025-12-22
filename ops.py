import psycopg2
from psycopg2.extras import RealDictCursor
import json
import socket
import datetime
import uuid
import os
import csv

class DbOperations:
    def __init__(self, db_config):
        self.db_config = db_config
        self.csv_file = 'user_access_logs.csv'

    def get_connection(self):
        return psycopg2.connect(**self.db_config)

    # --- Helper to format numbers (remove trailing zeros) ---
    @staticmethod
    def fmt_num(val):
        if val is None: return ""
        try:
            f_val = float(val)
            if f_val.is_integer():
                return str(int(f_val))
            return str(f_val)
        except:
            return str(val)
        
    def _set_audit_context(self, cur, audit_info):
        """Sets session variables for the Audit Trigger."""
        cur.execute("SET LOCAL audit.source = 'webapp'")
        cur.execute("SET LOCAL audit.username = %s", (audit_info.get('username') or 'Unknown',))
        cur.execute("SET LOCAL audit.system_name = %s", (audit_info.get('system_name') or 'Unknown',))
        cur.execute("SET LOCAL audit.comment = %s", (audit_info.get('comments') or '',))

    def _exec_update(self, query, params, audit_info):
        conn = self.get_connection()
        try:
            with conn:
                with conn.cursor() as cur:
                    self._set_audit_context(cur, audit_info)
                    cur.execute(query, params)
        finally:
            conn.close()

    # --- Dropdowns ---
    def get_customers(self):
        """Returns customers formatted as 'ShortCode - Name'."""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT short_code, customer_name FROM customer_mapping_table ORDER BY short_code ASC")
                rows = cur.fetchall()
                result = []
                for r in rows:
                    display = f"{r['short_code']} - {r['customer_name']}"
                    result.append({"short_code": r['short_code'], "display": display})
                return result
        finally:
            conn.close()

    def get_months(self, short_code):
        """
        Returns months for UI.
        Returns a list of dicts: { 'value': '2025-06-01', 'display': 'June 2025' }
        """
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # Fetch distinct months, ordered by date descending
                # raw_date is for DB queries, display_date is for the UI dropdown
                cur.execute("""
                    SELECT DISTINCT 
                        to_char(month_year, 'YYYY-MM-DD') as raw_date,
                        to_char(month_year, 'FMMonth YYYY') as display_date
                    FROM final_computed_table 
                    WHERE short_code = %s 
                    ORDER BY 1 DESC
                """, (short_code,))
                
                rows = cur.fetchall()
                # Return list of objects
                return [{"value": r[0], "display": r[1]} for r in rows]
        finally:
            conn.close()

    # --- Load Dashboard Data ---
    def load_metrics_data(self, short_code, month_year):
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Fetch metrics from final_computed_table
                cur.execute("""
                    SELECT * FROM final_computed_table 
                    WHERE short_code = %s AND month_year = %s
                """, (short_code, month_year))
                data = cur.fetchone()
                
                # Fetch config from customer_mapping_table (Global config, not monthly)
                cur.execute("""
                    SELECT * FROM customer_mapping_table 
                    WHERE short_code = %s
                """, (short_code,))
                config = cur.fetchone()
                
                return data, config
        finally:
            conn.close()

    # --- Update Functions with Audit Context ---
    def _exec_update(self, query, params, audit_info):
        conn = self.get_connection()
        try:
            with conn:
                with conn.cursor() as cur:
                    # Set Audit Session Variables
                    cur.execute("SET LOCAL audit.source = 'webapp'")
                    cur.execute("SET LOCAL audit.username = %s", (audit_info.get('username'),))
                    cur.execute("SET LOCAL audit.system_name = %s", (audit_info.get('system_name'),))
                    cur.execute("SET LOCAL audit.comment = %s", (audit_info.get('comments'),))
                    
                    cur.execute(query, params)
        finally:
            conn.close()

    def _update_future_months(
        self,
        table_name,
        set_clause,
        params,
        short_code,
        month_year
    ):
        """
        Updates future months WITHOUT audit logging.
        """
        conn = self.get_connection()
        try:
            with conn:
                with conn.cursor() as cur:
                    # 🔴 IMPORTANT: suppress audit
                    cur.execute("SET LOCAL audit.source = 'devs'")
                    cur.execute("SET LOCAL audit.username = 'system'")
                    cur.execute("SET LOCAL audit.system_name = 'system'")
                    cur.execute("SET LOCAL audit.comment = ''")

                    query = f"""
                        UPDATE {table_name}
                        SET {set_clause}
                        WHERE short_code = %s
                        AND month_year > %s
                    """
                    cur.execute(query, params + (short_code, month_year))
        finally:
            conn.close()

    def update_availability(self, short_code, month, avail, target, audit_info):
        # Update both availability_table and final_computed_table
        # 1. Update source
        q1 = """
            UPDATE availability_table SET 
                updated_availability = %s, updated_target = %s
            WHERE short_code = %s AND month_year = %s
        """
        self._exec_update(q1, (avail, target, short_code, month), audit_info)
        
        # 2. Update final
        q2 = """
            UPDATE final_computed_table SET 
                updated_availability = %s, updated_target = %s
            WHERE short_code = %s AND month_year = %s
        """
        self._exec_update(q2, (avail, target, short_code, month), audit_info)

        # --- Apply TARGET to future months (NO AUDIT) ---
        self._update_future_months(
            table_name="availability_table",
            set_clause="updated_target = %s",
            params=(target,),
            short_code=short_code,
            month_year=month
        )

        self._update_future_months(
            table_name="final_computed_table",
            set_clause="updated_target = %s",
            params=(target,),
            short_code=short_code,
            month_year=month
        )


    def update_users(self, sc, month, p_lim, t_lim, d_lim, p_used, t_used, d_used, audit_info):
        # Update users_table and final
        params = (p_lim, t_lim, d_lim, p_used, t_used, d_used, sc, month)
        q1 = """
            UPDATE users_table SET 
                updated_prod_limit=%s, updated_test_limit=%s, updated_dev_limit=%s,
                updated_prod_used=%s, updated_test_used=%s, updated_dev_used=%s
            WHERE short_code=%s AND month_year=%s
        """
        self._exec_update(q1, params, audit_info)

        q2 = """
            UPDATE final_computed_table SET 
                updated_prod_limit=%s, updated_test_limit=%s, updated_dev_limit=%s,
                updated_prod_used=%s, updated_test_used=%s, updated_dev_used=%s
            WHERE short_code=%s AND month_year=%s
        """
        self._exec_update(q2, params, audit_info)

        # --- Apply limits to future months (NO AUDIT) ---
        self._update_future_months(
            table_name="users_table",
            set_clause="""
                updated_prod_limit = %s,
                updated_test_limit = %s,
                updated_dev_limit  = %s
            """,
            params=(p_lim, t_lim, d_lim),
            short_code=sc,
            month_year=month
        )

        self._update_future_months(
            table_name="final_computed_table",
            set_clause="""
                updated_prod_limit = %s,
                updated_test_limit = %s,
                updated_dev_limit  = %s
            """,
            params=(p_lim, t_lim, d_lim),
            short_code=sc,
            month_year=month
        )


    def update_storage(self, sc, month, pt, tt, dt, pa, ta, da, audit_info):
        params = (pt, tt, dt, pa, ta, da, sc, month)
        q1 = """
            UPDATE storage_table SET 
                updated_prod_target_storage_gb=%s, updated_test_target_storage_gb=%s, updated_dev_target_storage_gb=%s,
                updated_prod_storage_gb=%s, updated_test_storage_gb=%s, updated_dev_storage_gb=%s
            WHERE short_code=%s AND month_year=%s
        """
        self._exec_update(q1, params, audit_info)

        q2 = """
            UPDATE final_computed_table SET 
                updated_prod_target_storage_gb=%s, updated_test_target_storage_gb=%s, updated_dev_target_storage_gb=%s,
                updated_prod_storage_gb=%s, updated_test_storage_gb=%s, updated_dev_storage_gb=%s
            WHERE short_code=%s AND month_year=%s
        """
        self._exec_update(q2, params, audit_info)

        # --- Apply storage targets to future months (NO AUDIT) ---
        self._update_future_months(
            table_name="storage_table",
            set_clause="""
                updated_prod_target_storage_gb = %s,
                updated_test_target_storage_gb = %s,
                updated_dev_target_storage_gb  = %s
            """,
            params=(pt, tt, dt),
            short_code=sc,
            month_year=month
        )

        self._update_future_months(
            table_name="final_computed_table",
            set_clause="""
                updated_prod_target_storage_gb = %s,
                updated_test_target_storage_gb = %s,
                updated_dev_target_storage_gb  = %s
            """,
            params=(pt, tt, dt),
            short_code=sc,
            month_year=month
        )


    def update_tickets(self, sc, month, opened, closed, backlog, overall, audit_info):
        params = (opened, closed, backlog, overall, sc, month)
        q1 = """
            UPDATE tickets_computed_table SET 
                updated_tickets_opened=%s, updated_tickets_closed=%s, 
                updated_tickets_current_backlog=%s, updated_tickets_overall_backlog=%s
            WHERE short_code=%s AND month_year=%s
        """
        self._exec_update(q1, params, audit_info)

        q2 = """
            UPDATE final_computed_table SET 
                updated_tickets_opened=%s, updated_tickets_closed=%s, 
                updated_tickets_current_backlog=%s, updated_tickets_overall_backlog=%s
            WHERE short_code=%s AND month_year=%s
        """
        self._exec_update(q2, params, audit_info)

    def update_config(self, sc, name, csm_p, csm_l, uid, envs, months, note, audit_info):
        q = """
            UPDATE customer_mapping_table SET
                customer_name = %s, csm_primary = %s, csm_lead = %s,
                customer_uid = %s, no_of_environments = %s, no_of_months = %s,
                customer_note = %s
            WHERE short_code = %s
        """
        self._exec_update(q, (name, csm_p, csm_l, uid, envs, months, note, sc), audit_info)


    # --- Admin / Management ---
    def insert_new_customer(self, short_code, go_live, csm_p, csm_l, months, envs, audit_info):
        conn = self.get_connection()
        try:
            with conn:
                with conn.cursor() as cur:
                    self._set_audit_context(cur, audit_info)
                    # Check existence
                    cur.execute("SELECT 1 FROM customer_mapping_table WHERE short_code = %s", (short_code,))
                    if cur.fetchone():
                        raise ValueError(f"\nCustomer {short_code} already exists.\n\n")
                    
                    # Insert Config
                    # Note: Using [] for empty UID array, default values handled by DB if omitted
                    cur.execute("""
                        INSERT INTO customer_mapping_table (short_code, go_live_date, csm_primary, csm_lead, no_of_months, no_of_environments)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (short_code, go_live, csm_p, csm_l, months, envs))

                    # Insert dummy entry in Final Table for current month
                    # Determine current month start (e.g., 2025-12-01)
                    today = datetime.date.today().replace(day=1)
                    cur.execute("""
                        INSERT INTO final_computed_table (short_code, month_year) VALUES (%s, %s)
                    """, (short_code, today))
        finally:
            conn.close()

    def load_audits(self):
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM audit_logs ORDER BY changed_at DESC LIMIT 10")
                return cur.fetchall()
        finally:
            conn.close()

    def get_audit_csv_data(self):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM audit_logs ORDER BY changed_at DESC")
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                return cols, rows
        finally:
            conn.close()

    # --- Reporting ---

    # --- Reporting ---
    def load_report(self, short_code=None, csm=None, month_year=None, no_of_months=6):
        """
        Generates report data with specific column ordering.
        Shows EXACTLY N months including the selected month (calendar-based).
        Returns list of dicts.
        """
        conn = self.get_connection()
        data_rows = []
 
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
 
                # Selected month
                target_date = datetime.datetime.strptime(month_year, '%Y-%m-%d').date()
 
                # We want N months total INCLUDING selected month
                # So go back (N - 1) months
                months_back = max(int(no_of_months) - 1, 0)
 
                query = ""
                params = ()
 
                if short_code:
                    query = """
                        SELECT f.*, m.no_of_environments, m.customer_name,
                            m.csm_primary, m.csm_lead
                        FROM final_computed_table f
                        JOIN customer_mapping_table m
                        ON f.short_code = m.short_code
                        WHERE f.short_code = %s
                        AND f.month_year <= %s
                        AND f.month_year >= (%s::date - INTERVAL '%s months')
                        ORDER BY f.month_year DESC
                    """
                    params = (
                        short_code,
                        target_date,
                        target_date,
                        months_back
                    )
 
                elif csm:
                    query = """
                        SELECT f.*, m.no_of_environments, m.customer_name,
                            m.csm_primary, m.csm_lead
                        FROM final_computed_table f
                        JOIN customer_mapping_table m
                        ON f.short_code = m.short_code
                        WHERE (m.csm_primary = %s OR m.csm_lead = %s)
                        AND f.month_year <= %s
                        AND f.month_year >= (%s::date - INTERVAL '%s months')
                        ORDER BY f.short_code ASC, f.month_year DESC
                    """
                    params = (
                        csm,
                        csm,
                        target_date,
                        target_date,
                        months_back
                    )
 
                cur.execute(query, params)
                raw_rows = cur.fetchall()
 
                # Process rows with EXACT requested column order
                for r in raw_rows:
                    dt_str = r['month_year'].strftime('%B %Y')  # e.g. March 2025
                    envs = r.get('no_of_environments', 2)
 
                    row = {}
 
                    # 1. Identity
                    row["Customer Name"] = r['short_code']
                    row["Month & Year"] = dt_str
                    row["CSM Primary"] = r.get('csm_primary', '')
                    row["CSM Lead"] = r.get('csm_lead', '')
 
                    # 2. Availability
                    row["Availability (%)"] = self.fmt_num(
                        (r['updated_availability'] or 0) * 100
                    )
                    row["Target (%)"] = self.fmt_num(
                        (r['updated_target'] or 0) * 100
                    )
 
                    # 3. Users
                    row["Prod Limit"] = r['updated_prod_limit']
                    row["Prod Used"] = r['updated_prod_used']
                    row["Test Limit"] = r['updated_test_limit']
                    row["Test Used"] = r['updated_test_used']
 
                    if envs == 3:
                        row["Dev Limit"] = r['updated_dev_limit']
                        row["Dev Used"] = r['updated_dev_used']
 
                    # 4. Storage
                    row["Prod Target GB"] = self.fmt_num(r['updated_prod_target_storage_gb'])
                    row["Prod Actual GB"] = self.fmt_num(r['updated_prod_storage_gb'])
                    row["Test Target GB"] = self.fmt_num(r['updated_test_target_storage_gb'])
                    row["Test Actual GB"] = self.fmt_num(r['updated_test_storage_gb'])
 
                    if envs == 3:
                        row["Dev Target GB"] = self.fmt_num(r['updated_dev_target_storage_gb'])
                        row["Dev Actual GB"] = self.fmt_num(r['updated_dev_storage_gb'])
 
                    # 5. Tickets
                    row["Opened Tickets"] = r['updated_tickets_opened']
                    row["Closed Tickets"] = r['updated_tickets_closed']
                    row["Current Backlog Tickets"] = r['updated_tickets_current_backlog']
                    row["Tickets Backlog"] = r['updated_tickets_overall_backlog']
 
                    data_rows.append(row)
 
                return data_rows
 
        finally:
            conn.close() 

    def get_csm_list(self):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # Union primary and lead, distinct, order
                cur.execute("""
                    SELECT DISTINCT csm FROM (
                        SELECT csm_primary as csm FROM customer_mapping_table
                        UNION
                        SELECT csm_lead as csm FROM customer_mapping_table
                    ) x WHERE csm IS NOT NULL AND csm != '' ORDER BY 1
                """)
                return [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

    def get_reporting_months(self, short_code=None, csm=None):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                if short_code:
                    cur.execute("SELECT DISTINCT month_year FROM final_computed_table WHERE short_code=%s ORDER BY 1 DESC", (short_code,))
                elif csm:
                    cur.execute("""
                        SELECT DISTINCT f.month_year 
                        FROM final_computed_table f
                        JOIN customer_mapping_table m ON f.short_code = m.short_code
                        WHERE m.csm_primary=%s OR m.csm_lead=%s 
                        ORDER BY 1 DESC
                    """, (csm, csm))
                else:
                    return []
                
                # Format: "2022-11-01" -> "November 2022"
                rows = cur.fetchall()
                results = []
                for r in rows:
                    d = r[0]
                    display = d.strftime("%B %Y")
                    val = d.strftime("%Y-%m-%d")
                    results.append({"value": val, "display": display})
                return results
        finally:
            conn.close()


                
    def dt_fetch_entries(self, date,username):
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, userid, taskname, customername, task_type,
                        time_in_min, comments,
                        TO_CHAR(log_date,'YYYY-MM-DD') AS log_date
                    FROM task_entries
                    WHERE log_date = %s AND userid = %s
                    ORDER BY id
                """, (date,username))
                return cur.fetchall()
        finally:
            conn.close()

    def dt_aggregates(self, date, username):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        COALESCE(te.task_type,'Unknown') AS task_type,
                        SUM(te.time_in_min) AS total_minutes,
                        STRING_AGG(
                            COALESCE(cm.customer_name, te.customername) || ' - ' ||
                            te.taskname || ' - ' ||
                            te.comments || ' - ' ||
                            COALESCE(te.task_type,'') || ':' ||
                            te.time_in_min::text,
                            '; '
                            ORDER BY te.id
                        ) AS concat
                    FROM task_entries te
                    LEFT JOIN customer_mapping_table cm
                        ON cm.short_code = te.customername
                    WHERE te.log_date::date = %s
                    AND te.userid = %s
                    GROUP BY te.task_type
                    ORDER BY task_type
                """, (date, username))

                rows = cur.fetchall()

                return [{
                    'type': r[0],
                    'total_hours': round((r[1] or 0) / 60, 2),
                    'concatenated_string': r[2] or ''
                } for r in rows]
        finally:
            conn.close()


    def dt_add_entry(self, data, audit):
        try:
            date = data.get('date')
            customer = data.get('customer')
            task = data.get('task')
            time_min = int(data.get('time_in_min') or 0)
            comments = data.get('comments')

            if not all([date, customer, task, comments]) or time_min < 1:
                return {'success': False, 'message': 'All fields are mandatory.'}

            conn = self.get_connection()
            with conn:
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL audit.source = 'webapp'")
                    cur.execute(
                        "SET LOCAL audit.username = %s",
                        (audit.get('username') or 'SYSTEM',)
                    )
                    cur.execute(
                        "SET LOCAL audit.system_name = %s",
                        (audit.get('system_name') or 'DailyTracker',)
                    )
                    cur.execute(
                        "SET LOCAL audit.comment = %s",
                        (audit.get('comments') or '',)
                    )


                    cur.execute("""
                        SELECT cp_task_type
                        FROM task_details
                        WHERE TRIM(LOWER(new_subtasks)) = TRIM(LOWER(%s))
                    """, (task,))

                    row = cur.fetchone()
                    task_type = row[0] if row and row[0] else None

                    cur.execute("""
                        INSERT INTO task_entries
                        (id, userid, taskname, customername, time_in_min,
                        comments, log_date, task_type)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        str(uuid.uuid4()),
                        audit['username'],
                        task,
                        customer,
                        time_min,
                        comments,
                        date,
                        task_type
                    ))

            return {'success': True}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def dt_delete(self, ids):
        if not ids:
            return {'success': False, 'message': 'No IDs provided'}
        conn = self.get_connection()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM task_entries WHERE id = ANY(%s)", (ids,))
                    return {'success': True, 'deleted': cur.rowcount}
        finally:
            conn.close()

    def dt_copy(self, payload):
        ids = payload.get('ids', [])
        target_date = payload.get('target_date')
        if not ids or not target_date:
            return {'success': False, 'message': 'Invalid payload'}
 
        conn = self.get_connection()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT userid, taskname, customername,
                            time_in_min, comments, task_type
                        FROM task_entries
                        WHERE id = ANY(%s)
                    """, (ids,))
                    rows = cur.fetchall()
                    for r in rows:
                        cur.execute("""
                            INSERT INTO task_entries
                            (id, userid, taskname, customername,
                            time_in_min, comments, log_date, task_type)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        """, (
                            str(uuid.uuid4()),
                            r[0],  # userid
                            r[1],  # taskname
                            r[2],  # customername
                            r[3],  # time_in_min
                            r[4],  # comments
                            target_date,  # log_date
                            r[5]   # task_type
                        ))
            return {'success': True, 'created': len(rows)}
        finally:
            conn.close() 
 
    def dt_download_csv(self, args, username):
        import csv
        from io import StringIO, BytesIO
        from datetime import datetime, timedelta
        from flask import send_file, jsonify

        selected_date = args.get('date')
        from_date = args.get('from')
        to_date = args.get('to')

        def parse_date_flexible(s):
            if not s:
                return None
            s = s.strip()
            if s.lower() == 'all':
                return 'ALL'
            try:
                return datetime.fromisoformat(s).date()
            except:
                pass
            fmts = ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y')
            for f in fmts:
                try:
                    return datetime.strptime(s, f).date()
                except:
                    continue
            try:
                ts = int(s)
                if ts > 1e12:
                    ts /= 1000.0
                return datetime.utcfromtimestamp(ts).date()
            except:
                return None

        try:
            today = datetime.today().date()
            one_year_ago = today - timedelta(days=365)

            # -------- DATE RANGE --------
            if from_date or to_date:
                fd = parse_date_flexible(from_date)
                td = parse_date_flexible(to_date)

                if fd is None or td is None:
                    return jsonify({'success': False, 'message': 'Invalid from/to date format.'}), 400

                if fd > td:
                    return jsonify({'success': False, 'message': 'From date cannot be after To date.'}), 400

                filename_datepart = f"{fd}_to_{td}"
                query = """
                    SELECT id, userid, taskname, customername, task_type,
                        time_in_min, comments,
                        TO_CHAR(log_date,'YYYY-MM-DD HH24:MI:SS') AS log_date
                    FROM task_entries
                    WHERE log_date::date BETWEEN %s AND %s
                    AND userid = %s
                    ORDER BY id
                """
                params = (fd, td, username)

            # -------- SINGLE DATE / ALL --------
            else:
                sd = parse_date_flexible(selected_date)
                if sd is None:
                    return jsonify({'success': False, 'message': 'Invalid date.'}), 400

                if sd == 'ALL':
                    filename_datepart = 'all'
                    query = """
                        SELECT id, userid, taskname, customername, task_type,
                            time_in_min, comments,
                            TO_CHAR(log_date,'YYYY-MM-DD HH24:MI:SS') AS log_date
                        FROM task_entries
                        WHERE userid = %s
                        ORDER BY id
                    """
                    params = (username,)

                else:
                    if sd > today or sd < one_year_ago:
                        return jsonify({'success': False, 'message': 'Invalid date.'}), 400

                    filename_datepart = sd
                    query = """
                        SELECT id, userid, taskname, customername, task_type,
                            time_in_min, comments,
                            TO_CHAR(log_date,'YYYY-MM-DD HH24:MI:SS') AS log_date
                        FROM task_entries
                        WHERE log_date::date = %s
                        AND userid = %s
                        ORDER BY id
                    """
                    params = (sd, username)

            conn = self.get_connection()
            cur = conn.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
            colnames = [d[0] for d in cur.description]
            cur.close()
            conn.close()

            out = StringIO()
            writer = csv.writer(out)
            writer.writerow(colnames)
            writer.writerows(rows)

            buf = BytesIO(out.getvalue().encode('utf-8'))
            buf.seek(0)

            return send_file(
                buf,
                mimetype='text/csv; charset=utf-8',
                as_attachment=True,
                download_name=f'daily_tracker_{filename_datepart}.csv'
            )

        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500


     # =========================================================================
    # NEW METHODS FOR ACCESS LOGGING
    # =========================================================================
    
    def log_access_db(self, user_info):
        """
        Logs user access to the PostgreSQL database AND appends to CSV.
        """
        username = user_info.get('username') or 'Guest/Direct Link'
        system_name = user_info.get('system_name') or 'Unknown'
        ip_address = user_info.get('ip_address') or 'Unknown'
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = self.get_connection()
        try:
            # 1. Write to DB
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO user_access_logs (username, system_name, ip_address)
                        VALUES (%s, %s, %s)
                    """, (username, system_name, ip_address))
            
            # 2. Try to append to CSV (Best Effort)
            try:
                file_exists = os.path.isfile(self.csv_file)
                with open(self.csv_file, 'a', newline='') as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow(['Timestamp', 'Username', 'System Name', 'IP Address'])
                    writer.writerow([timestamp, username, system_name, ip_address])
            except PermissionError:
                print(f"[Warning] CSV Locked. Logged to DB only for: {username}")
            except Exception as e:
                print(f"[Error] CSV Write Failed: {e}")

        except Exception as e:
            print(f"[DB Log Error] Failed to log access: {e}")
        finally:
            conn.close()

    def get_access_logs(self):
        """Fetches all access logs for CSV download."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT access_time, username, system_name, ip_address
                    FROM user_access_logs
                    ORDER BY access_time DESC
                """)
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                return cols, rows
        finally:
            conn.close()
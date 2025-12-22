# import csv
# import os
# from datetime import datetime

# # The name of the log file
# LOG_FILE = 'user_access_logs.csv'

# def log_site_access(user_info):
#     """
#     Logs user access details (Timestamp, Username, System Name, IP) to a CSV file.
#     """
#     try:
#         # Check if file exists (to decide if we need to write headers)
#         file_exists = os.path.isfile(LOG_FILE)
        
#         # Get current time
#         timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
#         # Extract details from the user_info dictionary
#         username = user_info.get('username') or 'Guest/Direct Link'
#         system_name = user_info.get('system_name') or 'Unknown'
#         ip_address = user_info.get('ip_address') or 'Unknown'

#         # Prepare the row
#         row = [timestamp, username, system_name, ip_address]

#         # Write to CSV
#         with open(LOG_FILE, 'a', newline='') as f:
#             writer = csv.writer(f)
#             # Write Header if it's a new file
#             if not file_exists:
#                 writer.writerow(['Timestamp', 'Username', 'System Name', 'IP Address'])
            
#             writer.writerow(row)
            
#     except Exception as e:
#         # Log error to console so it doesn't break the UI
#         print(f"[Logger Error] Could not write to CSV: {str(e)}")
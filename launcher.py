import getpass
import os
import tempfile
import webbrowser
import time
import threading

# Configuration
SERVER_URL = "http://10.193.96.41:5000"

def launch():
    # 1. Get the username securely from the OS
    # getpass.getuser() calls the underlying OS API, it doesn't just read an editable var
    current_user = getpass.getuser()
    
    # 2. Create the HTML content for the POST request
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Logging in...</title></head>
    <body onload="document.getElementById('loginForm').submit()">
        <form id="loginForm" method="POST" action="{SERVER_URL}">
            <input type="hidden" name="username" value="{current_user}">
        </form>
        <p>Authenticating as {current_user}...</p>
    </body>
    </html>
    """

    # 3. Create a temporary file
    fd, path = tempfile.mkstemp(suffix=".html")
    try:
        with os.fdopen(fd, 'w') as tmp:
            tmp.write(html_content)
        
        # 4. Open the default browser
        webbrowser.open('file://' + path)
        
        # 5. Wait a few seconds for browser to load, then delete the temp file
        time.sleep(5)
    finally:
        if os.path.exists(path):
            os.remove(path)

if __name__ == "__main__":
    launch()
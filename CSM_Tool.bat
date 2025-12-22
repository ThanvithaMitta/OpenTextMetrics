@echo off
setlocal

:: Configuration
set "SERVER_URL=http://10.193.97.132:5000"
set "USER=%USERNAME%"

:: Create a temporary HTML file in the User's Temp folder
set "TEMP_HTML=%TEMP%\metrics_login_%RANDOM%.html"

echo Creating secure login launcher...

:: Write HTML content to the file
:: This creates a hidden form and auto-submits it to your Flask App
(
echo ^<!DOCTYPE html^>
echo ^<html^>
echo ^<body onload="document.getElementById('loginForm').submit()"^>
echo     ^<form id="loginForm" method="POST" action="%SERVER_URL%"^>
echo         ^<input type="hidden" name="username" value="%USER%"^>
echo     ^</form^>
echo ^</body^>
echo ^</html^>
) > "%TEMP_HTML%"

:: Open the temporary HTML file in the default browser
echo Launching Metrics Dashboard for user: %USER%
start "" "%TEMP_HTML%"

:: Give the browser a moment to load, then we could delete the file
:: (Optional: clean up the temp file after a short delay)
timeout /t 2 >nul
del "%TEMP_HTML%"

exit
# OpenText CSM Metrics & Reporting Application

## Document Purpose

This document provides a comprehensive overview, configuration guidance, and execution steps for the **OpenText CSM Metrics & Reporting Application**. It is intended for **developers, system administrators, Customer Success teams, and leadership stakeholders** to understand, deploy, and operate the application in an enterprise environment.


## Application Overview

The **OpenText CSM Metrics & Reporting Application** is an internal web-based solution designed to support Customer Success operations by centralizing customer metrics, historical reporting, audit tracking, and CSM effort management.

The application enables standardized monthly reporting, visibility into customer health indicators, and operational accountability through audit logs and effort tracking.


## Business Objectives

* Provide a **single source of truth** for customer success metrics
* Enable **consistent monthly and historical reporting**
* Support **leadership visibility** through dashboards and exports
* Maintain **auditability and traceability** of all metric changes
* Capture and report **CSM effort data** for operational analysis

---

## Key Capabilities

### Metrics Management

* Monthly customer metrics dashboard
* Availability, user consumption, storage usage, and ticket statistics
* Secure editing of metrics
* Automated PowerPoint report generation

### Reporting

* Historical metrics view across multiple months
* Customer and CSM-based filtering
* CSV export for offline analysis and sharing

### CSM Effort Tracking

* Daily effort capture in minutes
* Task-based categorization
* Automatic hour calculation
* CSV export for reporting

### Audit & Compliance

* Full audit trail for all create/update operations
* Old and new data capture
* User, timestamp, and system details
* Access logging for traceability

---

## Technology Stack

* **Backend:** Python (Flask)
* **Frontend:** HTML, CSS
* **Database:** PostgreSQL
* **Reporting:** PowerPoint (PPTX) generation
* **Platform:** Windows-based deployment

---

## Application Pages

### Metrics Dashboard

Displays customer-specific monthly metrics and supports report generation.

### Reporting

Provides historical metrics analysis with export functionality.

### Daily Tracker

Allows Customer Success Managers to record daily effort and tasks.

---

## Project Structure

```
csm_monthly_report_generation/
│
├── __pycache__/                  # Python runtime cache
│
├── static/
│   └── style.css                 # Global UI styling
│
├── templates/
│   ├── base.html                 # Base application layout
│   ├── daily_tracker.html        # CSM Effort Tracker UI
│   ├── metrics.html              # Metrics Dashboard UI
│   └── reporting.html            # Reporting UI
│
├── CSM_Tool.bat                  # Application startup script
│
├── app.py                        # Core Flask application and routing
├── launcher.py                   # Application startup handler
├── ops.py                        # Database access and business logic
├── ppt_generator.py              # PowerPoint generation logic
├── ppt_template.pptx             # Standard PPT report template
├── requirements.txt              # Python dependencies
└── user_access_logs.csv          # User access logs
```

---

## System Prerequisites

* Python 3.8 or later
* PostgreSQL database
* Windows operating system
* Network access to configured database and server

---

## Database Configuration

The application uses PostgreSQL for persistent data storage.

### Configuration Steps

Update the database connection parameters in **`app.py`** and/or **`ops.py`**:

```python
DB_HOST = "<YOUR_DB_HOST>"
DB_NAME = "<YOUR_DB_NAME>"
DB_USER = "<YOUR_DB_USERNAME>"
DB_PASSWORD = "<YOUR_DB_PASSWORD>"
DB_PORT = "5432"
```

> **Note:** Database host, credentials, and passwords must be provided by the target environment owner. These values should not be hardcoded in shared repositories.

---

## Server URL Configuration

### Batch File Configuration

The application startup URL must be configured in the batch file.

1. Open `CSM_Tool.bat`
2. Locate the server URL entry (example: `http://localhost:5000`)
3. Replace it with the environment-specific URL:

```
http://<YOUR_SERVER_HOST>:5000
```
or

## Environment Setup

### (Optional) Virtual Environment

```bash
python -m venv myenv
myenv\Scripts\activate
```

### Dependency Installation

```bash
pip install -r requirements.txt
```

---

## Application Startup

### Recommended Method (Batch File)

1. Ensure database and server URL configurations are completed
2. Double-click `CSM_Tool.bat`
3. The Flask server will start automatically

### Alternate Method (Manual)

```bash
python launcher.py
```

or

```bash
python app.py
```

---

## Application Access

Access the application through a web browser:

```
http://<CONFIGURED_SERVER_URL>:5000
```

---

## PowerPoint Report Generation

* Reports are generated using `ppt_template.pptx`
* Customer metrics are populated automatically
* Generated PowerPoint files are available for download from the UI

---

## Audit Logging & Security

* All data modifications are audited
* Audit records include:
  * Old and new values
  * User performing the action
  * Timestamp
* User access activity is recorded in `user_access_logs.csv`

---

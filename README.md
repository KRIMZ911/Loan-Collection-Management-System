# 📊 Зээл Төлүүлэх Удирдлагын Систем
# Collection Management System (CMS)

A web-based loan collection management system for Mongolian banks, built with Flask.

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Setup (3 minutes)

```bash
# 1. Navigate to project folder
cd collection-system

# 2. Create virtual environment
python -m venv venv

# 3. Activate virtual environment
# Windows:
venv\\Scripts\\activate
# Mac/Linux:
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Create .env file (copy from example)
cp .env.example .env

# 6. Seed the database with sample data
python run.py seed

# 7. Run the server
python run.py
```

### Open in browser
Navigate to **http://127.0.0.1:5000**

## 📁 Project Structure

```
collection-system/
├── run.py                  # Entry point
├── config.py               # App configuration
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variables template
├── app/
│   ├── __init__.py         # Flask app factory
│   ├── models.py           # Database models (SQLAlchemy)
│   ├── seed.py             # Sample data seeder
│   ├── routes/
│   │   ├── auth.py         # Role selection
│   │   ├── dashboard.py    # Dashboard views
│   │   └── api.py          # REST API endpoints
│   ├── static/
│   │   ├── css/style.css   # Stylesheet
│   │   └── js/app.js       # Frontend JavaScript
│   └── templates/
│       ├── base.html       # Base layout
│       ├── select_role.html
│       └── dashboard/      # Role-specific dashboards
│           ├── bpuh.html
│           ├── zm.html
│           ├── jdbbg.html
│           ├── taug.html
│           ├── outsourcing.html
│           ├── senior.html
│           └── mgmt.html
```

## 👥 Roles

| Role | Description | View |
|------|-------------|------|
| БПҮХ | Consumer Loan Monitor | Individual cases |
| ЗМ | Branch Loan Manager | Branch cases + aggregates |
| ЖДББГ | Corporate Monitor | Company-level cases |
| ТАУГ | Legal Specialist | Legal/transferred cases |
| Outsourcing | External Agency | Restricted view (🔒) |
| ЗЭГ Ахлах | Senior Supervisor | Aggregate only |
| Удирдлага | Executive | Full dashboard |

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/cases` | List cases (role-filtered) |
| GET | `/api/cases/<id>` | Case detail |
| POST | `/api/cases/<id>/actions` | Log action |
| POST | `/api/cases/<id>/transfer` | Transfer case |
| GET | `/api/stats` | Aggregate stats |
| GET | `/api/collectors/performance` | Collector metrics |

## 🛠️ Tech Stack
- **Backend**: Flask, SQLAlchemy, SQLite
- **Frontend**: Jinja2, Vanilla CSS/JS
- **Database**: SQLite (switchable to PostgreSQL)

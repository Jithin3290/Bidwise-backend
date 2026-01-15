# User Service - Local Development Guide

This is the **User Service** backend for BidWise, built with Django.

## Prerequisites

- [Python 3.10+](https://www.python.org/downloads/)
- [pip](https://pip.pypa.io/en/stable/installation/)

## Quick Start

### 1. Setup Environment

Navigate to the project directory:

```bash
cd user_service
```

Create a virtual environment:

```bash
# macOS/Linux
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configuration

Copy the example environment file to `.env`:

```bash
cp .env.example .env
```

> **Note**: The `.env` file contains sensitive configuration. Do not commit it to version control. The default values in `.env.example` are suitable for local development.

### 4. Run Migrations

Initialize the SQLite database:

```bash
python manage.py migrate
```

### 5. Start the Server

Run the Django development server:

```bash
python manage.py runserver
```

The service will be available at [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Project Structure

- `user_service/`: Main Django project configuration (`settings.py`, `urls.py`).
- `users/`: User management app (Models for User, Profiles, etc.).
- `manage.py`: Django command-line utility.
- `requirements.txt`: Python package dependencies.
- `.env`: Environment variables (API keys, Debug mode, etc.).
- `db.sqlite3`: Local SQLite database file.

## Common Commands

- **Create Superuser** (Admin):
    ```bash
    python manage.py createsuperuser
    ```
- **Make Migrations** (after changing models):
    ```bash
    python manage.py makemigrations
    ```
- **Run Tests**:
    ```bash
    python manage.py test
    ```
# BidWise-backend
# BidWise-backend
# BidWise-backend
# BidWise-backend
# Bidwise-backend

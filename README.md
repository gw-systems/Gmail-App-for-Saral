# Gmail App for Saral ERP

An industry-ready Gmail integration for Saral ERP, allowing multi-account email synchronization, conversation threading, and secure OAuth2 authentication.

## 🚀 Features

- **Multi-Account Support**: Connect and sync multiple Gmail accounts.
- **Bi-directional Sync**: Read and send emails directly from the dashboard.
- **Conversation Threading**: Intelligent grouping of emails into threads.
- **REST API**: Production-grade API endpoints for integration with other systems.
- **Standards**: 
    - API Rate Limiting (throttling)
    - Automated Swagger/Redoc documentation
    - PostgreSQL support for production
    - Secure environment variable management
    - Robust logging and error tracking

## 🛠️ Tech Stack

- **Backend**: Django 4.2+, Django Rest Framework
- **Database**: SQLite (Development), PostgreSQL (Production)
- **API**: Gmail API (OAuth2)
- **Documentation**: OpenAPI 3.0 (drf-spectacular)
- **Code Quality**: Black, Flake8, Isort, Mypy

## 📋 Prerequisites

- Python 3.9+
- Google Cloud Project with Gmail API enabled
- `credentials.json` from Google Cloud Console

## ⚙️ Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd "Gmail App with Saral ERP"
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment**:
   Create a `.env` file based on the template (see `.env` for examples).

4. **Run Migrations**:
   ```bash
   python manage.py migrate
   ```

5. **Start Development Server**:
   ```bash
   python manage.py runserver
   ```

## 📚 API Documentation

Once the server is running, access:
- **Swagger UI**: `http://localhost:8000/api/docs/`
- **Redoc**: `http://localhost:8000/api/redoc/`

## 🧪 Testing

Run the comprehensive test suite:

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=gmail_integration --cov-report=html

# Run specific test types
pytest -m unit  # Unit tests only
pytest -m api   # API tests only
```

See [TESTING.md](docs/TESTING.md) for detailed testing documentation.

## 🛡️ Security & Performance

- **Rate Limiting**: Default throttling is set at 1000 requests/day for authenticated users.
- **Security Headers**: HSTS, XSS Filter, and Content-Type Options are configured for production.
- **Logging**: Configured to capture critical errors and sync events.

## 📄 License

Internal tool for gw-systems / Saral ERP.

# Testing Documentation

This document provides comprehensive information about the test suite for the Gmail App with Saral ERP.

## Test Structure

```
tests/
├── __init__.py          # Makes tests a Python package
├── conftest.py          # Pytest fixtures and configuration
├── test_models.py       # Model unit tests
├── test_serializers.py  # Serializer unit tests
└── test_api.py          # API endpoint integration tests
```

## Running Tests

### Run all tests
```bash
pytest
```

### Run with verbose output
```bash
pytest -v
```

### Run specific test file
```bash
pytest tests/test_models.py
```

### Run specific test class
```bash
pytest tests/test_models.py::TestGmailToken
```

### Run specific test
```bash
pytest tests/test_models.py::TestGmailToken::test_create_gmail_token
```

### Run tests by marker
```bash
pytest -m unit          # Run only unit tests
pytest -m api           # Run only API tests
pytest -m integration   # Run only integration tests
```

### Run tests with coverage
```bash
pytest --cov=gmail_integration --cov-report=html
```

## Test Fixtures

The `conftest.py` file provides the following fixtures:

- **test_user**: A regular test user
- **admin_user**: An admin test user (systems@godamwale.com)
- **gmail_token**: A test Gmail OAuth token
- **sample_email**: A sample email for testing
- **sync_status**: A sample sync status record

## Test Coverage

### Model Tests (`test_models.py`)
- **GmailToken**: Token creation, string representation, user-specific operations
- **Email**: Email creation, properties (is_inbox, is_sent), label handling
- **SyncStatus**: Status creation, retrieval, record management

### Serializer Tests (`test_serializers.py`)
- **EmailSerializer**: Serialization/deserialization, field validation
- **GmailTokenSerializer**: Data exposure, read-only fields
- **SyncStatusSerializer**: Status serialization

### API Tests (`test_api.py`)
- **EmailViewSet**: Authentication, filtering, searching, admin access
- **GmailTokenViewSet**: User-specific token access, permissions
- **SyncStatusViewSet**: Read-only validation

## Best Practices

1. **Use Fixtures**: Always use the provided fixtures for consistent test data
2. **Mark Tests**: Use `@pytest.mark.unit`, `@pytest.mark.api`, etc.
3. **Isolate Tests**: Each test should be independent
4. **Clean Database**: Use `@pytest.mark.django_db` for database tests
5. **Descriptive Names**: Use clear, descriptive test names

## Continuous Integration

To integrate with CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
test:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v2
    - name: Install dependencies
      run: pip install -r requirements.txt
    - name: Run tests
      run: pytest --cov=gmail_integration
```

## Adding New Tests

When adding new features:
1. Create fixtures in `conftest.py` if needed
2. Add unit tests for models/serializers
3. Add API tests for new endpoints
4. Update this documentation

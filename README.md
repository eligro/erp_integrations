# ERP Integration System

A Python application for synchronizing data between Priority ERP and Atera systems.

## Features

- **Customer Sync**: Sync customers from Priority to Atera with custom field mapping
- **Contact Sync**: Sync contacts from Priority to Atera with validation
- **Contract Sync**: Sync contracts from Priority to Atera with filtering
- **Ticket Sync**: Sync closed tickets from Atera to Priority as service records

## Setup

### Prerequisites

- Python 3.9 or higher
- Virtual environment (recommended)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd erp_integrations
```

2. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements-dev.txt
```

4. Create and configure `config.txt`:
```bash
cp config.txt.example config.txt
# Edit config.txt with your API credentials and settings
```

## Configuration

Create a `config.txt` file with the following settings:

```ini
# API Configurations
PRIORITY_API_URL=https://your-priority-instance/odata/Priority/tabula.ini/ERP_COMPANY
PRIORITY_API_USER=your_priority_username
PRIORITY_API_PASSWORD=your_priority_password
ATERA_API_KEY=your_atera_api_key

# Sync Settings (true/false)
SYNC_CUSTOMERS=true
SYNC_CONTACTS=true
SYNC_CONTRACTS=false
SYNC_SERVICE_CALLS=false
SYNC_TICKETS=false

# Sync Parameters
DAYS_BACK_TICKETS=2
PULL_PERIOD_DAYS=2
CUSTOMERS_PULL_PERIOD_DAYS=2

# Status Mappings (Hebrew)
CANCELLED_CONTRACT_STATUS_HEBREW=מבוטל
ACTIVE_CUSTOMER_STATUS_HEBREW=פעיל
```

## Usage

### Running the Application

```bash
python main.py
```

### Development Commands

Use the provided Makefile for common development tasks:

```bash
make help          # Show available commands
make install       # Install dependencies
make test          # Run tests with coverage
make test-fast     # Run tests without coverage
make lint          # Run linting checks
make format        # Format code with black and isort
make type-check    # Run type checking
make security      # Run security checks
make clean         # Clean up generated files
make ci            # Run all CI checks locally
```

## Testing

### Running Tests

```bash
# Run all tests with coverage
pytest

# Run specific test file
pytest test_sync_module.py

# Run tests without coverage
pytest --no-cov

# Run tests with verbose output
pytest -v
```

### Test Structure

- `test_sync_module.py`: Main test file containing unit tests for all sync functions
- Tests use `pytest-mock` for mocking external API calls
- Coverage reports are generated in `htmlcov/` directory

## Code Quality

This project uses several tools to maintain code quality:

- **Black**: Code formatting
- **isort**: Import sorting
- **flake8**: Linting and style checking
- **mypy**: Type checking
- **pytest**: Testing framework
- **pytest-cov**: Coverage reporting

## CI/CD Pipeline

The project includes a GitHub Actions workflow (`.github/workflows/ci.yml`) that:

- Runs tests on Python 3.9, 3.10, and 3.11
- Performs code quality checks (linting, formatting, type checking)
- Runs security scans with bandit and safety
- Generates coverage reports
- Uploads coverage to Codecov

## Project Structure

```
erp_integrations/
├── main.py                 # Main application code
├── test_sync_module.py     # Test suite
├── config.txt              # Configuration file (not in git)
├── requirements.txt        # Production dependencies
├── requirements-dev.txt    # Development dependencies
├── pytest.ini             # Pytest configuration
├── pyproject.toml          # Tool configurations
├── .flake8                 # Flake8 configuration
├── Makefile                # Development commands
├── .gitignore              # Git ignore rules
├── .github/
│   └── workflows/
│       └── ci.yml          # CI/CD pipeline
└── README.md               # This file
```

## Security

- API credentials are stored in `config.txt` (excluded from git)
- Security scanning is performed with bandit and safety
- Dependencies are regularly updated for security patches

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and add tests
4. Run the full CI pipeline locally: `make ci`
5. Commit your changes: `git commit -am 'Add feature'`
6. Push to the branch: `git push origin feature-name`
7. Create a Pull Request

## License

This project is proprietary software. All rights reserved.
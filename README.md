# Store Audit System

A Django-based inventory and sales management system with reporting capabilities.

## Features
- Inventory management
- Sales processing
- Receipt generation
- Sales reporting
- Local storage support

## Requirements
- Python 3.8+
- PostgreSQL (optional, SQLite is default)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/store-audit-system.git
   cd store-audit-system
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   Create a `.env` file in the project root with the following content:
   ```
   SECRET_KEY=your-secret-key
   DEBUG=True
   ALLOWED_HOSTS=localhost,127.0.0.1
   ```

5. Run migrations:
   ```bash
   python manage.py migrate
   ```

6. Create a superuser:
   ```bash
   python manage.py createsuperuser
   ```

7. Run the development server:
   ```bash
   python manage.py runserver
   ```

8. Access the application at http://localhost:8000

## Deployment

For production deployment, follow these additional steps:

1. Set `DEBUG=False` in `.env`
2. Configure a production database (PostgreSQL recommended)
3. Set up a WSGI server (gunicorn)
4. Configure a web server (Nginx/Apache)
5. Set up static files collection:
   ```bash
   python manage.py collectstatic
   ```

## License
MIT License

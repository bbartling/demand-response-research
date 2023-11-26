# cloud DR Flask app with dashboard

![Alt text](/images/cloud_dashboard.jpg)

# Overview
This Flask application serves as a backend service for handling  the DR event communication to the building, user authentication to set DR events, 
data retrieval, and processing. It features a login system, caching mechanism, data manipulation using Pandas, 
and time zone handling with Pytz. The application also uses SQLAlchemy for database interaction and provides APIs for data updating and retrieval.

Features
* `User Authentication`: Handles user login with JWT tokens.
* `Data Processing`: Uses Pandas for data manipulation and storage in SQLite database.
* `Caching`: Implements Flask-Caching for efficient data retrieval.
* `Logging`: Configured with detailed logging for tracking activities and errors.
* `Time Zone Support`: Handles time zone conversions using Pytz.

# Security
This application uses JWT for secure authentication to set the DR events the posting script and Excel file containg the events. Ensure to keep the JWT secret key confidential.

# Endpoints
* `/login`: POST request for user authentication to set DR events from the Excel file.
* `/payload/current`: GET request to retrieve current payload data.
* `/update/data`: POST request to update payload data (JWT protected).
* `/`: Root endpoint serving an HTML template.

# Configurations
```python
app.config['JWT_SECRET_KEY'] = 'your_jwt_secret_key_here'
```

# Install packages
```bash
pip install Flask Flask-Caching pandas pytz sqlalchemy Flask-JWT-Extended
```

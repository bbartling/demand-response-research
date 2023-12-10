from datetime import datetime, timedelta
import jwt
from typing import Optional

# Secret key for JWT token encoding/decoding
SECRET_KEY = "your_secret_key"  # Change this to a secure, unique key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Mock database of clients (same as before)
clients_db = {
    "client1": {
        "client_id": "client1",
        "client_secret": "client1_secret",  # Hash in production
        "scopes": ["read:payload"]
    }
    # Add more clients as needed
}

def verify_client(client_id: str, client_secret: str):
    client = clients_db.get(client_id)
    if not client or client['client_secret'] != client_secret:
        print(f"{client['client_id']} failed to log in!")
        return False
    print(f"{client['client_id']} successfully logged in...")
    return client

def create_access_token(*, data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

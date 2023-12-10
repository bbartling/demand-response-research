import httpx
import asyncio
from datetime import datetime, timedelta

VTN_BASE_URL = "http://localhost:8000"

# Function to get a new token with a 15-minute expiration
async def get_new_token(client_id, client_secret):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{VTN_BASE_URL}/token",
            data={"username": client_id, "password": client_secret}
        )

    if response.status_code == 200:
        token = response.json()
        return token["access_token"]

# Function to access the payload endpoint with a valid token
async def access_payload(token):
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{VTN_BASE_URL}/payload", headers=headers)
    return response.json()

# Main function to renew token and access payload
async def main():
    client_id = "client1"
    client_secret = "client1_secret"  # Use a secure way to handle secrets

    while True:
        # Get a new token with a 15-minute expiration
        token = await get_new_token(client_id, client_secret)
        print("new token is: ",token)
        
        if token:
            # Access protected endpoint
            payload = await access_payload(token)
            print("Payload:", payload)
            
            # Sleep for 60 seconds before renewing the token
            await asyncio.sleep(60)
        else:
            print("Failed to authenticate. Exiting...")
            break

# Run the main function using asyncio
if __name__ == "__main__":
    asyncio.run(main())

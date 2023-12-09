import requests
import pandas as pd
import time

app_url = "http://localhost:5000"
auth_route = "/login"
upload_route = "/update/data"

username = "user1"
password = "password123"

print(f"Logging into API now @ {app_url + auth_route}")

# Authenticate and retrieve JWT token
response = requests.post(
    app_url + auth_route,
    json={"username": username, "password": password}
)
print("Response text: \n", response.text)

# Check if login was successful
if response.status_code != 200:
    print("Authentication failed!")
    exit()

token = response.json()["access_token"]

# Load data from the Excel file
try:
    print("Loading Excel File!")
    df = pd.read_excel(
        os.path.join(os.path.curdir, "event_schedule.xlsx"),
        engine="openpyxl",
        index_col="Time Block",
        parse_dates=True,
    )
    # Convert the index to the correct datetime format and then to ISO format
    df.index = pd.to_datetime(df.index).tz_localize('America/New_York').tz_convert('UTC')
    df.index = df.index.strftime('%Y-%m-%dT%H:%M:%SZ')  # ISO format
except PermissionError:
    print("You forgot to close the Excel file! Please try again...")
    exit()

# Convert DataFrame to a dictionary for JSON payload
post_this_dict = df.to_dict(orient="index")

print("Extracting data from the Excel file was successful!")

print(f"Posting data to API now @ {app_url + upload_route}")

# Set up headers with the JWT token
headers = {"Authorization": f"Bearer {token}"}

print(post_this_dict)

# Post the data to the Flask API
r = requests.post(app_url + upload_route, json=post_this_dict, headers=headers)
print("Server response:", r.text)

# Check the status of the data upload
if r.status_code == 200:
    print(f"Data upload successful. Check in web browser: {app_url}/payload/current")
    time.sleep(10)
else:
    print(f"Error uploading data. Status code: {r.status_code}")
    exit()


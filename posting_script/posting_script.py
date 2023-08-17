import requests
import pandas as pd
import time

app_url = "https://bensapi.pythonanywhere.com/"
auth_route = "/login"
upload_route = "/update/data"

username = "user1"
password = "password123" 

print(f"logging into API now @ {app_url + auth_route}!")

# Get JWT Token
response = requests.post(
    app_url + auth_route, json={"username": username, "password": password}
)
print("response.text: \n", response.text)


# Check if login was successful
if response.status_code != 200:
    print("Authentication failed!")
    exit()

token = response.json()["access_token"]

print("loading Excel File!")
df = pd.read_excel(
    "event_schedule.xlsx",
    engine="openpyxl",
    index_col="Time Block",
    parse_dates=True,
)
post_this_json = df.to_json(orient="index")
print("extracting data from the Excel file success!")

print(f"posting data to API now @ {app_url + upload_route}!")

headers = {"Authorization": f"Bearer {token}"}

# Using JWT Token to post data
r = requests.post(app_url + upload_route, json=post_this_json, headers=headers)
print(r.text)

if r.status_code == 200:
    print(f"Data upload successful. Check in web browser: {app_url}/payload/current")
    time.sleep(10)
else:
    print(f"Error uploading data. Status code: {r.text}")
    exit()





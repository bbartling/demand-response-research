# posting script

A value of `1` represents demand response `True` or a value of `0` represents a demand response `False` all in 15 minute time imcrements as shown below in the Excel file snip.

![Alt text](/images/post_script.jpg)

# Overview
This script will read the Excel file and post it across the internet to the DR server where ever it is running. 
First the script log's into the DR server via the servers `/login` route where then if the authentication is successful the server will return a token which is good for only 30 seconds.
The token is required to set the DR events.
If a token is recieved sucessfully the next step in the script is another post to the DR app's `/update/data` route with the access token along with the DR event data 
contained inside the Excel file. The DR events are then communicated to the building when the BACnet app checks into the cloud server all inspired by Open ADR but much more simple.

# Security
This application for tokens uses JWT for secure authentication to set the DR events the posting script and Excel file containg the events.
Keep server login information and JWT tokens safe and secure.


# Configurations
Before running the script, configure the following variables in the script:

* `app_url`: The base URL of the API.
* `auth_route`: The authentication endpoint route.
* `upload_route`: The endpoint route for data upload.
* `username`: Your API username.
* `password`: Your API password.

# Install packages
```bash
pip install requests pandas openpyxl
```
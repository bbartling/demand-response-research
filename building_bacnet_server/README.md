# Running a BACnet server inside the building on OT LAN as a Service on linux edge device using systemd

Update script constants with text editor:

```python
# DR Server Setup
DEVICE_NAME = "device_1"
DR_SERVER_URL = "http://localhost:5000/payload/current"
BACNET_INST_ID = 3056672
USE_DR_SERVER = False
SERVER_CHECK_IN_SECONDS = 10

# Use a local REST API to share DR signal to OT LAN
USE_REST = True

# BACnet NIC setup:
IP_ADDRESS = "192.168.0.109"
SUBNET_MASK_CIDAR = 24
PORT = "47808"
BBMD = None

# Logging setup
SAVE_LOGS_TO_FILE = True
```
* `DR_SERVER_URL` is the cloud based demand response app that is used to get and change the DR signal sent to the buildings.
* `USE_REST` is an option in addition to the BACnet API if there is an issue with some OT equipment inside the building that cannot read a BACnet API to get the DR signal into thier platform. Hit your device on the `IP_ADDRESS` with a GET request for example, `http://192.168.0.101:8080/api/demand-response-level` to retreive JSON payload of demand response event info like `{"demand_response_level": 1}`
* `SAVE_LOGS_TO_FILE` if True defaults to a log file name as `app_log.log`, is rotated daily, and only retains the previous 7 log files to prevent hard drive space from filling up if app is ran long term.
* This app has been successfully tested rasp pi and on dual nic card nanopi r1 that runs ubuntu where `IP_ADDRESS` can be statically assigned for OT network and the other nic card can be internet access to the `DR_SERVER_URL`.

Test script:
```bash
$ python bacnet_server.py
```

# Steps

### If successful with checkin to the `USE_DR_SERVER` run `bacnet_server.py` as a linux service.

1. **Create a Service Unit File**

   Open a terminal on your Raspberry Pi and navigate to the systemd service unit directory:

   ```bash
   cd /etc/systemd/system

   sudo nano bacnet_server.service
   ```

2. **Add the Service Configuration**

   ```bash
   [Unit]
   Description=BACnet Server
   After=network.target

   [Service]
   User=your_username
   WorkingDirectory=/home/your_username/bacnet-demand-response-client-server/building_bacnet_server
   ExecStart=/usr/bin/python3 bacnet_server.py --name Slipstream --instance 3056672 --debug
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
   Replace `your_username` with your actual username.

2. **Save and Exit the Text Editor**
   After adding the configuration, save the file and exit the text editor.

3. **Enable and Start the Service**
   Enable the service to start on boot:
   ```bash
   sudo systemctl enable bacnet_server.service
   ```
   Then, start the service:
   ```bash
   sudo systemctl start bacnet_server.service
   ```
4. **Check the Service Status**
   Check the status of your service to ensure it's running without errors:
   ```bash
   sudo systemctl status bacnet_server.service
   ```
5. **If errors and need to update script**
   If you make changes to the script, stop the service to update it:
   ```bash
   sudo systemctl stop bacnet_server.service
   ```
6. **Start the Service After Updating**
   After making changes to the script, start the service again:
   ```bash
   sudo systemctl start bacnet_server.service
   ```
7. **Check the Updated Status**
   Check the status again to confirm that the updated script is running:
   ```bash
   sudo systemctl status bacnet_server.service
   ```

### **Reload Linux service if modifiations are required to the .py file and or Linux service**
   Reload the systemd configuration. This tells systemd to recognize your changes:
   ```bash
   sudo systemctl daemon-reload
   ```

   Restart your service to apply the changes:
   ```bash
   sudo systemctl restart bacnet_server.service
   ```

   Check the status to ensure it's running as expected:
   ```bash
   sudo systemctl status bacnet_server.service
   ```

   See debug print statements:
   ```bash
   sudo journalctl -u bacnet_server.service -f
   ```

# Troubleshooting

If app runs but other OT platforms cannot see or integrate the app across the OT LAN, start with network `ping` and possibly even using a [BACnet scanning tool](https://www.ccontrols.com/sd/bdt.htm) from another device on the OT LAN. The link is to a free tool which runs on Windows made by contemporary controls where the app and `demand-response-level` BACnet point should come up on analog input 1 as shown below:


![Alt text](/images/bacnet_scan.jpg)
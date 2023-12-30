# BACnet server/client Open ADR 2.0 client app

This is a building side IoT BACnet gateway application designed for demand response, leveraging Open ADR 2.0b's SIMPLE_SIGNAL protocol. 
When a value of 1 is detected, it triggers the algorithm, and BACnet reads and writes occur at 60-second intervals. 
The application communicates with the Open ADR VTN server every 10 seconds, following the default configuration set by OpenLEADR. 
All BACnet operations are efficiently managed by bacpypes3.

## Setup:
```bash
python -m pip install bacpypes3 aiohttp ifaddr
```

Test script and use args to set BACnet device name and instance ID that comes by default with bacpypes3:
```bash
python main.py --name Slipstream --instance 3056672
```

If a different UDP port is required for the project use an arg like: `--address 192.168.13.14/24:47820`

## Algorithm Method in `main.py` needs to be customized for your application

```mermaid 
flowchart TD
    A[Start Algorithm Every 10 Seconds] -->|Check DR Event| D{DR Event Active?}
    D -->|True| B{Read BACnet Values}
    D -->|False| Z[End Algorithm]
    B -->|Read Success| C[Log Read Values]
    B -->|Read Failure| Z
    C --> E{Check PPM for Occupancy}
    E -->|PPM > PPM for Occ| F[Set Room Occupied]
    E -->|PPM < PPM for Occ - Dead Band| G[Set Room Unoccupied]
    F --> H[Log Current Occupancy]
    G --> H
    H --> I{Check if HVAC Mode or Occupancy Changed}
    I -->|Changed| J[Log Change]
    I -->|No Change| K[Log No Change]
    J --> L[Set Mecho AV for Occupancy]
    K --> L
    L --> M{Check HVAC Mode}
    M -->|Heating| N[Set Mecho to Heating]
    M -->|Cooling| O[Set Mecho to Cooling]
    M -->|Unknown Mode| P[Log Unknown Mode]
    N --> Q{Check DR Event Active}
    O --> Q
    P --> Q
    Q -->|Active| R[Check Setpoint Written]
    Q -->|Not Active| S{Check HVAC Needs Release}
    R -->|Not Written| T[Write New Setpoint]
    R -->|Written| U{Handle Write Ops}
    T --> U
    S -->|Needs Release| V[Release HVAC]
    S -->|No Release Needed| W[Log No BACnet Writes Needed] --> Z
    V --> X[Write to Mecho Again]
    X --> Y[Reset First Sweep Flag]
    Y --> Z
    U -->|Write Ops| AA[Log Handling Write Ops]
    AA --> Z
    U -->|No Need to Write| AB[Log No BACnet Writes Needed] --> Z

```

## Linux service notes

1. **Create a Service Unit File**

   Open a terminal on your Raspberry Pi and navigate to the systemd service unit directory:

   ```bash
   cd /etc/systemd/system

   sudo nano adr_client.service
   ```

2. **Add the Service Configuration** - Make sure you modify the field `User=your_username` and the correct `WorkingDirectory` fields

   ```bash
   [Unit]
   Description=BACnet Server
   After=network.target

   [Service]
   User=your_username
   WorkingDirectory=/home/your_username/bacnet-demand-response-client-server/building_adr_client
   ExecStart=/usr/bin/python3 adr_client.py --name Slipstream --instance 3056672 --debug
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
   sudo systemctl enable adr_client.service
   ```
   Then, start the service:
   ```bash
   sudo systemctl start adr_client.service
   ```
4. **Check the Service Status**
   Check the status of your service to ensure it's running without errors:
   ```bash
   sudo systemctl status adr_client.service
   ```
5. **If errors and need to update script**
   If you make changes to the script, stop the service to update it:
   ```bash
   sudo systemctl stop adr_client.service
   ```
6. **Start the Service After Updating**
   After making changes to the script, start the service again:
   ```bash
   sudo systemctl start adr_client.service
   ```
7. **Check the Updated Status**
   Check the status again to confirm that the updated script is running:
   ```bash
   sudo systemctl status adr_client.service
   ```

### **Reload Linux service if modifiations are required to the .py file and or Linux service**
   Reload the systemd configuration. This tells systemd to recognize your changes:
   ```bash
   sudo systemctl daemon-reload
   ```

   Restart your service to apply the changes:
   ```bash
   sudo systemctl restart adr_client.service
   ```

   Check the status to ensure it's running as expected:
   ```bash
   sudo systemctl status adr_client.service
   ```

   See debug print statements:
   ```bash
   sudo journalctl -u adr_client.service -f
   ```




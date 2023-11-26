# BACnet client Open ADR client app

This server application is designed to interact with a building's control system, rather than directly reading and writing to field-level devices on the Operational Technology (OT) LAN. It operates by providing the `demand-response-level` point for the control system to access. The control system is then expected to implement the appropriate demand response strategy for the specific project. After executing this strategy, the control system should write back the power meter value to this application using the BACnet writable or commandable point named `power-level`. This value is then relayed to the open ADR server to complete the data exchange process.

# Install packages with pip
```bash
pip install openleadr bacpypes pyyaml ifaddr
```

# bacpypes 3 args
When running the python script use args like this below which is built into bacpypes3 to `debug`, set your BACnet server `device` name, and `instance` ID. If you need to run your device on a unique port number other than default BACnet of 47808 use an arg like `--address 10.7.6.201/24:47820` would be for a static IP in Cidar notation and UDP port 47820. 

* **NOTE:** The BACnet device name, instance, or other parameters is set in args when the python script is ran or systemd linux service file and the open ADR opeleadr names and configs are set in the project yaml file.

```bash
# test the script
$ python adr_client.py --name Slipstream --instance 3056672 --debug
```

# Config yaml
Set your project configs in the yaml file which would be your open ADR device `ven name`, open ADR server `vtn url`, and the signal that would represent the `normal operations` for when the open ADR event expires. The payload coming from the server is used during the event.
```yaml
ven_name: "some_ven_id"
vtn_url: "https://some-openadr-server/OpenADR2/Simple/2.0b"
normal_operations: 0.0
```

# Linux service notes
```bash
# make systemd file
$ cd /etc/systemd/system

# edit file
$ sudo nano adr_client.service
```

Edit systemd file contents with nano and make sure to set your paths and `WorkingDirectory`:
```bash
[Unit]
Description=ADR Client Service
After=network.target

[Service]
User=bbartling
ExecStart=/usr/bin/python /home/bbartling/open_ADR/bacnet_client_adr_client/adr_client.py --name Slipstream --instance 3056672 --debug
WorkingDirectory=/home/bbartling/open_ADR/bacnet_client_adr_client
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Start the linux service
```bash
# Start linux service
$ sudo systemctl start adr_client.service

# Check status
$ sudo systemctl status adr_client.service

# Tail logs
$ sudo journalctl -fu adr_client.service
```

Commands if you need to restart the service if some change in the script or config was made
```bash
# stop linux service
$ sudo systemctl stop adr_client.service

# Reload if app code needs to be changed
$ sudo systemctl daemon-reload

# Restart linux service
$ sudo systemctl restart adr_client.service
```


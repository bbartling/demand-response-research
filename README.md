# demand-response-research
Building side research project with open ADR


# make virtual env
```bash
python -m venv drenv
```

# activate virt env
```bash
. drenv/bin/activate
```

# pip install python packges
```bash
pip install bacpypes3 openleadr ifaddr
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
User=dr
ExecStart=/home/dr/drenv/bin/python /home/dr/dr_app/app.py --name Slipstream --instance 3056672 --debug
WorkingDirectory=/home/dr/dr_app/

[Install]
WantedBy=multi-user.target

```

Start the linux service
```bash
# Start linux service
$ sudo systemctl enable adr_client.service

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
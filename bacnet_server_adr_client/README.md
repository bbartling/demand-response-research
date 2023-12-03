# BACnet server Open ADR client app

This server application is designed to interact with a building's control system, rather than directly reading and writing to field-level devices on the Operational Technology (OT) LAN. It operates by providing the `demand-response-level` point for the control system to access. The control system is then expected to implement the appropriate demand response strategy for the specific project. After executing this strategy, the control system should write back the power meter value to this application using the BACnet writable or commandable point named `power-level`. This value is then relayed to the open ADR server to complete the data exchange process.

# bacpypes 3 args
When running the python script use args like this below which is built into bacpypes3 to `debug`, set your BACnet server `device` name, and `instance` ID. If you need to run your device on a unique port number other than default BACnet of 47808 use an arg like `--address 10.7.6.201/24:47820` would be for a static IP in Cidar notation and UDP port 47820. 

* **NOTE:** The BACnet device name, instance, or other parameters is set in args when the python script is ran or systemd linux service file and the open ADR opeleadr names and configs are set in the project yaml file.

```bash
# test the script
$ python app.py --name Slipstream --instance 3056672 --debug
```

# Config yaml
Set your project configs in the yaml file which would be your open ADR device `ven name`, open ADR server `vtn url`, and the signal that would represent the `normal operations` for when the open ADR event expires. The payload coming from the server is used during the event.
```yaml
ven_name: "some_ven_id"
vtn_url: "https://some-openadr-server/OpenADR2/Simple/2.0b"
normal_operations: 0.0
```



# Custom-Algorithm

Custom algorith in BACnet reads and writes to accommodate other technology systems for a research project

# bacpypes 3 args
When running the python script use args like this below which is built into bacpypes3 to `debug`, set your BACnet server `device` name, and `instance` ID. If you need to run your device on a unique port number other than default BACnet of 47808 use an arg like `--address 10.7.6.201/24:47820` would be for a static IP in Cidar notation and UDP port 47820. 

* **NOTE:** The BACnet device name, instance, or other parameters is set in args when the python script is ran or systemd linux service file and the open ADR opeleadr names and configs are set in the project yaml file.

```bash
# test the script
$ python app.py --name Slipstream --instance 3056672 --debug
```

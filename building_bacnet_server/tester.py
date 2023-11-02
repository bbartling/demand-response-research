import BAC0, time

bacnet = BAC0.lite()

time.sleep(2)

'''
devices = bacnet.whois(global_broadcast=True)
device_mapping = {}
addresses = []
for device in devices:
    if isinstance(device, tuple):
        device_mapping[device[1]] = device[0]
        print("Detected device %s with address %s" % (str(device[1]), str(device[0])))
print(device_mapping)
print((str(len(device_mapping)) + " devices discovered on network."))

'''


time.sleep(.5)

read_str = f"12345:2 analogInput 2 presentValue"
sensor = bacnet.read(read_str)
print(f"Sensor is {sensor}")

time.sleep(.5)

read_str = f"12345:2 analogValue 301 presentValue"
analog_val = bacnet.read(read_str)
print(f"Analog_val is {analog_val}")

time.sleep(.5)

write_str = f"12345:2 analogValue 301 presentValue {sensor} - 1"
bacnet.write(write_str)
print(f"Write Success")

time.sleep(.5)

read_str = f"12345:2 analogValue 301 presentValue"
analog_val = bacnet.read(read_str)
print(f"Analog_val is now {analog_val}")

time.sleep(.5)

'''
write_str = f"12345:2 analogValue 301 presentValue null - 10"
bacnet.write(write_str)
print(f"The BACnet Write has been released!")

time.sleep(.5)
'''
print("All Done")
bacnet.disconnect()
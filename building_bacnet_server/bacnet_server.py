import asyncio
import re

from bacpypes3.debugging import ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser

from bacpypes3.app import Application
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.local.binary import BinaryValueObject
from bacpypes3.local.cmd import Commandable

from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.apdu import ErrorRejectAbortNack

import aiohttp

# $ python3 bacnet_server.py --name Slipstream --instance 3056672 --color --debug


# 'property[index]' matching
property_index_re = re.compile(r"^([A-Za-z-]+)(?:\[([0-9]+)\])?$")
487

class CommandableAnalogValueObject(Commandable, AnalogValueObject):
    """
    Commandable Analog Value Object
    """


_debug = 0
_log = ModuleLogger(globals())

DR_SERVER_URL = "https://bensapi.pythonanywhere.com/payload/current"
USE_DR_SERVER = True
cloud_server_check_in_SECONDS = 10

INTERVAL = 1.0
BACNET_REQ_INTERVAL = 60.0
WRITE_PRIORITY = 10
READ_REQUESTS = [
    {
        "device_address": "12345:2",
        "object_identifier": "analog-input,2",
        "property_identifier": "present-value",
        "property_array_index": None,
        "technology_silo": "hvac",
        "tags": "temp setpoint",
        "note": "conference room 241"
    },
    {
        "device_address": "12345:2",
        "object_identifier": "analog-value,301",
        "property_identifier": "present-value",
        "property_array_index": None,
        "technology_silo": "lighting",
        "tags": "occupancy sensor point",
        "note": "conference room 241"
    },
    {
        "device_address": "12345:2",
        "object_identifier": "analog-value,301",
        "property_identifier": "present-value",
        "technology_silo": "hvac",
        "tags": "occupancy sensor point",
        "note": "conference room 241"
    }
]

WRITE_REQUESTS = [
    {
        "device_address": "12345:2",
        "object_identifier": "analog-value,301",
        "property_identifier": "present-value",
        "technology_silo": "hvac",
        "tags": "occupancy sensor point",
        "note": "conference room 241"
    },
    {
        "device_address": "12345:2",
        "object_identifier": "analog-value,301",
        "property_identifier": "present-value",
        "technology_silo": "lighting",
        "tags": "occupancy sensor point",
        "note": "conference room 241"
    }
]

class SampleApplication:
    def __init__(self, 
                args,
                dr_signal,
                power_level,
                app_status,
                 ):
        # embed an application
        self.app = Application.from_args(args)

        # extract the kwargs that are special to this application
        self.dr_signal = dr_signal
        self.app.add_object(dr_signal)

        self.power_level = power_level
        self.app.add_object(power_level)

        self.app_status = app_status
        self.app.add_object(app_status)
        
        # demand resp server payload from cloud
        self.last_server_payload = 0

        # create a task to update the values
        asyncio.create_task(self.update_bacnet_server_values())
        asyncio.create_task(self.read_property_task())
        
        if USE_DR_SERVER:
            # Create a lock for the server check to ensure it's not running concurrently
            self.server_check_lock = asyncio.Lock()
            asyncio.create_task(self.cloud_server_check_in())
            
    async def cloud_server_check_in(self):
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(DR_SERVER_URL) as response:
                        if response.status == 200:
                            server_data = await response.json()
                            async with self.server_check_lock:
                                self.last_server_payload = server_data.get("payload", 0)
                            _log.info(f"Received server response: {self.last_server_payload}")
                        else:
                            _log.warning(f"Server returned status code {response.status}")
            except Exception as e:
                _log.error(f"Error while fetching server response: {e}")

            await asyncio.sleep(cloud_server_check_in_SECONDS)

    async def share_data_to_bacnet_server(self):
        async with self.server_check_lock:
            return self.last_server_payload
        
    async def update_bacnet_server_values(self):
        while True:
            await asyncio.sleep(INTERVAL)

            self.dr_signal.presentValue = await self.share_data_to_bacnet_server()
            self.app_status.presentValue = "active"
            
            if _debug:
                _log.debug(
                    "    - power_level: %r\n"
                    "    - dr_signal: %r\n"
                    "    - app_status: %r",
                    self.power_level.presentValue,
                    self.dr_signal.presentValue,
                    self.app_status.presentValue,
                )
        
    async def write_property_task(self, 
                                device_address, 
                                object_identifier, 
                                property_identifier, 
                                value, 
                                priority=WRITE_PRIORITY):
        
        if _debug:
            _log.debug("device_address: %r", device_address)
            _log.debug("object_identifier: %r", object_identifier)
        
        # split the property identifier and its index
        property_index_match = property_index_re.match(property_identifier)
        if not property_index_match:
            raise ValueError("property specification incorrect")
        
        property_identifier, property_array_index = property_index_match.groups()
        if property_array_index is not None:
            property_array_index = int(property_array_index)

        if _debug:
            _log.debug("property_array_index: %r", property_array_index)
            
        # check the priority
        if priority:
            priority = int(priority)
            if (priority < 1) or (priority > 16):
                raise ValueError(f"priority: {priority}")
        if _debug:
            _log.debug("priority: %r", priority)
        
        try:
            response = await self.app.write_property(
                device_address,
                object_identifier,
                property_identifier,
                value,
                property_array_index,
                priority,
            )
            if _debug:
                _log.debug("response: %r", response)
            if _debug:
                _log.debug("Write property successful")
        except ErrorRejectAbortNack as err:
            if _debug:
                _log.debug("    - exception: %r", err)
            else:
                print("Write property failed: ", err)

                
    async def condition_check(self, req, response):
        if req["object_identifier"] == "analog-input,2" and response is not None and response > 80:
            return True
        return False
        
    async def read_property_task(self):
        while True:
            for req in READ_REQUESTS:
                await asyncio.sleep(BACNET_REQ_INTERVAL)
                try:
                    device_address = Address(req["device_address"])
                    object_identifier = ObjectIdentifier(req["object_identifier"])
                    response = await self.app.read_property(
                        device_address,
                        object_identifier,
                        req["property_identifier"],
                        req["property_array_index"],
                    )
                    
                    if _debug:
                        _log.debug("device_address: %r", device_address)
                        _log.debug("object_identifier: %r", object_identifier)
                        _log.debug("response: %r", response)

                    # Conditional logic to call write_property_task
                    if await self.condition_check(req, response):
                        
                        # Call write_property_task with the value 100
                        await self.write_property_task(
                            Address(WRITE_REQUESTS[0]["device_address"]),
                            ObjectIdentifier(WRITE_REQUESTS[0]["object_identifier"]),
                            WRITE_REQUESTS[0]["property_identifier"],
                            100,
                        )
                        
                    else:
                        # Call write_property_task with the value 0
                        await self.write_property_task(
                            Address(WRITE_REQUESTS[0]["device_address"]),
                            ObjectIdentifier(WRITE_REQUESTS[0]["object_identifier"]),
                            WRITE_REQUESTS[0]["property_identifier"],
                            0,
                        )

                except ErrorRejectAbortNack as err:
                    if _debug:
                        _log.debug("    - exception: %r", err)
                    response = err

                _log.debug(str(response))


async def main():
    args = SimpleArgumentParser().parse_args()
    if _debug:
        _log.debug("args: %r", args)

    # define BACnet objects
    dr_signal = AnalogValueObject(
        objectIdentifier=("analogValue", 1),
        objectName="demand-response-level",
        presentValue=0.0,
        statusFlags=[0, 0, 0, 0],
        covIncrement=1.0,
        description="SIMPLE SIGNAL demand response level",
    )

    # Create an instance of your commandable object
    power_level = CommandableAnalogValueObject(
        objectIdentifier=("analogValue", 2),
        objectName="power-level",
        presentValue=-1.0,
        statusFlags=[0, 0, 0, 0],
        covIncrement=1.0,
        description="Writeable point for utility meter",
    )
    
    app_status = BinaryValueObject(
        objectIdentifier=("binaryValue", 1),
        objectName="cloud-dr-server-state",
        presentValue="active",
        statusFlags=[0, 0, 0, 0],
        description="True if app can reach to cloud DR server",
    )

    # instantiate the SampleApplication with test_av and test_bv
    app = SampleApplication(
        args,
        dr_signal=dr_signal,
        power_level=power_level,
        app_status=app_status,
    )
    if _debug:
        _log.debug("app: %r", app)

    await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")

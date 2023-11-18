import asyncio
import re

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser

from bacpypes3.app import Application
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.local.binary import BinaryValueObject
from bacpypes3.local.cmd import Commandable

from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.apdu import ErrorRejectAbortNack

import aiohttp

# python3 ~/bacnet-demand-response-client-server/building_bacnet_server/bacnet_server.py --name Slipstream --instance 3056672 --address 10.7.6.201/24:47820 --debug

# 'property[index]' matching
property_index_re = re.compile(r"^([A-Za-z-]+)(?:\[([0-9]+)\])?$")

class CommandableAnalogValueObject(Commandable, AnalogValueObject):
    """
    Commandable Analog Value Object
    """


_debug = 0
_log = ModuleLogger(globals())

DR_SERVER_URL = "https://bensapi.pythonanywhere.com/payload/current"
USE_DR_SERVER = True
CLOUD_DR_SERVER_CHECK_SECONDS= 30

INTERVAL = 1.0
BACNET_REQ_INTERVAL = 60.0
WRITE_PRIORITY = 10
DO_WRITES = False
READ_REQUESTS = [
    {
        "device_address": "32:18",
        "object_identifier": "analog-value,5",
        "property_identifier": "present-value",
        "property_array_index": None,
        "technology_silo": "hvac",
        "tags": "temp setpoint",
        "note": "this is different than the WRITE setpoint"
    },
    {
        "device_address": "32:18",
        "object_identifier": "analog-input,1",
        "property_identifier": "present-value",
        "property_array_index": None,
        "technology_silo": "hvac",
        "tags": "zone temp senor",
        "note": "conference room 241"
    },
    {
        "device_address": "32:18",
        "object_identifier": "analog-input,8",
        "property_identifier": "present-value",
        "property_array_index": None,
        "technology_silo": "hvac",
        "tags": "occupancy sensor point",
        "note": "using CO2 as occ"
    }
]

WRITE_REQUESTS = [
    {
        "device_address": "32:18",
        "object_identifier": "analog-value,14",
        "property_identifier": "present-value",
        "property_array_index": None,
        "technology_silo": "hvac",
        "tags": "temp setpoint",
        "note": "this is different than the READ setpoint"
    },
    {
        "device_address": "32:18",
        "object_identifier": "analog-value,13",
        "property_identifier": "present-value",
        "property_array_index": None,
        "technology_silo": "hvac",
        "tags": "air flow setpoint",
        "note": "conference room 241"
    },
    {
        "device_address": "32:18",
        "object_identifier": "analog-output,2",
        "property_identifier": "present-value",
        "property_array_index": None,
        "technology_silo": "hvac",
        "tags": "chilled beam valve",
        "note": "conference room 241"
    },
    {
        "device_address": "10.7.6.161/24:47820",
        "object_identifier": "analog-value,99",
        "property_identifier": "present-value",
        "property_array_index": None,
        "technology_silo": "blinds",
        "tags": "demand responce",
        "note": "conference room 241"
    },
    {
        "device_address": "10.7.6.161/24:47820",
        "object_identifier": "analog-value,98",
        "property_identifier": "present-value",
        "property_array_index": None,
        "technology_silo": "blinds",
        "tags": "occupancy signal",
        "note": "conference room 241"
    },
    {
        "device_address": "10.7.6.161/24:47820",
        "object_identifier": "analog-value,97",
        "property_identifier": "present-value",
        "property_array_index": None,
        "technology_silo": "blinds",
        "tags": "heating or cooling",
        "note": "conference room 241"
    }
]

''' NOTES
HVAC is AV 97, heat is a 0.0 and cooling is a 1.0
OCC is AV 98, unoc is a 0.0 and occ is a 1.0
DR is AV 99, normal is a 0.0 and DR EVENT is a 1.0
'''

@bacpypes_debugging
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
        self.dr_event_active = False
        self.last_server_payload = 0
        self.current_server_payload = 0
        self.hvac_setpoint_adj = 1.5
        self.hvac_needs_to_be_released = False
        self.room_setpoint_written = False
        
        # for mecho
        # 0 = heating and 1 = cooling
        self.hvac_mode = 0
        self.ppm_for_occ = 600
        self.room_is_occupied = False
        self.occ_to_write = 0.0

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
                                self.current_server_payload = server_data.get("payload", 0)
                            _log.info(f"Received cloud DR server response: {self.current_server_payload}")
                            
                            if self.last_server_payload != self.current_server_payload:
                                _log.info(f" DR EVENT SIGNAL CHANGE")
                                
                                if self.current_server_payload == 1:
                                    _log.info(f" SETTING DR EVENT TRUE")
                                    self.dr_event_active = True
                                    
                                elif self.current_server_payload == 0:
                                    _log.info(f" SETTING DR EVENT FALSE")
                                    self.dr_event_active = False
                                    
                                else: # default to false if the payload value is incorrect
                                    self.dr_event_active = False
                                
                                self.last_server_payload = self.current_server_payload
                        else:
                            _log.warning(f"Cloud DR Server returned status code {response.status}")
                            
            except aiohttp.ClientError as e:
                # Handle network errors and retry after a delay
                _log.error(f"Error while fetching Cloud DR server response: {e}")
                await asyncio.sleep(10)  # Adjust the delay as needed
            except Exception as e:
                _log.error(f"Other error while fetching Cloud DR server response: {e}")

            await asyncio.sleep(CLOUD_DR_SERVER_CHECK_SECONDS)

    async def share_data_to_bacnet_server(self):
        async with self.server_check_lock:
            return self.current_server_payload
        
    async def update_bacnet_server_values(self):
        while True:
            await asyncio.sleep(INTERVAL)

            self.dr_signal.presentValue = await self.share_data_to_bacnet_server()
            self.app_status.presentValue = "active"
            
        
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
            
        if _debug:
            SampleApplication._debug(
                "do_write %r %r %r %r %r",
                device_address,
                object_identifier,
                property_identifier,
                value,
                priority,
            )
        
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
                _log.error("Write property failed: ", err)
                
    async def read_property_task(self):
        while True:
            await asyncio.sleep(BACNET_REQ_INTERVAL)
            
            # Create a list to store read values
            read_values = []

            for req in READ_REQUESTS:
                _log.debug(" READ_REQUESTS GO!!!")
                _log.debug("    - req: %r", req)

                try:
                    if req["tags"] == "temp setpoint":
                        # Read the setpoint value.
                        setpoint_address = Address(req["device_address"])
                        setpoint_identifier = ObjectIdentifier(req["object_identifier"])
                        
                        if _debug:
                            SampleApplication._debug(
                                "do_read %r %r %r %r",
                                setpoint_address,
                                setpoint_identifier,
                                req["property_identifier"],
                                req["property_array_index"]
                            )
                            
                        hvac_setpoint_value = await self.app.read_property(
                            setpoint_address,
                            setpoint_identifier,
                            req["property_identifier"],
                            req["property_array_index"],
                        )
                        
                        _log.debug("    - hvac_setpoint_value: %r", hvac_setpoint_value)
                        read_values.append(hvac_setpoint_value)

                    if req["tags"] == "zone temp senor":
                        # Read the temp value.
                        temp_address = Address(req["device_address"])
                        temp_identifier = ObjectIdentifier(req["object_identifier"])
                        
                        if _debug:
                            SampleApplication._debug(
                                "do_read %r %r %r %r",
                                temp_address,
                                temp_identifier,
                                req["property_identifier"],
                                req["property_array_index"]
                            )
                            
                        hvac_temp_value = await self.app.read_property(
                            temp_address,
                            temp_identifier,
                            req["property_identifier"],
                            req["property_array_index"],
                        )
                        
                        _log.debug("    - hvac_temp_value: %r", hvac_temp_value)
                        read_values.append(hvac_temp_value)

                    if req["tags"] == "occupancy sensor point":
                        # Read the occ value.
                        occupancy_address = Address(req["device_address"])
                        occupancy_identifier = ObjectIdentifier(req["object_identifier"])
                        
                        if _debug:
                            SampleApplication._debug(
                                "do_read %r %r %r %r",
                                occupancy_address,
                                occupancy_identifier,
                                req["property_identifier"],
                                req["property_array_index"]
                            )
                            
                        ppm = await self.app.read_property(
                            occupancy_address,
                            occupancy_identifier,
                            req["property_identifier"],
                            req["property_array_index"],
                        )
                        
                        if ppm > self.ppm_for_occ:
                            self.room_is_occupied = True
                            
                        _log.debug("    - ppm: %r", ppm)
                        _log.debug("    - self.room_is_occupied: %r", self.room_is_occupied)
                        read_values.append(self.room_is_occupied)
                    
                except ErrorRejectAbortNack as err:
                    _log.error(f"Error while processing READ REQUESTS: {err}")

                except Exception as e:
                    _log.error(f"An unexpected error occurred on READ REQUESTS: {e}")

            # Calculate HVAC mode based on temperature and setpoint
            hvac_setpoint_value, hvac_temp_value, self.room_is_occupied = read_values
            _log.debug("    - read_values: %r %r %r", hvac_setpoint_value, hvac_temp_value, self.room_is_occupied)

            # mecho requires an AV for occupancy
            if self.room_is_occupied:
                self.occ_to_write = 1.0
            else:
                self.occ_to_write = 0.0
            
            if hvac_temp_value > hvac_setpoint_value:
                # for mecho window blinds, write continuously
                self.hvac_mode = 1.0 
            else:
                # for mecho window blinds, write continuously
                self.hvac_mode = 0.0 
                
            _log.debug("    - self.hvac_mode: %r", self.hvac_mode)
            _log.debug("    - hvac_setpoint_value: %r", hvac_setpoint_value)
            
            if self.dr_event_active:

                if not self.room_setpoint_written:
                    # for Trane HVAC write, calc new setpoint and write only once
                    hvac_setpoint_value += self.hvac_setpoint_adj 
                    self.room_setpoint_written = True
                    _log.debug("    - new hvac_setpoint_value: %r", hvac_setpoint_value)
                    
                if not self.room_setpoint_written:
                    # for Trane HVAC write, calc new setpoint and write only once
                    hvac_setpoint_value -= self.hvac_setpoint_adj
                    self.room_setpoint_written = True
                    _log.debug("    - new hvac_setpoint_value: %r", hvac_setpoint_value)

            _log.debug(" READ LOOP FINISHED")
            
            if DO_WRITES:
                
                try:
                    # Iterate through WRITE_REQUESTS
                    # always be writing to mecho doesn't need to be released
                    for write_req in WRITE_REQUESTS:
                        
                        if write_req["technology_silo"] == "blinds":
                            if write_req["tags"] == "demand response":
                                # Write last server payload to the "demand response" point.
                                # to Mecho window blind system AnalogValue
                                await self.write_property_task(
                                    Address(write_req["device_address"]),
                                    ObjectIdentifier(write_req["object_identifier"]),
                                    write_req["property_identifier"],
                                    self.current_server_payload,
                                )
                                
                            if write_req["tags"] == "occupancy signal":
                                # Write self.occ_to_write to the "heating or cooling" point.
                                # to Mecho window blind system AnalogValue
                                await self.write_property_task(
                                    Address(write_req["device_address"]),
                                    ObjectIdentifier(write_req["object_identifier"]),
                                    write_req["property_identifier"],
                                    self.occ_to_write,
                                )
                                
                            if write_req["tags"] == "heating or cooling":
                                # Write self.hvac_mode to the "heating or cooling" point.
                                # to Mecho window blind system AnalogValue
                                await self.write_property_task(
                                    Address(write_req["device_address"]),
                                    ObjectIdentifier(write_req["object_identifier"]),
                                    write_req["property_identifier"],
                                    self.hvac_mode,
                                )

                        # if demand response adjust hvac setpoint only if rm is occupied
                        if self.dr_event_active and self.room_is_occupied:
                            _log.debug(" DR EVENT ACTIVE Room is occupied")
                            
                            if write_req["technology_silo"] == "hvac":
                                # Adjust setpoint based on the mode and demand response.
                                if write_req["tags"] == "temp setpoint":
                                    await self.write_property_task(
                                        Address(write_req["device_address"]),
                                        ObjectIdentifier(write_req["object_identifier"]),
                                        write_req["property_identifier"],
                                        hvac_setpoint_value,
                                    )
                                    
                                if write_req["tags"] == "air flow setpoint":
                                    await self.write_property_task(
                                        Address(write_req["device_address"]),
                                        ObjectIdentifier(write_req["object_identifier"]),
                                        write_req["property_identifier"],
                                        "null"  # bacnet release
                                    )
                                    
                                if write_req["tags"] == "chilled beam valve":
                                    await self.write_property_task(
                                        Address(write_req["device_address"]),
                                        ObjectIdentifier(write_req["object_identifier"]),
                                        write_req["property_identifier"],
                                        "null"  # bacnet release
                                    )
                                    
                                self.hvac_needs_to_be_released = True

                        # if demand resp and not occupied close air damper and chilled beam valve
                        if self.dr_event_active and not self.room_is_occupied:
                            _log.debug(" DR EVENT ACTIVE Room is not occupied")
                            
                            if write_req["technology_silo"] == "hvac":
                                # Adjust setpoint based on the mode and demand response.
                                if write_req["tags"] == "temp setpoint":
                                    await self.write_property_task(
                                        Address(write_req["device_address"]),
                                        ObjectIdentifier(write_req["object_identifier"]),
                                        write_req["property_identifier"],
                                        "null"  # bacnet release
                                    )
                                if write_req["tags"] == "air flow setpoint":
                                    await self.write_property_task(
                                        Address(write_req["device_address"]),
                                        ObjectIdentifier(write_req["object_identifier"]),
                                        write_req["property_identifier"],
                                        0,
                                    )
                                if write_req["tags"] == "chilled beam valve":
                                    await self.write_property_task(
                                        Address(write_req["device_address"]),
                                        ObjectIdentifier(write_req["object_identifier"]),
                                        write_req["property_identifier"],
                                        0,
                                    )
                                self.hvac_needs_to_be_released = True

                    # if no demand response release all HVAC one last time
                    if not self.dr_event_active and self.hvac_needs_to_be_released:
                        for write_req in WRITE_REQUESTS:
                            if write_req["technology_silo"] == "hvac":
                                _log.debug(" DR EVENT NOT ACTIVE Releasing all HVAC")
                                
                                # Adjust setpoint based on the mode and demand response.
                                if write_req["tags"] == "temp setpoint":
                                    await self.write_property_task(
                                        Address(write_req["device_address"]),
                                        ObjectIdentifier(write_req["object_identifier"]),
                                        write_req["property_identifier"],
                                        "null"  # bacnet release
                                    )
                                if write_req["tags"] == "air flow setpoint":
                                    await self.write_property_task(
                                        Address(write_req["device_address"]),
                                        ObjectIdentifier(write_req["object_identifier"]),
                                        write_req["property_identifier"],
                                        "null"  # bacnet release
                                    )
                                if write_req["tags"] == "chilled beam valve":
                                    await self.write_property_task(
                                        Address(write_req["device_address"]),
                                        ObjectIdentifier(write_req["object_identifier"]),
                                        write_req["property_identifier"],
                                        "null"  # bacnet release
                                    )
                        self.hvac_needs_to_be_released = False
                        self.room_setpoint_written = False
                        
                    else:
                        _log.debug("passing on BACnet writes DO_WRITES is %r", DO_WRITES)

                except ErrorRejectAbortNack as err:
                    _log.error(f"Error while processing WRITE REQUESTS: {err}")

                except Exception as e:
                    _log.error(f"An unexpected error occurred on WRITE REQUESTS: {e}")


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

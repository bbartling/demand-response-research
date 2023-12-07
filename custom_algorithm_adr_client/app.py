#!/usr/bin/python3

import asyncio
import re
from enum import Enum
from datetime import datetime,timedelta,timezone

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.local.binary import BinaryValueObject
from bacpypes3.local.cmd import Commandable
from bacpypes3.primitivedata import Null
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.apdu import (
    ErrorRejectAbortNack,
    PropertyReference,
    PropertyIdentifier,
    ErrorType,
)

from openleadr import OpenADRClient, enable_default_logging

# $ source drenv/bin/activate

# $ python app.py --name Slipstream --instance 3056672 --debug

class EventActions(Enum):
    """
    Timer mechaninism for when an event ends or starts
    """
    GO = 'go'
    STOP = 'stop'
    
class CommandableAnalogValueObject(Commandable, AnalogValueObject):
    """
    used if writing utility meter value back to server
    """

# Enable OpenLEADR logging
enable_default_logging()

_debug = 0
_log = ModuleLogger(globals())

# 'property[index]' matching
property_index_re = re.compile(r"^([A-Za-z-]+)(?:\[([0-9]+)\])?$")

VEN_NAME = "some_ven"
DR_SERVER_URL = "https://bens.openadr.server/OpenADR2/Simple/2.0b"

USE_OPEN_ADR = True
VEN_TO_VTN_CHECK_IN_INTERVAL= 10

NORMAL_OPERATIONS = 0.0
BACNET_SERVER_UPDATE_INTERVAL = 2.0
BACNET_REQ_INTERVAL = 60.0
WRITE_PRIORITY = 10
APPLY_BACNET_WRITES = False # make BACnet writes to devices
READ_REQUESTS = [
    {
        "device_address": "32:18",
        "object_identifier": "multi-state-value,5",
        "property_identifier": "present-value",
        "property_array_index": None,
        "technology_silo": "hvac",
        "tags": "vav hvac mode",
        "note": "custom trane point for vav box mode"
    },
    {
        "device_address": "32:18",
        "object_identifier": "multi-state-value,5",
        "property_identifier": "present-value",
        "property_array_index": None,
        "technology_silo": "hvac",
        "tags": "hvac mode",
        "note": "hvac mode"
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
        "object_identifier": "analog-value,27",
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
                dr_event_app_error
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
        
        self.dr_event_app_error = dr_event_app_error
        self.app.add_object(dr_event_app_error)
        
        # demand resp server payload from cloud
        self.last_server_payload = 0
        self.current_server_payload = 0
        self.hvac_setpoint_adj = 2.0
        self.hvac_needs_to_be_released = False
        self.room_setpoint_written = False
        
        '''
        MODS NEEDED BELOW HERE
        '''
        # Demand response server payload from cloud
        self.dr_event_active = False
        self.building_meter = 0
        
        self.adr_event_ends = None
        self.adr_start = None
        self.event_payload_value = None
        self.adr_duration = None
        self.event_overrides_applied = False

        self.client = OpenADRClient(ven_name=VEN_NAME, vtn_url=DR_SERVER_URL)
        self.client.add_report(callback=self.collect_report_value,
                                resource_id="main_meter",
                                measurement="power",
                               sampling_rate=timedelta(seconds=VEN_TO_VTN_CHECK_IN_INTERVAL))
        self.client.add_handler('on_event', self.handle_event)
        '''
        MODS NEEDED ABOVE HERE
        '''
        
        # for mecho
        # 0 = heating and 1 = cooling
        self.hvac_mode = 0
        self.ppm_for_occ = 550.0
        self.room_is_occupied = False
        self.occ_to_write = 0.0

        # create a task to update the values
        asyncio.create_task(self.update_bacnet_server_values())
        asyncio.create_task(self.read_property_task())
        
        if USE_OPEN_ADR:
            # Create a lock for the server check to ensure it's not running concurrently
            #self.server_check_lock = asyncio.Lock()
            asyncio.create_task(self.client.run())
            
            
    async def collect_report_value(self):
        dr_sig_val = await self.get_dr_signal()
        bacnet_dr_sig = await self.get_bacnet_dr_signal_pv() 
        bacnet_power_sig = await self.get_bacnet_power_meter_pv()
        meter_reading = await self.get_building_meter_value()
        dr_overrides_status = await self.get_dr_event_active()
        bacnet_apply_err_status = await self.get_bacnet_dr_app_error_status_pv()
        _log.info(f"DR Sig is: {dr_sig_val}")
        _log.info(f"BACnet DR is: {bacnet_dr_sig}")
        _log.info(f"BACnet Power Meter is: {bacnet_power_sig}")
        _log.info(f"Meter Reading is: {meter_reading}")
        _log.info(f"DR Overrides Status is: {dr_overrides_status}")
        _log.info(f"BACnet Apply Error Status is: {bacnet_apply_err_status}")
        _log.info(f"APPLY_BACNET_WRITES: {APPLY_BACNET_WRITES}")
        return meter_reading

    async def handle_event(self, event):
        _log.info(f"handle_event: \n {event}")
        
        intervals = event["event_signals"]
        _log.info(f"Event intervals: \n {intervals}")

        for interval in intervals:
            await self.process_adr_event(interval)
            asyncio.create_task(self.event_checkr())
            
        _log.info(f"Opting in for the events")
        return "optIn"
    
    async def get_dr_event_active(self):
        return self.dr_event_active

    async def get_dr_signal(self):
        return self.current_server_payload

    async def get_bacnet_dr_app_error_status_pv(self):
        return self.dr_event_app_error.presentValue
    
    async def get_bacnet_dr_signal_pv(self):
        return self.dr_signal.presentValue
    
    async def get_bacnet_power_meter_pv(self):
        return self.power_level.presentValue
    
    async def get_building_meter_value(self):
        return self.building_meter

    async def get_adr_start(self):
        return self.adr_start

    async def get_event_payload_value(self):
        return self.event_payload_value

    async def get_adr_duration(self):
        return self.adr_duration

    async def get_adr_event_ends(self):
        return self.adr_event_ends

    async def set_dr_signal(self, val):
        self.current_server_payload = val
        
    async def set_adr_start(self, value):
        self.adr_start = value

    async def set_bacnet_dr_app_error_status_pv(self, value):
        if isinstance(value, bool):
            if value:
                self.dr_event_app_error.presentValue = "active"
                _log.info("set_bacnet_dr_app_error_status_pv set True")
            else:
                self.dr_event_app_error.presentValue = "inactive"
                _log.info("set_bacnet_dr_app_error_status_pv set False")

    async def set_dr_event_active(self, value):
        if isinstance(value, bool):
            self.dr_event_active = value
        else:
            _log.error("Error on dr_event_active")
            raise ValueError("Invalid value for dr_event_active")

    async def set_event_payload_value(self, value):
        self.event_payload_value = value

    async def set_adr_duration(self, value):
        self.adr_duration = value

    async def set_adr_event_ends(self, value):
        self.adr_event_ends = value
    
    async def reset_adr_attributes(self):
        await self.set_adr_start(None)
        await self.set_adr_duration(None)
        await self.set_adr_event_ends(None)
        await self.set_event_payload_value(None)
        
    async def load_shed_event_do(self, delay, item):
        await asyncio.sleep(delay)

        if item == EventActions.GO.value:
            await self.handle_load_shed_event_go()
        elif item == EventActions.STOP.value:
            await self.handle_load_shed_event_stop()
            
    async def handle_load_shed_event_stop(self):
        _log.info("LOAD SHED EVENT STOP!")

        # make changes to the BACnet API
        await self.set_dr_signal(NORMAL_OPERATIONS)
        await self.set_dr_event_active(False)
        await self.reset_adr_attributes()
            
    async def handle_load_shed_event_go(self):
        _log.info("LOAD SHED EVENT GO!")

        # make changes to the BACnet API
        await self.set_dr_signal(self.event_payload_value)
        await self.set_dr_event_active(True)

    async def event_checkr(self):
        now_utc = datetime.now(timezone.utc)
        event_type = await self.get_event_payload_value()
        
        _log.info(f"event_checkr event signal: {event_type}")
        _log.info(f"event_checkr event signal type: {type(event_type)}")

        until_start_time_seconds = (await self.get_adr_start() - now_utc).total_seconds()
        until_end_time_seconds = (await self.get_adr_event_ends() - now_utc).total_seconds()

        _log.info(f"Current time: {now_utc}")
        _log.info(f"Event start: {await self.get_adr_start()}")
        _log.info(f"Time until start: {until_start_time_seconds}")
        _log.info(f"Time until end: {until_end_time_seconds}")

        if event_type == 1.0: # 1.0 is load shed

            # sleeps and then on wake up changes BACnet API to DR event signal
            asyncio.create_task(
                self.load_shed_event_do(until_start_time_seconds, EventActions.GO.value)
            )

            # sleeps and then on wake up changes BACnet API to back to normal ops
            asyncio.create_task(
                self.load_shed_event_do(until_end_time_seconds, EventActions.STOP.value)
            )
            
        else:
            _log.error(f"Unknown event signal: {event_type}")

    async def process_adr_event(self, signal):
        _log.info(f"Processing signal: {signal}")
        interval = signal["intervals"][0]
        
        await self.set_adr_start(interval["dtstart"])
        _log.info(f"ADR start time: {await self.get_adr_start()}")
        
        await self.set_event_payload_value(interval["signal_payload"])
        _log.info(f"Event payload value: {await self.get_event_payload_value()}")
        
        await self.set_adr_duration(interval["duration"])
        _log.info(f"ADR duration: {await self.get_adr_duration()}")
        
        await self.set_adr_event_ends(await self.get_adr_start() + await self.get_adr_duration())
        _log.info(f"ADR event ends: {await self.get_adr_event_ends()}")


    async def update_bacnet_server_values(self):
        while True:
            await asyncio.sleep(BACNET_SERVER_UPDATE_INTERVAL)
            await self.set_bacnet_api_val()
            
    async def set_bacnet_api_val(self):
        dr_signal_val = await self.get_dr_signal()
        if isinstance(dr_signal_val, (float, int)):
            self.dr_signal.presentValue = dr_signal_val
        else:
            _log.error(f"Setting BACnet API error expected a numeric value for DR signal, but got: {type(dr_signal_val)}")
            self.dr_signal.presentValue = NORMAL_OPERATIONS
   
        
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
            
        if value == "null":
            if priority is None:
                raise ValueError("null only for overrides")
            value = Null(())
        
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
        should_continue = True
        hvac_address = Address("32:18")
        mecho_address = Address("10.7.6.161/24:47820")
        
        while True:
            await asyncio.sleep(BACNET_REQ_INTERVAL)
            
            _dr_event_active = await self.get_dr_event_active()
            
            # Create a list to store read values
            read_values = []
            
            _log.info(" READ_REQUESTS GO!!!")

            try:
                # Read the setpoint value.
                setpoint_identifier = ObjectIdentifier("analog-value,27")
                
                if _debug:
                    SampleApplication._debug(
                        "do_read %r %r %r",
                        hvac_address,
                        setpoint_identifier,
                        "present-value",
                    )
                    
                hvac_setpoint_value = await self.app.read_property(
                    hvac_address,
                    setpoint_identifier,
                    "present-value",
                )
                
                _log.info("    - hvac_setpoint_value: %r", hvac_setpoint_value)
                read_values.append(hvac_setpoint_value)

                # Read the vav hvac mode.
                mode_identifier = ObjectIdentifier("multi-state-value,5")
                
                if _debug:
                    SampleApplication._debug(
                        "do_read %r %r %r",
                        hvac_address,
                        mode_identifier,
                        "present-value",
                    )
                    
                hvac_mode_value = await self.app.read_property(
                    hvac_address,
                    mode_identifier,
                    "present-value"
                )
                
                _log.info("    - hvac_mode_value: %r", hvac_mode_value)
                read_values.append(hvac_mode_value)

                # Read the occ value which is C02
                occupancy_identifier = ObjectIdentifier("analog-input,8")
                
                if _debug:
                    SampleApplication._debug(
                        "do_read %r %r %r",
                        hvac_address,
                        occupancy_identifier,
                        "present-value",
                    )
                    
                ppm = await self.app.read_property(
                    hvac_address,
                    occupancy_identifier,
                    "present-value",
                )
                
                if ppm > self.ppm_for_occ:
                    self.room_is_occupied = True
                    
                _log.info("    - ppm: %r", ppm)
                _log.info("    - self.room_is_occupied: %r", self.room_is_occupied)
                read_values.append(self.room_is_occupied)
    
                hvac_setpoint_value, hvac_mode_value, self.room_is_occupied = read_values
                _log.info("    - read_values: %r %r %r", hvac_setpoint_value, hvac_mode_value, self.room_is_occupied)
                
            except ErrorRejectAbortNack as err:
                _log.error(f"Error while processing READ REQUESTS: {err}")
                await self.set_bacnet_dr_app_error_status_pv(True)
                should_continue = False
                return

            except Exception as e:
                _log.error(f"An unexpected error occurred on READ REQUESTS: {e}")
                await self.set_bacnet_dr_app_error_status_pv(True)
                should_continue = False
                return
    
            if should_continue:

                # mecho requires an AV for occupancy
                if self.room_is_occupied:
                    self.occ_to_write = 1.0
                else:
                    self.occ_to_write = 0.0
                
                # modify here. Trane is a 4 that is a cooling, convert to 0.0 for mecho
                # 16 is heating, convert to 1.0 for mecho
                if hvac_mode_value == 4:
                    # for mecho window blinds, write continuously
                    self.hvac_mode = 0.0 # cooling
                else:
                    # for mecho window blinds, write continuously
                    self.hvac_mode = 1.0 # heating
                    
                _log.info("    - self.hvac_mode: %r", self.hvac_mode)
                _log.info("    - hvac_setpoint_value: %r", hvac_setpoint_value)
                
                # add more logic to add or substract setpoints dependent on the cooling or heating modes
                # if heating mode substract the setpoint adj
                # if cooling mode add the setpoint adj
                if _dr_event_active:

                    if not self.room_setpoint_written:
                        # for Trane HVAC write, calc new setpoint and write only once
                        hvac_setpoint_value += self.hvac_setpoint_adj 
                        self.room_setpoint_written = True
                        _log.info("    - new hvac_setpoint_value: %r", hvac_setpoint_value)
                        
                    if not self.room_setpoint_written:
                        # for Trane HVAC write, calc new setpoint and write only once
                        hvac_setpoint_value -= self.hvac_setpoint_adj
                        self.room_setpoint_written = True
                        _log.info("    - new hvac_setpoint_value: %r", hvac_setpoint_value)

                _log.info(" READ LOOP FINISHED")
                
                if APPLY_BACNET_WRITES:
                    
                    try:
                        # Write last server payload to the "demand response" point.
                        # to Mecho window blind system AnalogValue
                        await self.write_property_task(
                            mecho_address,
                            "analog-value,99",
                            "present-value",
                            self.current_server_payload,
                        )
                        
                        # Write self.occ_to_write to the "heating or cooling" point.
                        # to Mecho window blind system AnalogValue
                        await self.write_property_task(
                            mecho_address,
                            "analog-value,98",
                            "present-value",
                            self.occ_to_write,
                        )
                                
                        # Write self.hvac_mode to the "heating or cooling" point.
                        # to Mecho window blind system AnalogValue
                        await self.write_property_task(
                            mecho_address,
                            "analog-value,97",
                            "present-value",
                            self.hvac_mode,
                        )
                        
                    except ErrorRejectAbortNack as err:
                        _log.error(f"Error while processing Mecho Writes: {err}")
                        await self.set_bacnet_dr_app_error_status_pv(True)

                    except Exception as e:
                        _log.error(f"An unexpected error occurred on Mecho Writes: {e}")
                        await self.set_bacnet_dr_app_error_status_pv(True)

                    # if demand response adjust hvac setpoint only if rm is occupied
                    if _dr_event_active and self.room_is_occupied:
                        try:
                            _log.info(" DR EVENT ACTIVE Room is occupied")
                            
                            # write new hvac temp setpoint
                            await self.write_property_task(
                                hvac_address,
                                "analog-value,27",
                                "present-value",
                                hvac_setpoint_value,
                            )
                                    
                            # release air flow
                            await self.write_property_task(
                                hvac_address,
                                "analog-value,13",
                                "present-value",
                                "null"  # bacnet release
                            )
                                    
                            # release chilled beam valve
                            await self.write_property_task(
                                hvac_address,
                                "analog-output,2",
                                "present-value",
                                "null"  # bacnet release
                            )
                                    
                            self.hvac_needs_to_be_released = True

                        except ErrorRejectAbortNack as err:
                            _log.error(f"Error while processing WRITE REQUESTS: {err}")
                            await self.set_bacnet_dr_app_error_status_pv(True)

                        except Exception as e:
                            _log.error(f"An unexpected error occurred on WRITE REQUESTS: {e}")
                            await self.set_bacnet_dr_app_error_status_pv(True)
                    
                    # if demand resp and not occupied close air damper and chilled beam valve
                    if _dr_event_active and not self.room_is_occupied:
                        _log.info(" DR EVENT ACTIVE Room is not occupied")
                        
                        try:
                            # release HVAC setpoint
                            await self.write_property_task(
                                hvac_address,
                                "analog-value,27",
                                "present-value",
                                "null"  # bacnet release
                            )

                            # close air valve
                            await self.write_property_task(
                                hvac_address,
                                "analog-value,13",
                                "present-value",
                                0,
                            )

                            # close chilled beam valve
                            await self.write_property_task(
                                hvac_address,
                                "analog-output,2",
                                "present-value",
                                0,
                            )
                            
                            self.hvac_needs_to_be_released = True

                        except ErrorRejectAbortNack as err:
                            _log.error(f"Error while processing WRITE REQUESTS: {err}")
                            await self.set_bacnet_dr_app_error_status_pv(True)

                        except Exception as e:
                            _log.error(f"An unexpected error occurred on WRITE REQUESTS: {e}")
                            await self.set_bacnet_dr_app_error_status_pv(True)
                            
                # if no demand response release all HVAC one last time
                if not _dr_event_active and self.hvac_needs_to_be_released:

                    _log.info(" DR EVENT NOT ACTIVE Releasing all HVAC")
                    
                    try:

                        # zone setpoint
                        await self.write_property_task(
                            hvac_address,
                            "analog-value,27",
                            "present-value",
                            "null"  # bacnet release
                        )
                        
                        # air flow
                        await self.write_property_task(
                            hvac_address,
                            "analog-value,13",
                            "present-value",
                            "null"  # bacnet release
                        )

                        # chilled beam valve
                        await self.write_property_task(
                            hvac_address,
                            "analog-output,2",
                            "present-value",
                            "null"  # bacnet release
                        )
                        
                        self.hvac_needs_to_be_released = False
                        self.room_setpoint_written = False
                            
                        self.set_bacnet_dr_app_error_status_pv(False)
                        _log.info("_dr_event_active status  %r", _dr_event_active)
                        _log.info("hvac_needs_to_be_released status %r", self.hvac_needs_to_be_released) 
                        _log.info("room_is_occupied status %r", self.room_is_occupied) 
                        
                    except ErrorRejectAbortNack as err:
                        _log.error(f"Error while processing WRITE REQUESTS: {err}")
                        await self.set_bacnet_dr_app_error_status_pv(True)

                    except Exception as e:
                        _log.error(f"An unexpected error occurred on WRITE REQUESTS: {e}")
                        await self.set_bacnet_dr_app_error_status_pv(True)


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
        presentValue="inactive",
        statusFlags=[0, 0, 0, 0],
        description="True if app can reach to cloud DR server",
    )
    
    dr_event_app_error = BinaryValueObject(
        objectIdentifier=("binaryValue", 2),
        objectName="dr-event-app-error",
        presentValue="inactive",
        statusFlags=[0, 0, 0, 0],
        description="App encountered an error when attempting DR event overrides",
    )

    # instantiate the SampleApplication with test_av and test_bv
    app = SampleApplication(
        args,
        dr_signal=dr_signal,
        power_level=power_level,
        app_status=app_status,
        dr_event_app_error=dr_event_app_error
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

import asyncio
import re
from datetime import timedelta, datetime, timezone

from openleadr import OpenADRClient, enable_default_logging

from bacpypes3.basetypes import BinaryPV
from bacpypes3.primitivedata import Null, CharacterString, ObjectIdentifier
from bacpypes3.pdu import Address
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.local.binary import BinaryValueObject
from bacpypes3.local.cmd import Commandable 
from bacpypes3.apdu import (
    ErrorRejectAbortNack,
    PropertyReference,
    PropertyIdentifier,
    ErrorType,
)

from enum import Enum

import yaml

# Enable OpenLEADR logging
enable_default_logging()

_debug = 0
_log = ModuleLogger(globals())

# 'property[index]' matching
property_index_re = re.compile(r"^([A-Za-z-]+)(?:\[([0-9]+)\])?$")

# Load YAML configuration
with open('config.yaml', 'r') as file:
    config = yaml.safe_load(file)

VEN_NAME = config['ven_name']
VTN_URL = config['vtn_url']
NORMAL_OPERATIONS = config['normal_operations_signal_value']
VEN_TO_VTN_CHECK_IN_INTERVAL = config['ven_to_vtn_check_interval_seconds']
BACNET_SERVER_UPDATE_INTERVAL = config['bacnet_server_update_interval_seconds']
METER_READ_INTERVAL = config['meter_read_interval_seconds']
DO_BACNET_WRITES_ON_EVENT_TRUE = config['do_bacnet_writes_on_event_true']

if 'load_shed_write_requests' in config and config['load_shed_write_requests']:
    LOAD_SHED_WRITE_REQUESTS = config['load_shed_write_requests']
else:
    LOAD_SHED_WRITE_REQUESTS = []
    _log.debug(f"LOAD_SHED_WRITE_REQUESTS is an empty list!")


# Define constants for meter_value_open_adr_report
METER_READ_CONFIGS = config['meter_value_open_adr_report'][0]
METER_DEVICE_ADDRESS = METER_READ_CONFIGS['device_address']
METER_OBJECT_ID = METER_READ_CONFIGS['object_identifier']
METER_PROPERTY_ID = METER_READ_CONFIGS['property_identifier']

# set a few globals for the BACnet meter device reading
property_index_match_meter = property_index_re.match(METER_PROPERTY_ID)
property_identifier_meter, _ = property_index_match_meter.groups()
if property_identifier_meter.isdigit():
    property_identifier_meter = int(property_identifier_meter)
object_identifier_meter = ObjectIdentifier.cast(METER_OBJECT_ID)
address_meter = Address(METER_DEVICE_ADDRESS)


# $ python app.py --name Slipstream --instance 3056672 --debug



class EventActions(Enum):
    """
    Timer mechaninism for when an event ends or starts
    """
    GO = 'go'
    STOP = 'stop'
    
class CommandableBinaryValueObject(Commandable, BinaryValueObject):
    """
    This BACnet point is set to be a Commandable or writeable.
    Commandable Binary Value BACnet Object, used for open ADR Opt In Opt Out
    when an open ADR event slides into the handle_event method. BAS or
    control sys inside the building can programmatically or human overrides set
    this BACnet var to Opt In or Opt Out based on conditions before an event comes
    in. IE., if building systems are down or overheating or emergency modes, etc.
    automatically Opt Out of the event if one comes in...
    """

@bacpypes_debugging
class SampleApplication:
    def __init__(self, args, dr_signal, power_level, opt_in_status, dr_event_app_error):
        # embed an application
        self.app = Application.from_args(args)

        # Extract the kwargs that are special to this application
        self.dr_signal = dr_signal
        self.app.add_object(dr_signal)

        self.power_level = power_level
        self.app.add_object(power_level)

        self.opt_in_status = opt_in_status
        self.app.add_object(opt_in_status)
        
        self.dr_event_app_error = dr_event_app_error
        self.app.add_object(dr_event_app_error)

        # Demand response server payload from cloud
        self.dr_event_active = False
        self.building_meter = 0
        self.last_server_payload = 0
        self.current_server_payload = 0
        
        self.adr_event_ends = None
        self.adr_start = None
        self.event_payload_value = None
        self.adr_duration = None
        self.event_overrides_applied = False
        
        self.client = OpenADRClient(ven_name=VEN_NAME, vtn_url=VTN_URL)
        self.client.add_report(callback=self.collect_report_value,
                                resource_id="main_meter",
                                measurement="power",
                               sampling_rate=timedelta(seconds=VEN_TO_VTN_CHECK_IN_INTERVAL))
        self.client.add_handler('on_event', self.handle_event)

        # Create a task to update the values asyncio.create_task(self.update_bacnet_server_values())
        asyncio.create_task(self.update_bacnet_server_values())
        asyncio.create_task(self.make_req_for_meter_value())
        asyncio.create_task(self.client.run())

    async def update_bacnet_server_values(self):
        while True:
            await asyncio.sleep(BACNET_SERVER_UPDATE_INTERVAL)
            await self.set_bacnet_api_val()

    async def make_req_for_meter_value(self):
        while True:
            await asyncio.sleep(METER_READ_INTERVAL)
            await self.set_building_meter_value()

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
    
    async def get_bacnet_opt_in_pv(self):
        return self.opt_in_status.presentValue
    
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
        _log.debug("BACnet API set_bacnet_dr_app_error_status_pv hit")
        if isinstance(value, bool):
            if value:
                self.dr_event_app_error.presentValue = "active"
                _log.debug("set_bacnet_dr_app_error_status_pv set True")
            else:
                self.dr_event_app_error.presentValue = "inactive"
                _log.debug("set_bacnet_dr_app_error_status_pv set False")

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

    async def set_building_meter_value(self):
        meter_value = await self.meter_read_req_bacnet()
        if meter_value is not None:
            self.building_meter = meter_value
        else:
            _log.error("Meter reading failed")

    async def meter_read_req_bacnet(self):
        try:

            if not property_index_match_meter:
                _log.debug("BACnet Meter read error property specification incorrect")
                return

            if _debug:
                _log.debug(
                    "meter_reading %r %r %r",
                    address_meter,
                    object_identifier_meter,
                    property_identifier_meter,
                )

            property_value = await self.app.read_property(
                address_meter, object_identifier_meter, property_identifier_meter
            )
            if _debug:
                _log.debug("Meter read value: %r", property_value)
            return property_value
        
        except ErrorRejectAbortNack as err:
            _log.error("Meter read request ErrorRejectAbortNack: %s", err)
        except Exception as e:
            _log.error("Other error while doing operation: %s", e)

        
    async def apply_bacnet_event_override(self, request, value=None):
        device_address = request.get("device_address")
        object_identifier = request.get("object_identifier")
        property_identifier = request.get("property_identifier")
        priority = request.get("write_priority")

        # If value is not provided in the method call, use the value from the request
        if value is None:
            value = request.get("write_value")

        if _debug:
            _log.debug(
                "apply_bacnet_event_override %r %r %r %r %r",
                device_address,
                object_identifier,
                property_identifier,
                value,
                priority,
            )

        await self.do_write(
            device_address, object_identifier, property_identifier, value, priority
        )

        
    async def do_write(
        self,
        address: Address,
        object_identifier: ObjectIdentifier,
        property_identifier: str,
        value,
        priority: int = -1,
    ) -> None:

        if _debug:
            _log.debug(
                "do_write %r %r %r %r %r",
                address,
                object_identifier,
                property_identifier,
                value,
                priority,
            )
            
        object_identifier = ObjectIdentifier.cast(object_identifier)
        address = Address(address)
            
        if _debug:
            _log.debug(
                "do_write type %r %r %r %r %r",
                type(address),
                type(object_identifier),
                type(property_identifier),
                type(value),
                type(priority),
            )

        # split the property identifier and its index
        property_index_match = property_index_re.match(property_identifier)
        if not property_index_match:
            _log.debug("property specification incorrect")
            return

        property_identifier, property_array_index = property_index_match.groups()
        if property_array_index is not None:
            property_array_index = int(property_array_index)

        if value == "null":
            if priority is None:
                raise ValueError("null only for overrides")
            value = Null(())

        try:
            response = await self.app.write_property(
                address,
                object_identifier,
                property_identifier,
                value,
                property_array_index,
                priority,
            )
            if _debug:
                _log.debug("    - response: %r", response)
                
            self.event_overrides_applied = True
            
            if _debug:
                _log.debug("event overrides applied: %r", self.event_overrides_applied)
            
            assert response is None

        except ErrorRejectAbortNack as err:
            _log.error("ErrorRejectAbortNack: %s", err)
            
        except Exception as e:
            _log.error("Other error while doing operation: %s", e)

    async def set_bacnet_api_val(self):
        dr_signal_val = await self.get_dr_signal()
        if isinstance(dr_signal_val, (float, int)):
            self.dr_signal.presentValue = dr_signal_val
        else:
            _log.error(f"Setting BACnet API error expected a numeric value for DR signal, but got: {type(dr_signal_val)}")
            self.dr_signal.presentValue = NORMAL_OPERATIONS

        meter_reading = await self.get_building_meter_value()
        if isinstance(meter_reading, (float, int)):
            self.power_level.presentValue = meter_reading
        else:
            _log.error(f"Setting BACnet API error expected a numeric value for Building Meter, but got: {type(meter_reading)}")
            self.power_level.presentValue = -1.0           
            
    # ran every VEN_TO_VTN_CHECK_IN_INTERVAL to power value to VTN
    # its a nice debug check when tailing logs
    async def collect_report_value(self):
        dr_sig_val = await self.get_dr_signal()
        bacnet_dr_sig = await self.get_bacnet_dr_signal_pv() 
        bacnet_power_sig = await self.get_bacnet_power_meter_pv()
        bacnet_opt_in_sig = await self.get_bacnet_opt_in_pv()
        meter_reading = await self.get_building_meter_value()
        dr_overrides_status = await self.get_bacnet_dr_app_error_status_pv()
        bacnet_apply_err_status = await self.get_bacnet_dr_app_error_status_pv()
        _log.info(f"DR Sig is: {dr_sig_val}")
        _log.info(f"BACnet DR is: {bacnet_dr_sig}")
        _log.info(f"BACnet Power Meter is: {bacnet_power_sig}")
        _log.info(f"BACnet Opt In Status: {bacnet_opt_in_sig}")
        _log.info(f"Meter Reading is: {meter_reading}")
        _log.info(f"DR Overrides Status is: {dr_overrides_status}")
        _log.info(f"BACnet Apply Error Status is: {bacnet_apply_err_status}")
        return meter_reading

    async def handle_event(self, event):
        bacnet_opt_in_sig = await self.get_bacnet_opt_in_pv()
        _log.info(f"Handling event: {event}")
        _log.info(f"Opt In Out Sig: {bacnet_opt_in_sig}")
        
        if bacnet_opt_in_sig != BinaryPV.active:
            _log.debug(f"Opting out for the events")
            return "optOut"
        
        else:
            intervals = event["event_signals"]
            _log.info(f"Event intervals: {intervals}")

            for interval in intervals:
                await self.process_adr_event(interval)
                asyncio.create_task(self.event_checkr())
                
            _log.info(f"Opting in for the events")
            return "optIn"


    async def load_shed_event_do(self, delay, item):
        await asyncio.sleep(delay)

        if item == EventActions.GO.value:
            await self.handle_load_shed_event_go()
        elif item == EventActions.STOP.value:
            await self.handle_load_shed_event_stop()

    async def handle_load_shed_event_go(self):
        _log.info("LOAD SHED EVENT GO!")

        if DO_BACNET_WRITES_ON_EVENT_TRUE:
            if LOAD_SHED_WRITE_REQUESTS:
                await self.apply_bacnet_event_overrides(LOAD_SHED_WRITE_REQUESTS)
                await self.set_bacnet_dr_app_error_status_pv(False)

            # make changes to the BACnet API
            await self.set_dr_signal(self.event_payload_value)
            await self.set_dr_event_active(True)

            _log.info("handle_load_shed_event_go Success!")
        else:
            _log.info("do_bacnet_writes_on_event_true is False")

    async def handle_load_shed_event_stop(self):
        _log.info("LOAD SHED EVENT STOP!")

        if DO_BACNET_WRITES_ON_EVENT_TRUE:
            if LOAD_SHED_WRITE_REQUESTS:
                await self.apply_bacnet_event_releases(LOAD_SHED_WRITE_REQUESTS)
                await self.set_bacnet_dr_app_error_status_pv(False)
            
            # make changes to the BACnet API
            await self.set_dr_signal(NORMAL_OPERATIONS)
            await self.set_dr_event_active(False)
            await self.reset_adr_attributes()
            
            _log.info("handle_load_shed_event_stop Success!")
        else:
            _log.info("do_bacnet_writes_on_event_true is False")

    async def apply_bacnet_event_overrides(self, requests):
        for request in requests:
            try:
                await self.apply_bacnet_event_override(request)
            except Exception as e:
                await self.set_bacnet_dr_app_error_status_pv(True)
                _log.error(f"Error while applying BACnet event override: {e}")

    async def apply_bacnet_event_releases(self, requests):
        for request in requests:
            try:
                await self.apply_bacnet_event_override(request, value="null")
            except Exception as e:
                await self.set_bacnet_dr_app_error_status_pv(True)
                _log.error(f"Error while applying BACnet event releases: {e}")

    async def reset_adr_attributes(self):
        await self.set_adr_start(None)
        await self.set_adr_duration(None)
        await self.set_adr_event_ends(None)
        await self.set_event_payload_value(None)

    async def event_checkr(self):
        now_utc = datetime.now(timezone.utc)
        event_type = await self.get_event_payload_value()
        
        _log.debug(f"event_checkr event signal: {event_type}")
        _log.debug(f"event_checkr event signal type: {type(event_type)}")

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
        covIncrement=10.0,
        description="SIMPLE SIGNAL demand response level",
    )

    # Create an instance of your commandable object CommandableAnalogValueObject
    power_level = AnalogValueObject(
        objectIdentifier=("analogValue", 0),
        objectName="power-level",
        presentValue=-1.0,
        statusFlags=[0, 0, 0, 0],
        covIncrement=10.0,
        description="Read only point for utility meter being scraped by app",
    )

    opt_in_status = CommandableBinaryValueObject(
        objectIdentifier=("binaryValue", 1),
        objectName="dr-evemt-opt-in",
        presentValue="active",
        statusFlags=[0, 0, 0, 0],
        description="Writeable opt in or out of dr events",
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
        opt_in_status=opt_in_status,
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
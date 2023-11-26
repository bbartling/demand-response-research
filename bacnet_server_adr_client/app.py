import asyncio
import re
from datetime import timedelta, datetime, timezone

from openleadr import OpenADRClient, enable_default_logging

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.local.binary import BinaryValueObject
from bacpypes3.local.cmd import Commandable 

from enum import Enum

import yaml

# Load YAML configuration
with open('config.yaml', 'r') as file:
    config = yaml.safe_load(file)

VEN_NAME = config['ven_name']
VTN_URL = config['vtn_url']
NORMAL_OPERATIONS = config['normal_operations']


# $ python adr_client.py --name Slipstream --instance 3056672 --debug

# Enable OpenLEADR logging
enable_default_logging()

# 'property[index]' matching
property_index_re = re.compile(r"^([A-Za-z-]+)(?:\[([0-9]+)\])?$")

class EventActions(Enum):
    """
    Timer mechaninism for when an event ends or starts
    """
    GO = 'go'
    STOP = 'stop'

class CommandableAnalogValueObject(Commandable, AnalogValueObject):
    """
    Commandable Analog Value Object
    """

_debug = 0
_log = ModuleLogger(globals())

@bacpypes_debugging
class SampleApplication:
    def __init__(self, args, dr_signal, power_level, app_status):
        # embed an application
        self.app = Application.from_args(args)

        # Extract the kwargs that are special to this application
        self.dr_signal = dr_signal
        self.app.add_object(dr_signal)

        self.power_level = power_level
        self.app.add_object(power_level)

        self.app_status = app_status
        self.app.add_object(app_status)

        # Demand response server payload from cloud
        self.dr_event_active = False
        self.building_meter = 0
        self.last_server_payload = 0
        self.current_server_payload = 0
        
        self.adr_event_ends = None
        self.adr_start = None
        self.event_payload_value = None
        self.adr_duration = None
        
        self.client = OpenADRClient(ven_name=VEN_NAME, vtn_url=VTN_URL)
        self.client.add_report(callback=self.collect_report_value,
                                resource_id="main_meter",
                                measurement="power",
                               sampling_rate=timedelta(seconds=10))
        self.client.add_handler('on_event', self.handle_event)

        # Create a task to update the values
        asyncio.create_task(self.update_bacnet_server_values())
        asyncio.create_task(self.grab_meter_value_from_bacnet_server())
        asyncio.create_task(self.client.run())

    async def get_dr_signal(self):
        return self.current_server_payload
    
    async def get_bacnet_dr_signal_pv(self):
        return self.dr_signal.presentValue
    
    async def set_dr_signal(self, val):
        self.current_server_payload = val
        
    async def set_building_meter_value(self, meter_val):
        self.building_meter = meter_val
        
    async def set_bacnet_api_val(self):
        dr_signal_val = await self.get_dr_signal()

        # Check if the value is an instance of float or int (or any numeric type)
        if isinstance(dr_signal_val, (float, int)):
            self.dr_signal.presentValue = dr_signal_val
        else:
            _log.error(f"Expected a numeric value for DR signal, but got: {type(dr_signal_val)}")
            self.dr_signal.presentValue = NORMAL_OPERATIONS
        
    async def collect_report_value(self):
        dr_sig_val = await self.get_dr_signal()
        bacnet_val = await self.get_bacnet_dr_signal_pv()
        _log.debug(f"DR Sig is: {dr_sig_val}")
        _log.debug(f"BACnet API is: {bacnet_val}")
        return self.building_meter

    async def update_bacnet_server_values(self):
        while True:
            await asyncio.sleep(2)
            await self.set_bacnet_api_val()
            
    async def grab_meter_value_from_bacnet_server(self):
        while True:
            await asyncio.sleep(60)
            await self.set_building_meter_value(self.power_level.presentValue)

    async def handle_event(self, event):
        _log.debug(f"Handling event: {event}")

        intervals = event["event_signals"]
        _log.debug(f"Event intervals: {intervals}")

        for interval in intervals:
            self.process_adr_event(interval)
            asyncio.create_task(self.event_checkr())
        return "optIn"
    
    async def event_do(self, delay, item):

        await asyncio.sleep(delay)

        if item == EventActions.GO.value:
            _log.debug("EVENT GO!")
            await self.set_dr_signal(self.event_payload_value)

        elif item == EventActions.STOP.value:
            _log.debug("EVENT STOP!")
            await self.set_dr_signal(NORMAL_OPERATIONS)
            self.adr_start = (
                self.adr_duration
            ) = self.adr_event_ends = self.event_payload_value = None

    async def event_checkr(self):
        now_utc = datetime.now(timezone.utc)
        _log.debug(f"EVENT CHECKR Current time (UTC): {now_utc}")
        _log.debug(f"EVENT CHECKR ADR event start time (UTC): {self.adr_start}")

        until_start_time_seconds = (self.adr_start - now_utc).total_seconds()
        until_end_time_seconds = (self.adr_event_ends - now_utc).total_seconds()

        _log.debug(f"Current time: {now_utc}")
        _log.debug(f"Event start: {self.adr_start}")
        _log.debug(f"Time until start: {until_start_time_seconds}")
        _log.debug(f"Time until end: {until_end_time_seconds}")

        # sleeps and then on wake up changes BACnet API to DR event signal
        asyncio.create_task(
            self.event_do(until_start_time_seconds, EventActions.GO.value)
        )

        # sleeps and then on wake up changes BACnet API to back to normal ops
        asyncio.create_task(
            self.event_do(until_end_time_seconds, EventActions.STOP.value)
        )


    def process_adr_event(self, signal):
        _log.debug(f"Processing signal: {signal}")

        interval = signal["intervals"][0]

        self.adr_start = interval["dtstart"]
        _log.debug(f"ADR start time: {self.adr_start}")

        self.event_payload_value = interval["signal_payload"]
        _log.debug(f"Event payload value: {self.event_payload_value}")

        self.adr_duration = interval["duration"]
        _log.debug(f"ADR duration: {self.adr_duration}")

        self.adr_event_ends = self.adr_start + self.adr_duration
        _log.debug(f"ADR event ends: {self.adr_event_ends}")

        
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
        objectIdentifier=("analogValue", 0),
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
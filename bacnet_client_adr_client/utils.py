from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.local.cmd import Commandable
from bacpypes3.primitivedata import Null
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.local.binary import BinaryValueObject

import re
import asyncio
import logging
from datetime import timedelta, datetime, timezone
import aiohttp
import asyncio
from enum import Enum
from openleadr import OpenADRClient, enable_default_logging

from constants import *


_debug = 1

# Enable logging for openleadr
enable_default_logging()

# Configure the root logger
logging.basicConfig(level=logging.INFO)
logging.getLogger('apscheduler').setLevel(logging.ERROR)


class EventActions(Enum):
    GO = "go"
    STOP = "stop"

class CommandableAnalogValueObject(Commandable, AnalogValueObject):
    """
    Commandable Analog Value Object
    """


class Utils:
    def __init__(self):
        self.current_server_payload = 0
        self.dr_event_active = False
        self.current_server_payload = DEFAULT_PAYLOAD_SIGNAL
        self.last_algorithm_run_time = None
        self.active_events = {}
        self.client = OpenADRClient(ven_name=VEN_NAME, vtn_url=VTN_URL)
        self.client.add_report(
            callback=self.collect_report_value,
            resource_id="main_meter",
            measurement="power",
            sampling_rate=timedelta(seconds=10),
        )
        self.client.add_handler("on_event", self.handle_event)
        
    async def is_any_event_scheduled(self):
        """
        Check if there are any events scheduled in the active_events dictionary.
        Returns True if there are events, False otherwise.
        """
        return bool(self.active_events)
        
    async def check_dr_event_status(self):
        last_dr_event_state = False
        while True:
            current_time = datetime.now(timezone.utc)
            
            if self.dr_event_active:
                if not last_dr_event_state:
                    logging.info("DR EVENT TURNED ON")
                last_dr_event_state = True
                
                if (
                    self.last_algorithm_run_time is None
                    or (current_time - self.last_algorithm_run_time) >= timedelta(seconds=60)
                ):
                    logging.info("DR EVENT IS TRUE!")
                    await self.algorithm()
                    self.last_algorithm_run_time = current_time
            else:
                if last_dr_event_state:
                    logging.info("DR EVENT TURNED OFF")
                    logging.info("RUNNING ALGORITHM ONE MORE TIME!")
                    await self.algorithm()
                last_dr_event_state = False
                logging.info("SETTING DR EVENT FALSE")
            
            await asyncio.sleep(CLOUD_DR_SERVER_CHECK_SECONDS)
        
    def current_adr_payload(self):
        # checked by the BACnet App
        return self.current_server_payload
    
    def is_dr_event_active(self):
        # checked by the BACnet App
        return self.dr_event_active

    async def collect_report_value(self):
        """
        Called every 10 secods by default in open Leadr
        for sending data to the VTN server and appears to
        be useful for debug prints in log to see when next
        ADR event is supposed to hit.
        """
        current_payload_val = self.current_adr_payload()
        logging.info(f" DR EVENT STATUS: {self.dr_event_active}")
        logging.info(f" EVENT PAYLOAD VAL: {current_payload_val}")
        if self.active_events:
            logging.info(" -- FUTURE SCHEDULED ADR EVENTS --")
            for event_id, event_details in self.active_events.items():
                logging.info(f" Event ID: {event_id}, Details: {event_details}")
        else:
            logging.info(" No scheduled ADR events")
        return 1.23  # Replace with actual data collection logic for metering
    
    def cancel_event(self, event_id):
        # Check if the event is in active_events
        if event_id in self.active_events:
            # Cancel associated tasks if they are scheduled
            go_task, stop_task = self.active_events[event_id].get('tasks', (None, None))
            if go_task and not go_task.done():
                go_task.cancel()
            if stop_task and not stop_task.done():
                stop_task.cancel()

            # Remove the event from active_events
            del self.active_events[event_id]
            logging.info(f" Event {event_id} cancelled and removed from active events.")
        else:
            logging.warning(f" Attempted to cancel non-existent event: {event_id}")

    async def handle_event(self, event):
        logging.info(f" Received event: {event}")
        await self.process_adr_event(event)
        return 'optIn'

    async def process_adr_event(self, event):
        event_id = event["event_descriptor"]["event_id"]  # Unique event identifier
        for signal in event["event_signals"]:
            for interval in signal["intervals"]:
                start_time = interval["dtstart"]
                duration = interval["duration"]
                end_time = start_time + duration

                # Store each event separately in the dictionary
                self.active_events[event_id] = {
                    "start": start_time,
                    "end": end_time,
                    "payload": interval["signal_payload"],
                }

                # Schedule tasks for each event
                await self.schedule_event_tasks(event_id)
                
    async def fetch_current_utc_time(self):
        url = "http://worldtimeapi.org/api/timezone/Etc/UTC"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    data = await response.json()
                    utc_time_str = data['utc_datetime']
                    return datetime.fromisoformat(utc_time_str)
        except Exception as e:
            logging.error(f"Failed to fetch UTC time: {e}")
            return None

    async def schedule_event_tasks(self, event_id):
        now_utc = await self.fetch_current_utc_time()
        if not now_utc:
            logging.warning("Using system UTC time as fallback.")
            now_utc = datetime.now(timezone.utc)

        start_delay = (self.active_events[event_id]["start"] - now_utc).total_seconds()
        end_delay = (self.active_events[event_id]["end"] - now_utc).total_seconds()

        logging.info(f"Event {event_id} will start in {start_delay:.2f} seconds and end in {end_delay:.2f} seconds.")
        
        asyncio.create_task(self.event_do(start_delay, event_id, EventActions.GO))
        asyncio.create_task(self.event_do(end_delay, event_id, EventActions.STOP))

    async def event_do(self, delay, event_id, action):
        await asyncio.sleep(delay)
        if action == EventActions.GO:
            self.dr_event_active = True
            self.current_server_payload = self.active_events[event_id]["payload"]
            logging.debug(f"Event {event_id} GO! DR event is now active.")
            # Implement logic to start the DR event
        elif action == EventActions.STOP:
            self.dr_event_active = False
            self.current_server_payload = DEFAULT_PAYLOAD_SIGNAL
            logging.debug(f"Event {event_id} STOP! DR event has ended.")
            # Implement logic to stop the DR event
            self.active_events.pop(event_id, None)

    async def share_data_to_bacnet_server(self):
        # BACnet server processes
        return self.current_server_payload

    async def update_bacnet_server_values(self):
        # BACnet server processes
        while True:
            await asyncio.sleep(BACNET_SERVER_API_UPDATE_INTERVAL)

            self.dr_signal.presentValue = await self.share_data_to_bacnet_server()
            self.app_status.presentValue = "active"

    def parse_property_identifier(self, property_identifier):
        # BACnet writes processess
        # Regular expression for 'property[index]' matching
        property_index_re = re.compile(r"^([A-Za-z-]+)(?:\[([0-9]+)\])?$")

        # Match the property identifier
        property_index_match = property_index_re.match(property_identifier)
        if not property_index_match:
            raise ValueError(" property specification incorrect")

        property_identifier, property_array_index = property_index_match.groups()
        if property_array_index is not None:
            property_array_index = int(property_array_index)

        return property_identifier, property_array_index

    async def do_write_property_task(
        self,
        device_address,
        object_identifier,
        property_identifier,
        value,
        priority=BACNET_WRITE_PRIORITY,
    ):
        if _debug:
            logging.info(" device_address: %r", device_address)
            logging.info(" object_identifier: %r", object_identifier)

        # Use the parse_property_identifier method to split the property identifier and its index
        property_identifier, property_array_index = self.parse_property_identifier(
            property_identifier
        )

        if _debug:
            logging.info(" property_array_index: %r", property_array_index)

        # Check the priority
        if priority:
            priority = int(priority)
            if (priority < 1) or (priority > 16):
                raise ValueError(f"priority: {priority}")
        if _debug:
            logging.info(" priority: %r", priority)

        if _debug:
            logging.info(" value: %r", value)

        if _debug:
            logging.debug(
                "do_write %r %r %r %r %r",
                device_address,
                object_identifier,
                property_identifier,
                value,
                priority,
            )

        if value == "null":
            if priority is None:
                raise ValueError(" null only for overrides")
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
                logging.info(" response: %r", response)
            if _debug:
                logging.info(" Write property successful")
        except ErrorRejectAbortNack as err:
            if _debug:
                logging.info("    - exception: %r", err)
            else:
                logging.error(" Write property failed: ", err)

    async def do_read_property_task(self, requests):
        read_values = []

        logging.info(" READ_REQUESTS GO!!!")

        for request in requests:
            try:
                # Destructure the request into its components
                address, object_id, prop_id, array_index = request

                # Perform the BACnet read property operation
                value = await self.app.read_property(
                    address, object_id, prop_id, array_index
                )
                logging.info(f" Read value for {object_id}: {value}")

                # Append the result to the read_values list
                read_values.append(value)

            except ErrorRejectAbortNack as err:
                logging.error(f" Error while processing READ REQUEST: {err}")
                # Insert "error" in place of the failed read value
                read_values.append("error")

            except Exception as e:
                logging.error(f" An unexpected error occurred on READ REQUEST: {e}")
                # Insert "error" in place of the failed read value
                read_values.append("error")

        return read_values

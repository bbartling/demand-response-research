
from bacpypes3.local.cmd import Commandable
from bacpypes3.primitivedata import Null
from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.local.analog import AnalogValueObject

import re
import asyncio
import logging
from datetime import timedelta, datetime, timezone
import asyncio
from enum import Enum
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from openleadr import OpenADRClient, enable_default_logging

from constants import *


_info = 1

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
        self.scheduler = AsyncIOScheduler()
        self.scheduler.start()
        
        
    def is_any_event_scheduled(self):
        """
        Check if there are any events scheduled in the active_events dictionary.
        Returns True if there are events, False otherwise.
        """
        return bool(self.active_events)
        

    async def handle_event_duration(self, start_delay, event_duration, event_id, payload):
        try:
            logging.info(f"Starting event {event_id} with payload {payload}.")
            self.dr_event_active = True
            self.current_server_payload = payload

            start_time = datetime.now(timezone.utc)
            logging.info(f"Event {event_id}: Loop start time: {start_time.isoformat()}")

            while datetime.now(timezone.utc) - start_time < timedelta(seconds=event_duration):
                current_time = datetime.now(timezone.utc)
                time_elapsed = current_time - start_time
                time_remaining = timedelta(seconds=event_duration) - time_elapsed
                logging.info(f" Executing algorithm for event {event_id}.")
                
                await self.algorithm()
                await asyncio.sleep(ALGORITHM_RUN_FREQUENCY_SECONDS)

            self.dr_event_active = False
            self.current_server_payload = DEFAULT_PAYLOAD_SIGNAL
            logging.info(f"Event {event_id} has ended.")
            await self.algorithm()  # Post-event cleanup to release overrides
            self.active_events.pop(event_id, None)
            

        except asyncio.CancelledError:
            logging.info(f"handle_event_duration: CancelledError hit for event {event_id}.")
        except Exception as e:
            logging.error(f"handle_event_duration: Exception in event {event_id}: {e}")


        
    def current_adr_payload(self):
        # checked by the BACnet App
        return self.current_server_payload
    
    
    def is_dr_event_active(self):
        # checked by the BACnet App
        return self.dr_event_active


    async def schedule_event_tasks(self, event_id):
        event = self.active_events[event_id]

        # Schedule the event handling directly at the start time
        self.scheduler.add_job(
            self.handle_event_duration, 
            'date', 
            run_date=event["start"], 
            args=[0, (event["end"] - event["start"]).total_seconds(), event_id, event["payload"]],
            id=f"{event_id}_start"
        )

            
    async def handle_event(self, event):
        logging.info(f" Received event: {event}")
        await self.process_adr_event(event)
        return 'optIn'


    async def process_adr_event(self, event):
        event_id = event["event_descriptor"]["event_id"]  # Unique event identifier
        current_time = datetime.now(timezone.utc)  # Get the current UTC time as timezone-aware

        for signal in event["event_signals"]:
            for interval in signal["intervals"]:
                start_time = interval["dtstart"]  # Assuming this is a timezone-aware datetime object
                duration = interval["duration"]  # Assuming duration is a timedelta object
                end_time = start_time + duration

                # Check if the event is in the past
                if end_time <= current_time:
                    logging.info(f"Passing on {event_id} as it is in the past")
                    continue

                # Check for overlap with existing events
                if any(self.event_overlaps(start_time, end_time, existing_event) for existing_event in self.active_events.values()):
                    logging.info(f"Skipping overlapping event: {event_id}")
                    continue

                # Store the new event and schedule it
                self.active_events[event_id] = {
                    "start": start_time,
                    "end": end_time,
                    "payload": interval["signal_payload"],
                }
                await self.schedule_event_tasks(event_id)


    def event_overlaps(self, new_start, new_end, existing_event):
        existing_start = existing_event['start']
        existing_end = existing_event['end']
        return new_start < existing_end and new_end > existing_start


    def cancel_event(self, event_id):
        # Check if the event is in active_events
        if event_id in self.active_events:
            # Cancel the scheduled jobs for this event
            start_job_id = f"{event_id}_start"
            end_job_id = f"{event_id}_end"

            start_job = self.scheduler.get_job(start_job_id)
            if start_job:
                start_job.remove()

            end_job = self.scheduler.get_job(end_job_id)
            if end_job:
                end_job.remove()

            # Remove the event from active_events
            del self.active_events[event_id]
            logging.info(f"Event {event_id} cancelled and removed from active events.")
        else:
            logging.warning(f"Attempted to cancel non-existent event: {event_id}")

            
    async def collect_report_value(self):
        """
        Called every 10 seconds by default in OpenLEADR
        for sending data to the VTN server and appears to
        be useful for info prints in log to see when next
        ADR event is supposed to hit.
        """
        current_payload_val = self.current_adr_payload()
        current_utc_time_ = datetime.utcnow()
        current_utc_time_aware = current_utc_time_.replace(tzinfo=timezone.utc)  
        formatted_time = current_utc_time_.strftime('%Y-%m-%d %H:%M:%S UTC')
        
        logging.info(f" DR Event Status: {self.dr_event_active}")
        logging.info(f" Current Payload Value: {current_payload_val}")
        logging.info(f" Current UTC Time: {formatted_time}")
        
        if self.is_any_event_scheduled():
            logging.info(" --- FUTURE SCHEDULED ADR EVENTS ---")
            past_events = []
            total_events = len(self.active_events)  # Total number of scheduled events
            current_event_number = 1  # Initialize event counter

            for event_id, event_details in self.active_events.items():
                try:
                    if event_details["end"] < current_utc_time_aware:
                        past_events.append(event_id)
                    else:
                        
                        start_formatted = event_details["start"].strftime('%Y-%m-%d %H:%M:%S UTC')
                        end_formatted = event_details["end"].strftime('%Y-%m-%d %H:%M:%S UTC')
                        payload = event_details["payload"]
                        
                        logging.info(f"********* EVENT: {current_event_number} ***********************")
                        logging.info(f" Event ID: {event_id}")
                        logging.info(f" Start Time: {start_formatted}")
                        logging.info(f" End Time: {end_formatted}")
                        logging.info(f" Payload: {payload}")
            
                        if current_event_number == total_events:
                            logging.info(f"*****************************************")
                        current_event_number += 1
                except Exception as e:
                    logging.error(f"Error checking event end time: {e}")
            
            for event_id in past_events:
                del self.active_events[event_id]
                logging.info(f" Removed past event: {event_id}")
        else:
            logging.info(" No scheduled ADR events")

        return 1.23  # Replace with actual data collection logic for metering


    async def update_bacnet_server_values(self):
        # BACnet server processes
        while True:
            await asyncio.sleep(BACNET_SERVER_API_UPDATE_INTERVAL)

            self.dr_signal.presentValue = self.share_data_to_bacnet_server()
            self.app_status.presentValue = "active"


    def share_data_to_bacnet_server(self):
        # BACnet server processes
        return self.current_server_payload

    
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
        if _info:
            logging.info(" device_address: %r", device_address)
            logging.info(" object_identifier: %r", object_identifier)

        # Use the parse_property_identifier method to split the property identifier and its index
        property_identifier, property_array_index = self.parse_property_identifier(
            property_identifier
        )

        if _info:
            logging.info(" property_array_index: %r", property_array_index)

        # Check the priority
        if priority:
            priority = int(priority)
            if (priority < 1) or (priority > 16):
                raise ValueError(f"priority: {priority}")
        if _info:
            logging.info(" priority: %r", priority)

        if _info:
            logging.info(" value: %r", value)

        if _info:
            logging.info(
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
            if _info:
                logging.info(" response: %r", response)
            if _info:
                logging.info(" Write property successful")
        except ErrorRejectAbortNack as err:
            if _info:
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

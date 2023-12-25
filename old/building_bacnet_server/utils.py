from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.local.cmd import Commandable
from bacpypes3.primitivedata import Null
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.local.binary import BinaryValueObject

from constants import *

import re
import aiohttp
import asyncio
import time
import logging

logger = logging.getLogger(__name__)
_debug = 0


class CommandableAnalogValueObject(Commandable, AnalogValueObject):
    """
    Commandable Analog Value Object
    """


class Utils:
    def __init__(self):
        self.dr_event_active = False
        self.current_server_payload = 0
        self.last_server_payload = 0
        self.last_dr_event_check = time.time()

    async def cloud_server_check_in(self):
        """
        This method continuously checks in with a cloud server to receive
        DR signals and updates the application's state accordingly every 10 seconds.
        """
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(DR_SERVER_URL) as response:
                        if response.status == 200:
                            server_data = await response.json()

                            self.current_server_payload = server_data.get("payload", 0)
                            logging.info(
                                f" Received cloud DR server response at {time.ctime()}: {self.current_server_payload}"
                            )

                            if self.last_server_payload != self.current_server_payload:
                                logging.info(f" DR EVENT SIGNAL CHANGE")

                                if self.current_server_payload == 1:
                                    logging.info(f" SETTING DR EVENT TRUE")
                                    self.dr_event_active = True
                                    await self.algorithm()

                                elif self.current_server_payload == 0:
                                    logging.info(f" SETTING DR EVENT FALSE")
                                    self.dr_event_active = False

                                    # only run this if it was an actual dr event
                                    # else pass if some other signal was tested
                                    if self.last_server_payload == 1:
                                        logging.info(f" SHOULD BE RUNNING DR RELEASES!")
                                        await self.algorithm()

                                else:  # default to false if the payload value is incorrect
                                    self.dr_event_active = False
                                    logging.info(
                                        f" UNKOWN DR SIGNAL of {self.current_server_payload}"
                                    )

                                self.last_server_payload = self.current_server_payload

                            # New logic for running every 60 seconds
                            elif self.dr_event_active and (
                                time.time() - self.last_dr_event_check >= 60
                            ):
                                logging.info(
                                    f" DR Event active, running task as per 60-second interval"
                                )
                                await self.algorithm()
                                self.last_dr_event_check = time.time()

                        else:
                            logging.warning(
                                f" Cloud DR Server returned status code {response.status}"
                            )

            except aiohttp.ClientError as e:
                # Handle network errors and retry after a delay
                logging.error(f" Error while fetching Cloud DR server response: {e}")
                await asyncio.sleep(10)  # Adjust the delay as needed
            except Exception as e:
                logging.error(
                    f" Other error while fetching Cloud DR server response: {e}"
                )

            await asyncio.sleep(CLOUD_DR_SERVER_CHECK_SECONDS)

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

        # check the priority
        if priority:
            priority = int(priority)
            if (priority < 1) or (priority > 16):
                raise ValueError(f"priority: {priority}")
        if _debug:
            logging.info(" priority: %r", priority)

        if _debug:
            DrApplication._debug(
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

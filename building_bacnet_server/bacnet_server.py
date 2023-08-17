import asyncio
import logging
import BAC0
from bacpypes.primitivedata import Real
from BAC0.core.devices.local.models import analog_value, binary_value
import aiohttp 

# set up logging
logging.basicConfig(level=logging.INFO)

# Constants
DEVICE_NAME = "device_1"
DR_SERVER_URL = "http://localhost:5000/payload/current"
BACNET_INST_ID = 3056672
USE_DR_SERVER = False
SERVER_CHECK_IN_SECONDS = 10

class BACnetApp:
    @classmethod
    async def create(cls):
        self = BACnetApp()
        self.bacnet = await asyncio.to_thread(BAC0.lite, ip=IP_ADDRESS,deviceId=BACNET_INST_ID)
        self.building_meter = 0.0  # default power val
        self.last_server_payload = 0
        _new_objects = self.create_objects()
        _new_objects.add_objects_to_application(self.bacnet)
        logging.info("BACnet APP Created Success!")
        return self

    def create_objects(self):
        _new_objects = analog_value(
            name="power-level",
            description="Writeable point for electric meter reading",
            presentValue=0,
            is_commandable=True,
        )
        _new_objects = analog_value(
            name="demand-response-level",
            description="SIMPLE SIGNAL demand response level",
            presentValue=0,
            is_commandable=False,
        )
        return _new_objects

    async def update_bacnet_api(self, value):
        electric_meter_obj = self.bacnet.this_application.get_object_name("demand-response-level")
        electric_meter_obj.presentValue = value
        
        # update adr payload value to the BACnet API
        adr_sig_object = self.bacnet.this_application.get_object_name(
            "demand-response-level"
        )
        adr_sig_object.presentValue = Real(value)

        # update electric meter write value from BAS for open ADR report
        electric_meter_obj = self.bacnet.this_application.get_object_name("power-level")

        # default value is a BACnet primitive data type called Real that
        if isinstance(electric_meter_obj.presentValue, Real):
            self.building_meter = electric_meter_obj.presentValue.value
        else:
            self.building_meter = electric_meter_obj.presentValue

        logging.info(
            f"Event Level: {self.last_server_payload}, Power Level: {self.building_meter}"
        )

    async def keep_baco_alive(self):
        counter = 0
        while True:
            counter += 1
            await asyncio.sleep(0.01)
            if counter == 100:
                counter = 0
                async with self.server_check_lock:
                    await self.update_bacnet_api(self.last_server_payload)

    async def server_check_in(self):
        while True:
            try:        
                async with aiohttp.ClientSession() as session:
                    async with session.get(DR_SERVER_URL) as response:
                        if response.status == 200:
                            server_data = await response.json()
                            self.last_server_payload = server_data.get("payload", 0)
                            logging.info(f"Received server response: {self.last_server_payload}")
                            async with self.server_check_lock:
                                await self.update_bacnet_api(self.last_server_payload)
                        else:
                            logging.warning(f"Server returned status code {response.status}")
            except Exception as e:
                logging.error(f"Error while fetching server response: {e}")
            
            await asyncio.sleep(SERVER_CHECK_IN_SECONDS)

async def main():
    bacnet_app = await BACnetApp.create()

    tasks = [bacnet_app.keep_baco_alive()]

    if USE_DR_SERVER:
        tasks.append(bacnet_app.server_check_in())

    bacnet_app.server_check_lock = asyncio.Lock()  # Create a lock for synchronization

    await asyncio.gather(*tasks)

asyncio.run(main())

import asyncio
import logging
import BAC0
from bacpypes.primitivedata import Real
from BAC0.core.devices.local.models import analog_value, binary_value

# set up logging
logging.basicConfig(level=logging.INFO)

# Constants
DEVICE_NAME = "device_1"
DR_SERVER_URL = "http://localhost:5000/payload/current"
BACNET_INST_ID = 3056672
USE_DR_SERVER = True
SERVER_CHECK_IN_SECONDS = 10

class BACnetApp:
    @classmethod
    async def create(cls):
        self = BACnetApp()
        self.bacnet = await asyncio.to_thread(BAC0.lite, deviceId=BACNET_INST_ID)
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
        return _new_objects

    def update_bacnet_api(self, value):
        electric_meter_obj = self.bacnet.this_application.get_object_name("power-level")
        electric_meter_obj.presentValue = value

    async def keep_baco_alive(self):
        counter = 0
        while True:
            counter += 1
            # update BACnet API ~ every second
            if counter == 100:
                await asyncio.to_thread(self.update_bacnet_api, 0)  # Set value to 0
                counter = 0
            await asyncio.sleep(0.01)

async def main():
    bacnet_app = await BACnetApp.create()

    tasks = [bacnet_app.keep_baco_alive()]

    if USE_DR_SERVER:
        async def server_check_in():
            while True:
                # Simulate sending POST request to server
                value_from_bacnet = 0
                response = {"response": value_from_bacnet}  # Simulated response
                server_response = response.get("payload", 0)
                logging.info(f"Received server response: {server_response}")
                await asyncio.to_thread(bacnet_app.update_bacnet_api, server_response)
                await asyncio.sleep(SERVER_CHECK_IN_SECONDS)
        
        tasks.append(server_check_in())

    await asyncio.gather(*tasks)

asyncio.run(main())

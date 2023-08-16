import asyncio
import logging
import BAC0
from bacpypes.primitivedata import Real
from BAC0.core.devices.local.models import analog_value, binary_value

# set up logging
logging.basicConfig(level=logging.INFO)

# Constants
DEVICE_NAME = "device_1"
PASSWORD = ""
BACNET_INST_ID = 3056672

# set up logging
logging.basicConfig(level=logging.INFO)

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

class SimpleClient:
    def __init__(self):
        self.server_url = "http://example.com/simple_server"  # Change to your server URL

    async def send_post_request(self, value):
        # Simulate sending POST request to server
        response = {"response": value}
        return response

logging.info("Starting main loop")

async def main():
    bacnet_app = await BACnetApp.create()
    simple_client = SimpleClient()

    while True:
        value_from_bacnet = 0 
        response = await simple_client.send_post_request(value_from_bacnet)

        # Assuming the server's response contains a "response" field with 0 or 1
        server_response = response.get("response", 0)
        await asyncio.to_thread(bacnet_app.update_bacnet_api, server_response)

        await asyncio.sleep(10)  # Adjust for check interval

asyncio.run(main())

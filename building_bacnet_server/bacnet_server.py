import asyncio
import logging
from logging.handlers import TimedRotatingFileHandler
import BAC0
from bacpypes.primitivedata import Real
from BAC0.core.devices.local.models import analog_value, binary_value
from datetime import datetime, timedelta
import aiohttp
from aiohttp import web
import os

# DR Server Setup
DEVICE_NAME = "device_1"
DR_SERVER_URL = "http://localhost:5000/payload/current"
BACNET_INST_ID = 3056672
USE_DR_SERVER = True
SERVER_CHECK_IN_SECONDS = 10

# BACnet NIC setup:
IP_ADDRESS = "192.168.0.101"
SUBNET_MASK_CIDAR = 24
PORT = "47808"
BBMD = None

# Use REST API locally
# to share DR signal to OT
USE_REST = True

# Logging setup
script_directory = os.path.dirname(os.path.abspath(__file__))
log_filename = os.path.join(script_directory, "app_log.log")
logging.basicConfig(level=logging.INFO)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler = TimedRotatingFileHandler(log_filename, when="midnight", interval=1, backupCount=7)
file_handler.setFormatter(log_formatter)

class BACnetApp:
    @classmethod
    async def create(cls):
        self = BACnetApp()
        self.bacnet = await asyncio.to_thread(BAC0.lite, 
                                              ip=IP_ADDRESS, 
                                              port=PORT , 
                                              mask=SUBNET_MASK_CIDAR, 
                                              deviceId=BACNET_INST_ID, 
                                              bbmdAddress=BBMD)
        self.building_meter = 0.0  # default power val
        self.last_server_payload = 0
        self.last_read_write_req_time = datetime.now() - timedelta(seconds=30)
        self.bacnet_app_started = False
        _new_objects = self.create_objects()
        _new_objects.add_objects_to_application(self.bacnet)
        self.server_check_lock = asyncio.Lock()  # Create a lock for synchronization
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
    
    def update_bacnet_points(self, value):
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

        return f"Update BACnet API Success - \
                Event Level: {self.last_server_payload} - \
                Power Level: {self.building_meter}"
                
    def bac0_read_req(self, read_str):
        sensor = self.bacnet.read(read_str)
        return sensor
    
    def bac0_write_req(self, write_str):
        self.bacnet.write(write_str)

    async def get_last_server_payload(self, request):
        payload = {"demand_response_level": self.last_server_payload}
        return web.json_response(payload)

    async def start_rest_api(self):
        app = web.Application()
        app.router.add_get('/api/demand-response-level', self.get_last_server_payload)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 8080)  # Bind to all network interfaces
        await site.start()

    async def update_bacnet_api(self, value):
        result = await asyncio.to_thread(self.update_bacnet_points, value)
        
        logging.info(
            result
        )
        
    async def fire_off_bacnet_requests(self, value):
        current_time = datetime.now()
        if current_time - self.last_read_write_req_time >= timedelta(seconds=30):
            logging.info(
                f"fire_off_bacnet_requests: {self.last_server_payload} \
                    - Value: {value}"
            )
            try:
                read_sensor_str = '12345:2 analogInput 2 presentValue'
                logging.info("Executing BACnet read_sensor_str statement: %s", read_sensor_str)
                sensor = await asyncio.to_thread(self.bac0_read_req, read_sensor_str)
                logging.info("sensor: %s", sensor)

                # write to rasp pi BACnet server running bacpypes
                write_vals = f'12345:2 analogValue 301 presentValue {sensor} - 10'
                await asyncio.to_thread(self.bac0_write_req, write_vals)
                logging.info("Executed BACnet write_vals statement: %s", write_vals)

                av_check_str = '12345:2 analogInput 2 presentValue'
                logging.info("Executing read_sensor_str statement: %s", av_check_str)
                av_check = await asyncio.to_thread(self.bac0_read_req, av_check_str)
                logging.info("av_check: %s", av_check)

            except Exception as e:
                logging.error("Error during fire_off_bacnet_requests: %s", e)

            self.last_read_write_req_time = current_time

            
    async def keep_baco_alive(self):
        counter = 0
        while True:
            if self.bacnet_app_started:
                async with self.server_check_lock:
                    await self.update_bacnet_api(self.last_server_payload)
                    await self.fire_off_bacnet_requests(self.last_server_payload)
                
            else:
                counter += 1
            
            if counter > 5:
                self.bacnet_app_started = True
                
            await asyncio.sleep(1)

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

    if USE_REST:
        tasks.append(bacnet_app.start_rest_api())

    if USE_DR_SERVER:
        tasks.append(bacnet_app.server_check_in())

    await asyncio.gather(*tasks)

asyncio.run(main())


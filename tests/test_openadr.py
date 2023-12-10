import asyncio
import pytest
import logging
from datetime import datetime, timezone, timedelta
from openleadr import OpenADRServer, OpenADRClient, enable_default_logging
from functools import partial

# Configure logging
logging.basicConfig(level=logging.DEBUG)
_log = logging.getLogger(__name__)

# Server Callbacks
async def on_create_party_registration(registration_info):
    if registration_info['ven_name'] == 'ven123':
        return 'ven_id_123', 'reg_id_123'
    else:
        return False

async def on_register_report(ven_id, resource_id, measurement, unit, scale,
                             min_sampling_interval, max_sampling_interval):
    callback = partial(on_update_report, ven_id=ven_id, resource_id=resource_id, measurement=measurement)
    sampling_interval = min_sampling_interval
    return callback, sampling_interval

async def on_update_report(data, ven_id, resource_id, measurement):
    for time, value in data:
        print(f"Ven {ven_id} reported {measurement} = {value} at time {time} for resource {resource_id}")

async def event_response_callback(ven_id, event_id, opt_type):
    print(f"VEN {ven_id} responded to Event {event_id} with: {opt_type}")

# Custom ADR Client
class CustomADRClient(OpenADRClient):
    async def handle_event(self, event):
        _log.debug(f"Handling event: {event}")
        intervals = event["event_signals"]
        _log.debug(f"Event intervals: {intervals}")

        for interval in intervals:
            self.process_adr_event(interval)
            asyncio.create_task(self.event_checkr())
        return "optIn"

    def process_adr_event(self, signal):
        # Process the ADR event signal
        interval = signal["intervals"][0]

        self.adr_start = interval["dtstart"]
        _log.debug(f"ADR start time: {self.adr_start}")

        self.event_payload_value = interval["signal_payload"]
        _log.debug(f"Event payload value: {self.event_payload_value}")

        self.adr_duration = interval["duration"]
        _log.debug(f"ADR duration: {self.adr_duration}")

        self.adr_event_ends = self.adr_start + self.adr_duration
        _log.debug(f"ADR event ends: {self.adr_event_ends}")

    async def event_checkr(self):
        # Check and process the event timing
        now_utc = datetime.now(timezone.utc)
        _log.debug(f"Current time (UTC): {now_utc}")
        _log.debug(f"ADR event start time (UTC): {self.adr_start}")

        until_start_time_seconds = (self.adr_start - now_utc).total_seconds()
        until_end_time_seconds = (self.adr_event_ends - now_utc).total_seconds()

        _log.debug(f"Time until start: {until_start_time_seconds}")
        _log.debug(f"Time until end: {until_end_time_seconds}")

        # Implement your event handling logic here


# Server Fixture
@pytest.fixture
async def server():
    enable_default_logging()
    server = OpenADRServer(vtn_id='myvtn')
    server.add_handler('on_create_party_registration', on_create_party_registration)
    server.add_handler('on_register_report', on_register_report)
    server.add_event(ven_id='ven_id_123', signal_name='simple', signal_type='level',
                     intervals=[{'dtstart': datetime.now(timezone.utc) + timedelta(minutes=1),
                                 'duration': timedelta(minutes=5),
                                 'signal_payload': 1}],
                     callback=event_response_callback)
    
    server_task = asyncio.create_task(server.run())
    yield server
    server_task.cancel()
    await server_task

# Client Fixture
@pytest.fixture
async def client():
    enable_default_logging()
    client = CustomADRClient(ven_name='ven123', vtn_url='http://localhost:8080/OpenADR2/Simple/2.0b')
    client.add_report(callback=collect_report_value, resource_id='device001', measurement='voltage', sampling_rate=timedelta(seconds=10))
    yield client
    client.close()

@pytest.mark.asyncio
async def test_server_client_communication(server, client):
    # Wait for the event to be sent and processed
    await asyncio.sleep(60)  # Wait for the event to start

    # Here you should add code to check the state of the client
    # For example, check if a certain variable or state in the client is set as expected
    # assert client.some_state == expected_value  # Replace with actual condition

    # Optionally, wait for the event to end and perform further checks
    # await asyncio.sleep(5 * 60)  # Wait for the duration of the event
    # Perform more checks/assertions here

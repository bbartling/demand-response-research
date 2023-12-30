from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.local.binary import BinaryValueObject
from bacpypes3.app import Application

import asyncio
import logging

from constants import *
from utils import Utils
from utils import CommandableAnalogValueObject

# python main.py --name Slipstream --instance 3056672 --address 10.7.6.201/24:47820


logging.basicConfig(level=logging.INFO)  

_debug = 0

class DrApplication(Utils):
    def __init__(self, args, dr_signal, power_level, app_status):
        self.hvac_setpoint_adj = 1.5
        self.hvac_needs_to_be_released = False
        self.room_setpoint_written = False
        self.hvac_setpoint_value = 70
        self.hvac_mode_trane = 2

        self.hvac_mode_mecho = 0
        self.ppm_for_occ = 600
        self.ppm_dead_band = 50
        self.room_is_occupied = False
        self.occ_to_write = 0.0

        self.dr_event_event_first_sweep_done = False
        
        super().__init__()

        # embed the bacpypes BACnet application
        self.app = Application.from_args(args)

        # add bacnet server objects to bacpypes3 app
        self.dr_signal = dr_signal
        self.app.add_object(dr_signal)
        self.power_level = power_level
        self.app.add_object(power_level)
        self.app_status = app_status
        self.app.add_object(app_status)
        
        # Start the openleadr client
        asyncio.create_task(self.client.run())

        # create a task to update the values
        asyncio.create_task(self.update_bacnet_server_values())
        
        # Start the periodic check for DR event status in DrApplication
        asyncio.create_task(self.check_dr_event_status())

    async def algorithm(self):
        """
        This method handles the logic for processing the demand response
        (DR) event signal changes and corresponding actions.
        """
        room_is_occupied = False
        hvac_mode_or_room_occ_has_changed = False

        read_requests = [
            # HVAC zone setpoint point
            (
                TRANE_ADDRESS,
                TRANE_TEMP_SETPOINT_READ_WRITE_POINT,
                BACNET_PRESENT_VALUE_PROP_IDENTIFIER,
                BACNET_PROPERTY_ARRAY_INDEX,
            ),
            # HVAC C02 point
            (
                TRANE_ADDRESS,
                TRANE_HVAC_MODE_READ_POINT,
                BACNET_PRESENT_VALUE_PROP_IDENTIFIER,
                BACNET_PROPERTY_ARRAY_INDEX,
            ),
            # HVAC mode point
            (
                TRANE_ADDRESS,
                TRANE_CO2_PPM_READ_POINT,
                BACNET_PRESENT_VALUE_PROP_IDENTIFIER,
                BACNET_PROPERTY_ARRAY_INDEX,
            ),
        ]

        # unpack the 3 values from the BACnet read requests
        hvac_setpoint_value, hvac_mode_trane, ppm = await self.do_read_property_task(
            read_requests
        )

        logging.info(
            " read_values: %r %r %r",
            hvac_setpoint_value,
            hvac_mode_trane,
            room_is_occupied,
        )

        # Adding a dead band of -50 PPM around self.ppm_for_occ
        # Check if ppm is greater than self.ppm_for_occ 
        # (no dead band) to set room as occupied
        if ppm > self.ppm_for_occ:
            room_is_occupied = True
        # If room is already occupied, check if ppm falls below 
        # self.ppm_for_occ - self.ppm_dead_band to set it as unoccupied
        elif self.room_is_occupied and ppm < self.ppm_for_occ - self.ppm_dead_band:
            room_is_occupied = False

        logging.info(" HVAC previous occupancy: %r", self.room_is_occupied)
        logging.info(" HVAC current occupancy: %r", room_is_occupied)

        hvac_mode_or_room_occ_has_changed = (
            self.hvac_mode_trane != hvac_mode_trane
            or self.room_is_occupied != room_is_occupied
        )
        logging.info(" HVAC occ or mode change: %r", hvac_mode_or_room_occ_has_changed)

        # mecho requires an AV for occupancy
        if room_is_occupied:
            self.occ_to_write = 1.0
        else:
            self.occ_to_write = 0.0

        if hvac_mode_trane == 2.0:  # trane is heating
            # for mecho window blinds, write continuously
            hvac_mode_mecho = 1.0
            logging.info(" Setting trane and mecho to heating")

        elif hvac_mode_trane == 4.0:  # trane is cooling
            hvac_mode_mecho = 0.0
            logging.info(" Setting trane and mecho to cooling")

        else:
            logging.info(" Unknown trane hvac mode: %r", hvac_mode_trane)

        if self.dr_event_active:
            if not self.room_setpoint_written and hvac_mode_trane == 2.0:
                # for Trane HVAC write, calc new setpoint and write only once
                hvac_setpoint_value -= self.hvac_setpoint_adj
                self.room_setpoint_written = True
                logging.info(
                    " new RAISED hvac_setpoint_value for a COOLING mode: %r",
                    hvac_setpoint_value,
                )

            elif not self.room_setpoint_written and hvac_mode_trane == 4.0:
                # for Trane HVAC write, calc new setpoint and write only once
                hvac_setpoint_value += self.hvac_setpoint_adj
                self.room_setpoint_written = True
                logging.info(
                    " new LOWERED hvac_setpoint_value for a HEATING mode: %r",
                    hvac_setpoint_value,
                )

        self.hvac_setpoint_value = hvac_setpoint_value
        self.hvac_mode_trane = hvac_mode_trane
        self.room_is_occupied = room_is_occupied
        self.hvac_mode_mecho = hvac_mode_mecho

        logging.info(" dr_event_active %r", self.dr_event_active)
        logging.info(" hvac_needs_to_be_released %r", self.hvac_needs_to_be_released)
        logging.info(" room_is_occupied %r", self.room_is_occupied)
        logging.info(
            " dr event first sweep done %r", self.dr_event_event_first_sweep_done
        )

        if (
            self.dr_event_active
            and not self.hvac_needs_to_be_released
            and not self.dr_event_event_first_sweep_done
            or hvac_mode_or_room_occ_has_changed
        ):
            logging.info("Handle DR Write Ops Go!")

            # always write to mecho window blinds
            await self.do_write_values_to_mecho()

            # HVAC writes
            if self.room_is_occupied:
                await self.do_write_hvac_dr_active_and_room_is_occupied()
            else:
                await self.do_write_hvac_dr_active_and_room_is_not_occupied()

            # set flag to indicate first sweep is done
            self.dr_event_event_first_sweep_done = True

        elif not self.dr_event_active and self.hvac_needs_to_be_released:
            logging.debug("Handling dr release operations!")

            await self.do_release_all_hvac()

            # write to mecho window blinds more time
            await self.do_write_values_to_mecho()

            # reset flag
            self.dr_event_event_first_sweep_done = False

        else:
            logging.info(" No Need to make BACnet writes")

    async def do_release_all_hvac(self):
        logging.info(" Releasing all HVAC!")

        write_requests = [
            (
                TRANE_ADDRESS,
                TRANE_TEMP_SETPOINT_READ_WRITE_POINT,
                BACNET_PRESENT_VALUE_PROP_IDENTIFIER,
                "null",
            ),
            (
                TRANE_ADDRESS,
                TRANE_AIR_FLOW_STP_WRITE_POINT,
                BACNET_PRESENT_VALUE_PROP_IDENTIFIER,
                "null",
            ),
            (
                TRANE_ADDRESS,
                TRANE_COOL_VALVE_WRITE_POINT,
                BACNET_PRESENT_VALUE_PROP_IDENTIFIER,
                "null",
            ),
        ]

        for request in write_requests:
            try:
                # Destructure the request into its components
                address, object_id, prop_id, value = request

                # Perform the BACnet write property operation
                await self.do_write_property_task(address, object_id, prop_id, value)
                logging.info(f" Write successful for {object_id}")

            except Exception as e:
                logging.error(f" An unexpected error occurred on WRITE REQUEST: {e}")

        self.room_setpoint_written = False
        self.hvac_needs_to_be_released = False
        logging.info(" Releasing all HVAC Success.")

    async def do_write_hvac_dr_active_and_room_is_occupied(self):
        logging.info(" DR EVENT ACTIVE Room is occupied Go!")

        write_requests = [
            (
                TRANE_ADDRESS,
                TRANE_TEMP_SETPOINT_READ_WRITE_POINT,
                BACNET_PRESENT_VALUE_PROP_IDENTIFIER,
                self.hvac_setpoint_value,
            ),
            (
                TRANE_ADDRESS,
                TRANE_AIR_FLOW_STP_WRITE_POINT,
                BACNET_PRESENT_VALUE_PROP_IDENTIFIER,
                "null",
            ),
            (
                TRANE_ADDRESS,
                TRANE_COOL_VALVE_WRITE_POINT,
                BACNET_PRESENT_VALUE_PROP_IDENTIFIER,
                "null",
            ),
        ]

        for request in write_requests:
            try:
                # Destructure the request into its components
                address, object_id, prop_id, value = request

                # Perform the BACnet write property operation
                await self.do_write_property_task(address, object_id, prop_id, value)
                logging.info(f" Write successful for {object_id}")

            except Exception as e:
                logging.error(f" An unexpected error occurred on WRITE REQUEST: {e}")

        self.hvac_needs_to_be_released = True
        logging.info(" DR EVENT ACTIVE Room is Occupied Writes Success.")

    async def do_write_hvac_dr_active_and_room_is_not_occupied(self):
        logging.info(" DR EVENT ACTIVE Room is not occupied Go!")

        write_requests = [
            (
                TRANE_ADDRESS,
                TRANE_TEMP_SETPOINT_READ_WRITE_POINT,
                BACNET_PRESENT_VALUE_PROP_IDENTIFIER,
                "null",
            ),
            (
                TRANE_ADDRESS,
                TRANE_AIR_FLOW_STP_WRITE_POINT,
                BACNET_PRESENT_VALUE_PROP_IDENTIFIER,
                0,
            ),
            (
                TRANE_ADDRESS,
                TRANE_COOL_VALVE_WRITE_POINT,
                BACNET_PRESENT_VALUE_PROP_IDENTIFIER,
                0,
            ),
        ]

        for request in write_requests:
            try:
                # Destructure the request into its components
                address, object_id, prop_id, value = request

                # Perform the BACnet write property operation
                await self.do_write_property_task(address, object_id, prop_id, value)
                logging.info(f" Write successful for {object_id}")

            except Exception as e:
                logging.error(f" An unexpected error occurred on WRITE REQUEST: {e}")

        self.hvac_needs_to_be_released = True
        logging.info(" DR EVENT ACTIVE Room is not occupied Writes Success.")

    async def do_write_values_to_mecho(self):
        logging.info(" Mecho Writes Go!")

        write_requests = [
            (
                MECHO_ADDRESS,
                MECHO_DR_WRITE_POINT,
                BACNET_PRESENT_VALUE_PROP_IDENTIFIER,
                self.current_server_payload,
            ),
            (
                MECHO_ADDRESS,
                MECHO_OCC_WRITE_POINT,
                BACNET_PRESENT_VALUE_PROP_IDENTIFIER,
                self.occ_to_write,
            ),
            (
                MECHO_ADDRESS,
                MECHO_HVAC_WRITE_POINT,
                BACNET_PRESENT_VALUE_PROP_IDENTIFIER,
                self.hvac_mode_mecho,
            ),
        ]

        for request in write_requests:
            try:
                # Destructure the request into its components
                address, object_id, prop_id, value = request

                # Perform the BACnet write property operation
                await self.do_write_property_task(address, object_id, prop_id, value)
                logging.info(f" Write successful to Mecho for {object_id}")

            except Exception as e:
                logging.error(
                    f" An unexpected error occurred on Mecho WRITE REQUEST: {e}"
                )

        logging.info(" Mecho Writes Success.")


async def main():
    args = SimpleArgumentParser().parse_args()
    if _debug:
        logging.debug("args: %r", args)

    # define BACnet objects for BACnet server
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
        objectIdentifier=("analogValue", 2),
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

    # instantiate the DrApplication with test_av and test_bv
    app = DrApplication(
        args,
        dr_signal=dr_signal,
        power_level=power_level,
        app_status=app_status,
    )
    if _debug:
        logging.debug("app: %r", app)

    await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if _debug:
            logging.debug("keyboard interrupt")

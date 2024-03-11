from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier


VEN_NAME = "some_ven"
VTN_URL = "https://some.adr.server/OpenADR2/Simple/2.0b"
DEFAULT_PAYLOAD_SIGNAL = 0 # normal operations

USE_DR_SERVER = True
CLOUD_DR_SERVER_CHECK_SECONDS = 10

BACNET_SERVER_API_UPDATE_INTERVAL = 2.0
ALGORITHM_RUN_FREQUENCY_SECONDS = 60.0
BACNET_WRITE_PRIORITY = 3

BACNET_PRESENT_VALUE_PROP_IDENTIFIER = "present-value"
BACNET_PROPERTY_ARRAY_INDEX = None

# devices inside building BACnet addresses
MECHO_ADDRESS = Address("10.7.6.161/24:47820")
TRANE_ADDRESS = Address("32:18")

# writes only to mecho object_identifiers
MECHO_DR_WRITE_POINT = ObjectIdentifier("analog-value,99")
MECHO_OCC_WRITE_POINT = ObjectIdentifier("analog-value,98")
MECHO_HVAC_WRITE_POINT = ObjectIdentifier("analog-value,97")

# HVAC reads object_identifiers
TRANE_TEMP_SETPOINT_READ_WRITE_POINT = ObjectIdentifier("analog-value,27")
TRANE_HVAC_MODE_READ_POINT = ObjectIdentifier("multi-state-value,5")
TRANE_CO2_PPM_READ_POINT = ObjectIdentifier("analog-input,8")

# HVAC writes object_identifiers
TRANE_AIR_FLOW_STP_WRITE_POINT = ObjectIdentifier("analog-value,13")
TRANE_COOL_VALVE_WRITE_POINT = ObjectIdentifier("analog-output,2")

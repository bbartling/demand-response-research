from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier

DR_SERVER_URL = "https://bensflaskapp.oncloud.com/payload/current"
USE_DR_SERVER = True
CLOUD_DR_SERVER_CHECK_SECONDS = 10

BACNET_SERVER_API_UPDATE_INTERVAL = 2.0
ALGORITHM_READ_REQ_INTERVAL = 60.0
BACNET_WRITE_PRIORITY = 3

BACNET_PRESENT_VALUE_PROP_IDENTIFIER = "present-value"
BACNET_PROPERTY_ARRAY_INDEX = None

# devices inside building BACnet addresses
MECHO_ADDRESS = Address("10.7.6.161/24:47820")
TRANE_ADDRESS = Address("32:18")

# writes only to mecho object_identifiers
MECHO_DR_WRITE_POINT = ObjectIdentifier("analog-value,97")
MECHO_HVAC_WRITE_POINT = ObjectIdentifier("analog-value,99")
MECHO_OCC_WRITE_POINT = ObjectIdentifier("analog-value,98")

# HVAC reads object_identifiers
TRANE_TEMP_SETPOINT_READ_WRITE_POINT = ObjectIdentifier("analog-value,27")
TRANE_HVAC_MODE_READ_POINT = ObjectIdentifier("multi-state-value,5")
TRANE_CO2_PPM_READ_POINT = ObjectIdentifier("analog-input,8")

# HVAC writes object_identifiers
TRANE_AIR_FLOW_STP_WRITE_POINT = ObjectIdentifier("analog-value,13")
TRANE_COOL_VALVE_WRITE_POINT = ObjectIdentifier("analog-output,2")

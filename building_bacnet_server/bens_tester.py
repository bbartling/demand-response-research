"""
Bens tester.

test a read of a sensor
> read 12345:2 analog-input,2 present-value

test a write of a point and a release on priority 10
> write 12345:2 analog-value,302 present-value 99 10
> write 12345:2 analog-value,302 present-value null 10

test whois on MSTP devices 2 and 6 on network 12345 with inst hi and low
test whois global with the * 
> whois 12345:2 1 999999
> whois 12345:6 1 999999
> whois *

test whohas
> whohas analog-value,302 12345:2
> whohas analog-value,302 *
> whohas 1 2345 analog-value,302

"""

import asyncio
import re

from typing import Callable

from bacpypes3.pdu import Address
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd
from bacpypes3.primitivedata import Null, CharacterString, ObjectIdentifier
from bacpypes3.comm import bind
from typing import Callable, Optional, List
from bacpypes3.constructeddata import AnyAtomic
from bacpypes3.apdu import ErrorRejectAbortNack, PropertyReference, PropertyIdentifier, ErrorType


# some debugging
_debug = 0
_log = ModuleLogger(globals())

# 'property[index]' matching
property_index_re = re.compile(r"^([A-Za-z-]+)(?:\[([0-9]+)\])?$")

# globals
app: Application

# Define a list to store command history
command_history = []

@bacpypes_debugging
class SampleCmd(Cmd):
    """
    Sample Cmd
    """

    _debug: Callable[..., None]

    async def do_read(
        self,
        address: Address,
        object_identifier: ObjectIdentifier,
        property_identifier: str,
    ) -> None:
        """
        usage: read address objid prop[indx]
        """
        if _debug:
            SampleCmd._debug(
                "do_read %r %r %r", address, object_identifier, property_identifier
            )

        # split the property identifier and its index
        property_index_match = property_index_re.match(property_identifier)
        if not property_index_match:
            await self.response("property specification incorrect")
            return

        property_identifier, property_array_index = property_index_match.groups()
        if property_array_index is not None:
            property_array_index = int(property_array_index)

        try:
            property_value = await app.read_property(
                address, object_identifier, property_identifier, property_array_index
            )
            if _debug:
                SampleCmd._debug("    - property_value: %r", property_value)
        except ErrorRejectAbortNack as err:
            if _debug:
                SampleCmd._debug("    - exception: %r", err)
            property_value = err

        if isinstance(property_value, AnyAtomic):
            if _debug:
                SampleCmd._debug("    - schedule objects")
            property_value = property_value.get_value()

        await self.response(str(property_value))
        
    async def do_write(
        self,
        address: Address,
        object_identifier: ObjectIdentifier,
        property_identifier: str,
        value: str,
        priority: int = -1,
    ) -> None:
        """
        usage: write address objid prop[indx] value [ priority ]
        """
        if _debug:
            SampleCmd._debug(
                "do_write %r %r %r %r %r",
                address,
                object_identifier,
                property_identifier,
                value,
                priority,
            )

        # Manually add the command to the history list
        command = f"write {address} {object_identifier} {property_identifier} {value} {priority}"
        command_history.append(command)

        # split the property identifier and its index
        property_index_match = property_index_re.match(property_identifier)
        if not property_index_match:
            await self.response("property specification incorrect")
            return
        property_identifier, property_array_index = property_index_match.groups()
        if property_array_index is not None:
            property_array_index = int(property_array_index)

        if value == "null":
            if priority is None:
                raise ValueError("null only for overrides")
            value = Null(())

        try:
            response = await app.write_property(
                address,
                object_identifier,
                property_identifier,
                value,
                property_array_index,
                priority,
            )
            if _debug:
                SampleCmd._debug("    - response: %r", response)
            assert response is None

        except ErrorRejectAbortNack as err:
            if _debug:
                SampleCmd._debug("    - exception: %r", err)
            await self.response(str(err))

    async def do_whois(
        self,
        address: Optional[Address] = None,
        low_limit: Optional[int] = None,
        high_limit: Optional[int] = None,
    ) -> None:
        """
        Send a Who-Is request and wait for the response(s).

        usage: whois [ address [ low_limit high_limit ] ]
        """
        if _debug:
            SampleCmd._debug("do_whois %r %r %r", address, low_limit, high_limit)

        i_ams = await app.who_is(low_limit, high_limit, address)
        if not i_ams:
            await self.response("No response(s)")
        else:
            for i_am in i_ams:
                if _debug:
                    SampleCmd._debug("    - i_am: %r", i_am)
                await self.response(f"{i_am.iAmDeviceIdentifier[1]} {i_am.pduSource}")

    async def do_iam(
        self,
        address: Optional[Address] = None,
    ) -> None:
        """
        Send an I-Am request, no response.

        usage: iam [ address ]
        """
        if _debug:
            SampleCmd._debug("do_iam %r", address)

        app.i_am(address)

    async def do_whohas(
        self,
        *args: str,
    ) -> None:
        """
        Send a Who-Has request, an objid or objname (or both) is required.

        usage: whohas [ low_limit high_limit ] [ objid ] [ objname ] [ address ]
        """
        if _debug:
            SampleCmd._debug("do_whohas %r", args)

        if not args:
            raise RuntimeError("object-identifier or object-name expected")
        args_list: List[str] = list(args)

        if args_list[0].isdigit():
            low_limit = int(args_list.pop(0))
        else:
            low_limit = None
        if args_list[0].isdigit():
            high_limit = int(args_list.pop(0))
        else:
            high_limit = None
        if _debug:
            SampleCmd._debug(
                "    - low_limit, high_limit: %r, %r", low_limit, high_limit
            )

        if not args_list:
            raise RuntimeError("object-identifier expected")
        try:
            object_identifier = ObjectIdentifier(args_list[0])
            del args_list[0]
        except ValueError:
            object_identifier = None
        if _debug:
            SampleCmd._debug("    - object_identifier: %r", object_identifier)

        if len(args_list) == 0:
            object_name = address = None
        elif len(args_list) == 2:
            object_name = args_list[0]
            address = Address(args_list[1])
        elif len(args_list) == 1:
            try:
                address = Address(args_list[0])
                object_name = None
            except ValueError:
                object_name = args_list[0]
                address = None
        else:
            raise RuntimeError("unrecognized arguments")
        if _debug:
            SampleCmd._debug("    - object_name: %r", object_name)
            SampleCmd._debug("    - address: %r", address)

        i_haves = await app.who_has(
            low_limit, high_limit, object_identifier, object_name, address
        )
        if not i_haves:
            await self.response("No response(s)")
        else:
            for i_have in i_haves:
                if _debug:
                    SampleCmd._debug("    - i_have: %r", i_have)
                await self.response(
                    f"{i_have.deviceIdentifier[1]} {i_have.objectIdentifier} {i_have.objectName!r}"
                )

    async def do_ihave(
        self,
        object_identifier: ObjectIdentifier,
        object_name: CharacterString,
        address: Optional[Address] = None,
    ) -> None:
        """
        Send an I-Have request.

        usage: ihave objid objname [ address ]
        """
        if _debug:
            SampleCmd._debug(
                "do_ihave %r %r %r", object_identifier, object_name, address
            )

        app.i_have(object_identifier, object_name, address)


async def main() -> None:
    global app

    app = None
    try:
        parser = SimpleArgumentParser()
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # build a very small stack
        console = Console()
        cmd = SampleCmd()
        bind(console, cmd)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # wait until the user is done
        await console.fini.wait()

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())

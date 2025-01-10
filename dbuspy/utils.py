import dbus_fast.aio
import os
import typing
import enum


def sort_dbus_services(services: list[str]) -> None:
    def dbus_service_sort_key(name: str):
        components = name.split(":")
        if components[0] == "":
            return (
                True,
                [int(x) for x in str.join("", components[1:]).split(".")],
                "",
            )
        return False, [], components

    list.sort(services, key=dbus_service_sort_key)


async def get_bus_proxy_object(
    bus: dbus_fast.aio.message_bus.MessageBus,
) -> dbus_fast.aio.proxy_object.ProxyInterface:
    return bus.get_proxy_object(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        await bus.introspect(
            bus_name="org.freedesktop.DBus", path="/org/freedesktop/DBus"
        ),
    ).get_interface("org.freedesktop.DBus")


async def list_dbus_services(
    bus: dbus_fast.aio.message_bus.MessageBus,
) -> list[str]:

    bus_proxy = await get_bus_proxy_object(bus)
    services = await bus_proxy.call_list_names()
    sort_dbus_services(services)

    return services


async def list_dbus_object_children(
    bus: dbus_fast.aio.message_bus.MessageBus, service: str, path: str
):

    return await bus.introspect(
        bus_name=service,
        path=path,
        validate_property_names=False,
    )


async def get_dbus_service_pid(
    bus: dbus_fast.aio.message_bus.MessageBus, service: str
) -> int:
    bus_proxy = await get_bus_proxy_object(bus)
    return await bus_proxy.call_get_connection_unix_process_id(service)


async def get_executable(pid: int) -> typing.Optional[str]:
    return os.readlink(f"/proc/{pid}/exe")


async def get_command_line(pid: int) -> typing.Optional[list[str]]:
    with open(f"/proc/{pid}/cmdline") as f:
        return f.read().split("\0")[:-1]


async def get_dbus_service_uid(
    bus: dbus_fast.aio.message_bus.MessageBus, service: str
) -> int:
    bus_proxy = await get_bus_proxy_object(bus)
    return await bus_proxy.call_get_connection_unix_user(service)


async def get_dbus_service_unique_name(
    bus: dbus_fast.aio.message_bus.MessageBus, service: str
) -> str:
    bus_proxy = await get_bus_proxy_object(bus)
    return await bus_proxy.call_get_name_owner(service)


async def get_user_name(uid: int) -> typing.Optional[str]:
    with open("/etc/passwd") as f:
        for line in f:
            parts = line.split(":")
            if int(parts[2]) == uid:
                return parts[0]
    return None


def get_textual_tree_node_path(node) -> str:
    path = ""
    while not node.is_root:
        path = node.label.__str__() + "/" + path
        assert node.parent is not None
        node = node.parent
    return "/" + path


def generate_dbus_send_argument(arg: dbus_fast.Variant) -> str:
    """Check `man dbus-send` for more information."""

    TOKEN_TO_TYPE = {
        "s": "string",
        "o": "objpath",
        "b": "boolean",
        "y": "byte",
        "q": "uint16",
        "n": "int16",
        "i": "int32",
        "u": "uint32",
        "x": "int64",
        "t": "uint64",
        "d": "double",
    }

    def is_type(v: dbus_fast.Variant) -> bool:
        return v.signature in TOKEN_TO_TYPE

    def to_type_string(v: dbus_fast.Variant) -> str:
        return TOKEN_TO_TYPE[v.signature]

    def is_dictotry(v: dbus_fast.Variant) -> bool:
        return v.signature.startswith("a{")

    def is_array(v: dbus_fast.Variant) -> bool:
        return v.signature.startswith("a") and not is_dictotry(v)

    def is_container(v: dbus_fast.Variant) -> bool:
        return v.signature[0] in ["a", "v"]

    def to_container_string(v: dbus_fast.Variant) -> str:
        if v.signature.startswith("a{"):
            if len(v.signature) != len("a{  }"):
                raise ValueError("Unsupported signature " + v.signature)
            key_type = v.signature[2]
            value_type = v.signature[3]
            if key_type not in TOKEN_TO_TYPE or value_type not in TOKEN_TO_TYPE:
                raise ValueError("Unsupported signature " + v.signature)
            return f"dict:{TOKEN_TO_TYPE[key_type]}:{TOKEN_TO_TYPE[value_type]}"
        if v.signature[0] == "a":
            if len(v.signature) != len("a "):
                raise ValueError("Unsupported signature " + v.signature)
            item_type = v.signature[1]
            if item_type not in TOKEN_TO_TYPE:
                raise ValueError("Unsupported signature " + v.signature)
            return "array:" + TOKEN_TO_TYPE[v.signature[1]]

        if v.signature[0] == "v":
            if len(v.signature) != len("v "):
                raise ValueError("Unsupported signature " + v.signature)
            value_type = v.signature[1]
            if value_type not in TOKEN_TO_TYPE:
                raise ValueError("Unsupported signature " + v.signature)
            return "variant:" + TOKEN_TO_TYPE[v.signature[1]]

        assert False

    def to_container_value(v: dbus_fast.Variant) -> str:
        if is_dictotry(v):
            return ",".join(
                [str(key) + "," + str(value) for key, value in v.value.items()]
            )
        if is_array(v):
            return ",".join([str(x) for x in v.value])

        assert v.signature[0] == "v"
        return str(v.value)

    if is_type(arg):
        return f"{to_type_string(arg)}:{arg.value}"
    elif is_container(arg):
        return f"{to_container_string(arg)}:{to_container_value(arg)}"
    else:
        raise ValueError("Unsupported signature " + arg.signature)


def generate_dbus_send_method_call_command(
    bus_type: typing.Optional[dbus_fast.BusType],
    bus_address: typing.Optional[str],
    service: str,
    path: str,
    interface: str,
    method: str,
    args: typing.Optional[list[dbus_fast.Variant]],
) -> list[str]:
    assert not (bus_type and bus_address)

    command: list[str] = ["dbus-send"]

    if bus_address is not None:
        command.extend(["--address", bus_address])
    elif bus_type is not None:
        if bus_type == dbus_fast.BusType.SESSION:
            command.append("--session")
        elif bus_type == dbus_fast.BusType.SYSTEM:
            command.append("--system")
    else:
        assert False

    command.extend(
        [
            "--type=method_call",
            "--print-reply",
            "--dest=" + service,
            path,
            interface + "." + method,
        ]
    )

    if args is None:
        return command

    for arg in args:
        command.append(generate_dbus_send_argument(arg))

    return command


class DBusArgumentPraseError(Exception):
    def __init__(self, signature: str, arg: str, error: Exception):
        super().__init__(
            f"parse input '{arg}' as D-Bus argument with signature '{signature}': {repr(error)}"
        )


def parse_dbus_argument(
    signature: str | dbus_fast.SignatureType, arg: str
) -> typing.Any:
    try:
        return dbus_fast.Variant(signature, eval(arg))
    except Exception as e:
        if isinstance(signature, dbus_fast.SignatureType):
            signature = signature.signature
        raise DBusArgumentPraseError(signature, arg, e)


class ToolType(enum.Enum):
    DBUS_SEND = "dbus-send"
    DBUS_MONITOR = "dbus-monitor"
    GDBUS = "gdbus"
    QDBUS = "qdbus"
    BUSCTL = "busctl"


class CommandType(enum.Enum):
    METHOD_CALL = "method-call"
    PROPERTY_GET = "property-get"
    PROPERTY_SET = "property-set"
    MONITOR_SIGNAL = "monitor-signal"
    MONITOR_METHOD_CALL = "monitor-method-call"
    MONITOR_METHOD_RETURN = "monitor-method-return"
    MONITOR_PROPERTY_CHANGE = "monitor-property-change"
    MONITOR_PROPERTY_GET = "monitor-property-get"
    MONITOR_PROPERTY_SET = "monitor-property-set"


def generate_dbus_monitor_command(
    bus_type: typing.Optional[dbus_fast.BusType],
    bus_address: typing.Optional[str],
    service: str,
    object_path: str,
    interface: str,
    member: str,
    type: CommandType,
) -> list[str]:
    command: list[str] = ["dbus-monitor"]

    if bus_address is not None:
        command.extend(["--address", bus_address])
    elif bus_type is not None:
        if bus_type == dbus_fast.BusType.SESSION:
            command.append("--session")
        elif bus_type == dbus_fast.BusType.SYSTEM:
            command.append("--system")
    else:
        assert False

    command.append("--monitor")

    if type == CommandType.MONITOR_METHOD_CALL:
        command.append(
            f"type='method_call',interface='{interface}',member='{member}',path='{object_path}',eavesdrop='true'"
        )
    elif type == CommandType.MONITOR_SIGNAL:
        command.append(
            f"type='signal',sender='{service}',interface='{interface}',member='{member}',path='{object_path}'"
        )
    elif type == CommandType.MONITOR_METHOD_RETURN:
        command.append(
            f"type='method_return',interface='{interface}',member='{member}',path='{object_path}',eavesdrop='true'"
        )
    elif type == CommandType.MONITOR_PROPERTY_CHANGE:
        command.append(
            f"type='signal',sender='{service}',interface='org.freedesktop.DBus.Properties',member='PropertiesChanged',path='{object_path}'"
        )
    elif type == CommandType.MONITOR_PROPERTY_GET:
        command.append(
            f"type='method_call',interface='org.freedesktop.DBus.Properties',member='Get',path='{object_path}',eavesdrop='true'"
        )
    elif type == CommandType.MONITOR_PROPERTY_SET:
        command.append(
            f"type='method_call',interface='org.freedesktop.DBus.Properties',member='Set',path='{object_path}',eavesdrop='true'"
        )
    else:
        assert False

    return command


def generate_command(
    bus_type: typing.Optional[dbus_fast.BusType],
    bus_address: typing.Optional[str],
    service: str,
    path: str,
    interface: str,
    member: str,
    args: typing.Optional[list[dbus_fast.Variant]],
    *,
    tool: ToolType,
    type: CommandType,
) -> list[str]:
    assert not (bus_type and bus_address)

    if tool == ToolType.DBUS_SEND:
        if type == CommandType.PROPERTY_GET:
            assert args is None
            args = [
                dbus_fast.Variant("s", interface),
                dbus_fast.Variant("s", member),
            ]
            interface = "org.freedesktop.DBus.Properties"
            member = "Get"
        elif type == CommandType.PROPERTY_SET:
            assert args is not None
            assert len(args) == 1
            args = [
                dbus_fast.Variant("s", interface),
                dbus_fast.Variant("s", member),
                args[0],
            ]
            interface = "org.freedesktop.DBus.Properties"
            member = "Set"
        elif type == CommandType.METHOD_CALL:
            pass
        else:
            assert False

        return generate_dbus_send_method_call_command(
            bus_type, bus_address, service, path, interface, member, args
        )
    elif tool == ToolType.DBUS_MONITOR:
        assert args is None
        return generate_dbus_monitor_command(
            bus_type, bus_address, service, path, interface, member, type
        )

    raise NotImplementedError

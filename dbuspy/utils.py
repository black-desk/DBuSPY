import dbus_next
import os

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

async def list_dbus_services(
    bus: dbus_next.aio.message_bus.MessageBus,
) -> list[str]:
    services = (
        await bus.get_proxy_object(
            "org.freedesktop.DBus",
            "/",
            await bus.introspect(bus_name="org.freedesktop.DBus", path="/"),
        )
        .get_interface("org.freedesktop.DBus")
        .call_list_names()
    )

    sort_dbus_services(services)

    return services

async def list_dbus_object_children(
    bus: dbus_next.aio.message_bus.MessageBus, service: str, path: str
) :
    children = await bus.introspect(bus_name=service, path=path),

    return children

async def get_dbus_service_pid(
    bus: dbus_next.aio.message_bus.MessageBus,
    service: str
) -> int:
    return (
        await bus.get_proxy_object(
            "org.freedesktop.DBus",
            "/",
            await bus.introspect(bus_name="org.freedesktop.DBus", path="/"),
        )
        .get_interface("org.freedesktop.DBus")
        .call_get_connection_unix_process_id(service)
    )

async def get_executable(
    pid: int
) -> str | None:
    return os.readlink(f"/proc/{pid}/exe")

async def get_command_line(
    pid: int
) -> list[str] | None:
    with open(f"/proc/{pid}/cmdline") as f:
        return f.read().split("\0")[:-1]

async def get_dbus_service_uid(
    bus: dbus_next.aio.message_bus.MessageBus,
    service: str
) -> int:
    return (
        await bus.get_proxy_object(
            "org.freedesktop.DBus",
            "/",
            await bus.introspect(bus_name="org.freedesktop.DBus", path="/"),
        )
        .get_interface("org.freedesktop.DBus")
        .call_get_connection_unix_user(service)
    )

async def get_dbus_service_unique_name(
    bus: dbus_next.aio.message_bus.MessageBus,
    service: str
) -> str:
    return (
        await bus.get_proxy_object(
            "org.freedesktop.DBus",
            "/",
            await bus.introspect(bus_name="org.freedesktop.DBus", path="/"),
        )
        .get_interface("org.freedesktop.DBus")
        .call_get_name_owner(service)
    )

async def get_user_name(uid: int) -> str | None:
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


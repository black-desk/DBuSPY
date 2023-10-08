import logging, asyncio
from typing import Optional
from dbus_next.aio.message_bus import MessageBus
from dbus_next.constants import BusType
from textual import on
from textual import work
from textual.binding import Binding
from textual.logging import TextualHandler
from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer, Vertical, Horizontal
from textual.message import Message
from textual.widgets import (
    ListItem,
    Markdown,
    Select,
    Tab,
    Tabs,
    Input,
    Button,
    Footer,
    Header,
    Tree,
    ListView,
    Label,
)

logging.basicConfig(
    level="NOTSET",
    handlers=[TextualHandler()],
)


class NewBus(Message):
    def __init__(self, name: str, bus: MessageBus) -> None:
        super().__init__()
        self.name = name
        self.bus = bus


class ActiveBusChanged(Message):
    def __init__(self, bus: MessageBus) -> None:
        super().__init__()
        self.bus = bus


class ActiveDBusNameChanged(Message):
    def __init__(self, bus: MessageBus, name: str) -> None:
        super().__init__()
        self.bus = bus
        self.name = name


class BusTabs(Tabs):
    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self.buses: dict[str, MessageBus] = {}

    def compose(self) -> ComposeResult:
        return super().compose()

    def add_bus(self, name: str, bus: MessageBus) -> None:
        self.buses[name] = bus
        self.add_tab(Tab(name, id=name))

    def watch_active(self, previously_active: str, active: str) -> None:
        self.post_message(ActiveBusChanged(self.buses[active]))
        super().watch_active(previously_active, active)


class DBusNameList(ListView):
    def __init__(self, id: str):
        super().__init__(id=id)
        self.bus: Optional[MessageBus] = None

    @work(exclusive=True)
    async def switch_to_bus(self, bus: MessageBus):
        self.bus = bus

        daemon_dbus_name = "org.freedesktop.DBus"
        introspection = await bus.introspect(
            daemon_dbus_name, "/org/freedesktop/DBus"
        )

        daemon = bus.get_proxy_object(
            daemon_dbus_name, "/", introspection
        ).get_interface("org.freedesktop.DBus")

        names = await daemon.call_list_names()

        logging.debug(names)

        await self.clear()
        for name in names:
            await self.append(ListItem(Label(name)))

    def watch_index(self, old_index: int, new_index: int) -> None:
        super().watch_index(old_index, new_index)

        if self.bus is None:
            return

        if new_index is None:
            return

        self.post_message(
            ActiveDBusNameChanged(
                self.bus,
                self.children[new_index]
                .get_child_by_type(Label)
                .renderable.__str__(),
            )
        )
        return


class DBusObjectTree(Tree):
    async def get_object_instropection(
        self, bus: MessageBus, name: str, path: str
    ) -> Optional[str]:
        instropection = None
        try:
            instropection = await bus.introspect(name, path)
        except Exception:
            pass

        if instropection is None:
            logging.error(
                "instropect dbus object of service {} on bus {} at {} failed".format(
                    name, bus, path
                )
            )
            return instropection

        instropection = instropection.tostring()
        return instropection

    @work(exclusive=True)
    async def show_dbus_object_tree_of_dbus_name(
        self, bus: MessageBus, name: str
    ) -> None:
        instropection = await self.get_object_instropection(bus, name, "/")


class MethodPanel(Vertical):
    def compose(self) -> ComposeResult:
        yield Input(placeholder="Arguments")

        yield Horizontal(
            Label(
                "copy as",
            ),
            Select(
                [
                    ("dbus-send", "dbus-send"),
                    ("gdbus", "gdbus"),
                    ("qdbus", "qdbus"),
                    ("busctl", "busctl"),
                ],
                value="dbus-send",
                allow_blank=False,
                id="copy-as",
            ),
            Button("copy", id="copy"),
        )

        yield Horizontal(
            Label("times"),
            Input("1", id="times"),
        )
        yield Horizontal(
            Label("result"),
            ScrollableContainer(Markdown("```XXX```", id="result")),
        )
        yield Horizontal(
            Button("call", id="call"),
            id="call_layout",
        )


class DBuSPY(App):
    """A Textual app to manage stopwatches."""

    CSS_PATH = "DBuSPY.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Footer()
        yield BusTabs(id="buses_tabs")
        yield Horizontal(
            ScrollableContainer(DBusNameList(id="dbus_name_list")),
            Vertical(
                ScrollableContainer(DBusObjectTree("/", id="tree")),
                MethodPanel(id="method"),
            ),
        )

    def on_mount(self):
        self.add_buses()

    @work()
    async def add_buses(self):
        # add common buses
        buses_tab = self.get_child_by_id("buses_tabs", expect_type=BusTabs)
        buses_tab.add_bus(
            "session", await MessageBus(bus_type=BusType.SESSION).connect()
        )
        buses_tab.add_bus(
            "system", await MessageBus(bus_type=BusType.SYSTEM).connect()
        )

    @on(ActiveBusChanged)
    def on_active_bus_changed(self, event: ActiveBusChanged) -> None:
        names = self.get_widget_by_id(
            "dbus_name_list", expect_type=DBusNameList
        )
        names.switch_to_bus(event.bus)

    @on(ActiveDBusNameChanged)
    def on_active_dbus_name_changed(self, event: ActiveDBusNameChanged) -> None:
        tree = self.get_widget_by_id("tree", expect_type=DBusObjectTree)
        tree.show_dbus_object_tree_of_dbus_name(event.bus, event.name)


def main():
    app = DBuSPY()
    app.run()

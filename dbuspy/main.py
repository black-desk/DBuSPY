import logging
from typing import Optional, Tuple
from dbus_next.aio.message_bus import MessageBus
from dbus_next.constants import BusType
from dbus_next.introspection import Node
from dbus_next.signature import SignatureType
from rich.style import Style
import rich.text
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


class ActiveDBusObjectChanged(Message):
    def __init__(
        self, bus: MessageBus, name: str, path: str, instropection: Node
    ) -> None:
        super().__init__()
        self.bus = bus
        self.name = name
        self.path = path
        self.instropection = instropection


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
    def __init__(
        self,
        label: str,
        id: str,
    ):
        self.bus: MessageBus | None
        self.dbus_name: str | None
        super().__init__(label, id=id)

    def get_path(self, node) -> str | None:
        path = node.label.__str__()

        while not node == self.root:
            node = node.parent
            if node is None:
                logging.error("node is None")
                return
            if node.label.__str__() != "/":
                path = "/" + path
            path = node.label.__str__() + path

        return path

    async def get_object_instropection(self, path: str) -> Optional[Node]:
        if self.bus is None:
            return
        if self.dbus_name is None:
            return

        instropection = None
        try:
            instropection = await self.bus.introspect(self.dbus_name, path)
        except Exception:
            pass

        if instropection is None:
            logging.error(
                "instropect dbus object of service {} on bus {} at {} failed".format(
                    self.dbus_name, self.bus, path
                )
            )
            return instropection

        return instropection

    @on(Tree.NodeSelected)
    async def on_node_highlighted(self, event: Tree.NodeSelected):
        if self.bus is None:
            return
        if self.dbus_name is None:
            return

        node = event.node
        if node.data is None:
            logging.error("no data found at highlighted node")
            return

        data: Tuple[str, Node] = node.data
        (path, instropection) = data

        self.post_message(
            ActiveDBusObjectChanged(
                self.bus, self.dbus_name, path, instropection
            )
        )

    @on(Tree.NodeCollapsed)
    async def on_node_collapsed(self, event: Tree.NodeCollapsed):
        event.node.remove_children()

    @on(Tree.NodeExpanded)
    async def on_node_expanded(self, event: Tree.NodeExpanded):
        if self.bus is None:
            return

        if self.dbus_name is None:
            return

        node = event.node

        path = self.get_path(event.node)
        if path is None:
            return

        instropection = await self.get_object_instropection(path)
        if instropection is None:
            return

        node.data = (path, instropection)

        for sub_node in instropection.nodes:
            logging.debug(
                "add node {} to tree at {}".format(sub_node.name, path)
            )
            node.add(sub_node.name)


class DBusInterfacesTree(Tree):
    def compose(self) -> ComposeResult:
        self.root.expand()
        return super().compose()

    @work(exclusive=True)
    async def update_content(
        self, bus: MessageBus, name: str, path: str, instropection: Node
    ) -> None:
        self.clear()
        logging.debug(instropection.tostring())
        for interface in instropection.interfaces:
            interface_node = self.root.add(interface.name)
            for prop in interface.properties:
                prop_node = interface_node.add(
                    rich.text.Text("{} [{}]".format(prop.name, prop.signature))
                )
                prop
            for method in interface.methods:
                in_sig = ",".join(
                    [
                        "{}{}".format(
                            (arg.name if not arg.name is None else ""),
                            arg.signature,
                        )
                        for arg in method.in_args
                    ]
                )
                out_sig = ",".join(
                    [
                        "{}{}".format(
                            (arg.name if not arg.name is None else ""),
                            arg.signature,
                        )
                        for arg in method.out_args
                    ]
                )
                sig = "{} -> {}".format(
                    in_sig,
                    out_sig,
                )
                text = rich.text.Text("{} [{}]".format(method.name, sig))
                interface_node.add_leaf(text)


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
            ScrollableContainer(
                DBusNameList(id="dbus_name_list"),
                id="dbus_name_list_container",
            ),
            Vertical(
                Horizontal(
                    ScrollableContainer(
                        DBusObjectTree("/", id="object_tree"),
                        id="object_tree_container",
                    ),
                    ScrollableContainer(
                        DBusInterfacesTree("Interfaces", id="interfaces_list"),
                        id="interfaces_list_container",
                    ),
                ),
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
        tree = self.get_widget_by_id("object_tree", expect_type=DBusObjectTree)
        tree.clear()
        tree.bus = event.bus
        tree.dbus_name = event.name
        tree.root.expand()

    @on(ActiveDBusObjectChanged)
    def on_active_dbus_object_changed(
        self, event: ActiveDBusObjectChanged
    ) -> None:
        interfaces = self.get_widget_by_id(
            "interfaces_list", expect_type=DBusInterfacesTree
        )
        interfaces.update_content(
            event.bus, event.name, event.path, event.instropection
        )


def main():
    app = DBuSPY()
    app.run()

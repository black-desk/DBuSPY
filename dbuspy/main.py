import logging
import xml.etree.ElementTree as ET
from typing import Optional, Tuple
from dbus_next.aio.message_bus import MessageBus
from dbus_next.message import Message as DBusMessage
from dbus_next.constants import BusType
from dbus_next.introspection import Node
from textual import on, work, events
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


class ExpandContainer(Message):
    pass


class ResetContainer(Message):
    pass


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
    def __init__(
        self, bus: MessageBus, old_name: Optional[str], name: str
    ) -> None:
        super().__init__()
        self.bus = bus
        self.old_name = old_name
        self.name = name


class ActiveDBusObjectChanged(Message):
    def __init__(
        self,
        bus: MessageBus,
        name: str,
        path: str,
        instropection: ET.Element,
    ) -> None:
        super().__init__()
        self.bus = bus
        self.name = name
        self.path = path
        self.instropection = instropection


class FocusScrollableContainer(ScrollableContainer):
    @on(ExpandContainer)
    def on_expand_container(self) -> None:
        self.set_styles("min-width: 40%;")

    @on(ResetContainer)
    def on_reset_container(self) -> None:
        self.set_styles("min-width: 0;")


class BusTabs(Tabs):
    def on_mount(self) -> None:
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
    def on_mount(self) -> None:
        self.bus: Optional[MessageBus] = None

    @on(events.Focus)
    async def on_focus(self):
        self.post_message(ExpandContainer())

    @on(events.Blur)
    async def on_blur(self):
        self.post_message(ResetContainer())

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

        self.clear()

        for name in names:
            self.append(ListItem(Label(name)))

    def watch_index(self, old_index: int, new_index: int) -> None:
        super().watch_index(old_index, new_index)

        if self.bus is None:
            return

        if new_index is None:
            return

        self.post_message(
            ActiveDBusNameChanged(
                self.bus,
                self.children[old_index]
                .get_child_by_type(Label)
                .renderable.__str__()
                if not old_index is None
                else None,
                self.children[new_index]
                .get_child_by_type(Label)
                .renderable.__str__(),
            )
        )
        return


class DBusObjectTree(Tree):
    def on_mount(self) -> None:
        self.bus: MessageBus | None
        self.dbus_name: str | None
        self.guide_depth = 3
        return super().on_mount()

    @on(events.Focus)
    async def on_focus(self):
        self.post_message(ExpandContainer())

    @on(events.Blur)
    async def on_blur(self):
        self.post_message(ResetContainer())

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

    async def get_object_instropection(self, path: str) -> Optional[ET.Element]:
        if self.bus is None:
            return
        if self.dbus_name is None:
            return

        instropection = None
        try:
            instropection = await self.bus.call(
                DBusMessage(
                    destination=self.dbus_name,
                    path=path,
                    interface="org.freedesktop.DBus.Introspectable",
                    member="Introspect",
                )
            )
        except Exception:
            pass

        if instropection is None:
            logging.error(
                "instropect dbus object of service {} on bus {} at {} failed".format(
                    self.dbus_name, self.bus, path
                )
            )
            return None
        try:
            return ET.fromstringlist(instropection.body[0])
        except Exception:
            pass

        return None

    @on(Tree.NodeSelected)
    async def on_node_selected(self, event: Tree.NodeSelected):
        if self.bus is None:
            return
        if self.dbus_name is None:
            return

        node = event.node
        if node.data is None:
            logging.error("no data found at highlighted node")
            return

        data: Tuple[str, ET.Element] = node.data
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

        for sub_node in instropection:
            if sub_node.tag != "node":
                continue
            name = sub_node.attrib["name"]
            logging.debug("add node {} to tree at {}".format(name, path))
            node.add(name, path)


class DBusInterfacesTree(Tree):
    def on_mount(self):
        self.guide_depth = 3
        return super().on_mount()

    @on(events.Focus)
    async def on_focus(self):
        self.post_message(ExpandContainer())

    @on(events.Blur)
    async def on_blur(self):
        self.post_message(ResetContainer())

    def compose(self) -> ComposeResult:
        self.root.expand()
        return super().compose()

    @work(exclusive=True)
    async def update_content(
        self, bus: MessageBus, name: str, path: str, instropection: ET.Element
    ) -> None:
        self.clear()
        logging.debug(instropection)
        for interface in instropection:
            if interface.tag != "interface":
                continue

            interface_node = self.root.add(
                interface.attrib["name"], expand=True
            )

            interface_node.expand()

            def signature_of(args):
                return ",".join(
                    [
                        "{}{}".format(
                            (
                                arg.get("name") + ":"
                                if not arg.get("name") is None
                                else ""
                            ),
                            arg.attrib["type"],
                        )
                        for arg in args
                    ]
                )

            properties = interface.findall("property")
            if len(properties):
                props_node = interface_node.add("Properties:", expand=True)
                for prop in properties:
                    props_text = "{} [dim]{}[/dim]".format(
                        prop.attrib["name"], prop.attrib["type"]
                    )
                    annos = prop.findall("annotation")
                    if len(annos):
                        node = props_node.add(props_text).expand()
                        node = node.add("Annotations:").expand()
                        for anno in annos:
                            node.add(anno.attrib["name"]).expand().add_leaf(
                                anno.attrib["value"]
                            )
                    else:
                        props_node.add_leaf("  " + props_text)

            methods = interface.findall("method")
            if len(methods):
                methods_node = interface_node.add("Methods:", expand=True)
                for method in methods:
                    method_text = "{} [dim]{} -> {}[/dim]".format(
                        method.attrib["name"],
                        signature_of(
                            [
                                arg
                                for arg in method.findall("arg")
                                if arg.attrib["direction"] == "in"
                            ]
                        ),
                        signature_of(
                            [
                                arg
                                for arg in method.findall("arg")
                                if arg.attrib["direction"] == "out"
                            ]
                        ),
                    )
                    annos = method.findall("annotation")
                    if len(annos):
                        node = methods_node.add(method_text).expand()
                        node = node.add("Annotations:").expand()
                        for anno in annos:
                            node.add(anno.attrib["name"]).expand().add_leaf(
                                anno.attrib["value"]
                            )

                    else:
                        methods_node.add_leaf("  " + method_text)
            signals = interface.findall("signal")
            if len(signals):
                signals_node = interface_node.add("Signals:", expand=True)
                for signal in signals:
                    signal_text = "{} [dim]{}[/dim]".format(
                        signal.attrib["name"],
                        signature_of(signal.findall("arg")),
                    )
                    annos = signal.findall("annotation")
                    if len(annos):
                        node = signals_node.add(signal_text).expand()
                        node = node.add("Annotations:").expand()
                        for anno in annos:
                            node.add(anno.attrib["name"]).expand().add_leaf(
                                anno.attrib["value"]
                            )
                    else:
                        signals_node.add_leaf("  " + signal_text)


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
            FocusScrollableContainer(
                DBusNameList(id="dbus_name_list"),
            ),
            FocusScrollableContainer(
                DBusObjectTree("/", id="object_tree"),
            ),
            FocusScrollableContainer(
                DBusInterfacesTree("Interfaces:", id="interfaces_list"),
            ),
            FocusScrollableContainer(MethodPanel(id="method")),
        )

    def on_mount(self):
        self.add_buses()
        self.get_widget_by_id(
            "dbus_name_list", expect_type=DBusNameList
        ).focus()

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
        if not event.old_name is None:
            tree.focus()

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
        interfaces.focus()


def main():
    app = DBuSPY()
    app.run()

from . import utils
import dbus_fast.aio
import dbus_fast.auth
import os
import rich.text
import shlex
import textual.app
import textual.binding
import textual.containers
import textual.css.query
import textual.message
import textual.reactive
import textual.screen
import textual.widgets
import typing
import uuid
import traceback


class DBuSPY(textual.app.App):
    """A D-Feet like application."""

    BINDINGS = [
        textual.binding.Binding("escape,q", "quit", "Quit"),
    ]

    def compose(self) -> textual.app.ComposeResult:
        yield textual.widgets.Header()
        yield textual.widgets.Footer()
        yield MainPage()


class MessageBus(dbus_fast.aio.message_bus.MessageBus):
    def __init__(
        self,
        bus_address: typing.Optional[str] = None,
        bus_type: dbus_fast.BusType = dbus_fast.BusType.SESSION,
        auth: typing.Optional[dbus_fast.auth.Authenticator] = None,
        negotiate_unix_fd: bool = False,
    ):
        super().__init__(
            bus_address=bus_address,
            bus_type=bus_type,
            auth=auth,
            negotiate_unix_fd=negotiate_unix_fd,
        )

        self.bus_type = bus_type
        self.bus_address = bus_address


class MainPage(textual.containers.Container):
    message_buses = textual.reactive.reactive[
        typing.Optional[dict[str, MessageBus]]
    ](None)

    def on_mount(self):
        self.loading = True
        self.add_buses()

    @textual.work()
    async def add_buses(self):
        message_buses = {}

        # NOTE: root user doesn't have session bus
        if os.getuid() != 0:
            message_buses["session"] = await MessageBus(
                bus_type=dbus_fast.constants.BusType.SESSION
            ).connect()

        message_buses["system"] = await MessageBus(
            bus_type=dbus_fast.constants.BusType.SYSTEM
        ).connect()

        self.set_reactive(MainPage.message_buses, message_buses)
        self.mutate_reactive(MainPage.message_buses)

        self.loading = False

    @textual.work(exclusive=True, group="watch_message_buses")
    async def watch_message_buses(self):
        if self.message_buses == None:
            return

        for id, bus in self.message_buses.items():
            try:
                self.query_one(textual.widgets.TabbedContent).get_pane(id)
            except textual.css.query.NoMatches:
                await self.query_one(textual.widgets.TabbedContent).add_pane(
                    textual.widgets.TabPane(id, BusPane(bus), id=id)
                )

    def compose(self) -> textual.app.ComposeResult:
        yield textual.widgets.TabbedContent()


class ObjectsTree(textual.widgets.Tree):
    def __init__(
        self,
        bus: dbus_fast.aio.message_bus.MessageBus,
        service: str,
        introspection: dbus_fast.introspection.Node,
    ):
        super().__init__("/", introspection)

        self.bus = bus
        self.service = service
        self.guide_depth = 2

        if not len(introspection.nodes):
            self.root.allow_expand = False
            return

        self.root.expand()

    @textual.work()
    async def on_tree_node_expanded(
        self,
        event: textual.widgets.Tree.NodeExpanded,
    ):
        if event.node.children:
            if len(event.node.children) != 1:
                return
            event.node.children[0].expand()
            return

        introspection = event.node.data
        assert isinstance(introspection, dbus_fast.introspection.Node)
        list.sort(introspection.nodes, key=lambda node: node.name)

        child_node = None

        for child in introspection.nodes:
            assert isinstance(child, dbus_fast.introspection.Node)
            assert child.name is not None
            path = utils.get_textual_tree_node_path(event.node) + child.name

            child_introspection = None

            try:
                child_introspection = await self.bus.introspect(
                    self.service,
                    path,
                    validate_property_names=False,
                )
            except Exception as e:
                self.log.info(
                    "introspect",
                    path,
                    "of",
                    self.service,
                    "failed, maybe object has been removed:",
                    e,
                )

            if child_introspection == None:
                continue

            self.log.debug(
                "Introspect D-Bus service",
                self.service,
                "at object path",
                path,
                "result:",
                child_introspection.tostring(),
            )

            child_node = event.node.add(
                child.name,
                child_introspection,
                allow_expand=len(child_introspection.nodes) > 0,
            )

        if len(introspection.nodes) != 1:
            return

        if child_node is None:
            return

        child_node.expand()


class UpdateServices(textual.message.Message):
    pass


class UpdateObjectsTree(textual.message.Message):
    pass


class MemberSelected(textual.message.Message):
    def __init__(
        self,
        interface_name: str,
        member_name: str,
    ):
        self.interface_name = interface_name
        self.member_name = member_name
        super().__init__()


class GeneratedCommandScreen(textual.screen.Screen):
    DEFAULT_CSS = """
    GeneratedCommandScreen  {
        align: center middle;
        background: $surface 50%;
    }
    GeneratedCommandScreen > VerticalScroll {
        border: round $border;
        border-title-align: center;
        border-title-style: bold;
        padding: 0 1 0 1;
        width: 80%;
        height: 80%;
    }
    GeneratedCommandScreen > VerticalScroll > Center {
        height: auto;
        margin-top: 1
    }
    """
    BINDINGS = [
        textual.binding.Binding("escape,q", "app.pop_screen", "Close"),
    ]

    def __init__(
        self,
        command: str,
    ):
        self.command = command
        super().__init__()

    def compose(self) -> textual.app.ComposeResult:
        with textual.containers.VerticalScroll():
            with textual.containers.Center():
                yield textual.widgets.Label(
                    rich.text.Text("Generated command", style="bold")
                )
            yield textual.widgets.TextArea(
                read_only=True,
                text=self.command,
            )


class MethodDetails(textual.containers.Container):
    DEFAULT_CSS = """
    MethodDetails {
        height: auto;
    }
    MethodDetails > Label {
        padding-bottom: 1;
    }
    MethodDetails > HorizontalScroll {
        height: auto;
    }
    MethodDetails > HorizontalScroll > Label {
        width: 1fr;
        height: 100%;
        content-align: center middle;
    }
    MethodDetails > HorizontalScroll > TextArea {
        width: 4fr;
        height: auto;
    }
    MethodDetails > Collapsible > Contents {
        height: auto;
    }
    MethodDetails > Collapsible > Contents > HorizontalScroll {
        height: auto;
    }
    MethodDetails > Collapsible > Contents > HorizontalScroll > Label {
        width: auto;
        margin-right: 2;
        height: 100%;
        content-align: center middle;
    }
    """

    button_callback: dict[str, typing.Callable] = {}

    def __init__(
        self,
        service: str,
        path: str,
        interface: str,
        introspection: dbus_fast.introspection.Method,
        bus_type: typing.Optional[dbus_fast.constants.BusType] = None,
        bus_address: typing.Optional[str] = None,
    ):
        self.bus_type = bus_type
        self.bus_address = bus_address

        assert not (bus_type and bus_address)

        self.service = service
        self.path = path
        self.interface = interface
        self.introspection = introspection
        self.button_callback = {}
        super().__init__()

    def compose(self) -> textual.app.ComposeResult:
        if self.introspection.annotations:

            yield textual.widgets.Label(
                rich.text.Text("Annotation(s)", style="bold")
            )
            for key, value in self.introspection.annotations.items():
                with textual.widgets.Collapsible(
                    title=key,
                ):
                    yield textual.widgets.Label(value)

            yield textual.widgets.Rule()

        if self.introspection.in_args:

            yield textual.widgets.Label(
                rich.text.Text("Input(s)", style="bold")
            )

            for index, arg in enumerate(self.introspection.in_args):
                with textual.containers.HorizontalScroll():
                    yield textual.widgets.Label(
                        arg.name or "arg_" + str(index),
                    )
                    yield textual.widgets.Label(str(arg.signature))
                    yield textual.widgets.TextArea(
                        tab_behavior="indent",
                        soft_wrap=False,
                        id="arg-" + str(index),
                    )
                if arg.annotations:
                    with textual.widgets.Collapsible(
                        title="Annotation(s) of "
                        + (arg.name or "arg_" + str(index)),
                    ):
                        table = textual.widgets.DataTable(show_header=False)
                        yield table
                        table.add_column("Key")
                        table.add_column("Value")
                        for key, value in arg.annotations.items():
                            table.add_row(key, value)

            yield textual.widgets.Rule()

        yield textual.widgets.Label(rich.text.Text("Operations", style="bold"))

        with textual.containers.HorizontalScroll():
            yield textual.widgets.Button("Execute")
            yield textual.widgets.Button("Monitor")

        yield textual.widgets.Rule()

        if self.introspection.out_args:

            yield textual.widgets.Label(
                rich.text.Text("Output(s)", style="bold")
            )

            for index, arg in enumerate(self.introspection.out_args):
                with textual.containers.HorizontalScroll():
                    yield textual.widgets.Label(
                        arg.name or "arg_" + str(index),
                    )
                    yield textual.widgets.Label(str(arg.signature))
                    yield textual.widgets.TextArea(
                        soft_wrap=False,
                        read_only=True,
                    )

            yield textual.widgets.Rule()

        yield textual.widgets.Label(
            rich.text.Text("Utilities", style="bold"),
        )

        with textual.widgets.Collapsible(
            title="Generate method call command",
            collapsed=True,
        ):
            command_type = utils.CommandType.METHOD_CALL
            with textual.containers.HorizontalScroll():
                for tool in [
                    utils.ToolType.DBUS_SEND,
                    utils.ToolType.GDBUS,
                    utils.ToolType.QDBUS,
                    utils.ToolType.BUSCTL,
                ]:
                    id = "id-" + uuid.uuid4().hex
                    yield textual.widgets.Button(tool.value, id=id)
                    self.button_callback[id] = (
                        lambda tool=tool, command_type=command_type: self.push_generate_command_screen(
                            tool, command_type
                        )
                    )

        with textual.widgets.Collapsible(
            title="Generate method-call monitor command",
            collapsed=True,
        ):
            command_type = utils.CommandType.MONITOR_METHOD_CALL
            with textual.containers.HorizontalScroll():
                for tool in [
                    utils.ToolType.DBUS_MONITOR,
                    utils.ToolType.BUSCTL,
                    utils.ToolType.GDBUS,
                    utils.ToolType.QDBUS,
                ]:
                    id = "id-" + uuid.uuid4().hex
                    yield textual.widgets.Button(tool.value, id=id)
                    self.button_callback[id] = (
                        lambda tool=tool, command_type=command_type: self.push_generate_command_screen(
                            tool, command_type
                        )
                    )

        with textual.widgets.Collapsible(
            title="Generate method-return monitor command",
            collapsed=True,
        ):
            command_type = utils.CommandType.MONITOR_METHOD_RETURN
            with textual.containers.HorizontalScroll():
                for tool in [
                    utils.ToolType.DBUS_MONITOR,
                    utils.ToolType.BUSCTL,
                    utils.ToolType.GDBUS,
                    utils.ToolType.QDBUS,
                ]:
                    id = "id-" + uuid.uuid4().hex
                    yield textual.widgets.Button(tool.value, id=id)
                    self.button_callback[id] = (
                        lambda tool=tool, command_type=command_type: self.push_generate_command_screen(
                            tool, command_type
                        )
                    )

    def collect_arguments(self) -> list[dbus_fast.Variant]:
        ret: list[dbus_fast.Variant] = []
        for index, arg in enumerate(self.introspection.in_args):
            widget = self.query_one("#arg-" + str(index))
            assert isinstance(widget, textual.widgets.TextArea)
            ret.append(utils.parse_dbus_argument(arg.signature, widget.text))
        return ret

    def push_generate_command_screen(
        self,
        tool: utils.ToolType,
        type: utils.CommandType,
    ):
        try:
            arguments = None
            if type == utils.CommandType.METHOD_CALL:
                arguments = self.collect_arguments()

            self.log.debug(arguments)

            command = utils.generate_command(
                self.bus_type,
                self.bus_address,
                self.service,
                self.path,
                self.interface,
                self.introspection.name,
                arguments,
                tool=tool,
                type=type,
            )
        except utils.DBusArgumentPraseError as e:
            self.app.push_screen(GeneratedCommandScreen("Error: " + str(e)))
            return
        except NotImplementedError as e:
            self.app.push_screen(GeneratedCommandScreen("Not implemented"))
            return
        except Exception as e:
            self.app.push_screen(
                GeneratedCommandScreen("Unknown error: " + repr(e))
            )
            return

        self.app.push_screen(
            GeneratedCommandScreen(
                " ".join([shlex.quote(arg) for arg in command])
            )
        )

    def on_button_pressed(self, event: textual.widgets.Button.Pressed):
        if event.button.id not in self.button_callback:
            self.log.warning("Button", event.button.id, "has no callback")
            return

        self.button_callback[event.button.id]()
        return


class SignalDetails(textual.containers.Container):

    DEFAULT_CSS = """
    SignalDetails {
        height: auto;
    }
    SignalDetails > Label {
        padding-bottom: 1;
    }
    SignalDetails > HorizontalScroll {
        height: auto;
    }
    SignalDetails > HorizontalScroll > Label {
        width: 1fr;
        height: 100%;
        content-align: center middle;
    }
    SignalDetails > Collapsible > Contents {
        height: auto;
    }
    SignalDetails > Collapsible > Contents > HorizontalScroll {
        height: auto;
    }
    SignalDetails > Collapsible > Contents > HorizontalScroll > Label {
        width: auto;
        margin-right: 2;
        height: 100%;
        content-align: center middle;
    }
    """

    button_callback: dict[str, typing.Callable] = {}

    def __init__(
        self,
        service: str,
        path: str,
        interface: str,
        introspection: dbus_fast.introspection.Signal,
        bus_type: typing.Optional[dbus_fast.constants.BusType] = None,
        bus_address: typing.Optional[str] = None,
    ):
        self.bus_type = bus_type
        self.bus_address = bus_address
        self.service = service
        self.path = path
        self.interface = interface
        self.introspection = introspection
        self.button_callback = {}
        super().__init__()

    def compose(self) -> textual.app.ComposeResult:
        if self.introspection.annotations:

            yield textual.widgets.Label(
                rich.text.Text("Annotation(s)", style="bold")
            )
            for key, value in self.introspection.annotations.items():
                with textual.widgets.Collapsible(
                    title=key,
                ):
                    yield textual.widgets.Label(value)

            yield textual.widgets.Rule()

        if self.introspection.args:

            table = textual.widgets.DataTable(cursor_type="row")
            yield table
            table.add_columns("Name", "Signature")

            for index, arg in enumerate(self.introspection.args):
                table.add_row(
                    arg.name or "arg_" + str(index), str(arg.signature)
                )

            yield textual.widgets.Rule()

        yield textual.widgets.Label(rich.text.Text("Operations", style="bold"))

        with textual.containers.HorizontalScroll():
            yield textual.widgets.Button("Listen")

        yield textual.widgets.Rule()

        yield textual.widgets.Label(
            rich.text.Text("Utilities", style="bold"),
        )

        with textual.widgets.Collapsible(
            title="Generate monitor command",
            collapsed=True,
        ):
            command_type = utils.CommandType.MONITOR_SIGNAL
            with textual.containers.HorizontalScroll():
                for tool in [
                    utils.ToolType.DBUS_MONITOR,
                    utils.ToolType.BUSCTL,
                    utils.ToolType.GDBUS,
                    utils.ToolType.QDBUS,
                ]:
                    id = "id-" + uuid.uuid4().hex
                    yield textual.widgets.Button(tool.value, id=id)
                    self.button_callback[id] = (
                        lambda tool=tool, command_type=command_type: self.push_generate_command_screen(
                            tool, command_type
                        )
                    )

    def push_generate_command_screen(
        self,
        tool: utils.ToolType,
        type: utils.CommandType,
    ):
        assert self.introspection.name

        try:
            command = utils.generate_command(
                self.bus_type,
                self.bus_address,
                self.service,
                self.path,
                self.interface,
                self.introspection.name,
                None,
                tool=tool,
                type=type,
            )
        except NotImplementedError:
            self.app.push_screen(GeneratedCommandScreen("Not implemented"))
            return

        self.app.push_screen(
            GeneratedCommandScreen(
                " ".join([shlex.quote(arg) for arg in command])
            )
        )

    def on_button_pressed(self, event: textual.widgets.Button.Pressed):
        if event.button.id not in self.button_callback:
            self.log.warning("Button", event.button.id, "has no callback")
            return
        self.button_callback[event.button.id]()
        return


class PropertyDetails(textual.containers.Container):
    DEFAULT_CSS = """
    PropertyDetails {
        height: auto;
    }
    PropertyDetails > HorizontalScroll {
        height: auto;
    }
    PropertyDetails > Label {
        padding-bottom: 1;
    }
    PropertyDetails > TextArea {
        height: auto;
    }
    PropertyDetails > Collapsible > Contents {
        height: auto;
    }
    PropertyDetails > Collapsible > Contents > HorizontalScroll {
        height: auto;
    }
    """

    def __init__(
        self,
        service: str,
        path: str,
        interface: str,
        introspection: dbus_fast.introspection.Property,
        bus_type: typing.Optional[dbus_fast.constants.BusType] = None,
        bus_address: typing.Optional[str] = None,
    ):
        self.service = service
        self.path = path
        self.interface = interface
        self.introspection = introspection
        self.bus_type = bus_type
        self.bus_address = bus_address
        super().__init__()

    def compose(self) -> textual.app.ComposeResult:
        if self.introspection.annotations:

            yield textual.widgets.Label(
                rich.text.Text("Annotation(s)", style="bold")
            )
            for key, value in self.introspection.annotations.items():
                with textual.widgets.Collapsible(
                    title=key,
                ):
                    yield textual.widgets.Label(value)

            yield textual.widgets.Rule()

        yield textual.widgets.Label(
            rich.text.Text("Value", style="bold"),
        )

        yield textual.widgets.TextArea()

        yield textual.widgets.Rule()

        yield textual.widgets.Label(
            rich.text.Text("Operations", style="bold"),
        )

        with textual.containers.HorizontalScroll():
            yield textual.widgets.Button("Get")
            yield textual.widgets.Button("Set")
            yield textual.widgets.Button("Monitor")

        yield textual.widgets.Rule()

        yield textual.widgets.Label(
            rich.text.Text("Utilities", style="bold"),
        )

        with textual.widgets.Collapsible(
            title="Generate command to get property",
            collapsed=True,
        ):
            with textual.containers.HorizontalScroll():
                yield textual.widgets.Button("dbus-send")
                yield textual.widgets.Button("gdbus")
                yield textual.widgets.Button("qdbus")
                yield textual.widgets.Button("busctl")

        with textual.widgets.Collapsible(
            title="Generate command to set property",
            collapsed=True,
        ):
            with textual.containers.HorizontalScroll():
                yield textual.widgets.Button("dbus-send")
                yield textual.widgets.Button("gdbus")
                yield textual.widgets.Button("qdbus")
                yield textual.widgets.Button("busctl")


class MemberDetailsPage(textual.containers.Container):
    DEFAULT_CSS = """
    MemberDetailsPage {
        border: round $border;
        border-title-align: center;
        border-title-style: bold;
        padding: 0 1 0 1;
        width: 90%;
        height: 90%;
    }
    MemberDetailsPage > Center {
        height: auto;
        margin-top: 1
    }
    """

    def __init__(
        self,
        bus: MessageBus,
        service: str,
        path: str,
        interface: dbus_fast.introspection.Interface,
        member_name: str,
    ):
        super().__init__()

        self.bus = bus
        self.service = service
        self.path = path
        self.interface = interface
        self.member_name = member_name

    def compose(self) -> textual.app.ComposeResult:
        with textual.containers.Center():
            yield textual.widgets.Label(
                rich.text.Text(
                    self.interface.name + "." + self.member_name, style="bold"
                ),
            )

        yield textual.widgets.Rule()

        with textual.containers.VerticalScroll():

            table = textual.widgets.DataTable(
                show_header=False,
                show_cursor=False,
            )
            yield table
            table.add_column("Key", key="key")
            table.add_column("Value", key="value")
            table.add_row("Service name", self.service)
            table.add_row("Object path", self.path)
            table.add_row("Interface", self.interface.name)
            table.add_row("Name", self.member_name)

            yield textual.widgets.Rule()

            for method in self.interface.methods:
                if method.name != self.member_name:
                    continue

                table.add_row("Type", "Method")

                yield MethodDetails(
                    self.service,
                    self.path,
                    self.interface.name,
                    method,
                    bus_type=self.bus.bus_type,
                    bus_address=self.bus.bus_address,
                )
                return

            for property in self.interface.properties:
                if property.name != self.member_name:
                    continue

                table.add_row("Type", "Property")
                table.add_row("Signature", property.signature)

                yield PropertyDetails(
                    self.service,
                    self.path,
                    self.interface.name,
                    property,
                    bus_type=self.bus.bus_type,
                    bus_address=self.bus.bus_address,
                )
                return

            for signal in self.interface.signals:
                if signal.name != self.member_name:
                    continue

                table.add_row("Type", "Signal")

                yield SignalDetails(
                    self.service,
                    self.path,
                    self.interface.name,
                    signal,
                    bus_type=self.bus.bus_type,
                    bus_address=self.bus.bus_address,
                )
                return

            assert False


class MemberScreen(textual.screen.Screen):
    DEFAULT_CSS = """
    MemberScreen {
        align: center middle;
        background: $surface 50%;
    }
    """
    BINDINGS = [
        textual.binding.Binding("escape,q", "app.pop_screen", "Close"),
    ]

    def __init__(
        self,
        bus: MessageBus,
        service: str,
        path: str,
        interface: dbus_fast.introspection.Interface,
        member_name: str,
    ):
        super().__init__()

        self.bus = bus
        self.service = service
        self.path = path
        self.interface = interface
        self.member_name = member_name

    def compose(self) -> textual.app.ComposeResult:
        yield textual.widgets.Footer()
        yield MemberDetailsPage(
            self.bus,
            self.service,
            self.path,
            self.interface,
            self.member_name,
        )


class BusPane(textual.containers.Container):
    services = textual.reactive.reactive[typing.Optional[list[str]]](None)
    objects_tree = textual.reactive.reactive[typing.Optional[ObjectsTree]](None)
    service = textual.reactive.reactive[typing.Optional[str]](None)

    pid = textual.reactive.reactive[typing.Optional[int]](None)
    executable = textual.reactive.reactive[typing.Optional[str]](None)
    command_line = textual.reactive.reactive[typing.Optional[list[str]]](None)
    uid = textual.reactive.reactive[typing.Optional[int]](None)
    user_name = textual.reactive.reactive[typing.Optional[str]](None)
    unique_name = textual.reactive.reactive[typing.Optional[str]](None)

    object_path = textual.reactive.reactive[typing.Optional[str]](None)
    interfaces = textual.reactive.reactive[
        typing.Optional[list[dbus_fast.introspection.Interface]]
    ](None)

    def __init__(self, bus: MessageBus):
        super().__init__()
        self.bus = bus

    def on_mount(self):
        self.loading = True
        self.update_services()

    @textual.work()
    @textual.on(UpdateServices)
    async def update_services(self):
        self.set_reactive(
            BusPane.services,
            await utils.list_dbus_services(self.bus),
        )
        self.mutate_reactive(BusPane.services)

        self.loading = False

    def compose(self) -> textual.app.ComposeResult:
        with textual.containers.Horizontal():
            yield ServiceNamesTable().data_bind(services=BusPane.services)
            yield Objects().data_bind(objects_tree=BusPane.objects_tree)
            yield ServiceDetails().data_bind(
                service=BusPane.service,
                pid=BusPane.pid,
                executable=BusPane.executable,
                command_line=BusPane.command_line,
                uid=BusPane.uid,
                user_name=BusPane.user_name,
                unique_name=BusPane.unique_name,
                object_path=BusPane.object_path,
                interfaces=BusPane.interfaces,
            )

    def on_data_table_cell_highlighted(
        self, event: textual.widgets.DataTable.CellHighlighted
    ):
        if event.data_table != (
            self.query_one(ServiceNamesTable)
            .query_one(textual.containers.VerticalScroll)
            .query_one(textual.widgets.DataTable)
        ):
            return

        if self.services == None:
            return

        self.service = self.services[event.coordinate.row]

    @textual.work()
    async def watch_service(self):
        if self.service == None:
            return

        self.pid = await utils.get_dbus_service_pid(self.bus, self.service)

        try:
            self.executable = await utils.get_executable(self.pid)
        except Exception as e:
            self.log.error(e)

        try:
            self.command_line = await utils.get_command_line(self.pid)
        except Exception as e:
            self.log.error(e)

        self.uid = await utils.get_dbus_service_uid(self.bus, self.service)
        self.user_name = await utils.get_user_name(self.uid)
        self.unique_name = await utils.get_dbus_service_unique_name(
            self.bus, self.service
        )

        self.update_objects_tree()

    @textual.work()
    @textual.on(UpdateObjectsTree)
    async def update_objects_tree(self):
        assert self.service

        introspection = None

        try:
            introspection = await self.bus.introspect(
                self.service, "/", validate_property_names=False
            )
        except Exception as e:
            self.log.error(e)

        tree = None

        if introspection != None:
            tree = ObjectsTree(self.bus, self.service, introspection)

        self.object_path = None

        self.set_reactive(BusPane.objects_tree, tree)
        self.mutate_reactive(BusPane.objects_tree)

    @textual.work()
    async def on_tree_node_selected(
        self,
        event: textual.widgets.Tree.NodeSelected,
    ):
        object_path = utils.get_textual_tree_node_path(event.node)
        if not len(object_path) == 1:
            object_path = object_path[:-1]

        self.object_path = object_path

    @textual.work()
    async def watch_object_path(self):
        if self.object_path == None:
            self.set_reactive(BusPane.interfaces, None)
            self.mutate_reactive(BusPane.interfaces)
            return

        assert self.service

        introspection = None
        try:
            introspection = await self.bus.introspect(
                self.service, self.object_path, validate_property_names=False
            )
        except Exception as e:
            self.log.error(e)

        if introspection == None:
            self.set_reactive(BusPane.interfaces, None)
            self.mutate_reactive(BusPane.interfaces)
            return

        def dbus_interface_sort_key(
            interface: dbus_fast.introspection.Interface,
        ) -> str:
            return interface.name

        list.sort(introspection.interfaces, key=dbus_interface_sort_key)

        self.set_reactive(BusPane.interfaces, introspection.interfaces)
        self.mutate_reactive(BusPane.interfaces)

    def on_member_selected(self, event: MemberSelected):
        assert self.service
        assert self.object_path
        assert self.objects_tree
        assert self.interfaces

        selected_interface = None

        for interface in self.interfaces:
            if interface.name != event.interface_name:
                continue
            selected_interface = interface

        assert selected_interface != None

        self.app.push_screen(
            MemberScreen(
                self.bus,
                self.service,
                self.object_path,
                selected_interface,
                event.member_name,
            )
        )


class ServiceNamesTable(textual.containers.Container):
    BINDINGS = [
        textual.binding.Binding("r", "reload_service", "Reload services"),
    ]

    services = textual.reactive.reactive[typing.Optional[list[str]]](None)

    def on_mount(self):
        self.loading = True
        self.query_one(textual.widgets.DataTable).add_columns("Services")

    @textual.work()
    async def watch_services(self):
        if self.services == None:
            return

        self.query_one(textual.widgets.DataTable).clear()
        self.query_one(textual.widgets.DataTable).add_rows(
            [[service] for service in self.services]
        )

        self.loading = False

    def compose(self) -> textual.app.ComposeResult:
        yield textual.widgets.Label(rich.text.Text("Services", style="bold"))
        with textual.containers.VerticalScroll():
            yield textual.widgets.DataTable(show_header=False)

    def action_reload_services(self):
        self.post_message(UpdateServices())


class Objects(textual.containers.Container):
    BINDINGS = [
        textual.binding.Binding("r", "reload_objects", "Reload objects"),
    ]

    objects_tree = textual.reactive.reactive[typing.Optional[ObjectsTree]](None)

    @textual.work()
    async def watch_objects_tree(self):
        widget = textual.widgets.LoadingIndicator()

        if self.objects_tree != None:
            widget = self.objects_tree

        container = self.query_one(textual.containers.VerticalScroll)

        await container.remove_children()
        await container.mount(widget)

        self.loading = False

    def compose(self) -> textual.app.ComposeResult:
        yield textual.widgets.Label(rich.text.Text("Objects", style="bold"))
        yield textual.containers.VerticalScroll()

    def action_reload_objects(self):
        self.post_message(UpdateObjectsTree())


class Interfaces(textual.containers.Container):
    DEFAULT_CSS = """
    Interfaces > ScrollableContainer Collapsible {
        border: none;
        padding-bottom: 0;
    }
    Interfaces > ScrollableContainer Collapsible > Contents {
        padding: 0 0 0 3;
    }
    """

    interfaces = textual.reactive.reactive[
        typing.Optional[list[dbus_fast.introspection.Interface]]
    ](None, recompose=True)

    def compose(self) -> textual.app.ComposeResult:
        yield textual.widgets.Label(rich.text.Text("Interfaces", style="bold"))

        if self.interfaces == None:
            yield textual.widgets.Label("No object selected")
            return

        if len(self.interfaces) == 0:
            yield textual.widgets.Label("No interfaces avaiable in this object")
            return

        with textual.containers.ScrollableContainer():
            for interface in self.interfaces:
                collapsed = False
                if interface.name in [
                    "org.freedesktop.DBus.Introspectable",
                    "org.freedesktop.DBus.Peer",
                    "org.freedesktop.DBus.Properties",
                ]:
                    collapsed = True

                with textual.widgets.Collapsible(
                    title=interface.name,
                    collapsed=collapsed,
                ):
                    if interface.annotations:
                        with textual.widgets.Collapsible(
                            title="Annotations",
                            collapsed=False,
                        ):
                            table = textual.widgets.DataTable(
                                show_header=False,
                                cursor_type="row",
                            )
                            yield table
                            table.add_column("Name", key="name")
                            table.add_column("Value", key="value")
                            for key, value in interface.annotations.items():
                                table.add_row(
                                    key,
                                    value,
                                )

                    if interface.properties:
                        with textual.widgets.Collapsible(
                            title="Properties",
                            collapsed=False,
                        ):
                            table = textual.widgets.DataTable(
                                show_header=False,
                                cursor_type="row",
                            )
                            yield table
                            table.add_column("Name", key="name")
                            table.add_column("Signature", key="signature")

                            list.sort(
                                interface.properties,
                                key=lambda property: property.name,
                            )

                            for property in interface.properties:
                                table.add_row(
                                    property.name,
                                    property.signature,
                                )

                    if interface.methods:
                        with textual.widgets.Collapsible(
                            title="Methods",
                            collapsed=False,
                        ):
                            table = textual.widgets.DataTable(
                                cursor_type="row",
                            )
                            yield table
                            table.add_column("Name", key="name")
                            table.add_column("in", key="in")
                            table.add_column("out", key="out")

                            list.sort(
                                interface.methods,
                                key=lambda method: method.name,
                            )

                            for method in interface.methods:
                                table.add_row(
                                    method.name,
                                    method.in_signature,
                                    method.out_signature,
                                )

                    if interface.signals:
                        with textual.widgets.Collapsible(
                            title="Signals",
                            collapsed=False,
                        ):
                            table = textual.widgets.DataTable(
                                show_header=False,
                                cursor_type="row",
                            )
                            yield table
                            table.add_column("Name", key="name")
                            table.add_column("Signature", key="signature")

                            list.sort(
                                interface.signals,
                                key=lambda signal: signal.name,
                            )

                            for signal in interface.signals:
                                table.add_row(
                                    signal.name,
                                    signal.signature,
                                )

    def on_data_table_row_selected(
        self, event: textual.widgets.DataTable.RowSelected
    ):
        assert isinstance(
            event.data_table.parent, textual.widgets.Collapsible.Contents
        )
        assert isinstance(
            event.data_table.parent.parent, textual.widgets.Collapsible
        )

        member_type = event.data_table.parent.parent.title.lower()

        if member_type == "annotations":
            return

        column = event.data_table.get_column_index("name")
        row = event.data_table.get_row(event.row_key)
        member_name = row[column]

        assert isinstance(
            event.data_table.parent.parent.parent,
            textual.widgets.Collapsible.Contents,
        )
        assert isinstance(
            event.data_table.parent.parent.parent.parent,
            textual.widgets.Collapsible,
        )

        interface_name = event.data_table.parent.parent.parent.parent.title

        self.post_message(MemberSelected(interface_name, member_name))


class ServiceDetails(textual.containers.Container):
    bus = textual.reactive.reactive[
        typing.Optional[dbus_fast.aio.message_bus.MessageBus]
    ](None)
    service = textual.reactive.reactive[typing.Optional[str]](None)
    pid = textual.reactive.reactive[typing.Optional[int]](None)
    executable = textual.reactive.reactive[typing.Optional[str]](None)
    command_line = textual.reactive.reactive[typing.Optional[list[str]]](None)
    uid = textual.reactive.reactive[typing.Optional[int]](None)
    user_name = textual.reactive.reactive[typing.Optional[str]](None)
    unique_name = textual.reactive.reactive[typing.Optional[str]](None)
    object_path = textual.reactive.reactive[typing.Optional[str]](None)
    interfaces = textual.reactive.reactive[
        typing.Optional[list[dbus_fast.introspection.Interface]]
    ](None)

    def compose(self) -> textual.app.ComposeResult:
        with textual.containers.VerticalScroll():
            yield textual.widgets.Label(rich.text.Text("Details", style="bold"))
            table = textual.widgets.DataTable(
                show_header=False,
                cursor_type="row",
            )
            yield table

            table.add_column("Key", key="key")
            table.add_column("Value", key="value")

            table.add_row("Well Known Name", "...", key="name")
            table.add_row("Unique Name", "...", key="unique_name")
            table.add_row("PID", "...", key="pid")
            table.add_row("Executable", "...", key="executable")
            table.add_row("Command Line", "...", key="command_line")
            table.add_row("UID", "...", key="uid")
            table.add_row("User Name", "...", key="user")
            table.add_row("Object Path", "...", key="object_path")

            yield Interfaces().data_bind(interfaces=ServiceDetails.interfaces)

    def watch_service(self):
        if self.service == None:
            return

        self.query_one(textual.containers.VerticalScroll).query_one(
            textual.widgets.DataTable
        ).update_cell("name", "value", self.service, update_width=True)

    def watch_pid(self):
        if self.pid == None:
            return

        self.query_one(textual.containers.VerticalScroll).query_one(
            textual.widgets.DataTable
        ).update_cell("pid", "value", self.pid, update_width=True)

    def watch_uid(self):
        if self.uid == None:
            return

        self.query_one(textual.containers.VerticalScroll).query_one(
            textual.widgets.DataTable
        ).update_cell("uid", "value", self.uid, update_width=True)

    def watch_unique_name(self):
        if self.unique_name == None:
            return
        self.query_one(textual.containers.VerticalScroll).query_one(
            textual.widgets.DataTable
        ).update_cell(
            "unique_name",
            "value",
            self.unique_name,
            update_width=True,
        )

    def watch_user_name(self):
        if self.user_name == None:
            return

        self.query_one(textual.containers.VerticalScroll).query_one(
            textual.widgets.DataTable
        ).update_cell(
            "user",
            "value",
            self.user_name,
            update_width=True,
        )

    def watch_executable(self):
        if self.executable == None:
            return

        self.query_one(textual.containers.VerticalScroll).query_one(
            textual.widgets.DataTable
        ).update_cell(
            "executable",
            "value",
            self.executable,
            update_width=True,
        )

    def watch_command_line(self):
        if self.command_line == None:
            return

        self.query_one(textual.containers.VerticalScroll).query_one(
            textual.widgets.DataTable
        ).update_cell(
            "command_line",
            "value",
            " ".join([shlex.quote(arg) for arg in self.command_line]),
            update_width=True,
        )

    def watch_object_path(self):
        self.query_one(textual.containers.VerticalScroll).query_one(
            textual.widgets.DataTable
        ).update_cell(
            "object_path",
            "value",
            self.object_path or "...",
            update_width=True,
        )

from . import utils
import dbus_next
import os
import rich.text
import shlex
import textual.app
import textual.binding
import textual.containers
import textual.css.query
import textual.message
import textual.reactive
import textual.widgets
import typing


class DBuSPY(textual.app.App):
    """A Textual app like d-feet."""

    BINDINGS = [
        textual.binding.Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> textual.app.ComposeResult:
        yield textual.widgets.Header()
        yield textual.widgets.Footer()
        yield MainPage()


class MainPage(textual.containers.Container):
    message_buses = textual.reactive.reactive[
        typing.Optional[dict[str, dbus_next.aio.message_bus.MessageBus]]
    ](None)

    def on_mount(self):
        self.loading = True
        self.add_buses()

    @textual.work()
    async def add_buses(self):
        message_buses = {}

        # NOTE: root user doesn't have session bus
        if os.getuid() != 0:
            message_buses["session"] = (
                await dbus_next.aio.message_bus.MessageBus(
                    bus_type=dbus_next.constants.BusType.SESSION
                ).connect()
            )

        message_buses["system"] = await dbus_next.aio.message_bus.MessageBus(
            bus_type=dbus_next.constants.BusType.SYSTEM
        ).connect()

        self.set_reactive(MainPage.message_buses, message_buses)
        self.mutate_reactive(MainPage.message_buses)

        self.loading = False

    @textual.work(exclusive=True, group="watch_message_buses")
    async def watch_message_buses(self):
        if self.message_buses == None:
            return

        self.log.info("Update message buses to", self.message_buses)

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
        bus: dbus_next.aio.message_bus.MessageBus,
        service: str,
        introspection: dbus_next.introspection.Node,
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
        assert isinstance(introspection, dbus_next.introspection.Node)

        child_node = None

        for child in introspection.nodes:
            assert isinstance(child, dbus_next.introspection.Node)
            path = utils.get_textual_tree_node_path(event.node) + child.name

            child_introspection = await self.bus.introspect(
                self.service,
                path,
            )

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

        assert child_node is not None

        child_node.expand()


class BusPane(textual.containers.Container):
    BINDINGS = [
        textual.binding.Binding("r", "reload", "Reload"),
    ]

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
        typing.Optional[list[dbus_next.introspection.Interface]]
    ](None)

    def __init__(self, bus: dbus_next.aio.message_bus.MessageBus):
        super().__init__()
        self.bus = bus

    def on_mount(self):
        self.loading = True
        self.update_services()

    def action_reload(self):
        self.update_services()

    @textual.work()
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

        self.initialize_objects_tree()

    @textual.work()
    async def initialize_objects_tree(self):
        assert self.service

        introspection = None
        try:
            introspection = await self.bus.introspect(self.service, "/")
        except Exception as e:
            self.log.error(e)
        if introspection == None:
            return

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
                self.service, self.object_path
            )
        except Exception as e:
            self.log.error(e)

        if introspection == None:
            self.set_reactive(BusPane.interfaces, None)
            self.mutate_reactive(BusPane.interfaces)
            return

        def dbus_interface_sort_key(
            interface: dbus_next.introspection.Interface,
        ) -> str:
            return interface.name

        list.sort(introspection.interfaces, key=dbus_interface_sort_key)

        self.set_reactive(BusPane.interfaces, introspection.interfaces)
        self.mutate_reactive(BusPane.interfaces)


class ServiceNamesTable(textual.containers.Container):
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


class Objects(textual.containers.Container):
    objects_tree = textual.reactive.reactive[typing.Optional[ObjectsTree]](None)

    @textual.work()
    async def watch_objects_tree(self):
        if self.objects_tree == None:
            return

        self.log.info("Initialize objects tree")

        container = self.query_one(textual.containers.VerticalScroll)

        await container.remove_children()
        await container.mount(self.objects_tree)

        self.loading = False

    def compose(self) -> textual.app.ComposeResult:
        yield textual.widgets.Label(rich.text.Text("Objects", style="bold"))
        yield textual.containers.VerticalScroll(
            textual.widgets.LoadingIndicator()
        )


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
        typing.Optional[list[dbus_next.introspection.Interface]]
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
                            table.add_columns("Name", "Signature")
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
                            table.add_columns("Name", "in", "out")
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
                            table.add_columns("Name", "Signature")
                            for signal in interface.signals:
                                table.add_row(
                                    signal.name,
                                    signal.signature,
                                )


class ServiceDetails(textual.containers.Container):
    bus = textual.reactive.reactive[
        typing.Optional[dbus_next.aio.message_bus.MessageBus]
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
        typing.Optional[list[dbus_next.introspection.Interface]]
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

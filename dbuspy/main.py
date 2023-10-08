import logging
from textual.binding import Binding
from textual.logging import TextualHandler
from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer, Vertical, Horizontal
from textual.widgets import (
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


class BusTabs(Tabs):
    def compose(self) -> ComposeResult:
        return super().compose()

    def watch_active(self, previously_active: str, active: str) -> None:
        logging.debug(active)
        return super().watch_active(previously_active, active)


class NamesPanel(ScrollableContainer):
    def compose(self) -> ComposeResult:
        yield ListView();


class TreePanel(ScrollableContainer):
    def compose(self) -> ComposeResult:
        yield Tree("/")


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
        yield Horizontal(Button("call", id="call"))


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
        yield BusTabs(id="buses")
        yield Horizontal(
            NamesPanel(id="names"),
            Vertical(
                TreePanel(id="tree"),
                MethodPanel(id="method"),
            ),
        )

    def on_mount(self):
        self.add_bus(Tab("session", id="session_bus"))
        self.add_bus(Tab("system", id="system_bus"))

    def add_bus(self, name: Tab):
        buses = self.get_child_by_id("buses", expect_type=BusTabs)
        buses.add_tab(name)


def main():
    app = DBuSPY()
    app.run()

from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer, Vertical, Horizontal
from textual.widgets import (
    Markdown,
    Select,
    Tabs,
    Input,
    Button,
    Footer,
    Header,
    Tree,
    ListView,
    Label,
)


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

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Footer()
        yield Tabs("session bus", "system bus")
        yield Horizontal(
            NamesPanel(id="names"),
            Vertical(
                TreePanel(id="tree"),
                MethodPanel(id="method"),
            ),
        )


def main():
    app = DBuSPY()
    app.run()

from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer, Vertical, Horizontal
from textual.widgets import (
    Select,
    Tabs,
    Input,
    Button,
    Footer,
    Header,
    Tree,
    ListView,
    ListItem,
    Label,
)


class DBuspyApp(App):
    """A Textual app to manage stopwatches."""

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Footer()
        yield Tabs("session bus", "system bus")
        yield Horizontal(
            ListView(
                ListItem(Label("aaa")),
                ListItem(Label("bbb")),
            ),
            Vertical(
                ScrollableContainer(Tree("test")),
                Horizontal(
                    Vertical(
                        Vertical(
                            Horizontal(
                                Label("well known name:"),
                                Label("XXX"),
                            ),
                            Horizontal(
                                Label("unique name:"),
                                Label("YYY"),
                            ),
                            Horizontal(
                                Label("object path:"),
                                Label("ZZZ"),
                            ),
                            Horizontal(
                                Label("method:"),
                                Label("FFF"),
                            ),
                        ),
                        Horizontal(
                            Input(placeholder="Arguments"),
                        ),
                        Vertical(
                            Horizontal(
                                Label("times:"),
                                Input("1"),
                                Button("call"),
                            ),
                            Horizontal(
                                Label("result:"),
                                Label("XXX"),
                                Button("copy"),
                            ),
                        ),
                        Horizontal(
                            Label("copy request as"),
                            Select(
                                [
                                    ("dbus-send", "dbus-send"),
                                    ("gdbus", "gdbus"),
                                    ("qdbus", "qdbus"),
                                    ("busctl", "busctl"),
                                ],
                                value="dbus-send",
                                allow_blank=False,
                            ),
                            Button("copy"),
                        ),
                    ),
                ),
            ),
        )


def main():
    app = DBuspyApp()
    app.run()

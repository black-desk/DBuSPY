from . import utils


def test_sort_dbus_services():
    class TestCase:
        def __init__(self, input: list[str], expected: list[str]):
            self.input = input
            self.expected = expected

    test_cases = [
        TestCase([], []),
        TestCase([
            ":1",
            "org.freedesktop.systemd1",
        ], [
            "org.freedesktop.systemd1",
            ":1",
        ]),
        TestCase([
            ":1.1.1",
            ":1.1",
        ], [
            ":1.1",
            ":1.1.1",
        ]),
        TestCase([
            ":1.0",
            ":1.18",
            "org.freedesktop.systemd1",
            ":1.235",
            "org.freedesktop.DBus",
            ":1.4",
            "org.freedesktop.hostname1",
            ":1.5",
            ":1.6",
            "org.freedesktop.locale1",
            ":1.3",
            ":1.8",
            "org.freedesktop.network1",
            ":1.9",
            "org.freedesktop.PackageKit",
            "org.freedesktop.PolicyKit1",
            ":1.1",
            "org.freedesktop.RealtimeKit1",
            "org.freedesktop.login1",
            ":1.7",
            "org.freedesktop.timedate1",
            "org.freedesktop.timesync",
        ],[
            "org.freedesktop.DBus",
            "org.freedesktop.PackageKit",
            "org.freedesktop.PolicyKit1",
            "org.freedesktop.RealtimeKit1",
            "org.freedesktop.hostname1",
            "org.freedesktop.locale1",
            "org.freedesktop.login1",
            "org.freedesktop.network1",
            "org.freedesktop.systemd1",
            "org.freedesktop.timedate1",
            "org.freedesktop.timesync",
            ":1.0",
            ":1.1",
            ":1.3",
            ":1.4",
            ":1.5",
            ":1.6",
            ":1.7",
            ":1.8",
            ":1.9",
            ":1.18",
            ":1.235",
        ])
    ]

    for case in test_cases:
        utils.sort_dbus_services(case.input)
        assert len(case.input) == len(case.expected)
        for i in range(len(case.input)):
            assert case.input[i] == case.expected[i]

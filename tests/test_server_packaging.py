from importlib.util import find_spec


def test_server_package_is_importable():
    assert find_spec("shipgate.server") is not None

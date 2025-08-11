import pgmig


def test_hello_world() -> None:
    print("Hello World!", pgmig.__all__())  # noqa: T201

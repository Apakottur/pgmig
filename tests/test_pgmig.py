from pgmig.main import mock_func


def test_mock_func() -> None:
    assert mock_func(1) == 2

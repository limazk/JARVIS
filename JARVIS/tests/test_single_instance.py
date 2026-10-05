import pytest

from core.single_instance import AlreadyRunningError, SingleInstanceLock


def test_second_instance_fails_safely(tmp_path):
    first = SingleInstanceLock(tmp_path / "jarvis.lock")
    second = SingleInstanceLock(tmp_path / "jarvis.lock")
    first.acquire()
    try:
        with pytest.raises(AlreadyRunningError):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()

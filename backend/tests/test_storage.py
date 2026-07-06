import os
import time

from core.storage import cleanup_expired_results


def _touch(path, age_days: float):
    with open(path, "w", encoding="utf-8") as f:
        f.write("{}")
    old = time.time() - age_days * 86400
    os.utime(path, (old, old))


def test_removes_only_expired_managed_files(tmp_path):
    d = str(tmp_path)
    _touch(os.path.join(d, "old.json"), age_days=40)
    _touch(os.path.join(d, "old.ifc"), age_days=40)
    _touch(os.path.join(d, "fresh.json"), age_days=1)
    _touch(os.path.join(d, "old.txt"), age_days=40)  # unmanaged suffix

    removed = cleanup_expired_results(d, ttl_days=30)

    assert removed == 2
    assert sorted(os.listdir(d)) == ["fresh.json", "old.txt"]


def test_ttl_zero_disables_cleanup(tmp_path):
    d = str(tmp_path)
    _touch(os.path.join(d, "old.json"), age_days=400)
    assert cleanup_expired_results(d, ttl_days=0) == 0
    assert os.listdir(d) == ["old.json"]


def test_missing_directory_is_noop():
    assert cleanup_expired_results("no/such/dir", ttl_days=30) == 0

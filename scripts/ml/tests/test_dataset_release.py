"""Publication testée sur un stockage en mémoire ; aucun appel AWS réel."""

from contextlib import redirect_stderr
from hashlib import md5
import importlib.util
from io import StringIO
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("dataset_release", ROOT / "infra/deploy/dataset_release.py")
release_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_tool)
REVISION = "a" * 40


class MemoryStorage:
    def __init__(self):
        self.objects = {}
        self.uploads = []
        self.reads = []
        self.fail_on = None

    def download(self, key, target):
        self.reads.append(key)
        if key not in self.objects:
            return False
        target.write_bytes(self.objects[key])
        return True

    def upload_if_absent(self, key, source):
        if key == self.fail_on:
            raise RuntimeError("transfert interrompu")
        self.uploads.append(key)
        self.objects.setdefault(key, source.read_bytes())


def fixture(root):
    folder = root / ".data/ml/splits"
    folder.mkdir(parents=True)
    files, entries = {}, []
    for name in release_tool.NAMES:
        path = folder / name
        path.write_bytes(("fixture-" + name).encode())
        info = release_tool.fingerprints(path)
        files[name] = {key: info[key] for key in ("sha256", "size")}
        entries.append({"md5": info["md5"], "relpath": name})
    raw = json.dumps(sorted(entries, key=lambda e: e["relpath"]), sort_keys=True).encode()
    version = md5(raw, usedforsecurity=False).hexdigest() + ".dir"
    cache = root / ".dvc/cache/files/md5" / version[:2] / version[2:]
    cache.parent.mkdir(parents=True)
    cache.write_bytes(raw)
    metadata = {"outs": [{
        "md5": version, "path": ".data/ml/splits", "hash": "md5",
        "nfiles": 3, "size": sum(info["size"] for info in files.values()),
    }]}
    release = {
        "schema_version": 1, "dataset_id": version, "bucket": "test-datalake",
        "dataset_uri": f"s3://test-datalake/{release_tool.PREFIX}/{version}",
        "git_revision": REVISION, "files": files,
    }
    return release, metadata, cache


class DatasetReleaseTests(unittest.TestCase):
    def test_prepare_verifies_the_dvc_tree_and_files_without_modifying_sources(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected, metadata, _ = fixture(root)
            before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (root / ".data/ml/splits").iterdir()}
            actual = release_tool.prepare_from_metadata(
                root, REVISION, metadata, "s3://test-datalake/ml/datasets/dvc",
            )
            self.assertEqual(actual, expected)
            self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before})

    def test_prepare_rejects_changed_data_or_corrupt_cache(self):
        for corrupt_cache in [False, True]:
            with self.subTest(corrupt_cache=corrupt_cache), TemporaryDirectory() as tmp:
                root = Path(tmp)
                _, metadata, cache = fixture(root)
                if corrupt_cache:
                    cache.write_bytes(b"corrupted")
                else:
                    (root / ".data/ml/splits/train.parquet").write_bytes(b"changed")
                with self.assertRaises(ValueError):
                    release_tool.prepare_from_metadata(
                        root, REVISION, metadata, "s3://test-datalake/ml/datasets/dvc",
                    )

    def test_publish_verifies_a_complete_roundtrip_and_writes_marker_last(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release, _, _ = fixture(root)
            store = MemoryStorage()
            release_tool.publish(root, release, store)
            release_tool.verify_remote(release, store)
            self.assertTrue(store.uploads[-1].endswith("/manifest.json"))
            self.assertEqual(len(store.uploads), 5)

    def test_retry_reuses_matching_objects_after_interrupted_upload(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release, _, _ = fixture(root)
            store = MemoryStorage()
            prefix = f"{release_tool.PREFIX}/{release['dataset_id']}"
            store.fail_on = prefix + "/validation.parquet"
            with self.assertRaisesRegex(RuntimeError, "interrompu"):
                release_tool.publish(root, release, store)
            self.assertNotIn(prefix + "/manifest.json", store.objects)
            store.fail_on = None
            release_tool.publish(root, release, store)
            release_tool.verify_remote(release, store)
            self.assertEqual(store.uploads.count(prefix + "/train.parquet"), 1)

    def test_new_git_commit_reuses_same_dataset_without_any_upload(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release, _, _ = fixture(root)
            store = MemoryStorage()
            release_tool.publish(root, release, store)
            before = list(store.uploads)
            release["git_revision"] = "b" * 40
            release_tool.publish(root, release, store)
            release_tool.verify_remote(release, store)
            self.assertEqual(store.uploads, before)

    def test_conflicting_remote_object_is_never_overwritten(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release, _, _ = fixture(root)
            store = MemoryStorage()
            key = f"{release_tool.PREFIX}/{release['dataset_id']}/train.parquet"
            store.objects[key] = b"another dataset"
            with self.assertRaisesRegex(ValueError, "aucun écrasement"):
                release_tool.publish(root, release, store)
            self.assertEqual(store.objects[key], b"another dataset")
            self.assertFalse(store.uploads)

    def test_wrong_local_input_fails_before_any_remote_access(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release, _, _ = fixture(root)
            (root / ".data/ml/splits/test.parquet").write_bytes(b"changed")
            store = MemoryStorage()
            with self.assertRaises(ValueError):
                release_tool.publish(root, release, store)
            self.assertFalse(store.reads)
            self.assertFalse(store.uploads)

    def test_verify_rejects_missing_marker_or_missing_or_corrupt_file(self):
        for failure in ["marker", "missing", "corrupt"]:
            with self.subTest(failure=failure), TemporaryDirectory() as tmp:
                root = Path(tmp)
                release, _, _ = fixture(root)
                store = MemoryStorage()
                release_tool.publish(root, release, store)
                prefix = f"{release_tool.PREFIX}/{release['dataset_id']}/"
                if failure == "marker":
                    del store.objects[prefix + "manifest.json"]
                elif failure == "missing":
                    del store.objects[prefix + "test.parquet"]
                else:
                    store.objects[prefix + "test.parquet"] = b"corrupted"
                with self.assertRaises(ValueError):
                    release_tool.verify_remote(release, store)

    def test_release_validation_checks_commit_exact_files_and_uri(self):
        with TemporaryDirectory() as tmp:
            release, _, _ = fixture(Path(tmp))
            for change in [
                {"git_revision": "b" * 40},
                {"dataset_uri": "s3://another-bucket/bronze"},
                {"files": {"train.parquet": release["files"]["train.parquet"]}},
                {"dataset_id": "../escape"},
            ]:
                with self.subTest(change=change), self.assertRaises(ValueError):
                    release_tool.validate_release({**release, **change}, REVISION)

    def test_access_denied_is_not_mistaken_for_a_missing_object(self):
        denied = subprocess.CompletedProcess([], 254, "", "(AccessDenied) Forbidden")
        missing = subprocess.CompletedProcess([], 254, "", "(NoSuchKey) missing")
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "download"
            with patch.object(release_tool.subprocess, "run", return_value=denied):
                with self.assertRaisesRegex(RuntimeError, "AccessDenied"):
                    release_tool.S3("test-bucket").download("key", target)
            with patch.object(release_tool.subprocess, "run", return_value=missing):
                self.assertFalse(release_tool.S3("test-bucket").download("key", target))

    def test_scoped_list_permission_can_confirm_absence_after_get_403(self):
        denied = subprocess.CompletedProcess([], 254, "", "(AccessDenied) Forbidden")
        empty = subprocess.CompletedProcess([], 0, '{"Contents": []}', "")
        with TemporaryDirectory() as tmp:
            with patch.object(release_tool.subprocess, "run", side_effect=[denied, empty]) as run:
                self.assertFalse(release_tool.S3("test-bucket").download("prefix/key", Path(tmp) / "out"))
            args = run.call_args.args[0]
            self.assertIn("list-objects-v2", args)
            self.assertEqual(args[args.index("--prefix") + 1], "prefix/key")

    def test_listing_existing_key_does_not_hide_a_real_get_denial(self):
        denied = subprocess.CompletedProcess([], 254, "", "(AccessDenied) Forbidden")
        exists = subprocess.CompletedProcess([], 0, '{"Contents": [{"Key": "prefix/key"}]}', "")
        with TemporaryDirectory() as tmp:
            with patch.object(release_tool.subprocess, "run", side_effect=[denied, exists]):
                with self.assertRaisesRegex(RuntimeError, "AccessDenied"):
                    release_tool.S3("test-bucket").download("prefix/key", Path(tmp) / "out")

    def test_s3_put_is_conditional_and_permission_failure_propagates(self):
        okay = subprocess.CompletedProcess([], 0, "{}", "")
        with patch.object(release_tool.subprocess, "run", return_value=okay) as run:
            release_tool.S3("test-bucket").upload_if_absent("key", Path("/tmp/source"))
        args = run.call_args.args[0]
        self.assertEqual(args[args.index("--if-none-match") + 1], "*")
        denied = subprocess.CompletedProcess([], 254, "", "(AccessDenied) Forbidden")
        with patch.object(release_tool.subprocess, "run", return_value=denied):
            with self.assertRaisesRegex(RuntimeError, "AccessDenied"):
                release_tool.S3("test-bucket").upload_if_absent("key", Path("/tmp/source"))

    def test_cli_wrong_commit_does_not_contact_aws(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release, _, _ = fixture(root)
            path = root / "release.json"
            path.write_bytes(release_tool.json_bytes(release))
            with (
                patch.object(release_tool.S3, "download") as download,
                redirect_stderr(StringIO()),
            ):
                status = release_tool.main([
                    "verify", "--release", str(path), "--git-revision", "b" * 40, "--remote",
                ])
            self.assertEqual(status, 1)
            download.assert_not_called()


if __name__ == "__main__":
    unittest.main()

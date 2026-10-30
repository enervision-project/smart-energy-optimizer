from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_dataset_release import fixture, release_tool, MemoryStorage, KEY, REVISION, parameter_value


class DatasetSecurityTests(unittest.TestCase):
    def test_cli_rejects_arbitrary_root_before_reading_or_preparing(self):
        with TemporaryDirectory() as tmp, TemporaryDirectory() as outside:
            root = Path(tmp)
            with (
                patch.object(release_tool, "PROJECT_ROOT", root),
                patch.object(release_tool, "prepare") as prepare,
                redirect_stderr(StringIO()),
            ):
                result = release_tool.main([
                    "prepare", "--root", outside, "--git-revision", REVISION,
                    "--output", ".data/ml/dataset-release.json",
                ])
            self.assertEqual(result, 1)
            prepare.assert_not_called()
            self.assertFalse(list(Path(outside).iterdir()))

    def test_cli_rejects_output_outside_or_at_unexpected_project_location(self):
        with TemporaryDirectory() as tmp, TemporaryDirectory() as outside:
            root = Path(tmp)
            for output in [str(Path(outside) / "escape.json"), "../escape.json", "README.md"]:
                with (
                    self.subTest(output=output),
                    patch.object(release_tool, "PROJECT_ROOT", root),
                    patch.object(release_tool, "prepare") as prepare,
                    redirect_stderr(StringIO()),
                ):
                    self.assertEqual(release_tool.main([
                        "prepare", "--git-revision", REVISION, "--output", output,
                    ]), 1)
                    prepare.assert_not_called()
            self.assertFalse(list(Path(outside).iterdir()))
            self.assertFalse((root / "README.md").exists())

    def test_cli_accepts_only_expected_release_files(self):
        with TemporaryDirectory() as tmp, TemporaryDirectory() as outside:
            root = Path(tmp)
            secret = Path(outside) / "secret.json"
            secret.write_text("private")
            for source in [str(secret), "../secret.json", "arbitrary.json"]:
                with (
                    self.subTest(source=source),
                    patch.object(release_tool, "PROJECT_ROOT", root),
                    patch.object(release_tool.S3, "download") as download,
                    redirect_stderr(StringIO()),
                ):
                    self.assertEqual(release_tool.main(["verify", "--release", source, "--remote"]), 1)
                    download.assert_not_called()
            self.assertEqual(secret.read_text(), "private")

    def test_output_symlink_cannot_overwrite_external_file(self):
        with TemporaryDirectory() as tmp, TemporaryDirectory() as outside:
            root = Path(tmp)
            target = Path(outside) / "keep.json"
            target.write_text("keep")
            folder = root / ".data/ml"
            folder.mkdir(parents=True)
            (folder / "dataset-release.json").symlink_to(target)
            with (
                patch.object(release_tool, "PROJECT_ROOT", root),
                patch.object(release_tool, "prepare") as prepare,
                redirect_stderr(StringIO()),
            ):
                self.assertEqual(release_tool.main([
                    "prepare", "--git-revision", REVISION,
                    "--output", ".data/ml/dataset-release.json",
                ]), 1)
            prepare.assert_not_called()
            self.assertEqual(target.read_text(), "keep")

    def test_parent_symlink_and_path_traversal_are_rejected(self):
        with TemporaryDirectory() as tmp, TemporaryDirectory() as outside:
            root = Path(tmp)
            (root / ".data").symlink_to(Path(outside), target_is_directory=True)
            for relative in [".data/ml/dataset-release.json", "../outside", str(Path(outside) / "file")]:
                with self.subTest(relative=relative), self.assertRaises(ValueError):
                    release_tool.project_path(root, relative)

    def test_publisher_rejects_symlinked_parquet_before_remote_access(self):
        with TemporaryDirectory() as tmp, TemporaryDirectory() as outside:
            root = Path(tmp)
            release, _, _ = fixture(root)
            original = root / ".data/ml/splits/train.parquet"
            target = Path(outside) / "private"
            target.write_bytes(original.read_bytes())
            original.unlink()
            original.symlink_to(target)
            store = MemoryStorage()
            with self.assertRaisesRegex(ValueError, "symbolique"):
                release_tool.publish(root, release, store)
            self.assertFalse(store.reads)
            self.assertFalse(store.uploads)

    def test_known_output_is_created_inside_project(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release, _, _ = fixture(root)
            before = {p: p.read_bytes() for p in (root / ".data/ml/splits").iterdir()}
            with (
                patch.object(release_tool, "PROJECT_ROOT", root),
                patch.object(release_tool, "prepare", return_value=release),
                redirect_stdout(StringIO()),
            ):
                self.assertEqual(release_tool.main([
                    "prepare", "--git-revision", REVISION,
                    "--output", ".data/ml/dataset-release.json",
                ]), 0)
            self.assertEqual(json.loads((root / ".data/ml/dataset-release.json").read_text()), release)
            self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_valid_manifests_can_be_read_at_ci_and_deploy_locations(self):
        for relative in [".data/ml/dataset-release.json", "dataset-release.json"]:
            with self.subTest(relative=relative), TemporaryDirectory() as tmp:
                root = Path(tmp)
                release, _, _ = fixture(root)
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(release_tool.json_bytes(release))
                with (
                    patch.object(release_tool, "PROJECT_ROOT", root),
                    patch.object(release_tool, "verify_remote") as verify,
                    redirect_stdout(StringIO()),
                ):
                    self.assertEqual(release_tool.main([
                        "verify", "--release", relative, "--git-revision", REVISION, "--remote",
                    ]), 0)
                verify.assert_called_once_with(release)

    def test_manifest_validation_rebuilds_and_rejects_unsafe_fields(self):
        with TemporaryDirectory() as tmp:
            release, _, _ = fixture(Path(tmp))
            release["unexpected"] = "--endpoint-url=evil"
            validated = release_tool.validate_release(release)
            self.assertNotIn("unexpected", validated)
            self.assertIsNot(validated, release)
            self.assertIsNot(validated["files"], release["files"])
            for changes in [
                {"bucket": "--profile=evil"}, {"dataset_id": "../escape"},
                {"dataset_id": "--debug"}, {"dataset_id": None},
                {"files": []}, {"git_revision": []},
            ]:
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    release_tool.validate_release({**release, **changes})

    def test_s3_rejects_keys_that_could_escape_or_change_operation(self):
        for key in [
            "--endpoint-url=evil", "bronze/readings/train.parquet",
            "ml/datasets/bootstrap/../train.parquet",
            "ml/datasets/bootstrap/v1/../../train.parquet",
            "ml/datasets/bootstrap/v1/train.parquet --profile evil",
            "ml/datasets/bootstrap/v1/unexpected.json",
        ]:
            with self.subTest(key=key), TemporaryDirectory() as tmp:
                with patch.object(release_tool.subprocess, "run") as run:
                    with self.assertRaises(ValueError):
                        release_tool.S3("test-bucket").download(key, Path(tmp) / "download")
                run.assert_not_called()

    def test_s3_request_metadata_never_becomes_command_arguments(self):
        okay = subprocess.CompletedProcess([], 0, "{}", "")
        requests = []

        def execute(command, **kwargs):
            bucket_file = command[command.index("--bucket") + 1]
            key_file = command[command.index("--key") + 1]
            requests.append((
                list(command), kwargs, parameter_value(command, "--bucket"),
                parameter_value(command, "--key"), bucket_file, key_file,
            ))
            return okay

        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.write_text("data")
            with patch.object(release_tool.subprocess, "run", side_effect=execute):
                client = release_tool.S3("test-bucket")
                client.download(KEY, Path(tmp) / "download")
                client.upload_if_absent(KEY, source)
            self.assertEqual(len(requests), 2)
            for command, kwargs, bucket, key, bucket_file, key_file in requests:
                self.assertEqual(bucket, "test-bucket")
                self.assertEqual(key, KEY)
                self.assertNotIn(KEY, command)
                self.assertNotIn("test-bucket", command)
                self.assertFalse(kwargs["shell"])
                self.assertTrue(bucket_file.startswith("file://"))
                self.assertTrue(key_file.startswith("file://"))
                self.assertFalse(Path(bucket_file.removeprefix("file://")).exists())
                self.assertFalse(Path(key_file.removeprefix("file://")).exists())

    def test_s3_rejects_symlinked_local_io_before_spawning(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "real"
            source.write_text("data")
            link = root / "link"
            link.symlink_to(source)
            with patch.object(release_tool.subprocess, "run") as run:
                with self.assertRaises(ValueError):
                    release_tool.S3("test-bucket").download(KEY, link)
                with self.assertRaises(ValueError):
                    release_tool.S3("test-bucket").upload_if_absent(KEY, link)
            run.assert_not_called()

    def test_published_checksums_match_the_verified_local_files(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release, _, _ = fixture(root)
            store = MemoryStorage()
            release_tool.publish(root, release, store)
            expected = "".join(
                release["files"][name]["sha256"] + "  " + name + "\n"
                for name in release_tool.NAMES
            ).encode()
            key = release_tool.PREFIX + "/" + release["dataset_id"] + "/sha256.txt"
            self.assertEqual(store.objects[key], expected)


class DvcDependencyLockTests(unittest.TestCase):
    def read_lock(self, filename):
        root = Path(__file__).resolve().parents[3]
        records = {}
        current = None
        for line in (root / "services/ml-service" / filename).read_text().splitlines():
            value = line.strip().rstrip(chr(92)).strip()
            if not value or value.startswith("#"):
                continue
            if value.startswith("--hash="):
                self.assertRegex(value, r"^--hash=sha256:[0-9a-f]{64}$")
                self.assertIsNotNone(current)
                records[current]["hashes"].append(value)
            else:
                self.assertRegex(value, r"^[a-zA-Z0-9_.-]+==[a-zA-Z0-9_.+!-]+$")
                name, version = value.split("==", 1)
                current = name.lower().replace("_", "-").replace(".", "-")
                self.assertNotIn(current, records)
                records[current] = {"version": version, "hashes": []}
        self.assertTrue(records)
        for name, info in records.items():
            self.assertTrue(info["hashes"], name + " has no verified artifact")
        return records

    def test_runtime_and_build_dependencies_are_pinned_and_hashed(self):
        runtime = self.read_lock("requirements-dvc.lock")
        build = self.read_lock("requirements-dvc-build.lock")
        self.assertIn("antlr4-python3-runtime", runtime)
        self.assertIn("setuptools", build)
        self.assertIn("wheel", build)

    def test_direct_dvc_versions_match_the_complete_runtime_lock(self):
        runtime = self.read_lock("requirements-dvc.lock")
        root = Path(__file__).resolve().parents[3]
        for line in (root / "services/ml-service/requirements-dvc.txt").read_text().splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            name, version = line.split("==", 1)
            name = name.split("[", 1)[0].lower().replace("_", "-").replace(".", "-")
            self.assertEqual(runtime[name]["version"], version)


if __name__ == "__main__":
    unittest.main()

"""Tests du lanceur DVC, sans accès AWS ni ouverture des Parquet."""

from contextlib import redirect_stdout
import importlib.util
from io import StringIO
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "dvc_launcher", Path(__file__).resolve().parents[1] / "run_dvc.py",
)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def make_project(root, with_data=False):
    folder = root / "services/ml-service"
    folder.mkdir(parents=True)
    (folder / "Dockerfile.dvc-tools").write_text("FROM fixture\n")
    (folder / "requirements-dvc.txt").write_text("fixture\n")
    (folder / "requirements-dvc.lock").write_text("fixture")
    (folder / "requirements-dvc-build.lock").write_text("fixture")
    (root / ".dvc").mkdir()
    (root / ".dvc/config").write_text("[core]\n")
    (root / ".data/ml").mkdir(parents=True)
    (root / launcher.POINTER).write_text("outs: []\n")
    if with_data:
        data = root / launcher.DATASET
        data.mkdir()
        for name in launcher.PARQUETS:
            (data / name).write_bytes(b"fixture: never opened by the launcher")


class RunDvcTests(unittest.TestCase):
    def test_dry_run_creates_nothing_and_hides_credentials(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "not created"
            aws = Path(temporary) / "aws"
            with (
                patch.dict(os.environ, {
                    "AWS_ACCESS_KEY_ID": "private-key-id",
                    "AWS_SECRET_ACCESS_KEY": "private-secret",
                    "AWS_SESSION_TOKEN": "private-token",
                }, clear=True),
                patch.object(launcher.subprocess, "run") as execute,
                redirect_stdout(StringIO()) as output,
            ):
                launcher.run_workflow(root, "push", aws_dir=aws, dry_run=True)
            execute.assert_not_called()
            self.assertFalse(root.exists())
            self.assertFalse(aws.exists())
            text = output.getvalue()
            self.assertIn("--env AWS_SESSION_TOKEN", text)
            self.assertNotIn("private-", text)

    def test_add_rejects_incomplete_or_unexpected_data_before_docker(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root, with_data=True)
            extra = root / launcher.DATASET / "unexpected.csv"
            extra.write_text("do not version me")
            with patch.object(launcher.subprocess, "run") as execute:
                with self.assertRaisesRegex(ValueError, "exactement"):
                    launcher.run_workflow(root, "add", aws_dir=root / "aws")
                extra.unlink()
                (root / launcher.DATASET / "test.parquet").unlink()
                with self.assertRaisesRegex(ValueError, "exactement"):
                    launcher.run_workflow(root, "add", aws_dir=root / "aws")
            execute.assert_not_called()

    def test_add_preserves_files_and_does_not_forward_aws(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root, with_data=True)
            originals = {p: p.read_bytes() for p in (root / launcher.DATASET).iterdir()}
            with (
                patch.dict(os.environ, {"AWS_SECRET_ACCESS_KEY": "private-secret"}, clear=True),
                patch.object(launcher.shutil, "which", return_value="/bin/docker"),
                patch.object(launcher.subprocess, "run") as execute,
                patch.object(Path, "open", side_effect=AssertionError("Do not open the data")),
                redirect_stdout(StringIO()),
            ):
                launcher.run_workflow(root, "add", aws_dir=root / "aws")
            args = execute.call_args.args[0]
            self.assertEqual(args[-3:], ["add", "--no-relink", launcher.DATASET])
            self.assertNotIn("AWS_SECRET_ACCESS_KEY", args)
            self.assertEqual(originals, {p: p.read_bytes() for p in originals})

    def test_pull_works_without_local_data_and_mounts_aws_read_only(self):
        with TemporaryDirectory(prefix="dvc launcher ") as temporary:
            root = Path(temporary)
            make_project(root)
            aws = root / "aws"
            aws.mkdir()
            with (
                patch.dict(os.environ, {"AWS_DEFAULT_PROFILE": "colleague"}, clear=True),
                patch.object(launcher.shutil, "which", return_value="/bin/docker"),
                patch.object(launcher.subprocess, "run") as execute,
                redirect_stdout(StringIO()),
            ):
                launcher.run_workflow(root, "pull", aws_dir=aws)
            args = execute.call_args.args[0]
            self.assertEqual(args[-2:], ["pull", launcher.POINTER])
            self.assertIn(f"type=bind,source={aws},target=/tmp/.aws,readonly", args)
            self.assertIn(f"type=bind,source={root},target=/workspace", args)
            self.assertEqual(execute.call_args.kwargs["env"]["AWS_PROFILE"], "colleague")
            self.assertEqual(args[args.index("--user") + 1], f"{os.getuid()}:{os.getgid()}")
            self.assertFalse((root / launcher.DATASET).exists())

    def test_explicit_profile_overrides_shell_and_secret_values_stay_out_of_arguments(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            with (
                patch.dict(os.environ, {
                    "AWS_PROFILE": "old-profile",
                    "AWS_ACCESS_KEY_ID": "private-key",
                    "AWS_SECRET_ACCESS_KEY": "private-secret",
                    "AWS_SESSION_TOKEN": "private-token",
                }, clear=True),
                patch.object(launcher.shutil, "which", return_value="/bin/docker"),
                patch.object(launcher.subprocess, "run") as execute,
                redirect_stdout(StringIO()) as output,
            ):
                launcher.run_workflow(root, "push", profile="chosen-profile", aws_dir=root / "absent")
            args = execute.call_args.args[0]
            self.assertEqual(execute.call_args.kwargs["env"]["AWS_PROFILE"], "chosen-profile")
            self.assertIn("AWS_SESSION_TOKEN", args)
            self.assertNotIn("private-", " ".join(args) + output.getvalue())
            self.assertFalse(any(".aws" in arg for arg in args))

    def test_no_credentials_fails_before_build(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(launcher.shutil, "which", return_value="/bin/docker"),
                patch.object(launcher.subprocess, "run") as execute,
            ):
                with self.assertRaisesRegex(RuntimeError, "profil AWS"):
                    launcher.run_workflow(root, "push", aws_dir=root / "absent")
            execute.assert_not_called()

    def test_missing_pointer_does_not_start_docker(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            (root / launcher.POINTER).unlink()
            with patch.object(launcher.subprocess, "run") as execute:
                for command in ["add", "pull"]:
                    with self.assertRaisesRegex(FileNotFoundError, "ml-datasets.dvc"):
                        launcher.run_workflow(root, command, aws_dir=root / "aws")
            execute.assert_not_called()

    def test_failed_build_does_not_start_dvc(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            with (
                patch.object(launcher.shutil, "which", return_value="/bin/docker"),
                patch.object(
                    launcher.subprocess, "run",
                    side_effect=subprocess.CalledProcessError(7, ["docker", "build"]),
                ) as execute,
                redirect_stdout(StringIO()),
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    launcher.run_workflow(root, "status", aws_dir=root / "aws")
            self.assertEqual(execute.call_count, 1)


if __name__ == "__main__":
    unittest.main()

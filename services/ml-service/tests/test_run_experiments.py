import base64
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "ml_workflow_launcher", Path(__file__).resolve().parents[1] / "run_experiments.py",
)
launcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = launcher
spec.loader.exec_module(launcher)

EXAMPLE = (
    "POSTGRES_USER=local\nPOSTGRES_PASSWORD=local-password\nPOSTGRES_DB=energy\n"
    "JWT_SECRET=\nMLFLOW_PORT=5007\n"
)


def make_project(root):
    (root / "services/ml-service/configs").mkdir(parents=True)
    (root / "compose.yaml").write_text("services: {}\n")
    (root / "services/ml-service/compose.training.yaml").write_text("services: {}\n")
    for name in ["hgb_search_no_weather.yaml", "hist_gradient_boosting_no_weather.yaml"]:
        (root / "services/ml-service/configs" / name).write_text("model: fixture\n")
    splits = root / ".data/ml/splits"
    splits.mkdir(parents=True)
    for name in ["train", "validation"]:
        (splits / f"{name}.parquet").write_bytes(b"fixture: read by the trainer, not the launcher")
    (root / ".env.example").write_text(EXAMPLE)


def simulated_run(command, **kwargs):
    command = list(command)
    stdout = ""
    if command[:3] == ["git", "rev-parse", "HEAD"]:
        stdout = "fixture-commit\n"
    return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")


class RunExperimentsTests(unittest.TestCase):
    def test_dry_run_has_no_side_effects_even_without_inputs(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "not created"
            with (
                patch.object(launcher.subprocess, "run") as execute,
                patch.object(launcher.secrets, "token_bytes") as token,
                redirect_stdout(StringIO()) as output,
            ):
                launcher.run_workflow(root, "preview", dry_run=True)
            execute.assert_not_called()
            token.assert_not_called()
            self.assertFalse(root.exists())
            self.assertIn("96 entraînements HGB sans météo", output.getvalue())
            self.assertIn("configs/hgb_search_no_weather.yaml", output.getvalue())
            self.assertNotIn("ml-prepare", output.getvalue())
            self.assertNotIn("test.parquet", output.getvalue())

    def test_missing_inputs_fail_before_configuration_or_docker(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(launcher.subprocess, "run") as execute, redirect_stdout(StringIO()):
                with self.assertRaisesRegex(FileNotFoundError, "Fichiers requis"):
                    launcher.run_workflow(root, "missing")
            execute.assert_not_called()
            self.assertFalse((root / ".env").exists())
            self.assertFalse((root / ".data/ml/splits").exists())

    def test_unavailable_docker_does_not_change_configuration(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            with patch.object(launcher.shutil, "which", return_value=None), redirect_stdout(StringIO()):
                with self.assertRaisesRegex(RuntimeError, "Installer Docker"):
                    launcher.run_workflow(root, "no-docker")
            self.assertFalse((root / ".env").exists())
            self.assertEqual(
                sorted(path.name for path in (root / ".data/ml/splits").iterdir()),
                ["train.parquet", "validation.parquet"],
            )

    def test_initial_env_has_private_permissions_and_secret_is_not_logged(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".env.example").write_text(EXAMPLE)
            with patch.dict(os.environ, {}, clear=True), redirect_stdout(StringIO()) as output:
                port = launcher.ensure_local_env(root)
            text = (root / ".env").read_text()
            secret = launcher.env_value(text, "JWT_SECRET")
            self.assertEqual(len(base64.b64decode(secret)), 32)
            self.assertEqual(port, "5007")
            self.assertNotIn(secret, output.getvalue())
            self.assertEqual((root / ".env").stat().st_mode & 0o777, 0o600)
            self.assertEqual(launcher.env_value(text, "POSTGRES_PASSWORD"), "local-password")

    def test_complete_existing_env_is_preserved_byte_for_byte(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = (
                b"POSTGRES_USER=local\r\nPOSTGRES_PASSWORD=some'password#value\r\n"
                b"POSTGRES_DB=energy\r\nJWT_SECRET='existing-secret' # keep\r\n"
                b"MLFLOW_PORT=5012\r\n"
            )
            (root / ".env").write_bytes(content)
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(launcher.secrets, "token_bytes") as token,
                redirect_stdout(StringIO()),
            ):
                port = launcher.ensure_local_env(root)
            token.assert_not_called()
            self.assertEqual((root / ".env").read_bytes(), content)
            self.assertEqual(port, "5012")

    def test_only_missing_jwt_is_initialized(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = EXAMPLE.replace("\n", "\r\n")
            (root / ".env").write_bytes(original.encode())
            with (
                patch.dict(os.environ, {"JWT_SECRET": "provided-by-shell"}, clear=True),
                redirect_stdout(StringIO()),
            ):
                launcher.ensure_local_env(root)
            self.assertEqual(
                (root / ".env").read_bytes(),
                original.replace("JWT_SECRET=", "JWT_SECRET=provided-by-shell").encode(),
            )

    def test_only_no_weather_campaign_runs_with_existing_parquets_and_healthy_mlflow(self):
        with TemporaryDirectory(prefix="ml launcher ") as temporary:
            root = Path(temporary)
            make_project(root)
            existing_env = EXAMPLE.replace("JWT_SECRET=", "JWT_SECRET=existing")
            (root / ".env").write_text(existing_env)
            splits = root / ".data/ml/splits"
            originals = {path: path.read_bytes() for path in splits.iterdir()}
            original_open = Path.open

            def no_parquet_access(path, *args, **kwargs):
                if path.suffix == ".parquet":
                    raise AssertionError(f"Le lanceur ne doit pas ouvrir {path}")
                return original_open(path, *args, **kwargs)

            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(launcher.shutil, "which", side_effect=lambda name: "/usr/bin/" + name),
                patch.object(launcher.subprocess, "run", side_effect=simulated_run) as execute,
                patch.object(Path, "open", no_parquet_access),
                redirect_stdout(StringIO()) as output,
            ):
                launcher.run_workflow(root, "all-tests")
            pipeline = [
                call for call in execute.call_args_list if call.kwargs.get("check")
            ]
            self.assertEqual(len(pipeline), 3)
            commands = [list(call.args[0]) for call in pipeline]
            self.assertEqual(commands[0][-2:], ["build", "ml-trainer"])
            self.assertEqual(commands[1][-1], "mlflow")
            self.assertIn("--wait", commands[1])
            search = commands[2]
            self.assertEqual(search[search.index("--config") + 1], "configs/hgb_search_no_weather.yaml")
            self.assertEqual(search[search.index("--campaign-id") + 1], "all-tests")
            self.assertIn("training.search_hgb", search)
            self.assertIn("--no-deps", search)
            self.assertNotIn("--resume", search)
            for call in pipeline:
                self.assertEqual(call.kwargs["cwd"], root)
                self.assertEqual(call.kwargs["env"]["TRAINING_GIT_REVISION"], "fixture-commit")
                self.assertEqual(call.kwargs["env"]["TRAINING_GIT_DIRTY"], "false")
                for forbidden in ["scheduler", "ml-prepare", "preparation", "test.parquet", "training.prepare_data"]:
                    self.assertNotIn(forbidden, call.args[0])
            self.assertEqual({path: path.read_bytes() for path in splits.iterdir()}, originals)
            self.assertEqual((root / ".env").read_text(), existing_env)
            self.assertFalse((root / ".data/ml/raw").exists())
            self.assertFalse((splits / "test.parquet").exists())
            self.assertIn("http://localhost:5007", output.getvalue())
            self.assertIn("consommation-horaire-sans-meteo-v1", output.getvalue())
            self.assertIn("campaign_id : all-tests", output.getvalue())

    def test_missing_validation_fails_before_configuration_or_docker(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            (root / ".data/ml/splits/validation.parquet").unlink()
            with patch.object(launcher.subprocess, "run") as execute, redirect_stdout(StringIO()):
                with self.assertRaisesRegex(FileNotFoundError, "validation.parquet"):
                    launcher.run_workflow(root, "missing-validation")
            execute.assert_not_called()
            self.assertFalse((root / ".env").exists())

    def test_resume_cli_targets_the_requested_campaign_without_preparation(self):
        with (
            patch.object(launcher, "__file__", "/project/services/ml-service/run_experiments.py"),
            patch.object(launcher.subprocess, "run") as execute,
            patch.object(launcher, "ensure_local_env") as configure,
            redirect_stdout(StringIO()) as output,
        ):
            result = launcher.main(["--dry-run", "--campaign-id", "interrupted", "--resume"])
        self.assertEqual(result, 0)
        execute.assert_not_called()
        configure.assert_not_called()
        self.assertIn("--campaign-id interrupted --resume", output.getvalue())
        self.assertEqual(output.getvalue().count("configs/hgb_search_no_weather.yaml"), 1)
        self.assertNotIn("ml-prepare", output.getvalue())

    def test_resume_without_campaign_id_is_rejected_before_any_work(self):
        with (
            patch.object(launcher, "run_workflow") as workflow,
            redirect_stderr(StringIO()) as output,
        ):
            with self.assertRaises(SystemExit) as error:
                launcher.main(["--resume"])
        self.assertEqual(error.exception.code, 2)
        workflow.assert_not_called()
        self.assertIn("--resume nécessite --campaign-id", output.getvalue())

    def test_mlflow_failure_prevents_training(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_project(root)
            attempted = []

            def failure(command, **kwargs):
                if kwargs.get("check"):
                    attempted.append(list(command))
                    if command[-1] == "mlflow":
                        raise subprocess.CalledProcessError(7, command)
                return simulated_run(command, **kwargs)

            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(launcher.shutil, "which", return_value="/usr/bin/tool"),
                patch.object(launcher.subprocess, "run", side_effect=failure),
                redirect_stdout(StringIO()),
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    launcher.run_workflow(root, "failure")
            self.assertEqual(len(attempted), 2)
            self.assertEqual(attempted[-1][-1], "mlflow")
            self.assertFalse(any("--config" in command for command in attempted))


if __name__ == "__main__":
    unittest.main()

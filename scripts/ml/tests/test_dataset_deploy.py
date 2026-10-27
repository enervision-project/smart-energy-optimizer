"""Exécute deploy.sh uniquement avec AWS et Docker factices, dans un dossier temporaire."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SHA = "a" * 40
OLD = "b" * 40
OLD_URI = "s3://test-datalake/ml/datasets/bootstrap/old"
NEW_URI = "s3://test-datalake/ml/datasets/bootstrap/new"

AWS = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args=sys.argv[1:]
with Path(os.environ["CALL_LOG"]).open("a") as f: f.write(json.dumps({"tool":"aws","args":args})+"\n")
if args[:2]==["ssm","get-parameters-by-path"]:
    print("/enervision/prod/env/TRAINING_BOOTSTRAP_URI\t"+os.environ["OLD_URI"])
elif args[:2]==["ecr","get-login-password"]:
    print("dummy-login")
else:
    print("Unexpected AWS operation",args,file=sys.stderr)
    sys.exit(90)
'''
DOCKER = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args=sys.argv[1:]
entry={"tool":"docker","args":args}
for i,arg in enumerate(args):
    if arg=="--env-file":
        for line in Path(args[i+1]).read_text().splitlines():
            if line.startswith(("TRAINING_BOOTSTRAP_URI=","PREDICTION_SERVICE_TAG=")):
                key,value=line.split("=",1)
                entry[key]=value
with Path(os.environ["CALL_LOG"]).open("a") as f: f.write(json.dumps(entry)+"\n")
if args and args[0]=="login": sys.stdin.read()
phase=os.environ.get("FAIL_PHASE")
if phase=="preflight" and "run" in args: sys.exit(12)
if phase=="up" and "up" in args and "--force-recreate" not in args: sys.exit(13)
if phase=="live" and "exec" in args and "prediction-jobs" in args: sys.exit(14)
'''
VERIFY = r'''import json, os, sys
from pathlib import Path
args=sys.argv[1:]
data=json.loads(Path(args[args.index("--release")+1]).read_text())
expected=args[args.index("--git-revision")+1]
if data["git_revision"]!=expected or os.environ.get("FAIL_PHASE")=="manifest":
    sys.exit("Snapshot refusé")
print(data["dataset_uri"])
'''


class DeployDatasetTests(unittest.TestCase):
    def run_deploy(self, root, phase="", services=("prediction-service",), existing=True, override=True):
        binary = root / "bin"
        binary.mkdir()
        for name, content in [("aws", AWS), ("docker", DOCKER)]:
            path = binary / name
            path.write_text(content)
            path.chmod(0o755)
        helper = root / "infra/deploy/dataset_release.py"
        helper.parent.mkdir(parents=True)
        helper.write_text(VERIFY)
        release = {"git_revision": SHA, "dataset_uri": NEW_URI}
        (root / "dataset-release.json").write_text(json.dumps(release))
        (root / ".env").write_text("TRAINING_BOOTSTRAP_URI=" + OLD_URI + "\n")
        if existing:
            content = f"ECR_REGISTRY=registry\nPREDICTION_SERVICE_TAG={OLD}\n"
            if override:
                content += f"TRAINING_BOOTSTRAP_URI={OLD_URI}\n"
            (root / "deploy.env").write_text(content)
        env = os.environ.copy()
        # Les seuls programmes aws/docker accessibles sont les exécutables factices ci-dessus.
        env.update(
            PATH=str(binary) + ":" + env["PATH"], ENERVISION_DIR=str(root),
            CALL_LOG=str(root / "calls.jsonl"), OLD_URI=OLD_URI, FAIL_PHASE=phase,
        )
        result = subprocess.run(
            ["bash", str(ROOT / "infra/deploy/deploy.sh"), SHA, "registry", *services],
            env=env, cwd=root, text=True, capture_output=True,
        )
        log = root / "calls.jsonl"
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return result, calls

    def test_success_uses_new_uri_for_preflight_and_running_jobs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result, calls = self.run_deploy(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            content = (root / "deploy.env").read_text()
            self.assertIn("TRAINING_BOOTSTRAP_URI=" + NEW_URI, content)
            self.assertIn("PREDICTION_SERVICE_TAG=" + SHA, content)
            relevant = [call for call in calls if call["tool"] == "docker" and (
                "run" in call["args"] or "up" in call["args"] or "exec" in call["args"]
            )]
            self.assertTrue(relevant)
            self.assertTrue(all(call["TRAINING_BOOTSTRAP_URI"] == NEW_URI for call in relevant))
            self.assertFalse(any(call["args"][:2] == ["ssm", "put-parameter"] for call in calls))
            self.assertFalse(list(root.glob(".deploy.env.*")))

    def test_bad_manifest_stops_before_any_aws_or_docker_call(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result, calls = self.run_deploy(root, phase="manifest")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(calls)
            self.assertIn(OLD, (root / "deploy.env").read_text())

    def test_preflight_failure_keeps_old_config_and_never_restarts_jobs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result, calls = self.run_deploy(root, phase="preflight")
            self.assertEqual(result.returncode, 12, result.stderr)
            self.assertIn("TRAINING_BOOTSTRAP_URI=" + OLD_URI, (root / "deploy.env").read_text())
            self.assertIn("PREDICTION_SERVICE_TAG=" + OLD, (root / "deploy.env").read_text())
            self.assertFalse(any("up" in call["args"] for call in calls))
            self.assertFalse(list(root.glob(".deploy.env.*")))

    def test_activation_or_live_check_failure_restores_old_jobs_and_uri(self):
        for phase, code in [("up", 13), ("live", 14)]:
            with self.subTest(phase=phase), TemporaryDirectory() as tmp:
                root = Path(tmp)
                result, calls = self.run_deploy(root, phase=phase)
                self.assertEqual(result.returncode, code, result.stderr)
                content = (root / "deploy.env").read_text()
                self.assertIn("TRAINING_BOOTSTRAP_URI=" + OLD_URI, content)
                self.assertIn("PREDICTION_SERVICE_TAG=" + OLD, content)
                rollback = [call for call in calls if "--force-recreate" in call["args"]]
                self.assertEqual(len(rollback), 1)
                self.assertEqual(rollback[0]["TRAINING_BOOTSTRAP_URI"], OLD_URI)
                self.assertEqual(rollback[0]["PREDICTION_SERVICE_TAG"], OLD)
                self.assertNotIn("scheduler", rollback[0]["args"])

    def test_first_dvc_migration_can_restore_legacy_uri_from_ssm_env(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result, calls = self.run_deploy(root, phase="up", override=False)
            self.assertEqual(result.returncode, 13, result.stderr)
            self.assertNotIn("TRAINING_BOOTSTRAP_URI=", (root / "deploy.env").read_text())
            rollback = [call for call in calls if "--force-recreate" in call["args"]]
            self.assertEqual(len(rollback), 1)
            self.assertEqual(rollback[0]["TRAINING_BOOTSTRAP_URI"], OLD_URI)
            self.assertEqual(rollback[0]["PREDICTION_SERVICE_TAG"], OLD)

    def test_first_failed_activation_stops_unconfirmed_jobs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result, calls = self.run_deploy(root, phase="up", existing=False)
            self.assertEqual(result.returncode, 13, result.stderr)
            self.assertTrue(any("stop" in call["args"] and "prediction-jobs" in call["args"] for call in calls))
            self.assertNotIn("TRAINING_BOOTSTRAP_URI=", (root / "deploy.env").read_text())

    def test_frontend_only_deployment_does_not_validate_or_change_ml_dataset(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result, calls = self.run_deploy(root, phase="manifest", services=("web",))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("TRAINING_BOOTSTRAP_URI=" + OLD_URI, (root / "deploy.env").read_text())
            self.assertFalse(any("prediction-jobs" in call["args"] for call in calls))


class DatasetSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("changed_services", ROOT / "scripts/ci/changed-services.py")
        cls.selector = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.selector)
        cls.config = json.loads((ROOT / ".github/services.json").read_text())

    def test_dataset_changes_select_prediction_service_only(self):
        for path in ["ml-datasets.dvc", ".dvc/config", "scripts/ml/upload-bootstrap.sh"]:
            with self.subTest(path=path), patch.object(self.selector, "changed_files", return_value=[path]):
                selected, _ = self.selector.select(self.config, "old", "new", "")
                self.assertEqual(selected, ["prediction-service"])

    def test_frontend_changes_do_not_select_prediction_service(self):
        with patch.object(self.selector, "changed_files", return_value=["app/web/src/main.ts"]):
            selected, _ = self.selector.select(self.config, "old", "new", "")
        self.assertEqual(selected, ["web"])


if __name__ == "__main__":
    unittest.main()

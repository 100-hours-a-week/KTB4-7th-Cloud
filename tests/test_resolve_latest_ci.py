import importlib.util
import pathlib
import unittest


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "deploy" / "resolve-latest-ci.py"
SPEC = importlib.util.spec_from_file_location("resolve_latest_ci", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ResolveLatestCiTest(unittest.TestCase):
    def test_uses_current_dev_head_and_successful_push_run(self):
        sha = "a" * 40
        paths = []

        def fetch(path):
            paths.append(path)
            if path.endswith("/branches/dev"):
                return {"commit": {"sha": sha}}
            return {"workflow_runs": [{"head_sha": sha, "head_branch": "dev", "event": "push", "conclusion": "success", "html_url": "https://github.com/run/1"}]}

        self.assertEqual(MODULE.resolve("backend", fetch), (sha, "https://github.com/run/1"))
        self.assertIn("head_sha=" + sha, paths[1])
        self.assertIn("event=push", paths[1])

    def test_rejects_success_for_an_older_commit(self):
        sha = "b" * 40

        def fetch(path):
            if path.endswith("/branches/dev"):
                return {"commit": {"sha": sha}}
            return {"workflow_runs": [{"head_sha": "a" * 40, "head_branch": "dev", "event": "push", "conclusion": "success"}]}

        with self.assertRaisesRegex(ValueError, "no successful push CI"):
            MODULE.resolve("ai", fetch)

    def test_rejects_incomplete_ci(self):
        sha = "c" * 40

        def fetch(path):
            if path.endswith("/branches/dev"):
                return {"commit": {"sha": sha}}
            return {"workflow_runs": [{"head_sha": sha, "head_branch": "dev", "event": "push", "conclusion": None}]}

        with self.assertRaisesRegex(ValueError, "no successful push CI"):
            MODULE.resolve("frontend", fetch)


if __name__ == "__main__":
    unittest.main()

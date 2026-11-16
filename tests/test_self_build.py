import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.self_build import validate, verify_candidate


class SelfBuildPatchTests(unittest.TestCase):
    def test_allows_small_source_patch(self):
        patch = """diff --git a/src/example.ts b/src/example.ts
--- a/src/example.ts
+++ b/src/example.ts
@@ -1 +1 @@
-old
+new
"""
        validate(patch)

    def test_rejects_workflow_and_path_traversal(self):
        for path in (".github/workflows/a.yml", "src/../../outside"):
            patch = f"""diff --git a/{path} b/{path}
--- a/{path}
+++ b/{path}
@@ -1 +1 @@
-old
+new
"""
            with self.assertRaises(RuntimeError):
                validate(patch)

    def test_candidate_verification_runs_python_after_typescript(self):
        calls = []
        def fake_run(command):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "ok")
        with patch("scripts.self_build.run", side_effect=fake_run):
            result = verify_candidate()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(calls, [
            ["npm", "run", "typecheck"],
            ["npm", "test"],
            ["python", "-m", "pytest", "-q"],
        ])

    def test_rejects_secret_shaped_patch_and_deletions(self):
        secret = """diff --git a/src/example.ts b/src/example.ts
--- a/src/example.ts
+++ b/src/example.ts
@@ -1 +1 @@
-old
+const key = sk-AAAAAAAAAAAAAAAAAAAAAAAAAAAA;
"""
        deletion = """diff --git a/src/example.ts b/src/example.ts
deleted file mode 100644
--- a/src/example.ts
+++ /dev/null
@@ -1 +0,0 @@
-old
"""
        for patch in (secret, deletion):
            with self.assertRaises(RuntimeError):
                validate(patch)


if __name__ == "__main__":
    unittest.main()

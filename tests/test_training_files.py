import compileall
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class TrainingSourceSyntaxTests(unittest.TestCase):
    def test_all_python_sources_compile(self):
        for folder in ("scripts","training","tests"):
            self.assertTrue(compileall.compile_dir(ROOT/folder,quiet=1,force=True))

if __name__ == "__main__": unittest.main()

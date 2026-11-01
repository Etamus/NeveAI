"""Check source packaging without touching the installed backend environment."""

from pathlib import Path
import subprocess
import tempfile
import unittest
import venv


ROOT = Path(__file__).resolve().parents[1]


def git(*arguments):
    return subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        check=True, capture_output=True,
    ).stdout.decode("utf-8")


class SourceHygieneTests(unittest.TestCase):
    def test_obsolete_environment_is_absent(self):
        self.assertFalse((ROOT / "backend/venv").exists())

    def test_source_tree_does_not_ship_virtual_environments(self):
        # Pending deletions remain in the index until the user commits them.
        # Inspect the candidate working tree without staging or changing Git.
        paths = git("ls-files", "-z").split("\0")
        environments = [path for path in paths if path
                        and (ROOT / path).is_file()
                        and {"venv", ".venv"}.intersection(Path(path).parts)]
        self.assertEqual(environments, [])

    def test_generated_environments_remain_ignored(self):
        paths = ["backend/venv/pyvenv.cfg",
                 "backend/neveai/venv/pyvenv.cfg"]
        ignored = git("check-ignore", "--no-index", *paths).splitlines()
        self.assertEqual(set(ignored), set(paths))

    def test_windows_launch_and_install_use_same_environment(self):
        for filename in ("launchers/iniciar.ps1", "launchers/instalar.ps1"):
            source = (ROOT / filename).read_text(encoding="utf-8-sig")
            self.assertIn("'backend\\neveai\\venv", source)
            self.assertNotIn("'backend\\venv", source)

    def test_fresh_environment_is_generated_for_its_own_location(self):
        with tempfile.TemporaryDirectory(prefix="NeveAI source test ") as folder:
            target = Path(folder) / "local environment"
            venv.EnvBuilder(with_pip=False).create(target)
            configuration = (target / "pyvenv.cfg").read_text(encoding="utf-8")
            self.assertIn(str(target), configuration)
            self.assertNotIn(str(ROOT / "backend/venv"), configuration)


if __name__ == "__main__":
    unittest.main()

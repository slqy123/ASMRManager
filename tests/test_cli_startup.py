import tests

import subprocess
import sys
import unittest


class CLIStartupTests(unittest.TestCase):
    def test_help_and_version_do_not_import_command_dependencies(self):
        for arguments in (["--help"], ["--version"], ["which", "--help"]):
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        (
                            "import sys; from asmrmanager.cli.main import main; "
                            f"main({arguments!r}, standalone_mode=False); "
                            "assert 'sqlalchemy' not in sys.modules; "
                            "assert 'asmrmanager.sync' not in sys.modules; "
                            "assert 'asmrmanager.spider' not in sys.modules"
                        ),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_only_lazy_commands_are_registered(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from asmrmanager.cli.main import main, LAZY_COMMANDS; "
                    "assert set(main.commands) == set(LAZY_COMMANDS)"
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_lazy_commands_resolve_to_real_commands(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import click; from asmrmanager.cli.main import main, LAZY_COMMANDS; "
                    "ctx = click.Context(main); "
                    "commands = [main.get_command(ctx, name) for name in LAZY_COMMANDS]; "
                    "assert all(command.callback is not None for command in commands)"
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

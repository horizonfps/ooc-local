from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolated_global_commands_file(tmp_path_factory):
    """Keeps the whole suite off ~/.ooc-local/commands.yaml: load_global_commands()
    resolves its default path lazily from this env var, and get_session (called by
    dozens of tests) always calls it with no argument."""
    os.environ["OOC_COMMANDS_FILE"] = str(tmp_path_factory.mktemp("cfg") / "commands.yaml")
    yield

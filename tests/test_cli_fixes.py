"""Issues2/3/4: actual CLI parser, no database or auth-side effects."""
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

from todotool import cli, db

COMMANDS = [
    ["init"], ["add", "fixture task"], ["list"], ["done", "1"],
    ["edit", "1"], ["history", "1"], ["due"], ["tag", "list"],
]


@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize("position", ["before", "after", "both", "split"])
def test_real_parser_retains_common_values(command, position):
    parser = cli.build_parser()
    before = ["--user", "fixture-user", "--password", "fixture-value", "--lids"]
    after = []
    if position == "after":
        before, after = [], before
    elif position == "both":
        after = ["--user", "child-user", "--password", "child-value", "--lids"]
    elif position == "split":
        before = ["--user", "fixture-user", "--lids"]
        after = ["--password", "fixture-value"]
    args = parser.parse_args(before + command + after)
    assert args.user == ("child-user" if position == "both" else "fixture-user")
    assert args.password == ("child-value" if position == "both" else "fixture-value")
    assert args.lids is True
    assert args.command == command[0]


def test_child_overrides_only_the_explicit_field():
    args = cli.build_parser().parse_args([
        "--user", "global-user", "--password", "global-value", "--lids",
        "add", "fixture", "--user", "child-user"])
    assert args.user == "child-user"
    assert args.password == "global-value"
    assert args.lids is True


def test_unspecified_common_options_keep_normal_defaults():
    args = cli.build_parser().parse_args(["list"])
    assert args.user is None
    assert args.password is None
    assert args.lids is False


def test_main_dispatches_actual_parsed_values_without_touching_database():
    with patch.object(cli.db, "init_db", side_effect=AssertionError("no real database")), \
         patch.object(cli, "cmd_add") as add, \
         patch("sys.argv", ["todotool", "--user", "fixture-user", "--password", "fixture-value",
                            "add", "fixture task", "--priority", "high"]):
        cli.main()
    args = add.call_args.args[0]
    assert args.user == "fixture-user"
    assert args.password == "fixture-value"
    assert args.title == "fixture task"
    assert args.priority == "high"
    assert Path(cli.__file__).resolve().parent == Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("days, expected", [(0, "2026-02-10"), (1, "2026-02-11"), (7, "2026-02-17")])
def test_existing_due_boundary_passes_inclusive_dates_to_adapter(days, expected):
    # Do not connect SQLite/PostgreSQL: verify the unchanged real function's bounds.
    class FrozenDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 2, 10)

    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = []
    with patch.object(db, "date", FrozenDate):
        db.list_due_within(conn, days)
    sql, values = conn.execute.call_args.args
    assert values == ("2026-02-10", expected)
    assert "due_date >= ?" in sql
    assert "due_date <= ?" in sql
    assert "status = 'pending'" in sql


def test_due_cli_keeps_days_and_displays_adapter_result(capsys):
    args = cli.build_parser().parse_args(["due", "--days", "7"])
    conn = object()
    with patch.object(db, "init_db", return_value=conn), \
         patch.object(cli, "require_auth", return_value=True), \
         patch.object(db, "list_due_within", return_value=[{
             "id": 7, "priority": "medium", "title": "fixture due", "due_date": "2026-02-15"}]) as due, \
         patch.object(db, "get_todo_tags", return_value=[]):
        cli.cmd_due(args)
    due.assert_called_once_with(conn, 7)
    assert "fixture due" in capsys.readouterr().out


def test_removed_delete_command_is_not_advertised_or_accepted(tmp_path):
    # A used checkout may legitimately retain its ignored local data file.
    existing = tmp_path / "todo.db"
    original = b"existing ignored file fixture; not a database schema"
    existing.write_bytes(original)
    with patch.object(db, "DB_PATH", str(existing)), \
         patch.object(db, "init_db", side_effect=AssertionError("parser must not open data")) as init:
        with pytest.raises(SystemExit) as caught:
            cli.build_parser().parse_args(["delete", "1"])
    assert caught.value.code == 2
    init.assert_not_called()
    assert existing.read_bytes() == original
    root = Path(cli.__file__).resolve().parent
    assert "todotool delete" not in (root / "README.md").read_text()

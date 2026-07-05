import curses
import unittest
from unittest.mock import patch, MagicMock

from todo import (
    create_todo_list,
    add_item,
    mark_done,
    set_due,
    undo,
    _tui_build_display,
    _tui_is_overdue,
    _tui_item_line,
    _tui_item_detail,
    _tui_help,
    _UNDO_STACKS,
    _PRIORITY_ORDER,
)


class TestTuiBuildDisplay(unittest.TestCase):
    def test_no_filter_sort(self):
        todos = create_todo_list()
        add_item(todos, "Beta")
        add_item(todos, "Alpha")
        result = _tui_build_display(todos, "all", "id", "")
        self.assertEqual(result, todos)

    def test_filter_done(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        mark_done(todos, todos[0]["id"])
        result = _tui_build_display(todos, "done", "id", "")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], todos[0]["id"])

    def test_filter_pending(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        mark_done(todos, todos[0]["id"])
        result = _tui_build_display(todos, "pending", "id", "")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], todos[1]["id"])

    def test_search_query_match(self):
        todos = create_todo_list()
        add_item(todos, "Buy groceries")
        add_item(todos, "Read a book")
        result = _tui_build_display(todos, "all", "id", "groceries")
        self.assertEqual(len(result), 1)
        self.assertIn("groceries", result[0]["task"])

    def test_search_query_no_match(self):
        todos = create_todo_list()
        add_item(todos, "Buy groceries")
        result = _tui_build_display(todos, "all", "id", "nonexistent")
        self.assertEqual(result, [])

    def test_search_case_insensitive(self):
        todos = create_todo_list()
        add_item(todos, "Buy Groceries")
        result = _tui_build_display(todos, "all", "id", "groceries")
        self.assertEqual(len(result), 1)

    def test_sort_priority(self):
        todos = create_todo_list()
        add_item(todos, "Low", priority="low")
        add_item(todos, "High", priority="high")
        add_item(todos, "Medium", priority="medium")
        result = _tui_build_display(todos, "all", "priority", "")
        self.assertEqual(result[0]["task"], "High")
        self.assertEqual(result[1]["task"], "Medium")
        self.assertEqual(result[2]["task"], "Low")

    def test_sort_due(self):
        todos = create_todo_list()
        add_item(todos, "Later", due="2025-12-31")
        add_item(todos, "Earlier", due="2025-01-01")
        add_item(todos, "No due")
        result = _tui_build_display(todos, "all", "due", "")
        self.assertEqual(result[0]["task"], "Earlier")
        self.assertEqual(result[1]["task"], "Later")
        self.assertEqual(result[2]["task"], "No due")

    def test_sort_status(self):
        todos = create_todo_list()
        add_item(todos, "Pending")
        add_item(todos, "Done task")
        mark_done(todos, todos[1]["id"])
        result = _tui_build_display(todos, "all", "status", "")
        self.assertEqual(result[0]["task"], "Pending")
        self.assertEqual(result[1]["task"], "Done task")

    def test_sort_created(self):
        todos = create_todo_list()
        a = add_item(todos, "First")
        b = add_item(todos, "Second")
        result = _tui_build_display(todos, "all", "created", "")
        self.assertEqual(len(result), 2)
        self.assertIn(result[0]["task"], ("First", "Second"))
        self.assertIn(result[1]["task"], ("First", "Second"))

    def test_combined_filter_search_sort(self):
        todos = create_todo_list()
        add_item(todos, "Buy milk", priority="low")
        add_item(todos, "Buy eggs", priority="high")
        add_item(todos, "Read book", priority="medium")
        mark_done(todos, todos[0]["id"])
        result = _tui_build_display(todos, "pending", "priority", "buy")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["task"], "Buy eggs")


class TestTuiIsOverdue(unittest.TestCase):
    def test_not_overdue_no_due(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        self.assertFalse(_tui_is_overdue(todos[0]))

    def test_not_overdue_done_item(self):
        todos = create_todo_list()
        add_item(todos, "Task", due="2020-01-01")
        mark_done(todos, todos[0]["id"])
        self.assertFalse(_tui_is_overdue(todos[0]))

    def test_overdue_past_due(self):
        todos = create_todo_list()
        add_item(todos, "Task", due="2020-01-01")
        self.assertTrue(_tui_is_overdue(todos[0]))

    def test_not_overdue_future_due(self):
        todos = create_todo_list()
        add_item(todos, "Task", due="2099-12-31")
        self.assertFalse(_tui_is_overdue(todos[0]))


class TestTuiItemLine(unittest.TestCase):
    def test_basic_item(self):
        todos = create_todo_list()
        add_item(todos, "Test task")
        line, priority = _tui_item_line(todos[0])
        self.assertIn("Test task", line)
        self.assertIn("[ ]", line)
        self.assertIn("[M]", line)
        self.assertEqual(priority, "medium")

    def test_done_item(self):
        todos = create_todo_list()
        add_item(todos, "Done task")
        mark_done(todos, todos[0]["id"])
        line, priority = _tui_item_line(todos[0])
        self.assertIn("[x]", line)

    def test_high_priority(self):
        todos = create_todo_list()
        add_item(todos, "Urgent", priority="high")
        line, priority = _tui_item_line(todos[0])
        self.assertIn("[H]", line)
        self.assertEqual(priority, "high")

    def test_with_due(self):
        todos = create_todo_list()
        add_item(todos, "Task", due="2025-12-31")
        line, _ = _tui_item_line(todos[0])
        self.assertIn("due:", line)

    def test_with_tags(self):
        todos = create_todo_list()
        add_item(todos, "Task", tags="work,urgent")
        line, _ = _tui_item_line(todos[0])
        self.assertIn("{work,urgent}", line)


class TestTuiItemDetail(unittest.TestCase):
    def test_detail_shows_all_fields(self):
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (40, 80)
        todos = create_todo_list()
        add_item(todos, "Test task", priority="high", due="2025-12-31", tags="work")
        _tui_item_detail(mock_stdscr, todos[0])
        calls = [c[0] for c in mock_stdscr.addstr.call_args_list]
        all_text = " ".join(str(c) for c in calls)
        self.assertIn("Test task", all_text)
        self.assertIn("high", all_text)
        self.assertIn("2025-12-31", all_text)
        self.assertIn("work", all_text)

    def test_detail_shows_no_due_none_tags(self):
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (40, 80)
        todos = create_todo_list()
        add_item(todos, "Simple task")
        _tui_item_detail(mock_stdscr, todos[0])
        calls = [c[0] for c in mock_stdscr.addstr.call_args_list]
        all_text = " ".join(str(c) for c in calls)
        self.assertIn("None", all_text)


class TestTuiHelp(unittest.TestCase):
    def test_help_shows_all_sections(self):
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (40, 80)
        mock_stdscr.getch.return_value = ord("q")
        _tui_help(mock_stdscr)
        calls = [c[0] for c in mock_stdscr.addstr.call_args_list]
        all_text = " ".join(str(c) for c in calls)
        for keyword in ["Navigation", "Actions", "Display", "Mouse", "Space", "/", "u", "f", "s", "i", "h"]:
            self.assertIn(keyword, all_text)


class TestTuiUndo(unittest.TestCase):
    def test_undo_restores_previous_state(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        from todo import remove_item, _push_undo
        _push_undo(todos)
        remove_item(todos, todos[0]["id"])
        self.assertEqual(len(todos), 1)
        result = undo(todos)
        self.assertTrue(result)
        self.assertEqual(len(todos), 2)

    def test_undo_nothing_to_undo(self):
        _UNDO_STACKS.clear()
        todos = create_todo_list()
        result = undo(todos)
        self.assertFalse(result)

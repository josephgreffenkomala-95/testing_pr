import curses
import json
import os
import unittest
from datetime import datetime
from io import StringIO
from unittest.mock import patch

from todo import (
    create_todo_list,
    add_item,
    edit_item,
    mark_done,
    mark_undone,
    remove_item,
    clear_done,
    search_items,
    set_priority,
    set_due,
    set_tags,
    list_items,
    stats,
    export_todo_list,
    undo,
    save_todo_list,
    load_todo_list,
    run_tui,
)
import todo


class TestCreateTodoList(unittest.TestCase):
    def test_creates_empty_list(self):
        result = create_todo_list()
        self.assertEqual(result, [])

    def test_returns_new_list_each_time(self):
        first = create_todo_list()
        second = create_todo_list()
        self.assertIsNot(first, second)


class TestAddItem(unittest.TestCase):
    def test_add_item_to_empty_list(self):
        todos = create_todo_list()
        result = add_item(todos, "Buy groceries")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["task"], "Buy groceries")
        self.assertFalse(result[0]["done"])

    def test_add_multiple_items(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        self.assertEqual(len(todos), 2)
        self.assertEqual(todos[1]["task"], "Task 2")

    def test_add_duplicate_items(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        add_item(todos, "Task")
        self.assertEqual(len(todos), 2)

    def test_returns_same_list(self):
        todos = create_todo_list()
        result = add_item(todos, "Task")
        self.assertIs(result, todos)

    def test_strips_whitespace(self):
        todos = create_todo_list()
        add_item(todos, "  Task  ")
        self.assertEqual(todos[0]["task"], "Task")

    def test_rejects_empty_string(self):
        todos = create_todo_list()
        with self.assertRaises(ValueError):
            add_item(todos, "")

    def test_rejects_whitespace_only(self):
        todos = create_todo_list()
        with self.assertRaises(ValueError):
            add_item(todos, "   ")

    def test_rejects_too_long_string(self):
        todos = create_todo_list()
        with self.assertRaises(ValueError):
            add_item(todos, "x" * 201)

    def test_allows_max_length_string(self):
        todos = create_todo_list()
        add_item(todos, "x" * 200)
        self.assertEqual(len(todos), 1)

    def test_assigns_unique_ids(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        self.assertNotEqual(todos[0]["id"], todos[1]["id"])

    def test_default_priority_is_medium(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        self.assertEqual(todos[0]["priority"], "medium")

    def test_custom_priority(self):
        todos = create_todo_list()
        add_item(todos, "Task", priority="high")
        self.assertEqual(todos[0]["priority"], "high")

    def test_priority_case_insensitive(self):
        todos = create_todo_list()
        add_item(todos, "Task", priority="HIGH")
        self.assertEqual(todos[0]["priority"], "high")

    def test_invalid_priority(self):
        todos = create_todo_list()
        with self.assertRaises(ValueError):
            add_item(todos, "Task", priority="urgent")

    def test_due_date(self):
        todos = create_todo_list()
        add_item(todos, "Task", due="2025-12-31")
        self.assertEqual(todos[0]["due"], "2025-12-31")

    def test_invalid_due_date(self):
        todos = create_todo_list()
        with self.assertRaises(ValueError):
            add_item(todos, "Task", due="12-31-2025")

    def test_no_due_date_default(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        self.assertIsNone(todos[0]["due"])

    def test_created_at_populated(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        self.assertIn("created_at", todos[0])
        self.assertTrue(len(todos[0]["created_at"]) > 0)

    def test_tags_single(self):
        todos = create_todo_list()
        add_item(todos, "Task", tags="work")
        self.assertEqual(todos[0]["tags"], ["work"])

    def test_tags_multiple(self):
        todos = create_todo_list()
        add_item(todos, "Task", tags="work,urgent,home")
        self.assertEqual(todos[0]["tags"], ["work", "urgent", "home"])

    def test_tags_strips_whitespace_and_lowercases(self):
        todos = create_todo_list()
        add_item(todos, "Task", tags=" Work , URGENT ")
        self.assertEqual(todos[0]["tags"], ["work", "urgent"])

    def test_tags_max_five(self):
        todos = create_todo_list()
        with self.assertRaises(ValueError):
            add_item(todos, "Task", tags="a,b,c,d,e,f")

    def test_tags_empty_string_default(self):
        todos = create_todo_list()
        add_item(todos, "Task", tags="")
        self.assertEqual(todos[0]["tags"], [])

    def test_no_tags_default(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        self.assertEqual(todos[0]["tags"], [])


class TestEditItem(unittest.TestCase):
    def test_edit_existing_item(self):
        todos = create_todo_list()
        add_item(todos, "Old task")
        result = edit_item(todos, todos[0]["id"], "New task")
        self.assertTrue(result)
        self.assertEqual(todos[0]["task"], "New task")

    def test_edit_nonexistent_item(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        result = edit_item(todos, 9999, "New task")
        self.assertFalse(result)

    def test_edit_strips_whitespace(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        edit_item(todos, todos[0]["id"], "  Updated  ")
        self.assertEqual(todos[0]["task"], "Updated")

    def test_edit_rejects_empty(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        with self.assertRaises(ValueError):
            edit_item(todos, todos[0]["id"], "")

    def test_edit_rejects_too_long_string(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        with self.assertRaises(ValueError):
            edit_item(todos, todos[0]["id"], "x" * 201)

    def test_edit_allows_max_length_string(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        result = edit_item(todos, todos[0]["id"], "x" * 200)
        self.assertTrue(result)
        self.assertEqual(todos[0]["task"], "x" * 200)


class TestSetPriority(unittest.TestCase):
    def test_set_priority_valid(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        result = set_priority(todos, todos[0]["id"], "high")
        self.assertTrue(result)
        self.assertEqual(todos[0]["priority"], "high")

    def test_set_priority_case_insensitive(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        result = set_priority(todos, todos[0]["id"], "HIGH")
        self.assertTrue(result)
        self.assertEqual(todos[0]["priority"], "high")

    def test_set_priority_invalid(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        with self.assertRaises(ValueError):
            set_priority(todos, todos[0]["id"], "urgent")

    def test_set_priority_nonexistent(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        result = set_priority(todos, 9999, "high")
        self.assertFalse(result)


class TestSetDue(unittest.TestCase):
    def test_set_due_date(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        result = set_due(todos, todos[0]["id"], "2025-12-31")
        self.assertTrue(result)
        self.assertEqual(todos[0]["due"], "2025-12-31")

    def test_clear_due_date(self):
        todos = create_todo_list()
        add_item(todos, "Task", due="2025-12-31")
        result = set_due(todos, todos[0]["id"], None)
        self.assertTrue(result)
        self.assertIsNone(todos[0]["due"])

    def test_set_due_invalid_format(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        with self.assertRaises(ValueError):
            set_due(todos, todos[0]["id"], "12-31-2025")

    def test_set_due_nonexistent(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        result = set_due(todos, 9999, "2025-12-31")
        self.assertFalse(result)


class TestSetTags(unittest.TestCase):
    def test_set_tags(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        result = set_tags(todos, todos[0]["id"], "work,urgent")
        self.assertTrue(result)
        self.assertEqual(todos[0]["tags"], ["work", "urgent"])

    def test_set_tags_exceeds_max(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        with self.assertRaises(ValueError):
            set_tags(todos, todos[0]["id"], "a,b,c,d,e,f")

    def test_set_tags_nonexistent(self):
        todos = create_todo_list()
        add_item(todos, "Task")
        result = set_tags(todos, 9999, "work")
        self.assertFalse(result)


class TestMarkDone(unittest.TestCase):
    def test_mark_valid_id(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        item_id = todos[0]["id"]
        result = mark_done(todos, item_id)
        self.assertTrue(todos[0]["done"])
        self.assertTrue(result)

    def test_mark_invalid_id(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        result = mark_done(todos, 9999)
        self.assertFalse(result)

    def test_mark_done_empty_list(self):
        todos = create_todo_list()
        result = mark_done(todos, 0)
        self.assertFalse(result)


class TestMarkUndone(unittest.TestCase):
    def test_mark_undone_valid_id(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        mark_done(todos, todos[0]["id"])
        result = mark_undone(todos, todos[0]["id"])
        self.assertTrue(result)
        self.assertFalse(todos[0]["done"])

    def test_mark_undone_invalid_id(self):
        todos = create_todo_list()
        result = mark_undone(todos, 9999)
        self.assertFalse(result)

    def test_mark_undone_already_pending(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        result = mark_undone(todos, todos[0]["id"])
        self.assertTrue(result)
        self.assertFalse(todos[0]["done"])


class TestListItems(unittest.TestCase):
    def test_list_empty(self):
        todos = create_todo_list()
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            list_items(todos, color=False)
        self.assertEqual(mock_stdout.getvalue().strip(), "No items in the to-do list.")

    def test_list_with_items(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            list_items(todos, color=False)
        output = mock_stdout.getvalue()
        self.assertIn("Task 1", output)
        self.assertIn("Task 2", output)

    def test_list_with_done_item(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        mark_done(todos, todos[0]["id"])
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            list_items(todos, color=False)
        self.assertIn("[x]", mock_stdout.getvalue())

    def test_list_filter_done(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        mark_done(todos, todos[0]["id"])
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            list_items(todos, filter_by="done", color=False)
        output = mock_stdout.getvalue()
        self.assertIn("Task 1", output)
        self.assertNotIn("Task 2", output)

    def test_list_filter_pending(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        mark_done(todos, todos[0]["id"])
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            list_items(todos, filter_by="pending", color=False)
        output = mock_stdout.getvalue()
        self.assertNotIn("Task 1", output)
        self.assertIn("Task 2", output)

    def test_list_sort_by_priority(self):
        todos = create_todo_list()
        add_item(todos, "Low task", priority="low")
        add_item(todos, "High task", priority="high")
        add_item(todos, "Med task", priority="medium")
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            list_items(todos, sort_by="priority", color=False)
        output = mock_stdout.getvalue()
        high_pos = output.find("High task")
        med_pos = output.find("Med task")
        low_pos = output.find("Low task")
        self.assertLess(high_pos, med_pos)
        self.assertLess(med_pos, low_pos)

    def test_list_filter_no_match(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            list_items(todos, filter_by="done", color=False)
        self.assertIn("No matching", mock_stdout.getvalue())

    def test_list_shows_priority(self):
        todos = create_todo_list()
        add_item(todos, "Task", priority="high")
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            list_items(todos, color=False)
        self.assertIn("[H]", mock_stdout.getvalue())

    def test_list_shows_due_date(self):
        todos = create_todo_list()
        add_item(todos, "Task", due="2025-12-31")
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            list_items(todos, color=False)
        self.assertIn("due: 2025-12-31", mock_stdout.getvalue())

    def test_list_tag_filter(self):
        todos = create_todo_list()
        add_item(todos, "Work task", tags="work,meeting")
        add_item(todos, "Home task", tags="home")
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            list_items(todos, tag_filter="work", color=False)
        output = mock_stdout.getvalue()
        self.assertIn("Work task", output)
        self.assertNotIn("Home task", output)

    def test_list_shows_tags(self):
        todos = create_todo_list()
        add_item(todos, "Task", tags="work,urgent")
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            list_items(todos, color=False)
        output = mock_stdout.getvalue()
        self.assertIn("{work,urgent}", output)


class TestRemoveItem(unittest.TestCase):
    def test_remove_valid_id(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        item_id = todos[0]["id"]
        result = remove_item(todos, item_id)
        self.assertEqual(len(todos), 1)
        self.assertEqual(todos[0]["task"], "Task 2")
        self.assertTrue(result)

    def test_remove_invalid_id(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        result = remove_item(todos, 9999)
        self.assertEqual(len(todos), 1)
        self.assertFalse(result)

    def test_remove_from_empty_list(self):
        todos = create_todo_list()
        result = remove_item(todos, 0)
        self.assertFalse(result)

    def test_ids_stable_after_removal(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        second_id = todos[1]["id"]
        remove_item(todos, todos[0]["id"])
        self.assertEqual(todos[0]["id"], second_id)


class TestClearDone(unittest.TestCase):
    def test_clear_done_removes_completed(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        add_item(todos, "Task 3")
        mark_done(todos, todos[0]["id"])
        mark_done(todos, todos[1]["id"])
        count = clear_done(todos)
        self.assertEqual(count, 2)
        self.assertEqual(len(todos), 1)
        self.assertFalse(todos[0]["done"])

    def test_clear_done_no_completed(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        count = clear_done(todos)
        self.assertEqual(count, 0)
        self.assertEqual(len(todos), 1)

    def test_clear_done_empty_list(self):
        todos = create_todo_list()
        count = clear_done(todos)
        self.assertEqual(count, 0)


class TestSearchItems(unittest.TestCase):
    def test_search_finds_match(self):
        todos = create_todo_list()
        add_item(todos, "Buy groceries")
        add_item(todos, "Clean house")
        results = search_items(todos, "groceries")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["task"], "Buy groceries")

    def test_search_case_insensitive(self):
        todos = create_todo_list()
        add_item(todos, "Buy Groceries")
        results = search_items(todos, "groceries")
        self.assertEqual(len(results), 1)

    def test_search_no_match(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        results = search_items(todos, "nonexistent")
        self.assertEqual(len(results), 0)

    def test_search_multiple_matches(self):
        todos = create_todo_list()
        add_item(todos, "Buy groceries")
        add_item(todos, "Buy milk")
        add_item(todos, "Clean house")
        results = search_items(todos, "buy")
        self.assertEqual(len(results), 2)

    def test_search_by_tag(self):
        todos = create_todo_list()
        add_item(todos, "Meeting", tags="work,meeting")
        add_item(todos, "Groceries", tags="home")
        results = search_items(todos, "work", search_tags=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["task"], "Meeting")

    def test_search_tags_false_by_default(self):
        todos = create_todo_list()
        add_item(todos, "Meeting", tags="work")
        results = search_items(todos, "work", search_tags=False)
        self.assertEqual(len(results), 0)


class TestStats(unittest.TestCase):
    def test_stats_output(self):
        todos = create_todo_list()
        add_item(todos, "Task 1", priority="high")
        add_item(todos, "Task 2")
        mark_done(todos, todos[0]["id"])
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            stats(todos)
        output = mock_stdout.getvalue()
        self.assertIn("Total:    2", output)
        self.assertIn("Done:", output)
        self.assertIn("Pending:", output)

    def test_stats_empty(self):
        todos = create_todo_list()
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            stats(todos)
        output = mock_stdout.getvalue()
        self.assertIn("Total:    0", output)

    def test_stats_shows_tags(self):
        todos = create_todo_list()
        add_item(todos, "Task 1", tags="work")
        add_item(todos, "Task 2", tags="work,home")
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            stats(todos)
        output = mock_stdout.getvalue()
        self.assertIn("Tags:", output)
        self.assertIn("work", output)


class TestUndo(unittest.TestCase):
    def setUp(self):
        import todo
        todo._UNDO_STACKS.clear()

    def test_undo_reverts_add(self):
        from todo import _push_undo
        todos = create_todo_list()
        add_item(todos, "Task 1")
        _push_undo(todos)
        add_item(todos, "Task 2")
        self.assertEqual(len(todos), 2)
        result = undo(todos)
        self.assertTrue(result)
        self.assertEqual(len(todos), 1)
        self.assertEqual(todos[0]["task"], "Task 1")

    def test_undo_nothing_to_undo(self):
        todos = create_todo_list()
        result = undo(todos)
        self.assertFalse(result)


class TestExport(unittest.TestCase):
    def setUp(self):
        self.test_file = "test_export.csv"
        self.test_txt = "test_export.txt"
        self.test_json = "test_export.json"

    def tearDown(self):
        for f in [self.test_file, self.test_txt, self.test_json]:
            if os.path.exists(f):
                os.remove(f)

    def test_export_csv(self):
        todos = create_todo_list()
        add_item(todos, "Task 1", priority="high", tags="work")
        export_todo_list(todos, self.test_file, fmt="csv")
        self.assertTrue(os.path.exists(self.test_file))
        with open(self.test_file, "r") as f:
            content = f.read()
        self.assertIn("task", content)
        self.assertIn("Task 1", content)

    def test_export_txt(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        export_todo_list(todos, self.test_txt, fmt="txt")
        self.assertTrue(os.path.exists(self.test_txt))
        with open(self.test_txt, "r") as f:
            content = f.read()
        self.assertIn("Task 1", content)

    def test_export_json(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        export_todo_list(todos, self.test_json, fmt="json")
        self.assertTrue(os.path.exists(self.test_json))
        with open(self.test_json, "r") as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["task"], "Task 1")

    def test_export_invalid_format(self):
        todos = create_todo_list()
        with self.assertRaises(ValueError):
            export_todo_list(todos, "output.xyz", fmt="xyz")


class TestPersistence(unittest.TestCase):
    def setUp(self):
        self.test_file = "test_todos.json"
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_save_and_load(self):
        import todo
        todo._next_id = 0
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        save_todo_list(todos, self.test_file)

        loaded = load_todo_list(self.test_file)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["task"], "Task 1")
        self.assertEqual(loaded[1]["task"], "Task 2")

    def test_load_nonexistent_file(self):
        loaded = load_todo_list(self.test_file)
        self.assertEqual(loaded, [])

    def test_load_preserves_ids(self):
        import todo
        todo._next_id = 0
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        save_todo_list(todos, self.test_file)

        loaded = load_todo_list(self.test_file)
        self.assertEqual(loaded[0]["id"], 0)
        self.assertEqual(loaded[1]["id"], 1)

    def test_save_and_load_priority(self):
        import todo
        todo._next_id = 0
        todos = create_todo_list()
        add_item(todos, "Task", priority="high")
        save_todo_list(todos, self.test_file)

        loaded = load_todo_list(self.test_file)
        self.assertEqual(loaded[0]["priority"], "high")

    def test_save_and_load_due_date(self):
        import todo
        todo._next_id = 0
        todos = create_todo_list()
        add_item(todos, "Task", due="2025-12-31")
        save_todo_list(todos, self.test_file)

        loaded = load_todo_list(self.test_file)
        self.assertEqual(loaded[0]["due"], "2025-12-31")

    def test_save_and_load_done_status(self):
        import todo
        todo._next_id = 0
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        mark_done(todos, todos[0]["id"])
        save_todo_list(todos, self.test_file)

        loaded = load_todo_list(self.test_file)
        self.assertTrue(loaded[0]["done"])
        self.assertFalse(loaded[1]["done"])

    def test_save_and_load_tags(self):
        import todo
        todo._next_id = 0
        todos = create_todo_list()
        add_item(todos, "Task", tags="work,urgent")
        save_todo_list(todos, self.test_file)

        loaded = load_todo_list(self.test_file)
        self.assertEqual(loaded[0]["tags"], ["work", "urgent"])

    def test_load_skips_items_missing_required_keys(self):
        with open(self.test_file, "w") as f:
            json.dump([
                {"id": 0, "task": "Valid task", "done": False},
                {"id": 1, "task": "Missing done"},
                {"task": "Missing id and done"},
                "not a dict",
            ], f)
        loaded = load_todo_list(self.test_file)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["task"], "Valid task")

    def test_load_defaults_missing_optional_fields(self):
        with open(self.test_file, "w") as f:
            json.dump([
                {"id": 0, "task": "Old task", "done": False}
            ], f)
        loaded = load_todo_list(self.test_file)
        self.assertEqual(loaded[0]["priority"], "medium")
        self.assertIsNone(loaded[0]["due"])
        self.assertEqual(loaded[0]["created_at"], "")
        self.assertEqual(loaded[0]["tags"], [])


class FakeScreen:
    def __init__(self, keys):
        self._keys = list(keys)
        self.added = []
        self.keypad_enabled = False

    def clear(self):
        pass

    def getmaxyx(self):
        return (20, 80)

    def addstr(self, *args):
        self.added.append(args)

    def refresh(self):
        pass

    def keypad(self, enabled):
        self.keypad_enabled = enabled

    def getch(self):
        if self._keys:
            return self._keys.pop(0)
        return ord("q")


class TestTui(unittest.TestCase):
    def test_run_tui_uses_curses_wrapper(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")

        with patch("todo.curses.wrapper", autospec=True) as mock_wrapper:
            mock_wrapper.return_value = True
            result = run_tui(todos)

        mock_wrapper.assert_called_once()
        self.assertTrue(result)

    def test_tui_main_toggles_selected_item(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        screen = FakeScreen([ord(" "), ord("q")])

        with patch("todo.curses.curs_set", return_value=None), patch("todo.curses.mousemask", return_value=0):
            changed = todo._tui_main(screen, todos)

        self.assertTrue(changed)
        self.assertTrue(todos[0]["done"])

    def test_tui_main_removes_selected_item(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        screen = FakeScreen([ord("x"), ord("q")])

        with patch("todo.curses.curs_set", return_value=None), patch("todo.curses.mousemask", return_value=0):
            changed = todo._tui_main(screen, todos)

        self.assertTrue(changed)
        self.assertEqual(len(todos), 1)
        self.assertEqual(todos[0]["task"], "Task 2")

    def test_tui_main_adds_item_from_prompt(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        screen = FakeScreen([ord("a"), ord("N"), ord("e"), ord("w"), 10, ord("q")])

        with patch("todo.curses.curs_set", return_value=None), patch("todo.curses.mousemask", return_value=0):
            changed = todo._tui_main(screen, todos)

        self.assertTrue(changed)
        self.assertEqual(len(todos), 2)
        self.assertEqual(todos[1]["task"], "New")

    def test_tui_main_uses_mouse_for_selection_and_toggle(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        screen = FakeScreen([curses.KEY_MOUSE, curses.KEY_MOUSE, ord("q")])

        mouse_event = (0, 0, 5, 0, curses.BUTTON1_CLICKED)

        with patch("todo.curses.curs_set", return_value=None), patch("todo.curses.mousemask", return_value=0), patch(
            "todo.curses.getmouse", side_effect=[mouse_event, mouse_event]
        ):
            changed = todo._tui_main(screen, todos)

        self.assertTrue(changed)
        self.assertTrue(todos[1]["done"])

    def test_tui_main_uses_mouse_for_removal(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        screen = FakeScreen([curses.KEY_MOUSE, ord("q")])

        mouse_event = (0, 0, 4, 0, curses.BUTTON3_CLICKED)

        with patch("todo.curses.curs_set", return_value=None), patch("todo.curses.mousemask", return_value=0), patch(
            "todo.curses.getmouse", return_value=mouse_event
        ):
            changed = todo._tui_main(screen, todos)

        self.assertTrue(changed)
        self.assertEqual(len(todos), 1)
        self.assertEqual(todos[0]["task"], "Task 2")

    def test_tui_render_shows_header_and_empty_state(self):
        screen = FakeScreen([])

        todo._tui_render(screen, [], 0, message="Saved.")

        rendered_text = [args[2] for args in screen.added if len(args) >= 3]
        self.assertTrue(any("TODO LIST" in text for text in rendered_text))
        self.assertTrue(any("Saved." in text for text in rendered_text))
        self.assertTrue(any("No items yet" in text for text in rendered_text))

    def test_tui_render_highlights_selected_item(self):
        todos = create_todo_list()
        add_item(todos, "Task 1", due="2025-12-31", tags="work")
        screen = FakeScreen([])

        todo._tui_render(screen, todos, 0)

        self.assertTrue(any(len(args) >= 4 and args[3] == curses.A_REVERSE for args in screen.added))
        self.assertTrue(any(len(args) >= 3 and args[2].startswith("> ") for args in screen.added))


if __name__ == "__main__":
    unittest.main()

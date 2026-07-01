import json
import os
import unittest
from io import StringIO
from unittest.mock import patch

from todo import (
    create_todo_list,
    add_item,
    mark_done,
    list_items,
    remove_item,
    save_todo_list,
    load_todo_list,
)


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


class TestListItems(unittest.TestCase):
    def test_list_empty(self):
        todos = create_todo_list()
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            list_items(todos)
        self.assertEqual(mock_stdout.getvalue().strip(), "No items in the to-do list.")

    def test_list_with_items(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            list_items(todos)
        output = mock_stdout.getvalue()
        self.assertIn("Task 1", output)
        self.assertIn("Task 2", output)

    def test_list_with_done_item(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        item_id = todos[0]["id"]
        mark_done(todos, item_id)
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            list_items(todos)
        self.assertIn("[x]", mock_stdout.getvalue())


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


if __name__ == "__main__":
    unittest.main()
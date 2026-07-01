import unittest
from io import StringIO
from unittest.mock import patch

from todo import (
    create_todo_list,
    add_item,
    mark_done,
    list_items,
    remove_item,
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


class TestMarkDone(unittest.TestCase):
    def test_mark_valid_index(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        result = mark_done(todos, 0)
        self.assertTrue(todos[0]["done"])
        self.assertTrue(result)

    def test_mark_invalid_index_negative(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        result = mark_done(todos, -1)
        self.assertFalse(todos[0]["done"])
        self.assertFalse(result)

    def test_mark_invalid_index_out_of_bounds(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        result = mark_done(todos, 5)
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
        mark_done(todos, 0)
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            list_items(todos)
        self.assertIn("[x]", mock_stdout.getvalue())


class TestRemoveItem(unittest.TestCase):
    def test_remove_valid_index(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        add_item(todos, "Task 2")
        result = remove_item(todos, 0)
        self.assertEqual(len(todos), 1)
        self.assertEqual(todos[0]["task"], "Task 2")
        self.assertTrue(result)

    def test_remove_invalid_index(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        result = remove_item(todos, 5)
        self.assertEqual(len(todos), 1)
        self.assertFalse(result)

    def test_remove_negative_index(self):
        todos = create_todo_list()
        add_item(todos, "Task 1")
        result = remove_item(todos, -1)
        self.assertFalse(result)

    def test_remove_from_empty_list(self):
        todos = create_todo_list()
        result = remove_item(todos, 0)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
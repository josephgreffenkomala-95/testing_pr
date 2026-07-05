import pytest
from textual import testing

from todo import create_todo_list, add_item
from todo.tui import TodoApp


@pytest.mark.asyncio
async def test_app_empty_snapshot():
    todos = create_todo_list()
    app = TodoApp(todos)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.screen._update_timer.reset()
        await pilot.pause()


@pytest.mark.asyncio
async def test_app_with_tasks_snapshot():
    todos = create_todo_list()
    add_item(todos, "Buy groceries", priority="high")
    add_item(todos, "Clean house", priority="medium")
    add_item(todos, "Read book", priority="low", tags="personal")
    app = TodoApp(todos)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.screen._update_timer.reset()
        await pilot.pause()


@pytest.mark.asyncio
async def test_app_help_screen_snapshot():
    todos = create_todo_list()
    app = TodoApp(todos)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.press("h")
        await pilot.pause()

import sys
import types

import curses

from . import models
from .models import (
    TodoList,
    _DEFAULT_FILE,
    _UNDO_STACKS,
    _UNDO_MAX,
    _VALID_PRIORITIES,
    _PRIORITY_ORDER,
    _ANSI_RESET,
    _ANSI_RED,
    _ANSI_YELLOW,
    _ANSI_GREEN,
    _ANSI_CYAN,
    _ANSI_BOLD,
    _ANSI_DIM,
    _ANSI_MAGENTA,
    _DEFAULT_CONFIG,
    _cached_config,
    _load_config,
    _get_undo_stack,
    _push_undo,
    undo,
)

from .core import (
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
)

from .io import save_todo_list, load_todo_list, export_todo_list

from .tui import (
    _tui_item_line,
    _tui_color_pair,
    _tui_addstr,
    _tui_is_overdue,
    _tui_render,
    _tui_prompt,
    _tui_handle_mouse,
    _tui_help,
    _tui_item_detail,
    _tui_build_display,
    _tui_main,
    run_tui,
)

from .cli import main


class _Module(types.ModuleType):
    @property
    def _next_id(self):
        return models._next_id

    @_next_id.setter
    def _next_id(self, value):
        models._next_id = value


sys.modules[__name__].__class__ = _Module

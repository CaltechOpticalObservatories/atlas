# Third-Party Library Imports
from PyQt5.QtWidgets import QStyle, QToolBar
from PyQt5.QtCore import Qt

from .registry import Tool, register


@register("save_button")
class SaveButtonTool(Tool):
    """
    Puts File → Save Frame on a toolbar, for stations where saving the
    live frame is the main thing anyone does and a menu is one step too far.
    """

    def __init__(self, window, settings):
        super().__init__(window, settings)
        self.toolbar = None

    def build(self):
        self.toolbar = QToolBar("Save", self.window)
        self.toolbar.setObjectName("save_toolbar")
        self.toolbar.setMovable(False)
        # Text alone on a toolbar reads as a label, not something to click.
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.window.save_action.setIcon(
            self.window.style().standardIcon(QStyle.SP_DialogSaveButton))
        # The menu's own action rather than a copy: the button then shares its
        # shortcut and its greying out with no frame, with nothing to keep in
        # step.
        self.toolbar.addAction(self.window.save_action)
        self.window.addToolBar(self.toolbar)

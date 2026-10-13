# Third-Party Library Imports
from PyQt5.QtWidgets import QLabel, QSpinBox, QStyle, QToolBar
from PyQt5.QtCore import Qt

from .registry import Tool, register

# Every frame of a capture is held in memory until it is written.
MAX_SAVE_FRAMES = 1000


@register("save_button")
class SaveButtonTool(Tool):
    """
    Puts File → Save Frame on a toolbar, for stations where saving the
    live frame is the main thing anyone does and a menu is one step too far.

    With shared memory on, a Frames box beside it sets how many frames each
    save takes: one saves the frame on screen, more saves that many frames
    straight off the stream into a single cube.
    """

    def __init__(self, window, settings):
        super().__init__(window, settings)
        self.toolbar = None
        self.count = None

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

        # Several frames can only come from a live stream.
        if self.window.config.tools.shm.enabled:
            self.count = QSpinBox()
            self.count.setRange(1, MAX_SAVE_FRAMES)
            self.count.setToolTip("How many frames each save takes. More than one "
                                  "saves the next frames off the stream as one cube.")
            self.toolbar.addWidget(QLabel(" Frames: "))
            self.toolbar.addWidget(self.count)
            # With a count on screen, Ctrl+S and the menu have to honour it as
            # much as the button does, so the shared action comes here first.
            self.window.save_action.triggered.disconnect()
            self.window.save_action.triggered.connect(self.save)

        self.window.addToolBar(self.toolbar)

    def save(self):
        """Saves as many frames as the Frames box says."""
        count = self.count.value()
        if count == 1:
            self.window.save_current_frame()
            return
        # Looked up now: tools are all built before anyone can press anything.
        self.window.tools["shm"].save_next_frames(count)

# Third-Party Library Imports
from PyQt5.QtWidgets import QLabel, QSpinBox, QStyle, QToolBar
from PyQt5.QtCore import Qt

from .registry import Tool, register


@register("save_button")
class SaveButtonTool(Tool):
    """
    Puts File → Save Frame on a toolbar, for stations where saving the
    live frame is the main thing anyone does and a menu is one step too far.

    With shared memory on, a Frames box beside it sets how many frames each
    save takes: one saves the frame on screen, more saves that many frames
    straight off the stream into a single cube. Every one of those frames is
    held in memory until written, so the box goes only as high as the free
    memory allows for the segment's frame size. Until a segment is found that
    size is unknown, and the box stays at 1.
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
            self.count.setRange(1, 1)
            # Thousands run long enough to want the separators.
            self.count.setGroupSeparatorShown(True)
            self.set_frame_limit(1, "Connect to shared memory to save several frames")
            self.toolbar.addWidget(QLabel(" Frames: "))
            self.toolbar.addWidget(self.count)
            # With a count on screen, Ctrl+S and the menu have to honour it as
            # much as the button does, so the shared action comes here first.
            self.window.save_action.triggered.disconnect()
            self.window.save_action.triggered.connect(self.save)

        self.window.addToolBar(self.toolbar)

    def set_frame_limit(self, limit, reason):
        """Lets the Frames box go up to `limit`, saying why it stops there."""
        # QSpinBox holds an int32; a machine with that much room for frames
        # this small has no practical limit anyway.
        self.count.setMaximum(min(limit, 2 ** 31 - 1))
        self.count.setToolTip(
            "How many frames each save takes. More than one saves the next frames "
            f"off the stream as one cube.\n{reason}.")

    def save(self):
        """Saves as many frames as the Frames box says."""
        count = self.count.value()
        if count == 1:
            self.window.save_current_frame()
            return
        # Looked up now: tools are all built before anyone can press anything.
        self.window.tools["shm"].save_next_frames(count)

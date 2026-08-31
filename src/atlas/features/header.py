# Third-Party Library Imports
from PyQt5.QtWidgets import QDockWidget, QTextEdit
from PyQt5.QtCore import Qt

from .registry import Tool, register


@register("header")
class HeaderTool(Tool):
    """A dock panel showing the FITS header of whichever frame is current."""

    def __init__(self, window, settings):
        super().__init__(window, settings)
        self.text = None
        self.dock = None

    def build(self):
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QTextEdit.NoWrap)
        self.text.setFontFamily("Menlo")

        self.dock = QDockWidget("Header", self.window)
        self.dock.setWidget(self.text)
        self.dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.window.addDockWidget(Qt.RightDockWidgetArea, self.dock)

        # QDockWidget supplies a ready-made show/hide action for the View menu.
        self.window.view_menu.addSeparator()
        self.window.view_menu.addAction(self.dock.toggleViewAction())

        self.view_model.current_changed.connect(self.refresh)
        self.view_model.frames_changed.connect(self.refresh)
        self.refresh()

    def refresh(self, *_):
        """Shows the current frame's header."""
        frame = self.view_model.current_frame
        if frame is None or frame.header is None:
            self.text.setPlainText("No frame selected.")
            return

        # str(card) gives the raw 80-column FITS card image, which is what a
        # header view should show; repr() would render a Python tuple. Going
        # card by card also preserves repeated keywords (COMMENT, HISTORY) and
        # blank cards, which indexing by keyword would collapse.
        self.text.setPlainText(
            "\n".join(str(card).rstrip() for card in frame.header.cards))

# Third-Party Library Imports
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap


class FrameWidget(QWidget):
    """
    Shows one frame: a caption above an aspect-preserving image.

    The image is always rescaled from the frame's original pixmap rather than
    from the previously scaled one, so repeated resizing does not compound
    quality loss.
    """

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frame = None
        self.is_current = False

        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        self.setLayout(layout)

        self.caption = QLabel()
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        font = self.caption.font()
        font.setBold(True)
        self.caption.setFont(font)

        self.image = QLabel()
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setMinimumSize(1, 1)
        # Ignored, not Expanding: a QLabel reports its pixmap size as its
        # sizeHint, so a large image would otherwise drive the layout and let
        # one frame squeeze its neighbours out of the grid.
        self.image.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image.setMouseTracking(True)

        layout.addWidget(self.caption)
        layout.addWidget(self.image)
        self.apply_border()

    def set_frame(self, frame):
        """Binds this widget to a frame, or clears it when given None."""
        self.frame = frame
        if frame is None:
            self.caption.setText("")
            self.image.setPixmap(QPixmap())
            return

        self.caption.setText(frame.label)
        self.rescale()

    def set_current(self, is_current):
        """Marks this frame as the current one."""
        if is_current != self.is_current:
            self.is_current = is_current
            self.apply_border()

    def apply_border(self):
        """Draws a highlight around the current frame."""
        colour = "#4a90d9" if self.is_current else "transparent"
        self.setStyleSheet(f"QWidget {{ border: 2px solid {colour}; }}"
                           "QLabel { border: none; }")

    def rescale(self):
        """Fits the frame's pixmap to the space currently available."""
        if self.frame is None or self.frame.pixmap is None:
            return

        target = self.image.size()
        if target.width() <= 0 or target.height() <= 0:
            return

        self.image.setPixmap(self.frame.pixmap.scaled(
            target, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):  # pylint: disable=invalid-name
        """Qt override: keep the image fitted as the widget changes size."""
        super().resizeEvent(event)
        self.rescale()

    def mousePressEvent(self, event):  # pylint: disable=invalid-name
        """Qt override: clicking a frame makes it current."""
        super().mousePressEvent(event)
        self.clicked.emit()

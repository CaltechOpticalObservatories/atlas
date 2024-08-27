# -----------------------------------------------------------------------------
# @file     fits_viewer_ui.py
# @brief    A dialog window for displaying and selecting between different image views. 
# @author   Prakriti Gupta <pgupta@astro.caltech.edu>
# -----------------------------------------------------------------------------

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QSize

class ViewfinderPopup(QDialog):
    """
    A popup window for viewing a selected region of an image.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Viewfinder")
        self.setModal(False)
        self.setFixedSize(300, 300)  # Adjust size as needed

        # Create layout and widgets
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.image_label = QLabel()
        self.layout.addWidget(self.image_label)

        self.image_selector = QComboBox()
        self.image_selector.addItem("Image 1")
        self.image_selector.addItem("Image 2")
        self.image_selector.addItem("Result")
        self.image_selector.currentIndexChanged.connect(self.update_image_display)
        self.layout.addWidget(self.image_selector)

        self.current_pixmap = None
        self.image_dict = {}

    def set_pixmaps(self, image1_pixmap: QPixmap, image2_pixmap: QPixmap, result_pixmap: QPixmap):
        """
        Set the pixmaps for the different images.
        """
        self.image_dict = {
            "Image 1": image1_pixmap,
            "Image 2": image2_pixmap,
            "Result": result_pixmap
        }
        self.update_image_display()  # Update display with the first image

    def update_image_display(self):
        """
        Update the displayed image based on the selected image.
        """
        selected_image = self.image_selector.currentText()
        if selected_image in self.image_dict:
            self.current_pixmap = self.image_dict[selected_image]
            self.image_label.setPixmap(self.current_pixmap)
            self.image_label.setScaledContents(True)  # Scale image to fit label

            # Resize label based on the image size
            if self.current_pixmap:
                self.image_label.resize(self.current_pixmap.size())
        else:
            self.image_label.clear()

    def set_image(self, pixmap: QPixmap):
        """
        Set a single image for the viewfinder.
        """
        self.current_pixmap = pixmap
        self.image_label.setPixmap(self.current_pixmap)
        self.image_label.setScaledContents(True)

        # Resize label based on the image size
        if self.current_pixmap:
            self.image_label.resize(self.current_pixmap.size())

# -----------------------------------------------------------------------------
# @file     fits_viewer.py
# @brief    The FITSViewer app allows users to open and view FITS files.
# @author   Prakriti Gupta <pgupta@astro.caltech.edu>
# -----------------------------------------------------------------------------

# pylint
# pylint: disable=line-too-long

# Standard Library Imports
import os
import sys

# Third-Party Library Imports
import numpy as np
from astropy.io import  fits
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, QSlider, QTextEdit, QMessageBox
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt, QSize

class FITSViewer(QMainWindow):
    """
    A PyQt5-based GUI application for viewing FITS images.
    """
    def __init__(self):
        super().__init__()

        # Initialize
        self.image_data = None
        self.original_image = None
        self.image_paths = []
        self.current_image_index = 0

        # Set up the UI
        self.setup_ui()

        # Initialize header_info
        self.header_info = None 

    def setup_ui(self):
        """
        Sets up the user interface of the FITSViewer.
        """
        # Set up the window
        self.setWindowTitle("FITS Image Viewer")
        self.setGeometry(100, 100, 1000, 1000)  # Default size

        # Set up the central widget and layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout()
        self.central_widget.setLayout(self.main_layout)

        # Create a horizontal layout for the buttons
        self.button_layout = QHBoxLayout()

        # Create and add buttons to the horizontal layout
        self.open_file_button = QPushButton("Open FITS Image")
        self.open_file_button.clicked.connect(self.open_fits_image)
        self.button_layout.addWidget(self.open_file_button)

        self.open_directory_button = QPushButton("Open Directory of FITS Images")
        self.open_directory_button.clicked.connect(self.open_fits_directory)
        self.button_layout.addWidget(self.open_directory_button)

        # Add the button layout to the main layout
        self.main_layout.addLayout(self.button_layout)

        # Create and add the image label and slider
        self.image_label = QLabel()
        self.main_layout.addWidget(self.image_label)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(100)
        self.slider.setValue(50)  # Default value for contrast
        self.slider.setTickInterval(10)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.valueChanged.connect(self.adjust_contrast)
        self.main_layout.addWidget(self.slider)

        # Create and add the FITS header button and text area
        self.header_button = QPushButton("View FITS Header")
        self.header_button.clicked.connect(self.show_fits_header)
        self.button_layout.addWidget(self.header_button)

        self.header_text_area = QTextEdit()
        self.header_text_area.setReadOnly(True)
        self.main_layout.addWidget(self.header_text_area)

    def open_fits_image(self):
        """
        Opens a file dialog to select a single FITS file and displays it.
        """
        # Open a file dialog to select a FITS file
        # NOTE: Ignores the filter type since we are not actively using it
        file_name, _ = QFileDialog.getOpenFileName(self, "Open FITS File", "", "FITS Files (*.fits)")
        if file_name:
            # Load and display the FITS image
            self.display_fits_image(file_name)

    def open_fits_directory(self):
        """
        Opens a directory dialog to select a directory containing FITS files.
        """
        # Open a directory dialog to select a directory of FITS files
        directory = QFileDialog.getExistingDirectory(self, "Open Directory")
        if directory:
            self.image_paths = [os.path.join(directory, f) for f in os.listdir(directory) if f.lower().endswith('.fits')]
            self.current_image_index = 0
            if self.image_paths:
                self.display_fits_image(self.image_paths[self.current_image_index])

    def on_directory_changed(self, path):
        """
        Refreshes the list of FITS files in the directory when it changes and updates the displayed image if necessary.
        """
        print("To be implemented")

    def display_fits_image(self, file_name):
        """
        Displays the FITS image from the specified file.
        """
        # Open the FITS file
        with fits.open(file_name) as hdul:
            self.image_data = hdul[0].data
            self.header_info = hdul[0].header

        if self.image_data is None:
            print("No data found in the FITS file.")
            return

        # Convert the FITS image data to a format suitable for QImage
        # Handle single-band grayscale image
        if self.image_data.ndim == 2:
            # Scale to 0-255 and Convert to Unsigned 8-bit Integer
            self.original_image = np.uint8((self.image_data - np.min(self.image_data)) / np.ptp(self.image_data) * 255)
            self.update_image(self.original_image)

    def update_image(self, image_data):
        """
        Converts the numpy array image data to QImage and updates the displayed image.
        """
        # Convert image data to QImage and display it
        height, width = image_data.shape
        q_image = QImage(image_data.data, width, height, width, QImage.Format_Grayscale8)
        pixmap = QPixmap.fromImage(q_image)

        # Calculate scaling to ensure image fills default size if smaller
        default_size = QSize(1000, 1000)
        pixmap_size = pixmap.size()

        # checks if the dimensions of the pixmap are smaller than the default size
        # if true, scales the pixmap up to the default size
        if pixmap_size.width() < default_size.width() or pixmap_size.height() < default_size.height():
            scaled_pixmap = pixmap.scaled(default_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            scaled_pixmap = pixmap

        self.image_label.setPixmap(scaled_pixmap)

        # Adjust the window size based on the scaled image size, with a maximum size limit
        max_size = 4000

        new_width = min(scaled_pixmap.width(), max_size)
        new_height = min(scaled_pixmap.height(), max_size)

        self.resize(new_width, new_height)

    def adjust_contrast(self):
        if self.original_image is not None:
            # Get the contrast value from the slider
            contrast = self.slider.value() / 50.0  # Scale factor, default is 1.0

            # Adjust the contrast
            min_val = np.min(self.original_image)
            adjusted_image = np.clip(min_val + (self.original_image - min_val) * contrast, 0, 255).astype(np.uint8)

            # Update the image with adjusted contrast
            self.update_image(adjusted_image)

    def show_fits_header(self):
        """
        Displays the FITS header information in the text area. 
        """
        if self.header_info is not None:
            header_text = "\n".join([f"{key}: {self.header_info[key]}" for key in self.header_info])
            self.header_text_area.setText(header_text)
        else:
            # Prompt user to open a FITS file if no header info is available
            reply = QMessageBox.question(self, 'No Image Loaded', 'No FITS image is currently loaded. Do you want to open a FITS file?', QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                self.open_fits_image()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    viewer = FITSViewer()
    viewer.show()
    sys.exit(app.exec_())

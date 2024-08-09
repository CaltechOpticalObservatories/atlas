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

from fits_viewer_ui import FITSViewerUI

# Third-Party Library Imports
from PyQt5.QtWidgets import QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QTextEdit, QFileDialog, QWidget, QSplitter

from PyQt5.QtGui import QPixmap, QImage
from astropy.io import fits
import numpy as np

class FITSViewer(FITSViewerUI):
    """
    Handles image processing and FITS file operations for the FITS Viewer application.
    """    
    def __init__(self):
        super().__init__()
        self.match_mode = False
        self.cached_images = [None, None]
        self.cached_headers = [None, None]
        self.setup_connections()

    def setup_connections(self):
        # Connect buttons to their respective functions
        self.open_file_button.clicked.connect(self.open_fits_image)
        self.open_directory_button.clicked.connect(self.open_fits_directory)
        self.match_mode_button.toggled.connect(self.toggle_match_mode)
        self.header_button.clicked.connect(self.show_fits_header)
        self.slider.valueChanged.connect(self.adjust_contrast)

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
        Displays the FITS image from the specified file. Supports grayscale, RGB, and RGBA images.
        """
        with fits.open(file_name) as hdul:
            self.image_data = hdul[0].data
            self.header_info = hdul[0].header

        if self.image_data is None:
            print("No data found in the FITS file.")
            return
        
        if self.header_info is not None:
          header_text = "\n".join([f"{key}: {self.header_info[key]}" for key in self.header_info])
          self.header_info = header_text

        if self.image_data.ndim == 2:
            self.original_image = self.normalize_image(self.image_data)
            q_image = self.convert_to_qimage(self.original_image)
            pixmap = QPixmap.fromImage(q_image)
            self.display_image(pixmap)

        elif self.image_data.ndim == 3 and self.image_data.shape[2] in [3, 4]:
            q_image = self.convert_to_qimage(self.image_data)
            pixmap = QPixmap.fromImage(q_image)
            self.display_image(pixmap)

        elif self.image_data.ndim == 3:
            print("Multispectral image detected. Displaying the first band.")
            self.original_image = self.normalize_image(self.image_data[:, :, 0])
            q_image = self.convert_to_qimage(self.original_image)
            pixmap = QPixmap.fromImage(q_image)
            self.display_image(pixmap)
        else:
          print("Unsupported image format.")

    def display_image(self, pixmap):
        """
        Displays the image based on whether match mode is enabled or not.
        """
        max_width, max_height = 1000, 1000
        
        # Calculate the scaling factors
        scaled_pixmap = self.scale_pixmap(pixmap, max_width, max_height)

        if not self.match_mode:
          # Single image mode
          self.image_label1.setPixmap(scaled_pixmap)
          self.image_label2.setPixmap(QPixmap())  # Clear the second label
          self.resize(scaled_pixmap.size())
          self.cached_headers[0] = self.header_info

        else:
          # Match mode
          if self.cached_images[0] is None:
              # Cache the first image
              self.cached_images[0] = scaled_pixmap
              self.image_label1.setPixmap(self.cached_images[0])
              self.cached_headers[0] = self.header_info
          elif self.cached_images[1] is None:
              # Cache the second image
              self.cached_images[1] = scaled_pixmap
              self.image_label2.setPixmap(self.cached_images[1])
              self.cached_headers[1] = self.header_info
          else:
              # Both images are cached, shift the images
              self.cached_images[0] = self.cached_images[1]  # Move the second image to the first slot
              self.cached_headers[0] = self.cached_headers[1]
              self.cached_images[1] = scaled_pixmap  # Add the new image as the second image
              self.cached_headers[1] = self.header_info

              # Display the updated images
              self.image_label1.setPixmap(self.scale_pixmap(self.cached_images[0], max_width, max_height))
              self.image_label2.setPixmap(self.scale_pixmap(self.cached_images[1], max_width, max_height))

          # Adjust the layout based on match mode
          self.adjust_layout_for_match_mode()

    def normalize_image(self, image_data):
        """
        Normalizes the image data to a 0-255 range for display purposes.
        """
        return np.uint8((image_data - np.min(image_data)) / np.ptp(image_data) * 255)

    def convert_to_qimage(self, image_data):
        """
        Converts RGB or RGBA image data to a QImage for display.
        """
        if image_data.ndim == 2:
          # Grayscale image
          height, width = image_data.shape
          q_image = QImage(image_data.data, width, height, width, QImage.Format_Grayscale8)
        elif image_data.ndim == 3:
          # RGB or RGBA image
          height, width, channels = image_data.shape
          bytes_per_line = channels * width
          if channels == 3:
              q_image = QImage(image_data.data, width, height, bytes_per_line, QImage.Format_RGB888)
          elif channels == 4:
              q_image = QImage(image_data.data, width, height, bytes_per_line, QImage.Format_RGBA8888)
          else:
              raise ValueError("Unsupported number of channels in image data.")
        else:
          raise ValueError("Unsupported image dimensions.")

        return q_image

    def show_fits_header(self):
        """
        Displays the FITS header information in the header text areas.
        If match mode is enabled, it shows the headers for both images.
        If no images are present, prompts the user to open an image.
        """
        if self.match_mode:
            # Update the header text areas for match mode
            self.header_text_area1.setText(self.cached_headers[0])
            self.header_text_area2.setText(self.cached_headers[1])
        else:
            # Show the header for the single image mode
            print(self.cached_headers[0])
            self.header_text_area1.setText(self.cached_headers[0])

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
from image_utils import normalize_image, convert_to_qimage

# Third-Party Library Imports
from PyQt5.QtWidgets import QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QTextEdit, QFileDialog, QWidget, QSplitter
from PyQt5.QtCore import Qt
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
        self.original_image = None
        self.signal_image = None
        self.reset_image = None
        self.setup_connections()

    def setup_connections(self):
        self.open_file_action.triggered.connect(self.open_fits_image)
        self.open_directory_action.triggered.connect(self.open_fits_directory)
        self.match_mode_action.toggled.connect(self.toggle_match_mode)
        self.show_header_action.triggered.connect(self.show_header_tab)
        self.slider.valueChanged.connect(self.adjust_contrast)
        self.subtract_signal_action.triggered.connect(self.subtract_from_images)

    def open_fits_image(self):
        """
        Opens a directory dialog to select a folder, retrieves all FITS file paths from that folder,
        and displays the first FITS image in the directory.
        """
        file_name, _ = QFileDialog.getOpenFileName(self, "Open FITS File", "", "FITS Files (*.fits)")
        if file_name:
            self.display_fits_image(file_name)

    def open_fits_directory(self):
        """
        Opens a directory selection dialog, retrieves the paths of all FITS files in the selected directory,
        and displays the first FITS image from the list of retrieved files.
        """
        directory = QFileDialog.getExistingDirectory(self, "Open Directory")
        if directory:
            self.image_paths = [os.path.join(directory, f) for f in os.listdir(directory) if f.lower().endswith('.fits')]
            self.current_image_index = 0
            if self.image_paths:
                self.display_fits_image(self.image_paths[self.current_image_index])

    def display_fits_image(self, file_name):
        """
        Displays a FITS image in the application based on the provided file name.

        Args:
            file_name (str): The path to the FITS file to be displayed.
        """
        with fits.open(file_name) as hdul:
            image_data = hdul[0].data
            header_info = hdul[0].header

        if image_data is None:
            print("No data found in the FITS file.")
            return

        self.original_image = image_data
        print("Image data type:", image_data.dtype)

        if header_info is not None:
            header_text = "\n".join([f"{key}: {header_info[key]}" for key in header_info])
            if self.cached_headers[0] is None or self.match_mode is False:
                self.cached_headers[0] = header_text
            elif self.cached_headers[1] is None:
                self.cached_headers[1] = header_text
            else:
                self.cached_headers[0] = self.cached_headers[1]
                self.cached_headers[1] = header_text

        if image_data.ndim == 2:
            original_image = normalize_image(image_data)
            q_image = convert_to_qimage(original_image)
            pixmap = QPixmap.fromImage(q_image)
            self.display_image(pixmap)

        elif image_data.ndim == 3 and image_data.shape[2] in [3, 4]:
            q_image = convert_to_qimage(image_data)
            pixmap = QPixmap.fromImage(q_image)
            self.display_image(pixmap)

        elif image_data.ndim == 3:
            print("Multispectral image detected. Displaying the first band.")
            original_image = normalize_image(image_data[:, :, 0])
            q_image = convert_to_qimage(original_image)
            pixmap = QPixmap.fromImage(q_image)
            self.display_image(pixmap)
        else:
            print("Unsupported image format.")
            
        # Convert QImage to QPixmap and display
        pixmap = QPixmap.fromImage(q_image)

        # Center and scale result image if displayed
        if self.result_label.pixmap():
            result_pixmap = pixmap.scaled(self.result_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.result_label.setPixmap(result_pixmap)

    def update_result_label_size(self):
        """
        Adjust result_label to match the size of image_label1 and image_label2
        """
        if self.image_label1.pixmap():
            size = self.image_label1.pixmap().size()
            self.result_label.setFixedSize(size)
            self.result_label.setPixmap(self.result_label.pixmap().scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            # Default size if image_label1 has no pixmap
            self.result_label.setFixedSize(1000, 500)  # or any default size you prefer

    def display_image(self, pixmap):
        """
        Displays the given QPixmap in the appropriate image label based on the match mode.
        Scales the image to fit within a maximum width and height, and manages cached images
        for comparison when in match mode.

        Args:
            pixmap (QPixmap): The QPixmap object containing the image to be displayed.
        """
        max_width, max_height = 1000, 1000
        scaled_pixmap = self.scale_pixmap(pixmap, max_width, max_height)

        if not self.match_mode:
            self.image_label1.setPixmap(scaled_pixmap)
            self.image_label2.setPixmap(QPixmap())  # Clear the second label
            self.resize(scaled_pixmap.size())
        else:
            if self.cached_images[0] is None:
                self.cached_images[0] = pixmap
                self.image_label1.setPixmap(self.scale_pixmap(self.cached_images[0], max_width, max_height))
            elif self.cached_images[1] is None:
                self.cached_images[1] = pixmap
                self.image_label2.setPixmap(self.scale_pixmap(self.cached_images[1], max_width, max_height))
            else:
                self.cached_images[0] = self.cached_images[1]
                self.cached_images[1] = pixmap

                self.image_label1.setPixmap(self.scale_pixmap(self.cached_images[0], max_width, max_height))
                self.image_label2.setPixmap(self.scale_pixmap(self.cached_images[1], max_width, max_height))

        self.show_headers()
        self.adjust_layout_for_match_mode()

    def scale_pixmap(self, pixmap, max_width, max_height):
        """
        Scales a QPixmap to fit within a specified maximum width and height while maintaining the aspect ratio.
    
        Args:
            pixmap (QPixmap): The QPixmap object to be scaled.
            max_width (int): The maximum width for scaling the pixmap.
            max_height (int): The maximum height for scaling the pixmap.

        Returns:
            QPixmap: A new QPixmap object scaled to fit within the maximum width and height.
        """
        original_size = pixmap.size()
        scale_x = max_width / original_size.width()
        scale_y = max_height / original_size.height()
        scale = min(scale_x, scale_y)
        return pixmap.scaled(original_size * scale, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def adjust_contrast(self):
        if self.original_image is not None:
            contrast = self.slider.value() / 50.0
            min_val = np.min(self.original_image)
            adjusted_image = np.clip(min_val + (self.original_image - min_val) * contrast, 0, 255).astype(np.uint8)
            q_image = convert_to_qimage(adjusted_image)
            pixmap = QPixmap.fromImage(q_image)
            self.display_image(pixmap)

    def show_headers(self):
        """
        Display the cached headers in the header tab
        """
        if self.cached_headers[0]:
            self.header_text_area1.setPlainText(self.cached_headers[0])
        else:
            self.header_text_area1.setPlainText("No header information available for Image 1.")

        if self.cached_headers[1]:
            self.header_text_area2.setPlainText(self.cached_headers[1])
        else:
            self.header_text_area2.setPlainText("No header information available for Image 2.")

    def toggle_match_mode(self, checked):
        """
        Toggles the match mode on and off.
        """
        self.match_mode = checked
        if self.match_mode:
            self.splitter.setVisible(True)
            self.header_label2.setVisible(True)
            self.header_text_area2.setVisible(True)
            
            # Update the result image to match the size of image_label1 and image_label2
            self.update_result_label_size()
            if self.result_label.pixmap():
                result_pixmap = self.result_label.pixmap().scaled(self.result_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.result_label.setPixmap(result_pixmap)

        else:
            self.splitter.setVisible(False)
            self.header_label2.setVisible(False)
            self.header_text_area2.setVisible(False)

    def show_header_tab(self):
        """
        Switches to the Header tab in the tab widget.
        """
        self.tab_widget.setCurrentWidget(self.header_tab)

    def toggle_header_visibility(self):
        """
        Toggles the visibility of the header section.
        """
        visible = not self.header_label1.isVisible()
        self.header_label1.setVisible(visible)
        self.header_text_area1.setVisible(visible)
        self.header_label2.setVisible(visible)
        self.header_text_area2.setVisible(visible)

    def adjust_layout_for_match_mode(self):
        """
        Adjusts the layout when match mode is enabled or disabled.
        """
        if self.match_mode:
            self.splitter.setSizes([self.width() // 2, self.width() // 2])
        else:
            self.splitter.setSizes([self.width(), 0])

    def extract_tap_from_fits(self, image_data, tap_index):
        """
        Extracts a specific TAP from the FITS image data.
        
        Parameters:
        - image_data: The image data array.
        - tap_index: Index of the TAP to extract.
        
        Returns:
        - A 2D numpy array representing the specific TAP.
        """
        if image_data.ndim == 3:
            # Assuming the last dimension represents TAPs
            return image_data[:, :, tap_index]
        elif image_data.ndim == 2:
            # If image_data is already 2D, no TAP extraction needed
            return image_data
        else:
            raise ValueError("Unsupported image dimensions for TAP extraction.")

    def get_fits_image_data(self, pixmap):
        """
        Convert a QPixmap object back to a numpy array.
        Currently displays theQPixmap image data in Grayscale format.
        """
        image = pixmap.toImage()

        # Ensure the QImage is in grayscale format
        if image.format() != QImage.Format_Grayscale16:
            image = image.convertToFormat(QImage.Format_Grayscale16)

        # Extract raw data from QImage
        width, height = image.width(), image.height()
        bytes_per_line = image.bytesPerLine()
        raw_data = image.bits().asstring(bytes_per_line * height)

        # Convert raw data to numpy array
        array = np.frombuffer(raw_data, dtype=np.uint16).reshape((height, width))
        return array

    def subtract_from_images(self):
        """
        Subtracts one image from another and displays the result.
        This method assumes that two images are cached and performs the subtraction
        operation in a segmented manner to handle large images efficiently.
        """
        if self.cached_images[0] is not None and self.cached_images[1] is not None:
            
            # If this is the first run, fetch the signal image from the first image
            self.create_signal_fits()

            # Create the reset image
            self.create_reset_fits()

            # Extract the QImage from the cached pixmaps
            image1_data = self.signal_image
            image2_data = self.reset_image

            result_array = np.zeros_like(image1_data, dtype=np.int16)
            for tap_index in range(32):
                # Calculate column indices for the tap
                    start_col = tap_index * 64
                    end_col = start_col + 64

                    # Extract the specific tap from both images
                    tap1 = image1_data[:, start_col:end_col]
                    tap2 = image2_data[:, start_col:end_col]

                    # Subtract corresponding taps
                    result_part = np.clip(tap2 -  tap1, -32768, 32767).astype(np.int16)
                    # result_part = np.clip(tap2 - tap1, 0, 255).astype(np.int16)

                    # Place the result into the corresponding section of the result_array
                    result_array[:, start_col:end_col] = result_part

            # Convert result to QImage
            result_image = QImage(result_array.data, result_array.shape[1], result_array.shape[0], result_array.strides[0], QImage.Format_Grayscale16)
            result_pixmap = QPixmap.fromImage(result_image)

            # Display images
            self.image_label1.setPixmap(self.cached_images[0].scaled(self.image_label1.size(), Qt.KeepAspectRatio))
            self.image_label2.setPixmap(self.cached_images[1].scaled(self.image_label2.size(), Qt.KeepAspectRatio))
            self.result_label.setPixmap(result_pixmap.scaled(self.result_label.size(), Qt.KeepAspectRatio))  # Set result image on result_label

    def create_signal_fits(self, tap_width=128, num_taps=32):
        """
        Creates a signal FITS image from the cached image data by extracting and processing
        specific parts of the image. This method assumes that the cached image is in a format
        where the image can be segmented into taps.

        Args:
            tap_width (int): Width of each tap segment in the image.
            num_taps (int): Number of tap segments to process.
        """
        # Extract the QImage from the cached pixmaps
        image1_data = self.get_fits_image_data(self.cached_images[0])

        # Check if the data is 2D
        if len(image1_data.shape) == 2:
            height, width = image1_data.shape

            # Ensure the width and number of taps are consistent
            if width == tap_width * (num_taps + 1):
                # Initialize arrays for signal and reset images
                self.signal_image = np.zeros((height, tap_width // 2 * num_taps), dtype=image1_data.dtype)

                # Extract signal and reset parts for each tap
                for tap_index in range(num_taps):
                    # Calculate column indices for the tap
                    start_col = tap_index * tap_width
                    end_col = start_col + tap_width

                    # Extract the specific tap
                    tap = image1_data[:, start_col:end_col]

                    # Extract signal and reset parts
                    signal_part = tap[:, :64]

                    # Place the signal and reset parts into the corresponding images
                    self.signal_image[:, tap_index * 64:(tap_index + 1) * 64] = signal_part

                # Create and save the FITS files for signal images
                #TODO: Add a flag for this portion
                # hdu_signal = fits.PrimaryHDU(signal_image)

                # hdul_signal = fits.HDUList([hdu_signal])

                # hdul_signal.writeto(output_signal_file, overwrite=True)

                # print(f"Signal FITS image saved to {output_signal_file}")

            else:
                print(f"Error: The width of the FITS image ({width}) does not match {tap_width} pixels per tap with {num_taps} taps.")
        else:
            print("The FITS file does not contain a 2D image. Please check the dimensionality.")

    def create_reset_fits(self, tap_width=128, num_taps=32):
        """
        Creates a reset FITS image from the cached image data by extracting and processing
        specific parts of the image. This method assumes that the cached image is in a 
        format where the image can be segmented into taps.

        Args:
            tap_width (int): Width of each tap segment in the image.
            num_taps (int): Number of tap segments to process.
        """
        # Extract the QImage from the cached pixmaps
        image2_data = self.get_fits_image_data(self.cached_images[0])

        # Check if the data is 2D
        if len(image2_data.shape) == 2:
            height, width = image2_data.shape

            # Ensure the width and number of taps are consistent
            if width == tap_width * (num_taps + 1):
                # Initialize arrays for signal and reset images
                self.reset_image = np.zeros((height, tap_width // 2 * num_taps), dtype=image2_data.dtype)

                # Extract signal and reset parts for each tap
                for tap_index in range(num_taps):
                    # Calculate column indices for the tap
                    start_col = tap_index * tap_width
                    end_col = start_col + tap_width

                    # Extract the specific tap
                    tap = image2_data[:, start_col:end_col]

                    # Extract signal and reset parts
                    reset_part = tap[:, 64:]

                    # Place the signal and reset parts into the corresponding images
                    self.reset_image[:, tap_index * 64:(tap_index + 1) * 64] = reset_part

                # Create and save the FITS files for reset images
                #TODO: Add a flag for this portion
                # hdu_reset = fits.PrimaryHDU(reset_image)

                # hdul_reset = fits.HDUList([hdu_reset])

                # hdul_reset.writeto(output_reset_file, overwrite=True)

                # print(f"Reset FITS image saved to {output_reset_file}")

            else:
                print(f"Error: The width of the FITS image ({width}) does not match {tap_width} pixels per tap with {num_taps} taps.")
        else:
            print("The FITS file does not contain a 2D image. Please check the dimensionality.")

# -----------------------------------------------------------------------------
# @file     fits_viewmodel.py
# @brief    The FITSViewModel manages FITS image data processing.
# @author   Prakriti Gupta <pgupta@astro.caltech.edu>
# -----------------------------------------------------------------------------

from model.fits_model import FITSModel

# Standard Library Imports
import os

# Third-Party Library Imports
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QSize, QEvent, QRect
from PyQt5.QtGui import QPixmap, QImage
from astropy.io import fits
import numpy as np

class FITSViewModel(QObject):
    image_data_changed = pyqtSignal(QPixmap)
    result_ready = pyqtSignal(QPixmap) 
    headers_updated = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.fits_model = FITSModel()
        self.cached_images = [None, None]
        self.cached_headers = [None, None]
        self.match_mode = False
        self.original_image = None
        self.result_image = None
        self.signal_image = None
        self.reset_image = None
        self.image_dir = None
        self.update_subtraction = False

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
            original_image = self.fits_model.normalize_image(image_data)
            q_image = self.fits_model.convert_to_qimage(original_image)
            pixmap = QPixmap.fromImage(q_image)
            self.image_data_changed.emit(pixmap)

        elif image_data.ndim == 3 and image_data.shape[2] in [3, 4]:
            q_image = self.fits_model.convert_to_qimage(image_data)
            pixmap = QPixmap.fromImage(q_image)
            self.image_data_changed.emit(pixmap)

        elif image_data.ndim == 3:
            print("Multispectral image detected. Displaying the first band.")
            original_image = self.fits_model.normalize_image(image_data[:, :, 0])
            q_image = self.fits_model.convert_to_qimage(original_image)
            pixmap = QPixmap.fromImage(q_image)
            self.image_data_changed.emit(pixmap)
        else:
            print("Unsupported image format.")
            
        # Convert QImage to QPixmap and display
        pixmap = QPixmap.fromImage(q_image)

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

    def update_images_in_directory(self):
        """
        Retrieves the paths of all FITS files in the directory, updates the image sequence,
        and displays the most recent images.
        """
        if not self.image_dir:
            return

        # Get all FITS files in the directory, sorted by modification time (most recent last)
        file_paths = [os.path.join(self.image_dir, f) for f in os.listdir(self.image_dir) if f.lower().endswith('.fits')]
        file_paths.sort(key=os.path.getmtime)  # Sort by modification time
        if self.match_mode:
            # Handle the most recent two FITS images
            if len(file_paths) >= 2:
                self.image_paths = file_paths[-2:]  # Take the two most recent files
                self.current_image_index = 0
                # Display images in match mode
                for i in range(len(self.image_paths)):
                    self.display_fits_image(self.image_paths[i])
            else:
                print("Not enough images in the directory for match mode.")
        else:
            # Handle single image display when not in match mode
            if file_paths:
                self.image_paths = [file_paths[-1]]  # Take the most recent file
                self.current_image_index = 0
                self.display_fits_image(self.image_paths[self.current_image_index])

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
            self.result_image = QImage(result_array.data, result_array.shape[1], result_array.shape[0], result_array.strides[0], QImage.Format_Grayscale16)
            result_pixmap = QPixmap.fromImage(self.result_image)

            # Emit signals to update the images in the view
            self.result_ready.emit(
                result_pixmap.scaled(self.result_image.size(), Qt.KeepAspectRatio)
            )

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
        image2_data = self.get_fits_image_data(self.cached_images[1])

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

    def reset(self):
        """Reset the ViewModel state."""
        self.cached_images = [None, None]
        self.cached_headers = [None, None]
        self.original_image = None
        self.result_image = None
        self.signal_image = None
        self.reset_image = None
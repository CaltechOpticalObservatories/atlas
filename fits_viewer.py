# -----------------------------------------------------------------------------
# @file     fits_viewer.py
# @brief    The FITSViewer app allows users to open and view FITS files.
# @author   Prakriti Gupta <pgupta@astro.caltech.edu>
# -----------------------------------------------------------------------------

# pylint
# pylint: disable=line-too-long

# Standard Library Imports
import os

from fits_viewer_ui import FITSViewerUI
from image_utils import normalize_image, convert_to_qimage
from viewfinder import ViewfinderPopup
from histogram import Histogram

# Third-Party Library Imports
from PyQt5.QtWidgets import QFileDialog, QDesktopWidget
from PyQt5.QtCore import Qt, QSize, QEvent, QRect
from PyQt5.QtGui import QPixmap, QImage
from astropy.io import fits
import numpy as np

class FITSViewer(FITSViewerUI):
    """
    Handles image processing and FITS file operations for the FITS Viewer application.
    """
    def __init__(self):

        # Initialize viewfinder popup
        self.viewfinder_popup = ViewfinderPopup()
        self.mouse_pos = None

        super().__init__()
        self.match_mode = False
        self.cached_images = [None, None]
        self.cached_headers = [None, None]
        self.original_image = None
        self.result_image = None
        self.signal_image = None
        self.reset_image = None
        self.update_subtraction = False
        self.image_dir = None

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
        and initializes directory monitoring.
        """
        self.image_dir = QFileDialog.getExistingDirectory(self, "Open Directory")
        if self.image_dir:
            self.update_images_in_directory()

    def check_for_new_images(self):
        """
        Periodically checks the directory for new FITS images and updates the display.
        """
        if self.image_dir:
            self.update_images_in_directory()

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
        screen = QDesktopWidget().screenGeometry()
        max_width, max_height = screen.width() - 100, screen.height() - 100  # Adjust margins if needed

        # max_width, max_height = 1000, 1000
        scaled_pixmap = self.scale_pixmap(pixmap, max_width, max_height)

        if not self.match_mode:
            self.cached_images[0] = pixmap
            self.image_label2.setPixmap(QPixmap())  # Clear the second label
            self.image_label1.setPixmap(self.cached_images[0].scaled(self.image_label1.size(), Qt.KeepAspectRatio))
        else:
            if self.cached_images[0] is None:
                self.cached_images[0] = pixmap
                self.image_label1.setPixmap(self.cached_images[0].scaled(self.image_label1.size(), Qt.KeepAspectRatio))
                #self.image_label1.setPixmap(self.scale_pixmap(self.cached_images[0], max_width, max_height))
            elif self.cached_images[1] is None:
                self.cached_images[1] = pixmap
                #self.image_label2.setPixmap(self.scale_pixmap(self.cached_images[1], max_width, max_height))
                self.image_label2.setPixmap(self.cached_images[1].scaled(self.image_label1.size(), Qt.KeepAspectRatio))
                if self.update_subtraction:
                    self.subtract_from_images()
            else:
                self.cached_images[0] = self.cached_images[1]
                self.cached_images[1] = pixmap

                self.image_label1.setPixmap(self.cached_images[0].scaled(self.image_label1.size(), Qt.KeepAspectRatio))
                self.image_label2.setPixmap(self.cached_images[1].scaled(self.image_label2.size(), Qt.KeepAspectRatio))
                
                if self.update_subtraction:
                    self.subtract_from_images()


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
            
            if self.result_label.pixmap():            
                # Update the result image to match the size of image_label1 and image_label2
                self.update_result_label_size()
                result_pixmap = self.result_label.pixmap().scaled(self.result_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.result_label.setPixmap(result_pixmap)

        else:
            self.splitter.setVisible(False)
            self.header_label2.setVisible(False)
            self.header_text_area2.setVisible(False)
            self.update_subtraction = False

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
            self.result_image = QImage(result_array.data, result_array.shape[1], result_array.shape[0], result_array.strides[0], QImage.Format_Grayscale16)
            result_pixmap = QPixmap.fromImage(self.result_image)

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
        """
        Resets the user interface and internal state of the application.
        """
        # Clear all images and reset paths
        self.image_label1.clear()
        self.image_label2.clear()
        self.result_label.clear()

        # Reset paths
        # self.match_mode = False
        self.cached_images = [None, None]
        self.cached_headers = [None, None]
        self.original_image = None
        self.signal_image = None
        self.reset_image = None

        # Optionally reset other elements here, e.g., text fields, selections, etc.
        print("UI has been reset.")

    def open_viewfinder_popup(self):
        """
        Opens the viewfinder popup and sets the pixmaps for the images.
        """
        # Ensure cached_images and reset_image are not None
        if (self.cached_images[0] is not None and
            self.cached_images[1] is not None and
            self is not None):
            
            # Convert QPixmap to QPixmap objects for the popup
            image1_pixmap = self.cached_images[0]
            image2_pixmap = self.cached_images[1]
            result_pixmap = QPixmap.fromImage(self.result_image)
            
            # Set the images in the popup
            self.viewfinder_popup.set_pixmaps(image1_pixmap, image2_pixmap, result_pixmap)
            
            # Show the popup
            self.viewfinder_popup.exec_()
        else:
            print("Not enough images to display in the viewfinder popup.")

    def eventFilter(self, obj, event):
        """
        Filters events to handle mouse movements over specific image labels.
        Parameters:
        - obj (QObject): The object that the event is associated with. This is typically one of 
                     the image labels (e.g., `self.image_label1`, `self.image_label2`, 
                     or `self.result_label`).
        - event (QEvent): The event object containing information about the event. Specifically,
                       this method checks if the event type is `QEvent.MouseMove`.
        """
        # Check if the event is a mouse move event
        if event.type() == QEvent.MouseMove:
            if obj == self.image_label1:
                if self.cached_images[0]:
                    self.mouse_pos = event.pos()
                    self.current_label = 1
                    self.update_viewfinder()
            elif obj == self.image_label2:
                if self.cached_images[1]:
                    self.mouse_pos = event.pos()
                    self.current_label = 2
                    self.update_viewfinder()
            elif obj == self.result_label:
                if self.reset_image is not None:
                    self.mouse_pos = event.pos()
                    self.current_label = 3
                    self.update_viewfinder()
        
        # Return False to ensure other event filters are still processed
        return super().eventFilter(obj, event)

    def update_viewfinder(self):
        """
        Updates the viewfinder popup with a cropped region of the image based on the mouse position.

        The method determines which image to use based on the current label and scales the image to fit
        the label size. The viewfinder is updated only if a valid image is available and the mouse position is set.
        """
        if self.mouse_pos:
            # Determine which image to use based on the current label
            if self.current_label == 1:
                image_pixmap = self.cached_images[0] if self.cached_images[0] else None
            elif self.current_label == 2:
                image_pixmap = self.cached_images[1] if self.cached_images[1] else None
            elif self.current_label == 3:
                image_pixmap = QPixmap.fromImage(self.result_image) if self.result_image else None
            else:
                # No valid image is set, exit the method
                return

            # Convert mouse position to the corresponding region in the image
            pixmap_size = image_pixmap.size()
            # Choose the appropriate size based on the current label
            scaled_size = self.image_label1.size() if self.current_label in (1, 2) else self.result_label.size()
            # Scale the image to match the label size
            scaled_pixmap = image_pixmap.scaled(scaled_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            # Calculate the scale factors based on the image and label sizes
            scale_x = scaled_size.width() / pixmap_size.width()
            scale_y = scaled_size.height() / pixmap_size.height()
            # Calculate the position of the viewfinder area in the image
            viewfinder_x = int(self.mouse_pos.x() * scale_x)
            viewfinder_y = int(self.mouse_pos.y() * scale_y)

            # Define the size of the viewfinder area
            viewfinder_size = QSize(200, 200)
            # Create a rectangle around the mouse position to show in the viewfinder
            rect = QRect(viewfinder_x - viewfinder_size.width() // 2, 
                        viewfinder_y - viewfinder_size.height() // 2, 
                        viewfinder_size.width(), 
                        viewfinder_size.height())
            
            # Ensure the rectangle stays within the bounds of the image
            rect = rect.intersected(QRect(0, 0, pixmap_size.width(), pixmap_size.height()))

            # Crop the region from the image based on the calculated rectangle
            cropped_pixmap = image_pixmap.copy(rect)
            
            # Update the viewfinder popup with the cropped pixmap
            self.viewfinder_popup.set_image(cropped_pixmap)

    def show_histogram(self):
        """
        Opens a histogram dialog for the cached images and result image.
        """
        if None in self.cached_images and self.result_image is None:
            print("No images available for histogram.")
            return

        # Combine cached images and result image into one list
        images_to_display = [img for img in self.cached_images if img is not None]
        if self.result_image is not None:
            images_to_display.append(QPixmap.fromImage(self.result_image))

        if not images_to_display:
            print("No valid images available for histogram.")
            return

        # Create and show the histogram dialog
        histogram_dialog = Histogram(images_to_display, self)
        histogram_dialog.exec_()

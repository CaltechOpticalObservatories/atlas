from PyQt5.QtGui import QImage
from astropy.io import fits
import numpy as np

class FITSModel:
    def load_fits_image(self, file_name):
        """Load image data and header information from a FITS file."""
        with fits.open(file_name) as hdul:
            image_data = hdul[0].data
            header_info = hdul[0].header
        return image_data, header_info

    def normalize_image(self, image_data):
        """
        Normalizes image data to the range [0, 255] for display purposes, 
        handling various data types from FITS files.

        Args:
            image_data (numpy.ndarray): The input image data to be normalized.

        Returns:
            numpy.ndarray: The normalized image data scaled to the range [0, 255].
        """
        # Handle endianness and convert to little-endian if necessary
        if image_data.dtype.byteorder == '>':
            image_data = image_data.newbyteorder('<')

        # Convert image data to float for normalization
        image_data = image_data.astype(np.float32)

        # Determine the min and max values
        min_val = np.min(image_data)
        max_val = np.max(image_data)

        # Special case handling for different data types
        if image_data.dtype.kind in {'i', 'u'}:  # Integer types
            # Normalize to the range [0, 255]
            normalized_data = 255 * (image_data - min_val) / (max_val - min_val)
        elif image_data.dtype.kind == 'f':  # Floating-point types
            # Assuming floating-point data is already in a reasonable range
            # Normalize to the range [0, 255] considering typical floating-point ranges
            normalized_data = 255 * (image_data - min_val) / (np.ptp(image_data) if np.ptp(image_data) > 0 else 1)
        else:
            raise TypeError("Unsupported data type for normalization")

        # Clip values to the range [0, 255]
        normalized_data = np.clip(normalized_data, 0, 255).astype(np.uint8)

        return normalized_data

    def convert_to_qimage(self, image_data):
        """
        Convert numpy array image data to QImage.
        """
        if image_data.ndim == 2:
            height, width = image_data.shape
            return QImage(image_data.data, width, height, width, QImage.Format_Grayscale8)
        elif image_data.ndim == 3:
            height, width, channels = image_data.shape
            return QImage(image_data.data, width, height, width * channels, QImage.Format_RGB888)
        else:
            raise ValueError("Unsupported image data format.")

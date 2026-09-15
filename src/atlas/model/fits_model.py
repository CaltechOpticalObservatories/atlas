# Third-Party Library Imports
from PyQt5.QtGui import QImage
from astropy.io import fits
import numpy as np

SCALES = ("linear", "log")
# DS9's log scale is log(a*x + 1) / log(a + 1) over values already mapped to
# [0, 1]; `a` decides how much of the display range the faint end gets, and
LOG_SOFTENING = 1000.0


class FITSModel:
    def load_fits_image(self, file_name):
        """
        Load image data and header information from a FITS file.

        The primary HDU is empty in many real files (multi-extension and
        tile-compressed products), so fall back to the first HDU that
        actually carries image data.

        Args:
            file_name (str): The path to the FITS file to read.

        Returns:
            tuple: (image_data, header_info). ``image_data`` is None when the
            file contains no image HDU.
        """
        with fits.open(file_name) as hdul:
            for hdu in hdul:
                if hdu.data is not None and hdu.is_image:
                    # Copy while the file is still open; astropy memory-maps
                    # the data and the buffer is invalid once we exit.
                    return np.array(hdu.data), hdu.header.copy()

            # pylint: disable=no-member  # astropy's HDUList.__getitem__ is
            # dynamic, so pylint cannot see that this is an HDU with a header.
            return None, hdul[0].header.copy()

    def normalize_image(self, image_data, scale="linear"):
        """
        Normalizes image data to the range [0, 255] for display purposes,
        handling various data types from FITS files.

        Args:
            image_data (numpy.ndarray): The input image data to be normalized.
            scale (str): Intensity scale to apply, one of ``SCALES``. The data
                is always mapped to [0, 1] by its own min and max first, so the
                scale changes only how that span is distributed over the
                display range.

        Returns:
            numpy.ndarray: The normalized image data scaled to the range [0, 255].
        """
        if scale not in SCALES:
            raise ValueError(f"Unknown intensity scale: {scale!r}")

        # Record the original kind before casting; the cast to float would
        # otherwise make an integer check always fail.
        kind = image_data.dtype.kind

        if kind not in {'i', 'u', 'f', 'b'}:
            raise TypeError(f"Unsupported data type for normalization: {image_data.dtype}")

        # FITS data is big-endian by specification. astype() handles the byte
        # swap for us and yields a native-order array.
        image_data = image_data.astype(np.float32)

        # Floating-point FITS data routinely carries NaN/inf for blank pixels;
        # they must not drag the display range to infinity.
        finite = np.isfinite(image_data)
        if not finite.any():
            return np.zeros(image_data.shape, dtype=np.uint8)

        min_val = float(image_data[finite].min())
        max_val = float(image_data[finite].max())

        value_range = max_val - min_val
        if value_range <= 0:
            # Constant image: render it as uniform black rather than dividing by zero.
            return np.zeros(image_data.shape, dtype=np.uint8)

        unit_data = (image_data - min_val) / value_range

        # Non-finite pixels normalize to NaN
        unit_data = np.where(finite, unit_data, 0.0)

        # Clipping before the transform keeps log's argument positive.
        unit_data = np.clip(unit_data, 0.0, 1.0)
        if scale == "log":
            unit_data = np.log1p(LOG_SOFTENING * unit_data) / np.log1p(LOG_SOFTENING)

        return np.clip(255.0 * unit_data, 0, 255).astype(np.uint8)

    def convert_to_qimage(self, image_data):
        """
        Convert numpy array image data to QImage.

        QImage does not take ownership of the buffer it is handed, so the
        result is copied before returning; otherwise it would point at freed
        memory as soon as ``image_data`` goes out of scope.
        """
        # QImage requires tightly packed, C-contiguous rows.
        image_data = np.ascontiguousarray(image_data)

        if image_data.ndim == 2:
            height, width = image_data.shape
            q_image = QImage(image_data.data, width, height,
                             image_data.strides[0], QImage.Format_Grayscale8)
        elif image_data.ndim == 3 and image_data.shape[2] == 3:
            height, width, _ = image_data.shape
            q_image = QImage(image_data.data, width, height,
                             image_data.strides[0], QImage.Format_RGB888)
        elif image_data.ndim == 3 and image_data.shape[2] == 4:
            height, width, _ = image_data.shape
            q_image = QImage(image_data.data, width, height,
                             image_data.strides[0], QImage.Format_RGBA8888)
        else:
            raise ValueError(f"Unsupported image data shape for display: {image_data.shape}")

        return q_image.copy()

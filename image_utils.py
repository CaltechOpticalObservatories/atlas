import numpy as np
from PyQt5.QtGui import QImage

def normalize_image(image_data):
    """
    Normalizes the image data to a 0-255 range for display purposes.
    """
    return np.uint8((image_data - np.min(image_data)) / np.ptp(image_data) * 255)

def convert_to_qimage(image_data):
    """
    Converts image data to QImage for display.
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


import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QSlider, QLabel, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt

class Histogram(QDialog):
    """
    A class for displaying histograms of images with interactive bin count adjustment and image navigation.
    """
    def __init__(self, images, parent=None):
        super().__init__(parent)
        self.images = images  # List of QPixmap objects
        self.current_image_index = 0  # Start with the first image
        
        self.setWindowTitle("Image Histograms")

        # Create layout
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Create a figure and axis for Matplotlib
        self.figure, self.ax = plt.subplots(figsize=(8, 6))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        # Create a slider for adjusting the number of bins
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(1)
        self.slider.setMaximum(256)
        self.slider.setValue(256)
        self.slider.setTickInterval(1)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.valueChanged.connect(self.update_histogram)
        layout.addWidget(self.slider)

        # Create a label to display current bin count
        self.bin_label = QLabel()
        layout.addWidget(self.bin_label)
        
        # Create navigation buttons
        nav_layout = QHBoxLayout()
        self.prev_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        self.prev_button.clicked.connect(self.show_prev_image)
        self.next_button.clicked.connect(self.show_next_image)
        nav_layout.addWidget(self.prev_button)
        nav_layout.addWidget(self.next_button)
        layout.addLayout(nav_layout)

        # Update initial histogram
        self.update_histogram()

    def update_histogram(self):
        """
        Updates the histogram plot based on the current bin count from the slider.
        """
        self.ax.clear()
        
        # Get the current image data
        image_data = self.pixmap_to_array(self.images[self.current_image_index])
        
        # Flatten the image data to 1D
        image_data_flat = image_data.flatten()
        
        # Compute the histogram with the current number of bins
        bin_count = self.slider.value()
        histogram, bin_edges = np.histogram(image_data_flat, bins=bin_count, range=(np.min(image_data_flat), np.max(image_data_flat)))
        
        # Plot the histogram with color-coded bins
        colors = plt.cm.viridis(np.linspace(0, 1, bin_count))  # Use a colormap for colors
        self.ax.bar(bin_edges[:-1], histogram, width=np.diff(bin_edges), color=colors, edgecolor='black')
        
        # Set labels and title
        self.ax.set_title('Histogram of Pixel Intensities')
        self.ax.set_xlabel('Pixel Intensity')
        self.ax.set_ylabel('Frequency')
        self.ax.grid(True)
        
        # Update the bin count label
        self.bin_label.setText(f'Number of Bins: {bin_count}')
        
        # Draw the canvas
        self.canvas.draw()

    def pixmap_to_array(self, pixmap):
        """
        Converts a QPixmap to a numpy array.
        """
        image = pixmap.toImage()
        width, height = image.width(), image.height()
        ptr = image.bits()
        ptr.setsize(height * width * 4)  # 4 bytes per pixel (RGBA)
        arr = np.array(ptr).reshape((height, width, 4))  # RGBA image
        return arr[:, :, 0]  # Use the red channel or convert to grayscale if needed

    def show_prev_image(self):
        """
        Shows the previous image in the list.
        """
        if self.current_image_index > 0:
            self.current_image_index -= 1
            self.update_histogram()

    def show_next_image(self):
        """
        Shows the next image in the list.
        """
        if self.current_image_index < len(self.images) - 1:
            self.current_image_index += 1
            self.update_histogram()

from PyQt5.QtWidgets import QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QTextEdit, QFileDialog, QWidget, QSplitter
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QImage

class FITSViewerUI(QMainWindow):
    """
    Handles the UI components and layout of the FITS Viewer application.
    """
    
    def __init__(self):
        super().__init__()

        # Initialize UI components
        self.setup_ui()

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

        # Create the Match Mode button
        self.match_mode_button = QPushButton("Match Mode")
        self.match_mode_button.setCheckable(True)  # Allow the button to be toggled
        self.match_mode_button.toggled.connect(self.toggle_match_mode)
        self.button_layout.addWidget(self.match_mode_button)

        # Add the button layout to the main layout
        self.main_layout.addLayout(self.button_layout)

        # Create and add the image label and slider
        self.image_label1 = QLabel()
        self.image_label2 = QLabel()

        #self.image_layout = QHBoxLayout()
        #self.image_layout.addWidget(self.image_label1)
        #self.image_layout.addWidget(self.image_label2)
        #self.main_layout.addLayout(self.image_layout)

        # Create the splitter for match mode
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.image_label1)
        self.splitter.addWidget(self.image_label2)

        # Set initial sizes for both images
        self.splitter.setSizes([self.width() // 2, self.width() // 2])

        # Add the splitter to the main layout
        self.main_layout.addWidget(self.splitter)

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

        # Create and add the FITS header text areas
        self.header_label1 = QLabel("Header 1:")
        self.header_text_area1 = QTextEdit()
        self.header_text_area1.setReadOnly(True)

        self.header_label2 = QLabel("Header 2:")
        self.header_text_area2 = QTextEdit()
        self.header_text_area2.setReadOnly(True)
        self.header_label2.setVisible(False)
        self.header_text_area2.setVisible(False)

        self.header_layout = QVBoxLayout()
        self.header_layout.addWidget(self.header_label1)
        self.header_layout.addWidget(self.header_text_area1)
        self.header_layout.addWidget(self.header_label2)
        self.header_layout.addWidget(self.header_text_area2)

        self.main_layout.addLayout(self.header_layout)

        # Initialize both image labels to be empty
        self.image_label1.setPixmap(QPixmap())
        self.image_label2.setPixmap(QPixmap())

    def toggle_match_mode(self, checked):
        """
        Toggles the match mode on and off.
        """
        self.match_mode = checked
        if self.match_mode:
            self.match_mode_button.setStyleSheet("background-color: lightgreen;")  # Change button color when match mode is enabled
            self.splitter.setVisible(True)  # Show the splitter in match mode
            self.header_label2.setVisible(True)
            self.header_text_area2.setVisible(True)
        else:
            self.match_mode_button.setStyleSheet("background-color: lightgray;")  # Change button color when match mode is disabled
            self.splitter.setVisible(False)
            self.header_label2.setVisible(False)
            self.header_text_area2.setVisible(False)

    def adjust_layout_for_match_mode(self):
        """
        Adjusts the layout to display images side by side in match mode.
        """
        if self.match_mode:
          self.image_label1.setVisible(True)
          self.image_label2.setVisible(True)
          if self.cached_images[0] is not None and self.cached_images[1] is not None:
              # Calculate the combined size based on the larger dimension
              img1_size = self.cached_images[0].size()
              img2_size = self.cached_images[1].size()
              combined_width = img1_size.width() + img2_size.width()
              combined_height = max(img1_size.height(), img2_size.height())
              self.resize(combined_width, combined_height)  # Resize the window to fit both images
          else:
              self.resize(1000, 1000)  # Default size or handle as needed
        else:
          # Single image mode
          self.image_label1.setVisible(True)
          self.image_label2.setVisible(False)  # Hide the second label
          self.resize(self.image_label1.pixmap().size())  # Resize to fit the single image

    def scale_pixmap(self, pixmap, max_width, max_height):
        """
        Scales the QPixmap to fit within the specified maximum width and height while preserving the aspect ratio.
        """
        # Get the original size of the pixmap
        original_size = pixmap.size()

        # Calculate the scaling factors
        scale_x = max_width / original_size.width()
        scale_y = max_height / original_size.height()

        # Choose the smaller scaling factor to ensure the pixmap fits within the max dimensions
        scale = min(scale_x, scale_y)

        # Scale the pixmap
        scaled_pixmap = pixmap.scaled(original_size * scale, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        return scaled_pixmap

    def adjust_contrast(self):
        """
        Adjusts the contrast of the displayed image based on the slider value.
        """
        if self.original_image is not None:
          # Get the contrast value from the slider
          contrast = self.slider.value() / 50.0  # Scale factor, default is 1.0

          # Adjust the contrast
          min_val = np.min(self.original_image)
          adjusted_image = np.clip(min_val + (self.original_image - min_val) * contrast, 0, 255).astype(np.uint8)

          # Convert the adjusted image to QImage and then to QPixmap
          q_image = self.convert_to_qimage(adjusted_image)
          pixmap = QPixmap.fromImage(q_image)

          # Display the adjusted image
          self.display_image(pixmap)


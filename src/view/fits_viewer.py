# -----------------------------------------------------------------------------
# @file     fits_viewer.py
# @brief    The FITSViewer Class handles the UI components and layout of the FITS Viewer. 
# @author   Prakriti Gupta <pgupta@astro.caltech.edu>
# -----------------------------------------------------------------------------

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QLabel, QTextEdit,
                             QSplitter, QSlider, QAction, QFileDialog, QTabWidget,
                             QDesktopWidget, QSizePolicy)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
import numpy as np

from .histogram import Histogram
from viewmodel.fits_viewmodel import FITSViewModel

class FITSViewer(QMainWindow):
    """
    Handles the UI components and layout of the FITS Viewer application.
    """
    def __init__(self, view_model: FITSViewModel):

        super().__init__()
        self.fits_view_model = view_model
        self.fits_view_model.image_data_changed.connect(self.display_image)
        self.fits_view_model.result_ready.connect(self.update_result)
        self.image_dir = None
        self.setup_ui()

    def setup_ui(self):
        """
        Sets up the user interface of the FITSViewer.
        """
        self.setWindowTitle("FITS Image Viewer")
        self.setGeometry(100, 100, 1200, 1000)
        # Get screen size and calculate proportional size
        screen_size = QDesktopWidget().screenGeometry()
        screen_width = screen_size.width()
        screen_height = screen_size.height()

        # Set window size to be 80% of the screen size
        self.setFixedSize(int(screen_width * 0.8), int(screen_height * 0.8))

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout()
        self.central_widget.setLayout(self.main_layout)

        self.create_tab_widget()
        self.create_image_tab()
        self.create_header_tab()
        self.create_menu_bar()

    def create_tab_widget(self):
        """
        Creates and configures the tab widget.
        """
        self.tab_widget = QTabWidget()
        self.main_layout.addWidget(self.tab_widget)

    def create_image_tab(self):
        """
        Creates and configures the image tab.
        """
        self.image_tab = QWidget()
        self.image_tab_layout = QVBoxLayout()
        self.image_tab.setLayout(self.image_tab_layout)

        self.create_image_splitter()
        self.create_contrast_slider()

        self.tab_widget.addTab(self.image_tab, "Images")

    def create_image_splitter(self):
        """
        Creates and configures the image splitter and its components.
        """
        self.splitter = QSplitter(Qt.Horizontal)
        self.image_tab_layout.addWidget(self.splitter)

        self.create_image_layout()
        self.create_result_image_widget()

        self.image_splitter_widget = QWidget()
        self.image_splitter_layout = QVBoxLayout()
        self.image_splitter_widget.setLayout(self.image_splitter_layout)
        self.image_splitter_layout.addLayout(self.image_layout)

        self.splitter.addWidget(self.image_splitter_widget)
        self.splitter.addWidget(self.result_image_widget)

    def create_image_layout(self):
        """
        Creates and configures the layout for images.
        """
        screen_size = QDesktopWidget().screenGeometry()
        screen_width = screen_size.width()
        screen_height = screen_size.height()

        self.image_layout = QVBoxLayout()
         # Set margins to zero
        self.image_layout.setContentsMargins(0, 0, 0, 0)

        # Calculate font size based on screen width
        font_size = int(screen_width * 0.01)

        # Create labels for image names
        self.image_name_label1 = QLabel("Image 1")
        self.image_name_label2 = QLabel("Image 2")

        # Set styles for the name labels
        font = self.image_name_label1.font()
        font.setBold(True)
        font.setPointSize(font_size)

        self.image_name_label1.setFont(font)
        self.image_name_label2.setFont(font)

        self.image_name_label1.setAlignment(Qt.AlignCenter)
        self.image_name_label2.setAlignment(Qt.AlignCenter)

        # Set margins and padding to zero
        self.image_name_label1.setContentsMargins(0, 0, 0, 0)
        self.image_name_label2.setContentsMargins(0, 0, 0, 0)
        self.image_name_label1.hide()
        self.image_name_label2.hide()

        # Create image display labels
        self.image_label1 = QLabel()
        self.image_label1.setFixedSize(int(screen_width * 0.35), int(screen_height * 0.35))
        self.image_label2 = QLabel()
        self.image_label2.setFixedSize(int(screen_width * 0.35), int(screen_height * 0.35))
        self.image_label1.setContentsMargins(0, 0, 0, 0)
        self.image_label2.setContentsMargins(0, 0, 0, 0)
        self.image_label1.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.image_label2.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.image_label1.setMouseTracking(True)
        self.image_label1.installEventFilter(self)
        self.image_label2.setMouseTracking(True)
        self.image_label2.installEventFilter(self)

        # Add the name labels and image labels to the layout
        self.image_layout.addWidget(self.image_name_label1)
        self.image_layout.addWidget(self.image_label1)
        self.image_layout.addSpacing(10)
        self.image_layout.addWidget(self.image_name_label2)
        self.image_layout.addWidget(self.image_label2)

        # Install event filter
        self.image_label1.installEventFilter(self)


    def create_result_image_widget(self):
        """
        Creates and configures the result image widget.
        """
        self.result_label = QLabel()
        screen_size = QDesktopWidget().screenGeometry()
        screen_width = screen_size.width()
        screen_height = screen_size.height()

        # Set window size to be 80% of the screen size
        self.result_label.setFixedHeight(int(screen_height * 0.4))
        self.result_label.setAlignment(Qt.AlignCenter)
        self.result_label.setMouseTracking(True)
        self.result_label.installEventFilter(self)

        # Create labels for image names
        self.result_name_label = QLabel("Result Image")

        # Set styles for the name labels
        font = self.result_name_label.font()
        font.setBold(True)
        font_size = int(screen_width * 0.01)
        font.setPointSize(font_size)

        self.result_name_label.setFont(font)
        self.result_name_label.hide()

        self.result_image_widget = QWidget()
        self.result_image_layout = QVBoxLayout()
        self.result_image_layout.setAlignment(Qt.AlignCenter)
        self.result_image_widget.setLayout(self.result_image_layout)
        self.result_image_layout.addWidget(self.result_name_label)
        self.result_image_layout.addWidget(self.result_label)

    def create_contrast_slider(self):
        """
        Creates and configures the contrast adjustment slider.
        """
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(50)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.setTickInterval(10)
        self.slider.setSingleStep(1)
        self.slider.setToolTip("Adjust contrast")

        self.image_tab_layout.addWidget(self.slider)
        self.slider.valueChanged.connect(self.adjust_contrast)

    def create_header_tab(self):
        """
        Creates and configures the header tab.
        """
        self.header_tab = QWidget()
        self.header_layout = QVBoxLayout()
        self.header_tab.setLayout(self.header_layout)

        self.create_header_text_areas()

        self.tab_widget.addTab(self.header_tab, "Header")

    def create_header_text_areas(self):
        """
        Creates and configures the FITS header text areas.
        """
        self.header_label1 = QLabel("Header 1:")
        self.header_text_area1 = QTextEdit()
        self.header_text_area1.setReadOnly(True)

        self.header_label2 = QLabel("Header 2:")
        self.header_text_area2 = QTextEdit()
        self.header_text_area2.setReadOnly(True)

        self.header_layout.addWidget(self.header_label1)
        self.header_layout.addWidget(self.header_text_area1)
        self.header_layout.addWidget(self.header_label2)
        self.header_layout.addWidget(self.header_text_area2)

    def create_menu_bar(self):
        """
        Creates and configures the menu bar.
        """
        self.menu_bar = self.menuBar()
        self.create_file_menu()
        self.create_connect_menu()
        self.create_tools_menu()
        self.create_view_menu()
        self.create_reset_button()

    def create_file_menu(self):
        """
        Creates and configures the File menu.
        """
        self.file_menu = self.menu_bar.addMenu("File")

        self.open_file_action = QAction("Open FITS Image", self)
        self.open_file_action.triggered.connect(self.open_fits_image)
        self.file_menu.addAction(self.open_file_action)

        self.open_directory_action = QAction("Open Directory of FITS Images", self)
        self.open_directory_action.triggered.connect(self.open_fits_directory)
        self.file_menu.addAction(self.open_directory_action)

        self.reset_action = QAction("Reset", self)
        self.reset_action.triggered.connect(self.fits_view_model.reset)
        self.file_menu.addAction(self.reset_action)

    def create_connect_menu(self):
        """
        Creates and configures the Connect menu with Redis option.
        """
        self.connect_menu = self.menu_bar.addMenu("Connect")

        self.connect_redis_action = QAction("Connect to Database", self)
        self.connect_redis_action.triggered.connect(self.connect_to_db)
        self.connect_menu.addAction(self.connect_redis_action)

    def create_tools_menu(self):
        """
        Creates and configures the Tools menu.
        """
        self.tools_menu = self.menu_bar.addMenu("Tools")

        self.match_mode_action = QAction("Match Mode", self)
        self.match_mode_action.setCheckable(True)
        self.match_mode_action.toggled.connect(self.toggle_match_mode)
        self.tools_menu.addAction(self.match_mode_action)

        self.subtract_signal_action = QAction("Subtract Signal", self)
        self.subtract_signal_action.triggered.connect(self.toggle_subtract_mode)
        self.subtract_signal_action.setCheckable(True)
        self.tools_menu.addAction(self.subtract_signal_action)

        self.show_header_action = QAction("Show Header", self)
        self.show_header_action.triggered.connect(self.show_header_tab)
        self.tools_menu.addAction(self.show_header_action)

        self.show_histogram_action = QAction("Histogram", self)
        self.show_histogram_action.triggered.connect(self.show_histogram)
        self.tools_menu.addAction(self.show_histogram_action)

    def create_view_menu(self):
        """
        Creates and configures the View menu.
        """
        self.view_menu = self.menu_bar.addMenu("View")
        self.view_options_action = QAction("View Options", self)
        self.view_options_action.triggered.connect(self.view_options)
        self.view_menu.addAction(self.view_options_action)

    def create_reset_button(self):
        """
        Creates and configures the reset button on the menu bar.
        """
        self.reset_action = QAction("Reset", self)
        self.reset_action.triggered.connect(self.fits_view_model.reset)
        self.menu_bar.addAction(self.reset_action)

    def open_fits_image(self):
        """
        Opens a directory dialog to select a folder, retrieves all FITS file paths from that folder,
        and displays the first FITS image in the directory.
        """
        self.file_name, _ = QFileDialog.getOpenFileName(self, "Open FITS File", "", "FITS Files (*.fits)")
        if self.file_name:
            self.fits_view_model.display_fits_image(self.file_name)

    def open_fits_directory(self):
        """
        Opens a directory selection dialog, retrieves the paths of all FITS files in the selected directory,
        and initializes directory monitoring.
        """
        self.fits_view_model.image_dir = QFileDialog.getExistingDirectory(self, "Open Directory")
        if self.fits_view_model.image_dir:
            self.fits_view_model.update_images_in_directory()
    
    def toggle_header_visibility(self):
        """
        Toggles the visibility of the header section.
        """
        # Check if the header section is currently visible
        is_visible = self.header_label1.isVisible()

        # Set visibility based on the current state
        new_visibility = not is_visible
        self.header_label1.setVisible(new_visibility)
        self.header_text_area1.setVisible(new_visibility)
        self.header_label2.setVisible(new_visibility)
        self.header_text_area2.setVisible(new_visibility)

        # Update the button text to reflect the current state
        if new_visibility:
            self.show_header_button.setText("Hide Header")
        else:
            self.show_header_button.setText("Show Header")

    def display_image(self, pixmap: QPixmap):
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
        scaled_pixmap = self.fits_view_model.scale_pixmap(pixmap, max_width, max_height)

        if not self.fits_view_model.match_mode:
            self.fits_view_model.cached_images[0] = pixmap
            self.image_label2.setPixmap(QPixmap())  # Clear the second label
            self.image_label1.setPixmap(self.fits_view_model.cached_images[0].scaled(self.image_label1.size(), Qt.KeepAspectRatio))
            self.image_name_label1.setText(self.file_name)
            self.image_name_label1.show()
        else:
            if self.fits_view_model.cached_images[0] is None:
                self.fits_view_model.cached_images[0] = pixmap
                self.image_label1.setPixmap(self.fits_view_model.cached_images[0].scaled(self.image_label1.size(), Qt.KeepAspectRatio))
                self.image_name_label1.setText(self.file_name)
                self.image_name_label1.show()
            elif self.fits_view_model.cached_images[1] is None:
                self.fits_view_model.cached_images[1] = pixmap
                self.image_label2.setPixmap(self.fits_view_model.cached_images[1].scaled(self.image_label1.size(), Qt.KeepAspectRatio))
                self.image_name_label2.setText(self.file_name)
                self.image_name_label2.show()
                if self.fits_view_model.update_subtraction:
                    self.fits_view_model.subtract_from_images()
                    self.result_name_label.show()
            else:
                self.fits_view_model.cached_images[0] = self.fits_view_model.cached_images[1]
                self.fits_view_model.cached_images[1] = pixmap

                self.image_label1.setPixmap(self.fits_view_model.cached_images[0].scaled(self.image_label1.size(), Qt.KeepAspectRatio))
                self.image_label2.setPixmap(self.fits_view_model.cached_images[1].scaled(self.image_label2.size(), Qt.KeepAspectRatio))
                
                if self.fits_view_model.update_subtraction:
                    self.fits_view_model.subtract_from_images()
                    self.result_name_label.show()

        self.show_headers()
        self.adjust_layout_for_match_mode()

    def show_header_tab(self):
        """
        Switches to the Header tab in the tab widget.
        """
        self.tab_widget.setCurrentWidget(self.header_tab)

    def connect_to_db(self):
        """
        Handles the connection to selected database.
        """
        print("Connecting to database...") 

    def view_options(self):
        """
        Handles the view options.
        """
        print("Opening view options...")  # Replace with actual view options logic

    def adjust_layout_for_match_mode(self):
        """
        Adjusts the layout when match mode is enabled or disabled.
        """
        if self.fits_view_model.match_mode:
            self.splitter.setSizes([self.width() // 2, self.width() // 2])
        else:
            self.splitter.setSizes([self.width(), 0])

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

    def adjust_contrast(self):
        if self.original_image is not None:
            contrast = self.slider.value() / 50.0
            min_val = np.min(self.original_image)
            adjusted_image = np.clip(min_val + (self.original_image - min_val) * contrast, 0, 255).astype(np.uint8)
            q_image = self.fits_model.convert_to_qimage(adjusted_image)
            pixmap = QPixmap.fromImage(q_image)
            self.display_image(pixmap)

    def show_headers(self):
        """
        Display the cached headers in the header tab
        """
        if self.fits_view_model.cached_headers[0]:
            self.header_text_area1.setPlainText(self.fits_view_model.cached_headers[0])
        else:
            self.header_text_area1.setPlainText("No header information available for Image 1.")

        if self.fits_view_model.cached_headers[1]:
            self.header_text_area2.setPlainText(self.fits_view_model.cached_headers[1])
        else:
            self.header_text_area2.setPlainText("No header information available for Image 2.")

    def toggle_match_mode(self, checked):
        """
        Toggles the match mode on and off.
        """
        self.fits_view_model.match_mode = checked
        if self.fits_view_model.match_mode:
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
            self.fits_view_model.update_subtraction = False

    def toggle_subtract_mode(self, checked):
        """
        Toggles the match mode on and off.
        """
        self.fits_view_model.update_subtraction = checked
        if self.fits_view_model.update_subtraction:
            self.result_name_label.show()
            self.result_label.show()
            self.fits_view_model.subtract_from_images()
        else:
            self.result_name_label.hide()
            self.result_label.hide()


    def update_result(self, result_pixmap: QPixmap):
        """
        Updates the result image displayed in the viewer.
        """
        self.result_label.setPixmap(result_pixmap)

    def show_histogram(self):
        """
        Opens a histogram dialog for the cached images and result image.
        """
        if None in self.fits_view_model.cached_images and self.fits_view_model.result_image is None:
            print("No images available for histogram.")
            return

        # Combine cached images and result image into one list
        images_to_display = [img for img in self.fits_view_model.cached_images if img is not None]
        if self.fits_view_model.result_image is not None:
            images_to_display.append(QPixmap.fromImage(self.fits_view_model.result_image))

        if not images_to_display:
            print("No valid images available for histogram.")
            return

        # Create and show the histogram dialog
        histogram_dialog = Histogram(images_to_display, self)
        histogram_dialog.exec_()

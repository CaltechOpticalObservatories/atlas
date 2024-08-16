# -----------------------------------------------------------------------------
# @file     fits_viewer_ui.py
# @brief    The FITSViewerUI Class handles the UI components and layout of the FITS Viewer. 
# @author   Prakriti Gupta <pgupta@astro.caltech.edu>
# -----------------------------------------------------------------------------

# pylint
# pylint: disable=line-too-long

from PyQt5.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QTextEdit, 
                             QSplitter, QSlider, QAction, QFileDialog, QMenuBar, QPushButton, QTabWidget)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QImage

class FITSViewerUI(QMainWindow):
    """
    Handles the UI components and layout of the FITS Viewer application.
    """
    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        """
        Sets up the user interface of the FITSViewer.
        """
        self.setWindowTitle("FITS Image Viewer")
        self.setGeometry(100, 100, 1200, 1000)

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
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setVisible(True)
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
        self.image_layout = QVBoxLayout()
        self.image_labels_layout = QHBoxLayout()
        self.image_label1 = QLabel()
        self.image_label2 = QLabel()
        self.image_labels_layout.addWidget(self.image_label1)
        self.image_labels_layout.addWidget(self.image_label2)

        self.image_layout.addLayout(self.image_labels_layout)

    def create_result_image_widget(self):
        """
        Creates and configures the result image widget.
        """
        self.result_label = QLabel()
        self.result_label.setFixedSize(1000, 500)
        self.result_label.setAlignment(Qt.AlignCenter)

        self.result_image_widget = QWidget()
        self.result_image_widget.setStyleSheet("background-color: #E5E4E2;")
        self.result_image_layout = QVBoxLayout()
        self.result_image_layout.setAlignment(Qt.AlignCenter)
        self.result_image_widget.setLayout(self.result_image_layout)
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
        self.create_tools_menu()

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
        self.subtract_signal_action.triggered.connect(self.subtract_from_images)
        self.tools_menu.addAction(self.subtract_signal_action)

        self.show_header_action = QAction("Show Header", self)
        self.show_header_action.triggered.connect(self.show_header_tab)
        self.tools_menu.addAction(self.show_header_action)

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

    def show_header_tab(self):
        """
        Switches to the Header tab in the tab widget.
        """
        self.tab_widget.setCurrentWidget(self.header_tab)

    def open_fits_image(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open FITS File", "", "FITS Files (*.fits)")
        if file_name:
            self.open_fits_image(file_name)

    def open_fits_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Open Directory")
        if directory:
            self.open_fits_directory(directory)


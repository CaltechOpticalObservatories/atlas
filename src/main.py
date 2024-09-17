import sys
from PyQt5.QtWidgets import QApplication
from view.fits_viewer import FITSViewer  # Import the view
from viewmodel.fits_viewmodel import FITSViewModel  # Import the view model

def main():
    app = QApplication(sys.argv)

    # Initialize the view model
    view_model = FITSViewModel()

    # Initialize the view with the view model
    viewer = FITSViewer(view_model)

    # Show the main window
    viewer.show()

    sys.exit(app.exec_())

if __name__ == '__main__':
    main()

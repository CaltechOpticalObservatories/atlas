import sys
from PyQt5.QtWidgets import QApplication
from fits_viewer import FITSViewer

def main():
    # Create the application instance
    app = QApplication(sys.argv)
    
    # Create the main window instance
    viewer = FITSViewer()
    
    # Show the main window
    viewer.show()
    
    # Run the application event loop
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

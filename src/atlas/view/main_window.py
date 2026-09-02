# Third-Party Library Imports
from PyQt5.QtWidgets import (QMainWindow, QAction, QActionGroup, QFileDialog,
                             QDesktopWidget)

from atlas.features import build_tools
from .frame_grid import FrameGrid

FITS_FILTER = "FITS Files (*.fits *.fit *.fts *.fits.gz *.fz);;All Files (*)"


class AtlasWindow(QMainWindow):
    """
    Main window for atlas.

    Only the menus and panels the configuration asks for are constructed, so a
    minimal profile really is a minimal application rather than a full one with
    things hidden.
    """

    def __init__(self, view_model, config):
        super().__init__()
        self.view_model = view_model
        self.config = config

        self.setWindowTitle(config.window.title)
        screen = QDesktopWidget().screenGeometry()
        self.resize(int(screen.width() * config.window.width_fraction),
                    int(screen.height() * config.window.height_fraction))
        self.setMinimumSize(int(screen.width() * 0.3), int(screen.height() * 0.3))

        self.frame_grid = FrameGrid(view_model, self)
        self.setCentralWidget(self.frame_grid)

        self.create_menus()
        self.statusBar().showMessage("Ready")
        self.view_model.message.connect(self.show_message)
        self.view_model.frames_changed.connect(self.update_frame_actions)
        self.view_model.current_changed.connect(self.update_frame_actions)

        # Tools are built last so they can append to menus that already exist.
        self.tools = build_tools(self, config.tools)
        if not self.tools_menu.actions():
            self.tools_menu.menuAction().setVisible(False)

        self.update_frame_actions()

    def closeEvent(self, event):  # pylint: disable=invalid-name
        """Qt override: stop tools' background work so the process actually exits."""
        for tool in self.tools.values():
            tool.shutdown()
        super().closeEvent(event)

    def create_menus(self):
        """Builds the menu bar."""
        menu_bar = self.menuBar()

        self.file_menu = menu_bar.addMenu("File")
        self.add_action(self.file_menu, "Open Image…", self.open_images, "Ctrl+O")
        self.add_action(self.file_menu, "Open Directory…", self.open_directory)
        self.file_menu.addSeparator()
        self.add_action(self.file_menu, "Quit", self.close, "Ctrl+Q")

        self.frame_menu = menu_bar.addMenu("Frame")
        self.next_action = self.add_action(
            self.frame_menu, "Next Frame", self.view_model.next_frame, "Ctrl+]")
        self.previous_action = self.add_action(
            self.frame_menu, "Previous Frame", self.view_model.previous_frame, "Ctrl+[")
        self.frame_menu.addSeparator()
        self.delete_action = self.add_action(
            self.frame_menu, "Delete Frame", self.view_model.delete_current_frame, "Ctrl+W")
        self.delete_all_action = self.add_action(
            self.frame_menu, "Delete All Frames", self.view_model.delete_all_frames)

        self.view_menu = menu_bar.addMenu("View")
        self.create_display_mode_actions()

        # Created up front so tools have somewhere to attach; hidden if empty.
        self.tools_menu = menu_bar.addMenu("Tools")

    def create_display_mode_actions(self):
        """Adds the single/tile display mode choice."""
        group = QActionGroup(self)
        group.setExclusive(True)

        self.mode_actions = {}
        for mode, title, shortcut in (("single", "Single Frame", "Ctrl+1"),
                                      ("tile", "Tile Frames", "Ctrl+2")):
            action = QAction(title, self)
            action.setCheckable(True)
            action.setShortcut(shortcut)
            action.setChecked(self.view_model.display_mode == mode)
            action.triggered.connect(lambda _, m=mode: self.view_model.set_display_mode(m))
            group.addAction(action)
            self.view_menu.addAction(action)
            self.mode_actions[mode] = action

        self.view_model.display_mode_changed.connect(self.sync_display_mode)

    def add_action(self, menu, title, slot, shortcut=None):
        """Creates a menu action wired to `slot`."""
        action = QAction(title, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def open_images(self):
        """Opens one or more FITS files, each into its own frame."""
        file_names, _ = QFileDialog.getOpenFileNames(
            self, "Open FITS Image", "", FITS_FILTER)
        if not file_names:
            return

        loaded = self.view_model.load_files(file_names)
        if loaded:
            self.show_message(f"Loaded {loaded} frame{'s' if loaded != 1 else ''}.")

    def open_directory(self):
        """Opens every FITS file in a directory."""
        directory = QFileDialog.getExistingDirectory(self, "Open Directory")
        if not directory:
            return

        loaded = self.view_model.load_directory(directory)
        if loaded:
            self.show_message(f"Loaded {loaded} frame{'s' if loaded != 1 else ''}.")

    def sync_display_mode(self, mode):
        """Keeps the View menu in step with the view model."""
        action = self.mode_actions.get(mode)
        if action is not None and not action.isChecked():
            action.setChecked(True)

    def update_frame_actions(self, *_):
        """Enables frame commands only when there is something to act on."""
        count = len(self.view_model.frames)
        for action in (self.delete_action, self.delete_all_action):
            action.setEnabled(count > 0)
        for action in (self.next_action, self.previous_action):
            action.setEnabled(count > 1)

        frame = self.view_model.current_frame
        title = self.config.window.title
        if frame is not None:
            title = f"{title} — {frame.label} ({self.view_model.current_index + 1}/{count})"
        self.setWindowTitle(title)

    def show_message(self, text):
        """Shows a message in the status bar."""
        self.statusBar().showMessage(text, 8000)

"""Custom widgets for copying/pasting items."""

# ==============================================================================
# IMPORTS
# ==============================================================================

# Python Imports
import re

from PySide2 import QtCore, QtGui, QtWidgets

# Houdini Toolbox Imports
import ht.ui.paste
import ht.ui.paste.models

# Houdini Imports
import hou


# ==============================================================================
# CLASSES
# ==============================================================================

class _CustomButtonBox(QtWidgets.QDialogButtonBox):
    """A custom QDialogButtonBox for copy/paste buttons."""

    def __init__(self, icon, label, parent=None):
        super(_CustomButtonBox, self).__init__(
            QtWidgets.QDialogButtonBox.Cancel,
            parent=parent
        )

        self.accept_button = QtWidgets.QPushButton(icon, label)
        self.accept_button.setEnabled(False)

        # Acts as the Accept role.
        self.addButton(
            self.accept_button,
            QtWidgets.QDialogButtonBox.AcceptRole
        )


class BasicSourceItemTable(QtWidgets.QTableView):
    """Table to display and act on items."""

    perform_operation_signal = QtCore.Signal()
    valid_sources_signal = QtCore.Signal(bool)

    def __init__(self, source, context, selection_mode=QtWidgets.QAbstractItemView.SingleSelection,
                 allow_double_click=False, allow_delete=False, parent=None):
        super(BasicSourceItemTable, self).__init__(parent)
        self.source = source
        self.context = context

        self.allow_delete = allow_delete

        self.table_model = ht.ui.paste.models.BasicSourceItemTableModel(source, context)

        self.setModel(self.table_model)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(selection_mode)

        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.setAlternatingRowColors(True)

        self.selection_model = self.selectionModel()

        self.resizeColumnsToContents()

        if allow_double_click:
            self.doubleClicked.connect(self.accept_double_click)

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.open_menu)

        self.selection_model.selectionChanged.connect(self._on_table_selection_changed)

    def _delete_selected(self):
        """Remove selected item sources from disk."""
        selected = self.get_selected_sources()

        result = hou.ui.displayMessage(
            "Are you sure you want to delete these items?",
            buttons=("Yes", "No"),
            severity=hou.severityType.Warning,
            default_choice=1,
            close_choice=1,
            title="Delete items",
            help="\n".join([item.name for item in selected])
        )

        # Chose No, clear selection and bail.
        if result == 1:
            self.clearSelection()
            return

        for item in selected:
            self.source.destroy_item(item)

        self.clearSelection()

        self._refresh_source()

    def _refresh_source(self):
        """Refresh the item sources."""
        self.clearSelection()
        self.source.refresh()
        self.table_model.refresh()

    def _on_table_selection_changed(self, new_selection, old_selection):  # pylint: disable=unused-argument
        """Verify the selection to enable the Paste button.

        The selection is valid if one or more rows is selected.

        """
        self.valid_sources_signal.emit(self.has_rows_selected())

    def accept_double_click(self, index):
        """Accept a double click and paste the selected item."""
        if not index.isValid():
            return

        # When there is a double click we want to immediately perform the
        # action on the item item so emit a signal to let the parent know this is the case.
        self.perform_operation_signal.emit()

    def get_selected_sources(self):
        """Get a list of selected item sources"""
        indexes = self.selection_model.selectedRows()

        # Get the selected sources from the model based on the indexes.
        return [self.table_model.items[index.row()] for index in indexes]

    def has_rows_selected(self):
        """Quick check if the table has anything selected"""
        return bool(self.selection_model.selectedRows())

    def keyPressEvent(self, event):
        """Handle keystrokes."""
        key = event.key()

        if self.allow_delete and key == QtCore.Qt.Key_Delete:
            self._delete_selected()

            return

        super(BasicSourceItemTable, self).keyPressEvent(event)

    def open_menu(self, position):
        """Open the RMB context menu."""
        menu = QtWidgets.QMenu(self)

        menu.addAction(
            "Refresh",
            self._refresh_source,
        )

        if self.allow_delete:
            menu.addSeparator()

            menu.addAction(
                "Delete",
                self._delete_selected,
                QtGui.QKeySequence(QtCore.Qt.Key_Delete),
            )

        menu.exec_(self.mapToGlobal(position))


class CopyButtonBox(_CustomButtonBox):
    """Copy button box."""

    def __init__(self, parent=None):
        super(CopyButtonBox, self).__init__(
            hou.qt.createIcon("BUTTONS_copy"),
            "Copy",
            parent
        )


class CopyItemNameWidget(QtWidgets.QWidget):
    """Widget to enter an item name."""

    # Signal to emit if anything is changed.
    valid_source_signal = QtCore.Signal(bool)

    def __init__(self, invalid_names=None, parent=None):
        super(CopyItemNameWidget, self).__init__(parent)

        if invalid_names is None:
            invalid_names = ()

        self.invalid_names = invalid_names

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        layout.addWidget(QtWidgets.QLabel("Enter a simple name (ie: a cool box)"))

        # ---------------------------------------------------------------------

        self.name = QtWidgets.QLineEdit()
        layout.addWidget(self.name)

        # =====================================================================

        layout.addWidget(QtWidgets.QLabel("Optional description"))

        # =====================================================================

        self.description = QtWidgets.QLineEdit()
        layout.addWidget(self.description)

        # =====================================================================

        self.warning_widget = WarningWidget()
        layout.addWidget(self.warning_widget)

        # =====================================================================

        self.name.textChanged.connect(self.validate_name)

    def validate_name(self):
        """Validate names against bad characters."""
        value = self.name.text().strip()

        warning_message = ""

        if not value:
            valid = False
            warning_message = "Must enter a value"

        else:
            if bool(re.search(r"[^a-zA-Z0-9_ ]", value)):
                valid = False
                warning_message = "Name can only contain [a-zA-Z0-9_ ]"

            else:
                valid = True

        if value in self.invalid_names:
            valid = False
            warning_message = "'{}' already exists".format(value)

        if not valid and value:
            self.warning_widget.set_warning(warning_message)

        else:
            self.warning_widget.clear_warning()

        # Emit changed signal.
        self.valid_source_signal.emit(valid)


class NewOrExistingWidget(QtWidgets.QComboBox):
    """Widget to choose a new or existing source."""

    def __init__(self, parent=None):
        super(NewOrExistingWidget, self).__init__(parent)

        self.addItem("New File")
        self.addItem("Existing File")

    def get_current_source(self):
        """Get the currently selected source."""
        return self.itemText(self.currentIndex())


class PasteButtonBox(_CustomButtonBox):
    """Paste button box."""

    def __init__(self, parent=None):
        super(PasteButtonBox, self).__init__(
            hou.qt.createIcon("BUTTONS_paste"),
            "Paste",
            parent
        )


class RepositoryWidget(QtWidgets.QWidget):
    """Widget displaying a label and a source chooser."""

    def __init__(self, parent=None):
        super(RepositoryWidget, self).__init__(parent)

        layout = QtWidgets.QHBoxLayout()
        self.setLayout(layout)

        label = QtWidgets.QLabel("Repository")
        layout.addWidget(label)

        self.menu = QtWidgets.QComboBox()
        layout.addWidget(self.menu, 1)

        for source in ht.ui.paste.MANAGER.sources:
            # Force a refresh of the source so that it is up to date with any
            # changes which may have occurred since it was initialized.
            source.refresh()

            self.menu.addItem(source.icon, source.display_name, source)

    def get_current_source(self):
        """Get the selected source."""
        return self.menu.itemData(self.menu.currentIndex())

    def get_sources(self):
        """Get all the sources in the menu."""
        return [self.menu.itemData(i) for i in range(self.menu.count())]


class WarningWidget(QtWidgets.QWidget):
    """Widget to display warning messages."""

    def __init__(self, parent=None):
        super(WarningWidget, self).__init__(parent)

        layout = QtWidgets.QHBoxLayout()
        self.setLayout(layout)

        self.icon = QtWidgets.QLabel()
        layout.addWidget(self.icon)

        warning_icon = hou.qt.createIcon("DIALOG_warning")
        self.icon.setPixmap(warning_icon.pixmap(14, 14))
        self.icon.setHidden(True)

        self.label = QtWidgets.QLabel()
        layout.addWidget(self.label)

        layout.addStretch(1)

    def clear_warning(self):
        """Clear the warning text and icon."""
        self.label.setText("")
        self.icon.setHidden(True)

    def set_warning(self, message):
        """Set the warning text and icon."""
        self.label.setText(message)
        self.icon.setHidden(False)

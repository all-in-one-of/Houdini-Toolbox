"""This module contains custom dialogs for creating and editing AOVs and
AOVGroups.

"""

# =============================================================================
# IMPORTS
# =============================================================================

# Python Imports
import os
import re
from PySide2 import QtCore, QtWidgets

# Houdini Toolbox Imports
from ht.sohohooks.aovs import constants as consts
from ht.sohohooks.aovs import manager
from ht.sohohooks.aovs.aov import AOV, AOVGroup, IntrinsicAOVGroup
from ht.ui.aovs import uidata, utils, widgets

# Houdini Imports
import hou


# =============================================================================
# CLASSES
# =============================================================================


# =============================================================================
# Create/Edit Dialogs
# =============================================================================

class _BaseHoudiniStyleDialog(QtWidgets.QDialog):
    """Base dialog for Houdini related dialogs.  Automatically sets the Houdini
    Qt stylesheet and custom sheets.

    """

    def __init__(self, parent=None):
        super(_BaseHoudiniStyleDialog, self).__init__(parent)

        self.setProperty("houdiniStyle", True)

        self.setStyleSheet(
            uidata.TOOLTIP_STYLE
        )


# =============================================================================

class _BaseAOVDialog(_BaseHoudiniStyleDialog):
    """Base dialog for creating and editing AOVs."""

    validInputSignal = QtCore.Signal(bool)

    def __init__(self, parent=None):
        super(_BaseAOVDialog, self).__init__(parent)

        # UI elements are valid.
        self._variable_valid = False
        self._file_valid = False

        self.initUI()

        self.setMinimumWidth(450)

    # =========================================================================
    # NON-PUBLIC METHODS
    # =========================================================================

    def _additionalAOVVariableValidation(self, variable_name):
        """Perform additional validation against a variable name."""
        pass

    # =========================================================================
    # METHODS
    # =========================================================================

    def buildAOVDataFromUI(self):
        """Set AOV data from UI values."""
        aov_data = {}

        channel_name = self.channel_name.text()

        aov_data[consts.CHANNEL_KEY] = channel_name

        # =====================================================================

        quantize = self.quantize_box.itemData(self.quantize_box.currentIndex())

        aov_data[consts.QUANTIZE_KEY] = None

        if not utils.isValueDefault(quantize, "quantize"):
            aov_data[consts.QUANTIZE_KEY] = quantize

        # =====================================================================

        sfilter = self.sfilter_box.itemData(self.sfilter_box.currentIndex())

        aov_data[consts.SFILTER_KEY] = None

        if not utils.isValueDefault(sfilter, "sfilter"):
            aov_data[consts.SFILTER_KEY] = sfilter

        # =====================================================================

        pfilter = self.pfilter_widget.value()

        if not utils.isValueDefault(pfilter, "pfilter"):
            aov_data[consts.PFILTER_KEY] = pfilter

        else:
            aov_data[consts.PFILTER_KEY] = None

        # =====================================================================

        if self.exclude_from_dcm.isChecked():
            aov_data[consts.EXCLUDE_DCM_KEY] = True

        # =====================================================================

        if self.componentexport.isChecked():
            aov_data[consts.COMPONENTEXPORT_KEY] = True
            aov_data[consts.COMPONENTS_KEY] = self.components.text().split()

        # =====================================================================

        lightexport = self.lightexport.itemData(self.lightexport.currentIndex())

        if lightexport:
            aov_data[consts.LIGHTEXPORT_KEY] = lightexport

            if lightexport != consts.LIGHTEXPORT_PER_CATEGORY_KEY:
                aov_data[consts.LIGHTEXPORT_SCOPE_KEY] = self.light_mask.text()
                aov_data[consts.LIGHTEXPORT_SELECT_KEY] = self.light_select.text()

        # =====================================================================

        priority = self.priority.value()

        if not utils.isValueDefault(priority, "priority"):
            aov_data[consts.PRIORITY_KEY] = priority

        # =====================================================================

        intrinsics = self.intrinsics.text()

        aov_data[consts.INTRINSICS_KEY] = intrinsics.replace(',', ' ').split()

        # =====================================================================

        comment = self.comment.text()

        aov_data[consts.COMMENT_KEY] = comment

        # =====================================================================

        aov_data[consts.PATH_KEY] = os.path.expandvars(self.file_widget.getPath())

        # =====================================================================

        return aov_data

    # =========================================================================

    def enableComponentMode(self, enable):
        """Enable the Export Components field."""
        self.component_mode_label.setEnabled(enable)
        self.component_mode.setEnabled(enable)

        if not enable:
            self.components_label.setDisabled(True)
            self.components.setDisabled(True)

        else:
            if self.component_mode.currentIndex() == 1:
                self.components_label.setDisabled(False)
                self.components.setDisabled(False)

    def enableComponents(self, value):
        """Enable the components list."""
        if value == 1:
            self.components_label.setDisabled(False)
            self.components.setDisabled(False)
        else:
            self.components_label.setDisabled(True)
            self.components.setDisabled(True)

    # =========================================================================

    def enableCreation(self, enable):
        """Enable the Ok button."""
        self.button_box.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(enable)

    # =========================================================================

    def enableExports(self, value):
        """Enable the Light Mask and Light Selection fields."""
        # Current index must be 2 or 3 to enable the fields.
        enable = value in (2, 3)

        self.light_mask_label.setEnabled(enable)
        self.light_mask.setEnabled(enable)

        self.light_select_label.setEnabled(enable)
        self.light_select.setEnabled(enable)

    # =========================================================================

    def initUI(self):
        """Initialize the UI."""
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        # =====================================================================

        help_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(help_layout)

        help_layout.addStretch(1)

        help_layout.addWidget(widgets.HelpButton("aov_dialog"))

        # =====================================================================

        grid_layout = QtWidgets.QGridLayout()
        layout.addLayout(grid_layout)

        grid_layout.setSpacing(5)

        row = 1

        # =====================================================================

        grid_layout.addWidget(QtWidgets.QLabel("VEX Variable"), row, 0)

        self.variable_name = QtWidgets.QLineEdit()
        grid_layout.addWidget(self.variable_name, row, 1)

        row += 1

        # =====================================================================

        grid_layout.addWidget(QtWidgets.QLabel("VEX Type"), row, 0)

        self.type_box = widgets.ComboBox()
        grid_layout.addWidget(self.type_box, row, 1)

        for entry in uidata.VEXTYPE_MENU_ITEMS:
            icon = utils.getIconFromVexType(entry[0])

            self.type_box.addItem(
                icon,
                entry[1],
                entry[0]
            )

        row += 1

        # =====================================================================

        grid_layout.addWidget(QtWidgets.QLabel("Channel Name"), row, 0)

        self.channel_name = QtWidgets.QLineEdit()
        grid_layout.addWidget(self.channel_name, row, 1)

        self.channel_name.setToolTip(
            "Optional channel name Mantra will rename the AOV to."
        )

        row += 1

        # =====================================================================

        grid_layout.addWidget(QtWidgets.QLabel("Quantize"), row, 0)

        self.quantize_box = widgets.ComboBox()
        grid_layout.addWidget(self.quantize_box, row, 1)

        for entry in uidata.QUANTIZE_MENU_ITEMS:
            self.quantize_box.addItem(entry[1], entry[0])

        self.quantize_box.setCurrentIndex(2)

        row += 1

        # =====================================================================

        grid_layout.addWidget(QtWidgets.QLabel("Sample Filter"), row, 0)

        self.sfilter_box = widgets.ComboBox()
        grid_layout.addWidget(self.sfilter_box, row, 1)

        for entry in uidata.SFILTER_MENU_ITEMS:
            self.sfilter_box.addItem(entry[1], entry[0])

        row += 1

        # =====================================================================

        grid_layout.addWidget(QtWidgets.QLabel("Pixel Filter"), row, 0)

        self.pfilter_widget = widgets.MenuField(
            uidata.PFILTER_MENU_ITEMS
        )
        grid_layout.addWidget(self.pfilter_widget, row, 1)

        row += 1

        # =====================================================================

        grid_layout.setRowMinimumHeight(row, 15)

        row += 1

        # =====================================================================

        grid_layout.addWidget(
            QtWidgets.QLabel("Exclude from DCM"),
            row,
            0
        )

        self.exclude_from_dcm = hou.qt.createCheckBox()
        grid_layout.addWidget(self.exclude_from_dcm, row, 1)

        row += 1

        # =====================================================================

        grid_layout.setRowMinimumHeight(row, 15)

        row += 1

        # =====================================================================

        self.export_label = QtWidgets.QLabel("Export variable \nfor each component")

        grid_layout.addWidget(self.export_label, row, 0, 2, 1)

        self.componentexport = hou.qt.createCheckBox()
        grid_layout.addWidget(self.componentexport, row, 1, 2, 1)

        row += 2

        # =====================================================================

        self.component_mode_label = QtWidgets.QLabel("Set Components")
        grid_layout.addWidget(self.component_mode_label, row, 0)

        self.component_mode = widgets.ComboBox()
        grid_layout.addWidget(self.component_mode, row, 1)

        self.component_mode.addItem("From ROP", "rop")
        self.component_mode.addItem("In AOV", "aov")

        self.component_mode_label.setDisabled(True)
        self.component_mode.setDisabled(True)

#        self.component_mode.currentIndexChanged.connect(self.enableExports)

        row += 1

        # =====================================================================

        self.components_label = QtWidgets.QLabel("Export Components")
        grid_layout.addWidget(self.components_label, row, 0)

        self.components_label.setDisabled(True)

        self.components = QtWidgets.QLineEdit()
        self.components.setText("diffuse reflect coat refract volume sss")
        grid_layout.addWidget(self.components, row, 1)

        self.components.setDisabled(True)
        self.components.setToolTip(
            "Shading component names.  Leaving this field empty will use the components"
            " selected on the Mantra ROP."
        )

        self.componentexport.stateChanged.connect(self.enableComponentMode)
        self.component_mode.currentIndexChanged.connect(self.enableComponents)

        row += 1

        # =====================================================================

        grid_layout.setRowMinimumHeight(row, 15)

        row += 1

        # =====================================================================

        grid_layout.addWidget(QtWidgets.QLabel("Light Exports"), row, 0)

        self.lightexport = widgets.ComboBox()
        grid_layout.addWidget(self.lightexport, row, 1)

        for entry in uidata.LIGHTEXPORT_MENU_ITEMS:
            self.lightexport.addItem(entry[1], entry[0])

        self.lightexport.currentIndexChanged.connect(self.enableExports)

        row += 1

        # =====================================================================

        self.light_mask_label = QtWidgets.QLabel("Light Mask")
        grid_layout.addWidget(self.light_mask_label, row, 0)

        self.light_mask_label.setDisabled(True)

        self.light_mask = QtWidgets.QLineEdit()
        grid_layout.addWidget(self.light_mask, row, 1)

        self.light_mask.setText("*")
        self.light_mask.setDisabled(True)

        row += 1

        # =====================================================================

        self.light_select_label = QtWidgets.QLabel("Light Selection")
        grid_layout.addWidget(self.light_select_label, row, 0)

        self.light_select_label.setDisabled(True)

        self.light_select = QtWidgets.QLineEdit()
        grid_layout.addWidget(self.light_select, row, 1)

        self.light_select.setText("*")
        self.light_select.setDisabled(True)

        row += 1

        # =====================================================================

        grid_layout.setRowMinimumHeight(row, 15)

        row += 1

        # =====================================================================

        grid_layout.addWidget(QtWidgets.QLabel("Priority"), row, 0)

        self.priority = QtWidgets.QSpinBox()
        grid_layout.addWidget(self.priority, row, 1)

        self.priority.setMinimum(-1)
        self.priority.setValue(-1)

        row += 1

        # =====================================================================

        grid_layout.addWidget(QtWidgets.QLabel("Intrinsics"), row, 0)

        self.intrinsics = QtWidgets.QLineEdit()
        grid_layout.addWidget(self.intrinsics, row, 1)

        self.intrinsics.setToolTip(
            "Optional intrinsic groups for automatic group addition, eg. Diagnostic"
        )

        row += 1

        # =====================================================================

        grid_layout.setRowMinimumHeight(row, 15)

        row += 1

        # =====================================================================

        grid_layout.addWidget(QtWidgets.QLabel("Comment"), row, 0)

        self.comment = QtWidgets.QLineEdit()
        grid_layout.addWidget(self.comment, row, 1)

        self.comment.setToolTip(
            "Optional comment, eg. 'This AOV represents X'."
        )

        row += 1

        # =====================================================================

        grid_layout.setRowMinimumHeight(row, 15)

        row += 1

        # =====================================================================

        grid_layout.addWidget(QtWidgets.QLabel("File Path"), row, 0)

        self.file_widget = widgets.FileChooser()
        grid_layout.addWidget(self.file_widget, row, 1)

        row += 1

        # =====================================================================

        self.status_widget = widgets.StatusMessageWidget()
        layout.addWidget(self.status_widget)

        # =====================================================================

        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        layout.addWidget(self.button_box)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        self.validInputSignal.connect(self.enableCreation)

    # =========================================================================

    def initFromAOV(self, aov):
        """Initialize the dialog from an AOV."""

        self.variable_name.setText(aov.variable)

        self.type_box.setCurrentIndex(utils.getVexTypeMenuIndex(aov.vextype))

        if aov.channel:
            self.channel_name.setText(aov.channel)

        if aov.quantize is not None:
            self.quantize_box.setCurrentIndex(utils.getQuantizeMenuIndex(aov.quantize))

        if aov.sfilter is not None:
            self.sfilter_box.setCurrentIndex(utils.getSFilterMenuIndex(aov.sfilter))

        if aov.pfilter:
            self.pfilter_widget.set(aov.pfilter)

        if aov.exclude_from_dcm is not None:
            self.exclude_from_dcm.setChecked(aov.exclude_from_dcm)

        if aov.componentexport:
            self.componentexport.setChecked(True)

            if aov.components:
                self.components.setText(" ".join(aov.components))

        if aov.lightexport is not None:
            self.lightexport.setCurrentIndex(utils.getLightExportMenuIndex(aov.lightexport))

            self.light_mask.setText(aov.lightexport_scope)
            self.light_select.setText(aov.lightexport_select)

        if aov.priority != -1:
            self.priority.setValue(aov.priority)

        if aov.intrinsics:
            self.intrinsics.setText(", ".join(aov.intrinsics))

        if aov.comment:
            self.comment.setText(aov.comment)

        self.file_widget.setPath(aov.path)

    # =========================================================================

    def validateAllValues(self):
        """Check all the values are valid."""
        valid = True

        if not self._variable_valid:
            valid = False

        if not self._file_valid:
            valid = False

        self.validInputSignal.emit(valid)

    # =========================================================================

    def validateFilePath(self):
        """Check that the file path is valid."""
        self.status_widget.clear(1)

        path = self.file_widget.getPath()

        self._file_valid = utils.filePathIsValid(path)

        if not self._file_valid:
            self.status_widget.addError(1, "Invalid file path")

        self.validateAllValues()

    # =========================================================================

    def validateVariableName(self):
        """Check that the variable name is valid."""
        self.status_widget.clear(0)

        self._variable_valid = True

        variable_name = self.variable_name.text()

        # Only allow letters, numbers and underscores.
        result = re.match("^\\w+$", variable_name)

        if result is None:
            self._variable_valid = False
            self.status_widget.addError(0, "Invalid variable name")

        else:
            self._additionalAOVVariableValidation(variable_name)

        self.validateAllValues()

class NewAOVDialog(_BaseAOVDialog):
    """Dialog for creating a new AOV."""

    newAOVSignal = QtCore.Signal(AOV)

    def __init__(self, parent=None):
        super(NewAOVDialog, self).__init__(parent)

        self.setWindowTitle("Create AOV")

    # =========================================================================
    # NON-PUBLIC METHODS
    # =========================================================================

    def _additionalAOVVariableValidation(self, variable_name):
        """Perform additional validation against a variable name."""
        if variable_name in manager.MANAGER.aovs:
            aov = manager.MANAGER.aovs[variable_name]

            priority = self.priority.value()

            if priority > aov.priority:
                msg = "This definition will have priority for {}".format(
                    variable_name,
                )

                self.status_widget.addInfo(0, msg)

            else:
                msg = "Variable {} already exists with priority {}".format(
                    variable_name,
                    aov.priority
                )

                self.status_widget.addWarning(0, msg)

    # =========================================================================
    # METHODS
    # =========================================================================

    def accept(self):
        """Accept the operation."""
        aov_data = self.buildAOVDataFromUI()

        aov_data["variable"] = self.variable_name.text()
        aov_data["vextype"] = self.type_box.itemData(self.type_box.currentIndex())

        aov = AOV(aov_data)

        # Open file for writing.
        aov_file = manager.AOVFile(aov.path)

#        if aov_file.exists:
#                if aov_file.containsAOV(new_aov):

#                    existing_aov = aov_file.aovs[aov_file.aovs.index(new_aov)]

#                    choice = hou.ui.displayMessage(
#                        "{} already exists in file, overwrite?".format(new_aov.variable),
#                        buttons=("Cancel", "OK"),
#                        severity=hou.severityType.Warning,
#                        details=str(existing_aov.as_data()),
#                        details_expanded=True,
#                    )
#
#                    if choice == 0:
#                        return

#                    aov_file.replace_aov(new_aov)

#                else:
#                    aov_file.add_aov(new_aov)

#            else:
#                aov_file.add_aov(new_aov)

        aov_file.add_aov(aov)

        aov_file.write_to_file()

        self.newAOVSignal.emit(aov)

        return super(NewAOVDialog, self).accept()

    # =========================================================================

    def initUI(self):
        """Initialize the UI."""
        super(NewAOVDialog, self).initUI()

        self.variable_name.setFocus()
        self.variable_name.textChanged.connect(self.validateVariableName)

        self.type_box.setCurrentIndex(1)

        self.priority.valueChanged.connect(self.validateVariableName)

        self.file_widget.field.textChanged.connect(self.validateFilePath)

        self.status_widget.addInfo(0, "Enter a variable name")
        self.status_widget.addInfo(1, "Choose a file")

        self.enableCreation(False)

# =============================================================================

class EditAOVDialog(_BaseAOVDialog):
    """Dialog for editing an AOV."""

    aovUpdatedSignal = QtCore.Signal(AOV)

    def __init__(self, aov, parent=None):
        super(EditAOVDialog, self).__init__(parent)

        self._aov = aov

        self.initFromAOV()

        self.setWindowTitle("Edit AOV")

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def aov(self):
        """The AOV being edited."""
        return self._aov

    # =========================================================================
    # METHODS
    # =========================================================================

    def accept(self):
        """Accept the operation."""
        aov_data = self.buildAOVDataFromUI()

        self.aov._updateData(aov_data)

        # Open file for writing.
        aov_file = manager.AOVFile(self.aov.path)
        aov_file.replace_aov(self.aov)
        aov_file.write_to_file()

        self.aovUpdatedSignal.emit(self.aov)

        return super(EditAOVDialog, self).accept()

    # =========================================================================

    def initFromAOV(self):  # pylint: disable=arguments-differ
        """Initialize the dialog from its AOV."""

        super(EditAOVDialog, self).initFromAOV(self.aov)

    # =========================================================================

    def initUI(self):
        """Initialize the UI."""
        super(EditAOVDialog, self).initUI()

        self.variable_name.setEnabled(False)

        self.type_box.setEnabled(False)

        self.file_widget.setEnabled(False)

        self.enableCreation(True)

        self.button_box.addButton(QtWidgets.QDialogButtonBox.Reset)

        reset_button = self.button_box.button(QtWidgets.QDialogButtonBox.Reset)
        reset_button.clicked.connect(self.reset)

    # =========================================================================

    def reset(self):
        """Reset any changes made."""
        self.initFromAOV()

# =============================================================================

class _BaseGroupDialog(_BaseHoudiniStyleDialog):
    """Base dialog for creating and editing groups of AOVs."""

    validInputSignal = QtCore.Signal(bool)

    def __init__(self, parent=None):
        super(_BaseGroupDialog, self).__init__(parent)

        self._group_name_valid = False
        self._file_valid = False
        self._aovs_valid = False

        self.initUI()

        self.resize(450, 475)
        self.setMinimumWidth(450)

        self.validInputSignal.connect(self.enableCreation)

    # =========================================================================
    # NON-PUBLIC METHODS
    # =========================================================================

    def _additionalGroupNameValidation(self, group_name):
        """Perform additional validation against a group name."""
        pass

    # =========================================================================
    # METHODS
    # =========================================================================

    def buildGroupFromUI(self, group):
        """Set group information from UI values."""
        comment = str(self.comment.text())

        group.comment = comment

        priority = self.priority.value()

        if priority > -1:
            group.priority = priority

        # Find the AOVs to be in this group.
        aovs = self.aov_list.getSelectedAOVs()

        group.aovs.extend(aovs)

    # =========================================================================

    def enableCreation(self, enable):
        """Enable the Ok button."""
        self.button_box.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(enable)

    # =========================================================================

    def initUI(self):
        """Initialize the UI."""
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        # =====================================================================

        help_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(help_layout)

        help_layout.addStretch(1)

        help_layout.addWidget(widgets.HelpButton("group_dialog"))

        # =====================================================================

        grid_layout = QtWidgets.QGridLayout()
        layout.addLayout(grid_layout)

        # =====================================================================

        grid_layout.addWidget(QtWidgets.QLabel("Group Name"), 1, 0)

        self.group_name = QtWidgets.QLineEdit()
        grid_layout.addWidget(self.group_name, 1, 1)

        self.group_name.textChanged.connect(self.validateGroupName)

        self.group_name.setFocus()

        # =====================================================================

        grid_layout.addWidget(QtWidgets.QLabel("File Path"), 2, 0)

        self.file_widget = widgets.FileChooser()
        grid_layout.addWidget(self.file_widget, 2, 1)

        self.file_widget.field.textChanged.connect(self.validateFilePath)

        # =====================================================================

        grid_layout.addWidget(QtWidgets.QLabel("Comment"), 3, 0)

        self.comment = QtWidgets.QLineEdit()
        grid_layout.addWidget(self.comment, 3, 1)

        self.comment.setToolTip(
            "Optional comment, eg. 'This group is for X'."
        )

        # ====================================================================

        grid_layout.addWidget(QtWidgets.QLabel("Priority"), 4, 0)

        self.priority = QtWidgets.QSpinBox()
        grid_layout.addWidget(self.priority, 4, 1)

        self.priority.setMinimum(-1)
        self.priority.setValue(-1)

        # ====================================================================

        self.aov_list = widgets.NewGroupAOVListWidget(self)
        layout.addWidget(self.aov_list)

        # Signal triggered when check boxes are toggled.
        self.aov_list.model().sourceModel().dataChanged.connect(self.validateAOVs)

        # =====================================================================

        self.filter = widgets.FilterWidget()
        layout.addWidget(self.filter)

        self.filter.field.textChanged.connect(
            self.aov_list.proxy_model.setFilterWildcard
        )

        # =====================================================================

        self.status_widget = widgets.StatusMessageWidget()
        layout.addWidget(self.status_widget)

        # =====================================================================

        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )

        layout.addWidget(self.button_box)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    # =========================================================================

    def setSelectedAOVs(self, aovs):
        """Set a list of AOVs to be selected."""
        source_model = self.aov_list.model().sourceModel()

        source_model.beginResetModel()

        source_model.uncheck_all()

        for aov in aovs:
            try:
                row = source_model.aovs.index(aov)

            except ValueError:
                continue

            source_model.checked[row] = True

        source_model.endResetModel()

        self.validateAOVs()

    # =========================================================================

    def validateAOVs(self):
        """Check that one or more AOVs is selected."""
        self.status_widget.clear(2)

        num_checked = len(self.aov_list.getSelectedAOVs())

        self._aovs_valid = num_checked > 0

        if not self._aovs_valid:
            self.status_widget.addError(2, "No AOVs selected")

        self.validateAllValues()

    # =========================================================================

    def validateAllValues(self):
        """Check all values are valid."""
        valid = True

        if not self._group_name_valid:
            valid = False

        if not self._file_valid:
            valid = False

        if not self._aovs_valid:
            valid = False

        self.validInputSignal.emit(valid)

    # =========================================================================

    def validateFilePath(self):
        """Check that the file path is valid."""
        self.status_widget.clear(1)

        path = self.file_widget.getPath()
        self._file_valid = utils.filePathIsValid(path)

        if not self._file_valid:
            self.status_widget.addError(1, "Invalid file path")

        self.validateAllValues()

    # =========================================================================

    def validateGroupName(self):
        """Check that the group name is valid."""
        self.status_widget.clear(0)

        self._group_name_valid = True

        group_name = self.group_name.text()

        # Only allow letters, numbers and underscores.
        result = re.match("^\\w+$", group_name)

        if result is None:
            self._group_name_valid = False
            self.status_widget.addError(0, "Invalid group name")

        # Check if the group exists when creating a new group.
        else:
            self._additionalGroupNameValidation(group_name)

        self.validateAllValues()

# =============================================================================

class NewGroupDialog(_BaseGroupDialog):
    """Dialog for creating a new AOV group."""

    newAOVGroupSignal = QtCore.Signal(AOVGroup)

    def __init__(self, parent=None):

        super(NewGroupDialog, self).__init__(parent)

        self.setWindowTitle("Create AOV Group")

    # =========================================================================
    # NON-PUBLIC METHODS
    # =========================================================================

    def _additionalGroupNameValidation(self, group_name):
        """Perform additional validation against a group name."""
        if group_name in manager.MANAGER.groups:
            group = manager.MANAGER.groups[group_name]

            priority = self.priority.value()

            if priority > group.priority:
                msg = "This definition will have priority for {}".format(
                    group_name,
                )

                self.status_widget.addInfo(0, msg)

            else:
                msg = "Group {} already exists with priority {}".format(
                    group_name,
                    group.priority
                )

                self.status_widget.addWarning(0, msg)

        super(NewGroupDialog, self)._additionalGroupNameValidation(group_name)

    # =========================================================================
    # METHODS
    # =========================================================================

    def accept(self):
        """Accept the operation."""
        group_name = str(self.group_name.text())

        group = AOVGroup(group_name)
        group.path = os.path.expandvars(self.file_widget.getPath())

        self.buildGroupFromUI(group)

        aov_file = manager.AOVFile(group.path)

        aov_file.add_group(group)

        aov_file.write_to_file()

        self.newAOVGroupSignal.emit(group)

        return super(NewGroupDialog, self).accept()

    # =========================================================================

    def initUI(self):
        """Initialize the UI."""
        super(NewGroupDialog, self).initUI()

        # Set default messages for new groups.
        self.status_widget.addInfo(0, "Enter a group name")
        self.status_widget.addInfo(1, "Choose a file")
        self.status_widget.addInfo(2, "Select AOVs for group")

        self.priority.valueChanged.connect(self.validateGroupName)

        self.enableCreation(False)

# =============================================================================

class EditGroupDialog(_BaseGroupDialog):
    """Dialog for editing AOV groups."""

    groupUpdatedSignal = QtCore.Signal(AOVGroup)

    def __init__(self, group, parent=None):
        super(EditGroupDialog, self).__init__(parent)

        self._group = group

        self.setWindowTitle("Edit AOV Group")

        self.initFromGroup()

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def group(self):
        """The group being edited."""
        return self._group

    # =========================================================================
    # METHODS
    # =========================================================================

    def accept(self):
        """Accept the operation."""
        # Want to edit the existing group so use it and clear out the
        # current AOVs.
        group = self._group
        group.clear()

        self.buildGroupFromUI(group)

        aov_file = manager.AOVFile(group.path)
        aov_file.replaceGroup(group)
        aov_file.write_to_file()

        self.groupUpdatedSignal.emit(group)

        return super(EditGroupDialog, self).accept()

    # =========================================================================

    def initFromGroup(self):
        """Initialize the UI values from the group."""
        self.group_name.setText(self.group.name)
        self.file_widget.setPath(self.group.path)

        if self.group.comment:
            self.comment.setText(self.group.comment)

        if self.group.priority != -1:
            self.priority.setValue(self.group.priority)

        self.setSelectedAOVs(self.group.aovs)

    # =========================================================================

    def initUI(self):
        """Initialize the UI."""
        super(EditGroupDialog, self).initUI()

        self.group_name.setEnabled(False)
        self.file_widget.enable(False)

        # Add a Reset button.
        self.button_box.addButton(QtWidgets.QDialogButtonBox.Reset)

        reset_button = self.button_box.button(QtWidgets.QDialogButtonBox.Reset)
        reset_button.clicked.connect(self.reset)

        self.enableCreation(True)

    # =========================================================================

    def reset(self):
        """Reset any changes made."""
        # Reset the dialog by just calling the initFromGroup function again.
        self.initFromGroup()

# =============================================================================
# Info Dialogs
# =============================================================================

class AOVInfoDialog(_BaseHoudiniStyleDialog):
    """Dialog for displaying information about an AOV."""

    aovUpdatedSignal = QtCore.Signal(AOV)

    def __init__(self, aov, parent=None):
        super(AOVInfoDialog, self).__init__(parent)

        self._aov = aov

        self.setWindowTitle("View AOV Info")

        self.initUI()

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def aov(self):
        """The currently displayed AOV."""
        return self._aov

    @aov.setter
    def aov(self, aov):
        self._aov = aov

    # =========================================================================
    # METHODS
    # =========================================================================

    def delete(self):
        """Delete the currently selected AOV."""
        self.accept()

        choice = hou.ui.displayMessage(
            "Are you sure you want to delete {}?".format(self.aov.variable),
            buttons=("Cancel", "OK"),
            severity=hou.severityType.Warning,
            close_choice=0,
            help="This action cannot be undone.",
            title="Confirm AOV Deletion"
        )

        if choice == 1:
            aov_file = manager.AOVFile(self.aov.path)
            aov_file.remove_aov(self.aov)
            aov_file.write_to_file()

            manager.MANAGER.remove_aov(self.aov)

    # =========================================================================

    def edit(self):
        """Launch the Edit dialog for the currently selected AOV."""
        # Accept the dialog so it closes.
        self.accept()

        parent = hou.qt.mainWindow()

        self.dialog = EditAOVDialog(
            self.aov,
            parent
        )

        self.dialog.aovUpdatedSignal.connect(self.emitAOVUpdated)

        self.dialog.show()

    # =========================================================================

    def emitAOVUpdated(self, aov):
        """Emit a signal that the supplied AOV has been updated."""
        self.aovUpdatedSignal.emit(aov)

    # =========================================================================

    def initUI(self):
        """Initialize the UI."""
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        self.aov_chooser = widgets.ComboBox()
        layout.addWidget(self.aov_chooser)

        # Start menu index.
        start_idx = -1

        # Populate the AOV chooser with all the existing AOVs.
        for idx, aov in enumerate(sorted(manager.MANAGER.aovs.values())):
            # If a channel is specified, put it into the display name.
            if aov.channel is not None:
                label = "{} ({})".format(
                    aov.variable,
                    aov.channel
                )

            else:
                label = aov.variable

            self.aov_chooser.addItem(
                utils.getIconFromVexType(aov.vextype),
                label,
                aov
            )

            # The AOV matches our start AOV so set the start index.
            if aov == self.aov:
                start_idx = idx

        if start_idx != -1:
            self.aov_chooser.setCurrentIndex(start_idx)

        self.aov_chooser.currentIndexChanged.connect(self.selectionChanged)

        # =====================================================================

        self.table = widgets.AOVInfoTableView(self.aov)
        layout.addWidget(self.table)

        # =====================================================================

        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok
        )
        layout.addWidget(self.button_box)

        self.button_box.accepted.connect(self.accept)

        edit_button = QtWidgets.QPushButton(
            hou.qt.createIcon("BUTTONS_edit"),
            "Edit"
        )

        edit_button.setToolTip("Edit this AOV.")

        self.button_box.addButton(edit_button, QtWidgets.QDialogButtonBox.ResetRole)
        edit_button.clicked.connect(self.edit)

        # =====================================================================

        delete_button = QtWidgets.QPushButton(
            hou.qt.createIcon("COMMON_delete"),
            "Delete"
        )

        self.button_box.addButton(delete_button, QtWidgets.QDialogButtonBox.ResetRole)

        delete_button.setToolTip("Delete this AOV.")
        delete_button.clicked.connect(self.delete)

        # =====================================================================

        self.table.resizeColumnToContents(0)
        self.setMinimumSize(self.table.size())

    # =========================================================================

    def selectionChanged(self, index):
        """Update the dialog to display the selected AOV."""
        # Update the current AOV to the now selected one.
        self.aov = self.aov_chooser.itemData(index)

        # Update the table data.
        model = self.table.model()
        model.beginResetModel()
        model.init_data_from_aov(self.aov)
        model.endResetModel()

        self.table.resizeColumnToContents(0)

# =============================================================================

class AOVGroupInfoDialog(_BaseHoudiniStyleDialog):
    """Dialog for displaying information about an AOVGroup."""

    groupUpdatedSignal = QtCore.Signal(AOVGroup)

    def __init__(self, group, parent=None):
        super(AOVGroupInfoDialog, self).__init__(parent)

        self._group = group

        self.setWindowTitle("View AOV Group Info")

        self.initUI()

        self.enableEdit(group)

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def group(self):
        """The currently displayed group."""
        return self._group

    @group.setter
    def group(self, group):
        self._group = group

    # =========================================================================
    # METHODS
    # =========================================================================

    def delete(self):
        """Delete the currently selected AOV."""
        self.accept()

        choice = hou.ui.displayMessage(
            "Are you sure you want to delete {}?".format(self.group.name),
            buttons=("Cancel", "OK"),
            severity=hou.severityType.Warning,
            close_choice=0,
            help="This action cannot be undone.",
            title="Confirm Group Deletion"
        )

        if choice == 1:
            aov_file = manager.AOVFile(self.group.path)
            aov_file.remove_group(self.group)
            aov_file.write_to_file()

            manager.MANAGER.remove_group(self.group)

    # =========================================================================

    def edit(self):
        """Launch the Edit dialog for the currently selected group."""
        # Accept the dialog so it closes.
        self.accept()

        parent = hou.qt.mainWindow()

        self.dialog = EditGroupDialog(
            self.group,
            parent
        )

        self.dialog.groupUpdatedSignal.connect(self.emitGroupUpdated)

        self.dialog.show()

    # =========================================================================

    def emitGroupUpdated(self, group):
        """Emit a signal that the supplied group has been updated."""
        self.groupUpdatedSignal.emit(group)

    # =========================================================================

    def enableEdit(self, group):
        """Enable or disable the edit and delete buttons based on the group."""
        if isinstance(group, IntrinsicAOVGroup):
            self.delete_button.setDisabled(True)
            self.edit_button.setDisabled(True)

        else:
            self.delete_button.setDisabled(False)
            self.edit_button.setDisabled(False)

    # =========================================================================

    def initUI(self):
        """Initialize the UI."""
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        # =====================================================================

        self.group_chooser = widgets.ComboBox()
        layout.addWidget(self.group_chooser)

        # Start menu index.
        start_idx = -1

        # Populate the group chooser with all the existing groups.
        for idx, group in enumerate(sorted(manager.MANAGER.groups.values())):
            label = group.name

            self.group_chooser.addItem(
                utils.getIconFromGroup(group),
                label,
                group
            )

            # The group matches our start group so set the start index.
            if group == self.group:
                start_idx = idx

        if start_idx != -1:
            self.group_chooser.setCurrentIndex(start_idx)

        self.group_chooser.currentIndexChanged.connect(self.selectionChanged)

        # =====================================================================

        self.table = widgets.AOVGroupInfoTableWidget(self.group)
        layout.addWidget(self.table)

        # =====================================================================

        self.members = widgets.GroupMemberListWidget(self.group)
        layout.addWidget(self.members)

        # =====================================================================

        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok
        )
        layout.addWidget(self.button_box)

        self.button_box.accepted.connect(self.accept)

        # Button to launch the Edit dialog on the current group.
        self.edit_button = QtWidgets.QPushButton(
            hou.qt.createIcon("BUTTONS_edit"),
            "Edit"
        )

        self.edit_button.setToolTip("Edit this group.")

        # Use HelpRole to force the button to the left size of the dialog.
        self.button_box.addButton(self.edit_button, QtWidgets.QDialogButtonBox.HelpRole)
        self.edit_button.clicked.connect(self.edit)

        # =====================================================================

        self.delete_button = QtWidgets.QPushButton(
            hou.qt.createIcon("COMMON_delete"),
            "Delete"
        )

        self.button_box.addButton(self.delete_button, QtWidgets.QDialogButtonBox.HelpRole)

        self.delete_button.setToolTip("Delete this group.")
        self.delete_button.clicked.connect(self.delete)

        # =====================================================================

        self.table.resizeColumnToContents(0)
        self.setMinimumSize(self.table.size())

    # =========================================================================

    def selectionChanged(self, index):
        """Update the dialog to display the selected group."""
        # Update the current group to the now selected one.
        self.group = self.group_chooser.itemData(index)

        # Update the group information table.
        table_model = self.table.model()
        table_model.beginResetModel()
        table_model.init_data_from_group(self.group)
        table_model.endResetModel()

        # Update the group member data.
        member_model = self.members.model().sourceModel()
        member_model.beginResetModel()
        member_model.init_data_from_group(self.group)
        member_model.endResetModel()

        self.table.resizeColumnToContents(0)

        # Enable/disable editing features.
        self.enableEdit(self.group)

# =============================================================================
# FUNCTIONS
# =============================================================================

def createNewAOV(aov=None):
    """Display the Create AOV dialog."""
    parent = hou.qt.mainWindow()

    dialog = NewAOVDialog(parent)

    if aov is not None:
        dialog.initFromAOV(aov)

    dialog.newAOVSignal.connect(
        manager.MANAGER.add_aov
    )

    dialog.show()


def createNewGroup(aovs=()):
    """Display the Create AOV Group dialog."""
    parent = hou.qt.mainWindow()

    new_group_dialog = NewGroupDialog(parent)

    if aovs:
        new_group_dialog.setSelectedAOVs(aovs)

    new_group_dialog.newAOVGroupSignal.connect(
        manager.MANAGER.add_group
    )

    new_group_dialog.show()


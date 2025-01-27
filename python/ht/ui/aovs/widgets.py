"""This module contains custom PySide widgets."""

# =============================================================================
# IMPORTS
# =============================================================================

# Python Imports
import os
import pickle

from PySide2 import QtCore, QtGui, QtWidgets

# Houdini Toolbox Imports
from ht.sohohooks.aovs import manager
from ht.sohohooks.aovs.aov import AOV, AOVGroup, IntrinsicAOVGroup
from ht.ui.aovs import models, uidata, utils

# Houdini Imports
import hou


# =============================================================================
# CLASSES
# =============================================================================

class AOVManagerWidget(QtWidgets.QWidget):
    """Primary AOV Manager widget."""

    invalidAOVSelectedSignal = QtCore.Signal()
    selectedAOVContainedSignal = QtCore.Signal(bool)

    def __init__(self, node=None, parent=None):
        super(AOVManagerWidget, self).__init__(parent)

        self._node = None

        self.initUI()

        # Left/right button action signals.
        self.select_widget.installSignal.connect(self.to_add_widget.installListener)
        self.select_widget.uninstallSignal.connect(self.to_add_widget.uninstallListener)

        # Update left/right buttons after data changed.
        self.select_widget.aov_tree.selectionChangedSignal.connect(self.checkNodeAdded)
        self.to_add_widget.updateEnabledSignal.connect(self.checkNodeAdded)

        # Left/right button enabling/disabling.
        self.selectedAOVContainedSignal.connect(self.select_widget.install_bar.enableHandler)
        self.invalidAOVSelectedSignal.connect(self.select_widget.install_bar.disableHandler)

        # Really need a signal?  Maybe just refresh everything?
        manager.MANAGER.init_interface()
        manager.MANAGER.interface.aovAddedSignal.connect(self.select_widget.aov_tree.insert_aov)
        manager.MANAGER.interface.aovRemovedSignal.connect(self.select_widget.aov_tree.remove_aov)
        manager.MANAGER.interface.groupAddedSignal.connect(self.select_widget.aov_tree.insert_group)
        manager.MANAGER.interface.groupRemovedSignal.connect(self.select_widget.aov_tree.remove_group)

        self.to_add_widget.tree.model().sourceModel().insertedItemsSignal.connect(
            self.select_widget.markItemsInstalled
        )

        self.to_add_widget.tree.model().sourceModel().removedItemsSignal.connect(
            self.select_widget.markItemsUninstalled
        )

        self.setStyleSheet(uidata.TOOLTIP_STYLE)

        self.setProperty("houdiniStyle", True)

        # If a node was passed along, set the UI to use it.
        if node is not None:
            self.setNode(node)

    # =========================================================================
    # METHODS
    # =========================================================================

    def checkNodeAdded(self):
        """This function detects whether selected tree nodes are currently
        in the 'AOVs to Apply' tree.

        """
        # Get selected nodes in the 'AOVs and Groups' tree.
        nodes = self.select_widget.getSelectedNodes()

        if nodes:
            # Are any contained.
            contains = False

            for node in nodes:
                # See if the node corresponds to an index in the target view.
                if self.to_add_widget.tree.nodeIndexInModel(node) is not None:
                    contains = True
                    break

            # Notify the move to left/right buttons on the status.
            self.selectedAOVContainedSignal.emit(contains)

        else:
            self.invalidAOVSelectedSignal.emit()

    def initUI(self):
        """Initialize the UI."""
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        layout.setContentsMargins(0, 0, 0, 0)

        # =====================================================================

        splitter = QtWidgets.QSplitter()
        layout.addWidget(splitter)

        self.select_widget = AOVSelectWidget()
        splitter.addWidget(self.select_widget)

        # =====================================================================

        self.to_add_widget = AOVsToAddWidget()
        splitter.addWidget(self.to_add_widget)

    def setNode(self, node):
        """Register a node as the target apply node."""
        self._node = node

        self.to_add_widget.setNode(node)


class AOVViewerToolBar(QtWidgets.QToolBar):
    """This class represents a base toolbar class used for AOVs."""

    def __init__(self, parent=None):
        super(AOVViewerToolBar, self).__init__(parent)

        self.setStyleSheet(uidata.AOVVIEWERTOOLBAR_STYLE)
        self.setIconSize(QtCore.QSize(24, 24))

# =============================================================================
# AOVs and Groups
# =============================================================================

class AOVSelectTreeWidget(QtWidgets.QTreeView):
    """This class represents a tree with AOVs and AOVGroups that can be
    added to renders.

    """
    selectionChangedSignal = QtCore.Signal()

    installItemsSignal = QtCore.Signal(models.AOVBaseNode)
    uninstallItemsSignal = QtCore.Signal(models.AOVBaseNode)

    def __init__(self, parent=None):
        super(AOVSelectTreeWidget, self).__init__(parent)

        self.root = models.TreeNode()

        model = models.AOVSelectModel(self.root)
        self.proxy_model = models.LeafFilterProxyModel()
        self.proxy_model.setSourceModel(model)
        self.setModel(self.proxy_model)

        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

        self.setAlternatingRowColors(True)
        self.setHeaderHidden(True)
        self.setDragEnabled(True)

        self.setSortingEnabled(True)
        self.sortByColumn(0, QtCore.Qt.AscendingOrder)

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.openMenu)

        selection_model = self.selectionModel()
        selection_model.selectionChanged.connect(self.selectionChangedHandler)

        self.init_from_manager()

        self.setAcceptDrops(True)

    # =========================================================================
    # METHODS
    # =========================================================================

    def collapseBelow(self):
        """Collapse all child folders and groups."""
        indexes = self.selectedIndexes()

        for index in indexes:
            self.collapseIndex(index)

    def collapseIndex(self, index):
        """Collapse an index and all it's children."""
        self.collapse(index)

        if self.model().hasChildren(index):
            for i in range(self.model().rowCount(index)):
                idx = self.model().index(i, 0, index)
                self.collapseIndex(idx)

    def collapseSelected(self):
        """Collapse selected folders and groups."""
        indexes = self.selectedIndexes()

        for index in reversed(indexes):
            self.collapse(index)

    def dragEnterEvent(self, event):
        """Event occurring when something is dragged into the widget."""
        # Accept text containing events so we can drop Houdini nodes and files.
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Event when dropping items onto widget."""
        import ht.ui.aovs.dialogs

        # Get the data attached to this event.
        mime_data = event.mimeData()

        # Get text data which corresponds to node paths (or files).
        data = str(mime_data.text())
        paths = data.split(",")

        # Process any urls (files).
        if mime_data.hasUrls():
            for url in mime_data.urls():
                # Only care about actual files on disk.
                if not url.scheme() == "file":
                    continue

                # Extract file path.
                path = str(url.toLocalFile())

                # Load a .json file that exists on disk.
                if os.path.exists(path):
                    ext = os.path.splitext(path)[-1]

                    if ext == ".json":
                        manager.MANAGER.load(path)

        # Process paths, looking for nodes.  Any file paths represented by
        # urls that were handled above will also be in this list because they
        # are strings but will be ignored below since the call to hou.node()
        # will not return anything.
        for path in paths:
            # Find the node.
            node = hou.node(path)

            if node is None:
                continue

            # Can only import from Mantra nodes.
            if node.type() != hou.nodeType("Driver/ifd"):
                continue

            num_aovs = node.evalParm("vm_numaux")

            if not num_aovs:
                continue

            # Get AOV objects from multi parms.
            aovs = utils.buildAOVsFromMultiparm(node)

            # Launch the Create New AOV dialog on each AOV.
            for aov in aovs:
                ht.ui.aovs.dialogs.createNewAOV(aov)

    def editSelected(self):
        """Edit selected nodes."""
        self.editSelectedAOVs()
        self.editSelectedGroups()

    def editSelectedAOVs(self):
        """Edit selected AOVs."""
        import ht.ui.aovs.dialogs

        aovs = self.getSelectedAOVs()

        parent = hou.qt.mainWindow()

        for aov in aovs:
            dialog = ht.ui.aovs.dialogs.EditAOVDialog(
                aov,
                parent
            )

            dialog.show()

    def editSelectedGroups(self):
        """Edit selected groups."""
        import ht.ui.aovs.dialogs

        groups = self.getSelectedGroups(allow_intrinsic=False)

        parent = hou.qt.mainWindow()

        for group in groups:
            dialog = ht.ui.aovs.dialogs.EditGroupDialog(
                group,
                parent
            )

            dialog.groupUpdatedSignal.connect(self.update_group)

            dialog.show()

    def expandBelow(self):
        """Expand all child folders and groups."""
        indexes = self.selectedIndexes()

        for index in indexes:
            self.expandIndex(index)

    def expandIndex(self, index):
        """Expand an index and all it's children."""
        self.expand(index)

        if self.model().hasChildren(index):
            for i in range(self.model().rowCount(index)):
                idx = self.model().index(i, 0, index)
                self.expandIndex(idx)

    def expandSelected(self):
        """Expand selected folders and groups."""
        indexes = self.selectedIndexes()

        for index in reversed(indexes):
            self.expand(index)

    def getSelectedAOVs(self):
        """Get selected AOVs."""
        selected = self.getSelectedNodes()

        aovs = [node.item for node in selected
                if not isinstance(node, models.FolderNode) and
                isinstance(node.item, AOV)]

        return aovs

    def getSelectedGroups(self, allow_intrinsic=True):
        """Get selected groups."""
        selected = self.getSelectedNodes()

        groups = [node.item for node in selected
                  if not isinstance(node, models.FolderNode) and
                  isinstance(node.item, AOVGroup)]

        if not allow_intrinsic:
            groups = [group for group in groups
                      if not isinstance(group, IntrinsicAOVGroup)]

        return groups

    def getSelectedNodes(self):
        """Get a list of selected tree nodes."""
        nodes = []

        indexes = self.selectionModel().selectedIndexes()

        model = self.model()
        source_model = model.sourceModel()

        for index in indexes:
            index = model.mapToSource(index)
            nodes.append(source_model.get_node(index))

        return nodes

    def init_from_manager(self):
        """Initialize the tree from the manager."""
        self.root.remove_all_children()

        self.proxy_model.sourceModel().init_from_manager()

        # Expand the main folders but not the groups.
        self.expandToDepth(0)

    def insert_aov(self, aov):
        """Add an AOV to the model."""
        self.model().sourceModel().insert_aov(aov)

    def insert_group(self, group):
        """Add an AOVGroup to the model."""
        self.model().sourceModel().insert_group(group)

    def install_selected(self):
        """Install selected nodes."""
        nodes = self.getSelectedNodes()

        if nodes:
            self.installItemsSignal.emit(nodes)

    def keyPressEvent(self, event):
        """Handle keystrokes."""
        key = event.key()

        if key == QtCore.Qt.Key_I:
            self.showInfo()
            return

        elif key == QtCore.Qt.Key_Y:
            self.install_selected()
            return

        elif key == QtCore.Qt.Key_U:
            self.uninstall_selected()
            return

        elif key == QtCore.Qt.Key_E:
            self.editSelected()
            return

        super(AOVSelectTreeWidget, self).keyPressEvent(event)

    def markItemsInstalled(self, items):
        """Mark items as currently installed in the tree."""
        self.model().sourceModel().mark_installed(items)

    def markItemsUninstalled(self, items):
        """Mark items as not currently installed in the tree."""
        self.model().sourceModel().mark_uninstalled(items)

    def openMenu(self, position):
        """Open the RMB context menu."""
        indexes = self.selectedIndexes()

        menu = QtWidgets.QMenu(self)

        show_expand = False
        show_collapse = False
        show_exp_col_all = False

        show_install = False
        show_uninstall = False

        show_edit = False
        show_info = False

        model = self.model()
        source_model = model.sourceModel()

        for index in indexes:
            source_index = model.mapToSource(index)
            node = source_index.internalPointer()

            # We can collapse and expand folder and group nodes.
            if isinstance(node, (models.AOVGroupNode, models.FolderNode)):
                show_exp_col_all = True

                show_collapse = self.isExpanded(index)

                show_expand = not show_collapse

            # Show into item for AOVs and groups.
            if isinstance(node, (models.AOVNode, models.AOVGroupNode)):
                show_info = True

                if isinstance(node, models.IntrinsicAOVGroupNode):
                    show_edit = show_edit or False

                else:
                    show_edit = True

                is_installed = source_model.is_installed(node)

                show_uninstall = is_installed

                show_install = not show_uninstall

        if show_collapse:
            menu.addAction(
                "Collapse",
                self.collapseSelected,
                QtGui.QKeySequence(QtCore.Qt.Key_Left)
            )

        if show_expand:
            menu.addAction(
                "Expand",
                self.expandSelected,
                QtGui.QKeySequence(QtCore.Qt.Key_Right)
            )

        if show_exp_col_all:
            menu.addAction(
                "Collapse All",
                self.collapseBelow
            )

            menu.addAction(
                "Expand All",
                self.expandBelow
            )

            menu.addSeparator()

        menu.addAction(
            "Select All",
            self.selectAll,
            QtGui.QKeySequence.SelectAll
        )

        menu.addSeparator()

        if show_info:
            menu.addAction(
                "Info",
                self.showInfo,
                QtGui.QKeySequence(QtCore.Qt.Key_I),
            )

            menu.addSeparator()

        if show_install:
            menu.addAction(
                "Install",
                self.install_selected,
                QtGui.QKeySequence(QtCore.Qt.Key_Y),
            )

        if show_uninstall:
            menu.addAction(
                "Uninstall",
                self.uninstall_selected,
                QtGui.QKeySequence(QtCore.Qt.Key_U),
            )

        if show_edit:
            menu.addSeparator()

            menu.addAction(
                "Edit",
                self.editSelected,
                QtGui.QKeySequence(QtCore.Qt.Key_E),
            )

        menu.exec_(self.mapToGlobal(position))

    def remove_aov(self, aov):
        """Remove an AOV from the model."""
        self.model().sourceModel().remove_aov(aov)

    def remove_group(self, group):
        """Remove a group from the model."""
        self.model().sourceModel().remove_group(group)

    def selectionChangedHandler(self, selected, deselected):  # pylint: disable=unused-argument
        """Selection change handler."""
        self.selectionChangedSignal.emit()

    def showAOVInfo(self):
        """Show info for selected AOVs."""
        import ht.ui.aovs.dialogs

        aovs = self.getSelectedAOVs()

        parent = hou.qt.mainWindow()

        for aov in aovs:
            info_dialog = ht.ui.aovs.dialogs.AOVInfoDialog(
                aov,
                parent
            )

            info_dialog.show()

    def showAOVGroupInfo(self):
        """Show info for selected AOVGroups."""
        import ht.ui.aovs.dialogs

        groups = self.getSelectedGroups()

        parent = hou.qt.mainWindow()

        for group in groups:
            info_dialog = ht.ui.aovs.dialogs.AOVGroupInfoDialog(
                group,
                parent
            )

            info_dialog.groupUpdatedSignal.connect(self.update_group)

            info_dialog.show()

    def showInfo(self):
        """Show info for selected nodes."""
        self.showAOVInfo()
        self.showAOVGroupInfo()

    def uninstall_selected(self):
        """Uninstall selected nodes."""
        nodes = self.getSelectedNodes()

        if nodes:
            self.uninstallItemsSignal.emit(nodes)

    def update_group(self, group):
        """Update a group's members."""
        self.model().sourceModel().update_group(group)


class AOVInstallBarWidget(QtWidgets.QWidget):
    """This class represents the vertical bar with buttons to install and
    uninstall items from the 'AOVs and Groups' tree.

    """

    installSignal = QtCore.Signal()
    uninstallSignal = QtCore.Signal()

    def __init__(self, parent=None):
        super(AOVInstallBarWidget, self).__init__(parent)

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        # =====================================================================

        self.reload = QtWidgets.QPushButton("")
        layout.addWidget(self.reload)

        self.reload.setIcon(
            hou.qt.createIcon("BUTTONS_reload")
        )
        self.reload.setIconSize(QtCore.QSize(14, 14))
        self.reload.setMaximumSize(QtCore.QSize(20, 20))
        self.reload.setToolTip("Refresh the tree display.")
        self.reload.setFlat(True)

        # =====================================================================

        layout.addStretch(1)

        # =====================================================================

        self.install_button = QtWidgets.QPushButton("")
        layout.addWidget(self.install_button, alignment=QtCore.Qt.AlignVCenter)

        self.install_button.setIcon(
            hou.qt.createIcon("BUTTONS_move_to_right")
        )
        self.install_button.setIconSize(QtCore.QSize(14, 14))
        self.install_button.setMaximumSize(QtCore.QSize(20, 20))
        self.install_button.setToolTip("Add selected to list.")
        self.install_button.setEnabled(False)
        self.install_button.setFlat(True)

        self.install_button.clicked.connect(self.installSignal)

        # =====================================================================

        self.uninstall_button = QtWidgets.QPushButton("")
        layout.addWidget(self.uninstall_button, alignment=QtCore.Qt.AlignVCenter)

        self.uninstall_button.setIcon(
            hou.qt.createIcon("BUTTONS_move_to_left")
        )
        self.uninstall_button.setIconSize(QtCore.QSize(14, 14))
        self.uninstall_button.setMaximumSize(QtCore.QSize(20, 20))
        self.uninstall_button.setToolTip("Remove selected from list.")
        self.uninstall_button.setEnabled(False)
        self.uninstall_button.setFlat(True)

        self.uninstall_button.clicked.connect(self.uninstallSignal)

        # =====================================================================

        layout.addStretch(1)
        layout.setContentsMargins(0, 0, 0, 0)

    # =========================================================================
    # METHODS
    # =========================================================================

    def disableHandler(self):
        """Disable both buttons."""
        self.install_button.setEnabled(False)
        self.uninstall_button.setEnabled(False)

    def enableHandler(self, contains):
        """Enable and disable buttons based on if an item is contained."""
        self.install_button.setEnabled(not contains)
        self.uninstall_button.setEnabled(contains)


class AvailableAOVsToolBar(AOVViewerToolBar):
    """This class represents the toolbar for the 'AOVs and Groups' tree."""

    displayInfoSignal = QtCore.Signal()
    editAOVSignal = QtCore.Signal()
    editGroupSignal = QtCore.Signal()
    newGroupSignal = QtCore.Signal()

    def __init__(self, parent=None):
        super(AvailableAOVsToolBar, self).__init__(parent)

        import ht.ui.aovs.dialogs

        # Button and action to create a new AOV.
        new_aov_button = QtWidgets.QToolButton(self)
        self.addWidget(new_aov_button)

        new_aov_action = QtWidgets.QAction(
            QtGui.QIcon(":ht/rsc/icons/aovs/create_aov.png"),
            "Create a new AOV.",
            self,
            triggered=ht.ui.aovs.dialogs.createNewAOV
        )

        new_aov_button.setDefaultAction(new_aov_action)

        # =====================================================================

        # Button and action to edit an AOV.
        self.edit_aov_button = QtWidgets.QToolButton(self)
        self.addWidget(self.edit_aov_button)

        edit_aov_action = QtWidgets.QAction(
            QtGui.QIcon(":ht/rsc/icons/aovs/edit_aov.png"),
            "Edit AOV.",
            self,
            triggered=self.editAOVSignal.emit
        )

        self.edit_aov_button.setDefaultAction(edit_aov_action)
        self.edit_aov_button.setEnabled(False)

        # =====================================================================

        self.addSeparator()

        # =====================================================================

        # Button and action to create a new AOVGroup.
        new_group_button = QtWidgets.QToolButton(self)
        self.addWidget(new_group_button)

        new_group_action = QtWidgets.QAction(
            QtGui.QIcon(":ht/rsc/icons/aovs/create_group.png"),
            "Create a new AOV group.",
            self,
            triggered=self.newGroupSignal.emit
        )

        new_group_button.setDefaultAction(new_group_action)

        # =====================================================================

        # Button and action to edit an AOVGroup.
        self.edit_group_button = QtWidgets.QToolButton(self)
        self.addWidget(self.edit_group_button)

        edit_group_action = QtWidgets.QAction(
            QtGui.QIcon(":ht/rsc/icons/aovs/edit_group.png"),
            "Edit an AOV group.",
            self,
            triggered=self.editGroupSignal.emit
        )

        self.edit_group_button.setDefaultAction(edit_group_action)
        self.edit_group_button.setEnabled(False)

        # =====================================================================

        self.addSeparator()

        # =====================================================================

        # Button and action to load a .json file.
        load_file_button = QtWidgets.QToolButton(self)
        self.addWidget(load_file_button)

        load_file_action = QtWidgets.QAction(
            hou.qt.createIcon("COMMON_file"),
            "Load AOVs from .json files.",
            self,
            triggered=manager.load_json_files
        )

        load_file_button.setDefaultAction(load_file_action)

        # =====================================================================

        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        self.addWidget(spacer)

        # =====================================================================

        # Button and action to display information for selected items.
        self.info_button = QtWidgets.QToolButton(self)
        self.addWidget(self.info_button)

        info_action = QtWidgets.QAction(
            hou.qt.createIcon("BUTTONS_info"),
            "Display information about the AOV or group.",
            self,
            triggered=self.displayInfoSignal.emit
        )

        self.info_button.setDefaultAction(info_action)
        self.info_button.setEnabled(False)

    # =========================================================================
    # METHODS
    # =========================================================================

    def enableEditAOV(self, enable):
        """Enable the Edit AOV button."""
        self.edit_aov_button.setEnabled(enable)

    def enableEditAOVGroup(self, enable):
        """Enable the Edit AOV Group button."""
        self.edit_group_button.setEnabled(enable)

    def enableInfoButton(self, enable):
        """Enable the View Info button."""
        self.info_button.setEnabled(enable)


class AOVSelectWidget(QtWidgets.QWidget):
    """This class represents the AOVs and Groups widget."""

    # Install and remove signals.
    installSignal = QtCore.Signal(models.AOVBaseNode)
    uninstallSignal = QtCore.Signal(models.AOVBaseNode)

    # Button enabling signals.
    enableEditAOVSignal = QtCore.Signal(bool)
    enableEditAOVGroupSignal = QtCore.Signal(bool)
    enableInfoButtonSignal = QtCore.Signal(bool)

    def __init__(self, parent=None):
        super(AOVSelectWidget, self).__init__(parent)

        layout = QtWidgets.QHBoxLayout()
        self.setLayout(layout)

        tree_layout = QtWidgets.QVBoxLayout()
        layout.addLayout(tree_layout)

        # =====================================================================

        label = QtWidgets.QLabel("AOVs and Groups")
        tree_layout.addWidget(label)

        bold_font = QtGui.QFont()
        bold_font.setBold(True)
        label.setFont(bold_font)

        # =====================================================================

        self.aov_tree = AOVSelectTreeWidget(parent=self)
        tree_layout.addWidget(self.aov_tree)

        self.aov_tree.selectionChangedSignal.connect(self.updateToolButtons)
        self.aov_tree.installItemsSignal.connect(self.installSignal.emit)
        self.aov_tree.uninstallItemsSignal.connect(self.uninstallSignal.emit)

        # =====================================================================

        self.filter = FilterWidget()
        tree_layout.addWidget(self.filter)

        self.filter.field.textChanged.connect(self.aov_tree.proxy_model.setFilterWildcard)

        # =====================================================================

        self.toolbar = AvailableAOVsToolBar(parent=self)
        tree_layout.addWidget(self.toolbar)

        self.toolbar.displayInfoSignal.connect(self.displayInfo)
        self.toolbar.editAOVSignal.connect(self.editAOV)
        self.toolbar.editGroupSignal.connect(self.editGroup)
        self.toolbar.newGroupSignal.connect(self.createGroup)

        # =====================================================================

        self.install_bar = AOVInstallBarWidget()
        layout.addWidget(self.install_bar)

        self.install_bar.installSignal.connect(self.emitInstallSignal)
        self.install_bar.uninstallSignal.connect(self.emitUninstallSignal)
        self.install_bar.reload.clicked.connect(self.reload)

        # =====================================================================

        # Connect signals to update the toolbar.
        self.enableEditAOVSignal.connect(self.toolbar.enableEditAOV)
        self.enableEditAOVGroupSignal.connect(self.toolbar.enableEditAOVGroup)
        self.enableInfoButtonSignal.connect(self.toolbar.enableInfoButton)

    # =========================================================================
    # METHODS
    # =========================================================================

    def createGroup(self):
        """Create a new group using any selected AOVs."""
        import ht.ui.aovs.dialogs

        aovs = [node.item for node in self.aov_tree.getSelectedNodes()
                if isinstance(node.item, AOV)]

        ht.ui.aovs.dialogs.createNewGroup(aovs)

    def displayInfo(self):
        """Display information based on the tree selection."""
        self.aov_tree.showInfo()

    def editAOV(self):
        """Edit selected AOVs."""
        self.aov_tree.editSelectedAOVs()

    def editGroup(self):
        """Edit selected AOVGroups."""
        self.aov_tree.editSelectedGroups()

    def emitInstallSignal(self):
        """Emit a signal to install selected nodes."""
        nodes = self.getSelectedNodes()

        if nodes:
            self.installSignal.emit(nodes)

    def emitUninstallSignal(self):
        """Emit a signal to removal selected nodes."""
        nodes = self.getSelectedNodes()

        if nodes:
            self.uninstallSignal.emit(nodes)

    def getSelectedNodes(self):
        """Get a list of selected nodes in the tree."""
        return self.aov_tree.getSelectedNodes()

    def markItemsInstalled(self, items):
        """Mark items as currently installed in the tree."""
        self.aov_tree.markItemsInstalled(items)

    def markItemsUninstalled(self, items):
        """Mark items as not currently installed in the tree."""
        self.aov_tree.markItemsUninstalled(items)

    def reload(self):
        """Reinitialize the tree from the manager."""
        self.aov_tree.init_from_manager()

    def updateToolButtons(self):
        """Enable toolbar buttons based on node selection."""
        nodes = self.getSelectedNodes()

        enable_edit_aov = False
        enable_edit_group = False
        enable_info = False

        if nodes:
            for node in nodes:
                if isinstance(node, models.AOVNode):
                    enable_edit_aov = True
                    enable_info = True

                elif isinstance(node, models.IntrinsicAOVGroupNode):
                    enable_edit_group = False
                    enable_info = True

                elif isinstance(node, models.AOVGroupNode):
                    enable_edit_group = True
                    enable_info = True

        self.enableEditAOVSignal.emit(enable_edit_aov)
        self.enableEditAOVGroupSignal.emit(enable_edit_group)
        self.enableInfoButtonSignal.emit(enable_info)

# =============================================================================
# AOVs to Apply
# =============================================================================

class AOVsToAddTreeWidget(QtWidgets.QTreeView):
    """This class represents a tree with AOVs and AOVGroups that can be applied
    to a node or render.

    """

    def __init__(self, parent=None):
        super(AOVsToAddTreeWidget, self).__init__(parent)

        self.root = models.TreeNode(None)

        model = models.AOVsToAddModel(self.root)

        self.proxy_model = models.LeafFilterProxyModel()
        self.proxy_model.setSourceModel(model)
        self.setModel(self.proxy_model)

        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

        self.setAlternatingRowColors(True)
        self.setHeaderHidden(True)
        self.setAcceptDrops(True)

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.openMenu)

    # =========================================================================
    # METHODS
    # =========================================================================

    def clear_all(self):
        """Clear all items from the tree."""
        self.model().sourceModel().clear_all()

    def collapseSelected(self):
        """Collapse any selected indexes."""
        indexes = self.selectedIndexes()

        for index in indexes:
            self.collapse(index)

    def dragEnterEvent(self, event):
        """Event occurring when something is dragged into the widget."""
        # Dropping our items.
        if event.mimeData().hasFormat("text/csv"):
            data = pickle.loads(event.mimeData().data("text/csv"))

            if not data:
                event.ignore()

            else:
                event.acceptProposedAction()

        # Dropping Houdini nodes.
#        elif event.mimeData().hasFormat("text/plain"):
#            event.setDropAction(QtCore.Qt.CopyAction)

#            event.accept()

        else:
            event.ignore()

    def dragMoveEvent(self, event):
        event.accept()

    def dropEvent(self, event):
        """Event when dropping items onto widget."""
        # Get the data attached to this event.
        mime_data = event.mimeData()

        # Handle our own drop events.
        if mime_data.hasFormat("text/csv"):
            # Extract the serialized json mime data from the event.
            data = pickle.loads(mime_data.data("text/csv"))

            # Flatten any data when moving with Ctrl.
            if event.keyboardModifiers() == QtCore.Qt.ControlModifier:
                data = utils.flattenList(data)

                # Repack the data with out flattened list.
                mime_data.setData("text/csv", pickle.dumps(data))

        # Try to handle dropping nodes on the tree.
        elif mime_data.hasFormat("text/plain"):
            # Nodes are represented as string paths, possibly comma-separated
            # in the case of multiple nodes.
            data = str(mime_data.data("text/plain"))
            paths = data.split(",")

            found_nodes = False

            new_data = []

            for path in paths:
                node = hou.node(path)

                if node is not None:
                    value = ""
                    aov_parm = node.parm("auto_aovs")

                    if aov_parm is not None:
                        value = aov_parm.eval()

                    names = utils.getAOVNamesFromMultiparm(node)
                    if names:
                        value = "{} {}".format(value, " ".join(names))

                    aovs = manager.MANAGER.get_aovs_from_string(value)

                    if aovs:
                        new_data.extend(aovs)
                        found_nodes = True

            # Allow for Ctrl + Drop to extract groups.
            if event.keyboardModifiers() == QtCore.Qt.ControlModifier:
                new_data = utils.flattenList(new_data)

            # If we've found any nodes we'll add the AOV data and remove the
            # old data.
            if found_nodes:
                mime_data.setData("text/csv", pickle.dumps(new_data))
                mime_data.removeFormat("text/plain")

        # Call the superclass dropEvent() with our possibly modified data to
        # pass the work to the model dropMimeData() method.
        super(AOVsToAddTreeWidget, self).dropEvent(event)

    def expandSelected(self):
        """Expand selected AOVGroups."""
        indexes = self.selectedIndexes()

        for index in indexes:
            self.expand(index)

    def extractSelected(self):
        """Extract AOVs from selected AOVGroups."""
        indexes = self.selectedIndexes()

        model = self.model()

        # Process list in reverse since we're removing things.
        for index in reversed(indexes):
            source_index = model.mapToSource(index)
            node = source_index.internalPointer()

            # Only care about AOVGroupNodes.
            if isinstance(node, models.AOVNode):
                continue

            # Use a reversed list of AOVs since we're inserting them all in the
            # sample position so they maintain their order as shown in the
            # group.
            aovs = reversed(node.group.aovs)
            row = index.row()

            # Remove the AOVGroupNode from the list.
            model.remove_index(index)

            # Add the AOVs from that group to the tree it the groups previous
            # position.
            model.sourceModel().insert_data(aovs, row)

    def getElementsToAdd(self):
        """Get a list of elements in the tree."""
        return self.model().sourceModel().items

    def installItems(self, items):
        """Install items into the tree."""
        self.model().insert_data(items)

    def keyPressEvent(self, event):
        """Handle keystrokes."""
        key = event.key()

        if key == QtCore.Qt.Key_Delete:
            self.remove_selected()
            return

        elif key == QtCore.Qt.Key_E:
            self.extractSelected()
            return

        super(AOVsToAddTreeWidget, self).keyPressEvent(event)

    def nodeIndexInModel(self, node):
        """Given an tree node, attempt to find its index in the trees model."""
        model = self.model()

        root = QtCore.QModelIndex()

        if model.hasChildren(root):
            for i in range(model.rowCount(root)):
                index = model.index(i, 0, root)
                item = model.mapToSource(index).internalPointer()

                if item == node:
                    return index

        return None

    def numItemsToAdd(self):
        """Get the number of items in the tree."""
        return self.model().sourceModel().rowCount(QtCore.QModelIndex())

    def openMenu(self, position):
        """Open the RMB context menu."""
        indexes = self.selectedIndexes()

        menu = QtWidgets.QMenu(self)

        # Expand/collapse
        show_expand = False
        show_collapse = False

        for index in indexes:
            source_index = self.model().mapToSource(index)
            node = source_index.internalPointer()

            if isinstance(node, models.AOVGroupNode):
                show_collapse = self.isExpanded(index)

                show_expand = not show_collapse

        if show_collapse:
            menu.addAction(
                "Collapse",
                self.collapseSelected,
                QtGui.QKeySequence(QtCore.Qt.Key_Left)
            )

        if show_expand:
            menu.addAction(
                "Expand",
                self.expandSelected,
                QtGui.QKeySequence(QtCore.Qt.Key_Right)
            )

        if show_collapse or show_expand:
            menu.addAction(
                "Collapse All",
                self.collapseAll
            )

            menu.addAction(
                "Expand All",
                self.expandAll
            )

            menu.addSeparator()

        menu.addAction(
            "Select All",
            self.selectAll,
            QtGui.QKeySequence.SelectAll
        )

        menu.addAction(
            "Delete",
            self.remove_selected,
            QtGui.QKeySequence.Delete,
        )

        menu.addSeparator()

        show_extract = False

        for index in indexes:
            idx = self.model().mapToSource(index)
            node = idx.internalPointer()

            if isinstance(node, models.AOVGroupNode):
                show_extract = True
                break

        if show_extract:
            menu.addAction(
                "Extract AOVs from group",
                self.extractSelected,
                QtGui.QKeySequence(QtCore.Qt.Key_E),
            )

        menu.exec_(self.mapToGlobal(position))

    def remove_selected(self):
        """Remove selected items."""
        indexes = self.selectedIndexes()

        for index in reversed(indexes):
            self.model().remove_index(index)


class AOVsToAddToolBar(AOVViewerToolBar):
    """This class represents the toolbar for the 'AOVs to Apply' tree."""

    # Signals for applying to nodes.
    applyAtRenderTimeSignal = QtCore.Signal()
    applyToParmsSignal = QtCore.Signal()

    # Signal to create a group from selected things.
    newGroupSignal = QtCore.Signal()

    # Signal to install items to the tree.
    installSignal = QtCore.Signal(list)

    # Signal for clearing all items.
    clearAOVsSignal = QtCore.Signal()

    def __init__(self, parent=None):
        super(AOVsToAddToolBar, self).__init__(parent)

        # Button and action to apply AOVs at render time.
        self.apply_button = QtWidgets.QToolButton(self)
        self.addWidget(self.apply_button)

        apply_action = QtWidgets.QAction(
            hou.qt.createIcon("NETWORKS_rop"),
            "Apply",
            self,
            triggered=self.applyAtRenderTimeSignal.emit

        )

        apply_action.setToolTip("Apply AOVs to selected nodes at render time.")

        self.apply_button.setDefaultAction(apply_action)
        self.apply_button.setEnabled(False)

        # =====================================================================

        # Button and action to apply AOVs are multi parms.
        self.apply_as_parms_button = QtWidgets.QToolButton(self)
        self.addWidget(self.apply_as_parms_button)

        parms_action = QtWidgets.QAction(
            hou.qt.createIcon("PANETYPES_parameters"),
            "Apply AOVs to selected nodes as parameters.",
            self,
            triggered=self.applyToParmsSignal.emit

        )

        self.apply_as_parms_button.setDefaultAction(parms_action)
        self.apply_as_parms_button.setEnabled(False)

        # =====================================================================

        self.addSeparator()

        # =====================================================================

        # Button and action to create a new AOVGroup from chosen items.
        self.new_group_button = QtWidgets.QToolButton(self)
        self.addWidget(self.new_group_button)

        new_group_action = QtWidgets.QAction(
            QtGui.QIcon(":ht/rsc/icons/aovs/create_group.png"),
            "Create a new group from chosen AOVs.",
            self,
            triggered=self.newGroupSignal.emit
        )

        self.new_group_button.setDefaultAction(new_group_action)
        self.new_group_button.setEnabled(False)

        # =====================================================================

        self.addSeparator()

        # =====================================================================

        # Button and action to load from a node.
        load_button = QtWidgets.QToolButton(self)
        self.addWidget(load_button)

        load_action = QtWidgets.QAction(
            hou.qt.createIcon("DATATYPES_node_path"),
            "Load AOVs from a node.",
            self,
            triggered=self.load_from_node
        )

        load_button.setDefaultAction(load_action)

        # =====================================================================

        spacer = QtWidgets.QWidget()
        self.addWidget(spacer)

        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        # =====================================================================

        # Button and action to clear all items from the tree.
        self.clear_button = QtWidgets.QToolButton(self)
        self.addWidget(self.clear_button)

        clear_action = QtWidgets.QAction(
            hou.qt.createIcon("BUTTONS_clear"),
            "Clear all AOVs.",
            self,
            triggered=self.clearAOVsSignal.emit
        )

        self.clear_button.setDefaultAction(clear_action)
        self.clear_button.setEnabled(False)

    # =========================================================================
    # METHODS
    # =========================================================================

    def load_from_node(self, node=None):
        """Populate the tree with AOVs and AOVGroups assigned to selected
        nodes.

        """
        if node is not None:
            nodes = [node]

        else:
            nodes = utils.findSelectedMantraNodes()

        items = []

        for node in nodes:  # pylint: disable=redefined-argument-from-local
            value = ""

            if node.parm("auto_aovs") is not None:
                value = node.evalParm("auto_aovs")

            names = utils.getAOVNamesFromMultiparm(node)

            if names:
                value = "{} {}".format(value, " ".join(names))

            items.extend(manager.MANAGER.get_aovs_from_string(value))

        if items:
            self.installSignal.emit(items)


class AOVsToAddWidget(QtWidgets.QWidget):
    """This class represents the 'AOVs to Apply' widget."""

    updateEnabledSignal = QtCore.Signal()

    def __init__(self, node=None, parent=None):
        super(AOVsToAddWidget, self).__init__(parent)

        self._node = node

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        top_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(top_layout)

        # =====================================================================

        self.label = QtWidgets.QLabel("AOVs to Apply")
        top_layout.addWidget(self.label)

        bold_font = QtGui.QFont()
        bold_font.setBold(True)

        self.label.setFont(bold_font)

        # =====================================================================

        top_layout.addStretch(1)

        # =====================================================================

        top_layout.addWidget(HelpButton("aov_manager"))

        # =====================================================================

        # Tree View
        self.tree = AOVsToAddTreeWidget(parent=self)
        layout.addWidget(self.tree)

        # =====================================================================

        # Tool bar
        self.toolbar = AOVsToAddToolBar(parent=self)
        layout.addWidget(self.toolbar)

        # =====================================================================

        self.toolbar.applyAtRenderTimeSignal.connect(self.applyAtRenderTime)
        self.toolbar.applyToParmsSignal.connect(self.applyAsParms)
        self.toolbar.newGroupSignal.connect(self.createGroup)
        self.toolbar.clearAOVsSignal.connect(self.clearAOVs)
        self.toolbar.installSignal.connect(self.installItems)

        self.tree.model().sourceModel().rowsInserted.connect(self.dataUpdatedHandler)
        self.tree.model().sourceModel().rowsRemoved.connect(self.dataUpdatedHandler)
        self.tree.model().sourceModel().modelReset.connect(self.dataClearedHandler)

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def node(self):
        """The node to apply to."""
        return self._node

    # =========================================================================
    # METHODS
    # =========================================================================

    def applyAsParms(self):
        """Apply AOVs and AOVGroups as multi parms."""
        if self.node is not None:
            nodes = [self.node]

        else:
            nodes = utils.findSelectedMantraNodes()

        if not nodes:
            return

        elements = self.tree.getElementsToAdd()

        utils.applyElementsAsParms(elements, nodes)

    def applyAtRenderTime(self):
        """Apply AOVs and AOVGroups at render time."""
        if self.node is not None:
            nodes = [self.node]

        else:
            nodes = utils.findSelectedMantraNodes()

        if not nodes:
            return

        elements = self.tree.getElementsToAdd()
        utils.applyElementsAsString(elements, nodes)

    def clearAOVs(self):
        """Clear all AOVs and AOVGroups in the tree."""
        self.tree.clear_all()

    def createGroup(self):
        """Create a new AOVGroup from items in the tree."""
        import ht.ui.aovs.dialogs

        aovs = utils.flattenList(self.tree.getElementsToAdd())

        ht.ui.aovs.dialogs.createNewGroup(aovs)

    def dataClearedHandler(self):
        """Handle the tree being cleared."""
        self.toolbar.apply_button.setEnabled(False)
        self.toolbar.apply_as_parms_button.setEnabled(False)
        self.toolbar.new_group_button.setEnabled(False)
        self.toolbar.clear_button.setEnabled(False)

        self.updateEnabledSignal.emit()

    def dataUpdatedHandler(self, index, start, end):  # pylint: disable=unused-argument
        """Handle the tree being updated."""
        enable = self.tree.numItemsToAdd() > 0

        self.toolbar.apply_button.setEnabled(enable)
        self.toolbar.apply_as_parms_button.setEnabled(enable)
        self.toolbar.new_group_button.setEnabled(enable)
        self.toolbar.clear_button.setEnabled(enable)

        self.updateEnabledSignal.emit()

    def installItems(self, items):
        """Install items into the tree."""
        self.tree.installItems(items)

    def installListener(self, nodes):
        """Listen for items to be installed."""
        items = []

        for node in nodes:
            if isinstance(node, models.FolderNode):
                items.extend(node.items)

            else:
                items.append(node.item)

        self.installItems(items)

    def setNode(self, node):
        """Register a node as the target apply node."""
        self._node = node

        # Update the top label to indicate that we are targeting a specific
        # node when applying.
        self.label.setText("AOVs to Apply - {}".format(node.path()))

        # Initialize the tree by loading the AOVs from the target node.
        self.toolbar.load_from_node(node)

    def uninstallListener(self, nodes):
        """Listen for items to be removed."""
        model = self.tree.model()

        for node in nodes:
            # Look for the index of the node to remove.
            index = self.tree.nodeIndexInModel(node)

            # If the node exists, remove its index from the source model
            if index is not None:
                model.remove_index(index)

# =============================================================================
# New Group Widgets
# =============================================================================

class NewGroupAOVListWidget(QtWidgets.QListView):
    """This widget allows editing of group AOV membership."""

    def __init__(self, parent=None):
        super(NewGroupAOVListWidget, self).__init__(parent)

        self.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)

        model = models.AOVGroupEditListModel()

        self.proxy_model = QtCore.QSortFilterProxyModel()
        self.proxy_model.setSourceModel(model)
        self.proxy_model.sort(QtCore.Qt.AscendingOrder)

        self.setModel(self.proxy_model)

        self.setAlternatingRowColors(True)

    def getSelectedAOVs(self):
        """Get a list of selected AOVs."""
        return self.proxy_model.sourceModel().checked_aovs()


# =============================================================================
# Info Widgets
# =============================================================================

class InfoTableView(QtWidgets.QTableView):
    """This class represents a generic table view for information."""
    def __init__(self, parent=None):
        super(InfoTableView, self).__init__(parent)

        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.setWordWrap(False)

        h_header = self.horizontalHeader()
        h_header.setVisible(False)
        h_header.setStretchLastSection(True)
        h_header.resizeSection(0, 250)

    def contextMenuEvent(self, event):
        """Handle RMB menu clicks."""
        index = self.indexAt(event.pos())

        if not index.isValid():
            return

        # Create a menu.
        menu = QtWidgets.QMenu(self)

        # Create an entry to copy cells.
        copy_action = QtWidgets.QAction("Copy", self)
        menu.addAction(copy_action)

        copy_action.setShortcut(
            QtGui.QKeySequence(QtCore.Qt.CTRL + QtCore.Qt.Key_C)
        )

        # Display the menu and get the choice..
        action = menu.exec_(event.globalPos())

        # Copy the cell.
        if action == copy_action:
            self.copyCell(index)

    def copyCell(self, index):
        """Copy the contents of a table cell to the clipboard."""
        result = self.model().data(index)

        if result is not None:
            clipboard = QtGui.QApplication.clipboard()  # pylint: disable=c-extension-no-member
            clipboard.setText(result)


class AOVInfoTableView(InfoTableView):
    """This class represents the AOV information table."""
    def __init__(self, aov, parent=None):
        super(AOVInfoTableView, self).__init__(parent)

        model = models.AOVInfoTableModel()
        model.init_data_from_aov(aov)
        self.setModel(model)


class AOVGroupInfoTableWidget(InfoTableView):
    """This class represents the AOVGroup information table."""
    def __init__(self, group, parent=None):
        super(AOVGroupInfoTableWidget, self).__init__(parent)

        model = models.AOVGroupInfoTableModel()
        model.init_data_from_group(group)
        self.setModel(model)


class GroupMemberListWidget(QtWidgets.QListView):
    """This widget is for displaying AOVGroup membership."""
    def __init__(self, group, parent=None):
        super(GroupMemberListWidget, self).__init__(parent)

        model = models.AOVGroupMemberListModel()

        self.proxy_model = QtCore.QSortFilterProxyModel()
        self.proxy_model.setSourceModel(model)
        self.proxy_model.sort(QtCore.Qt.AscendingOrder)

        self.setModel(self.proxy_model)

        self.setAlternatingRowColors(True)

        model.init_data_from_group(group)


# =============================================================================
# Generic Widgets
# =============================================================================

class ComboBox(QtWidgets.QComboBox):
    """Custom ComboBox class."""
    def __init__(self, parent=None):
        super(ComboBox, self).__init__(parent)

        self.setView(QtWidgets.QListView())


class FileChooser(QtWidgets.QWidget):
    """This class represents a file choosing widget."""

    def __init__(self, parent=None):
        super(FileChooser, self).__init__(parent)

        layout = QtWidgets.QHBoxLayout()
        self.setLayout(layout)

        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # =====================================================================

        self.field = QtWidgets.QLineEdit()
        layout.addWidget(self.field)

        # =====================================================================

        self.button = QtWidgets.QPushButton(
            hou.qt.createIcon("BUTTONS_chooser_file"),
            ""
        )
        layout.addWidget(self.button)

        self.button.setFlat(True)
        self.button.setIconSize(QtCore.QSize(16, 16))
        self.button.setMaximumSize(QtCore.QSize(24, 24))

        self.button.clicked.connect(self.chooseFile)

    # =========================================================================
    # METHODS
    # =========================================================================

    def chooseFile(self):
        """Open the file chooser dialog."""
        current = self.getPath()

        start_directory = None
        default_value = None

        if current:
            start_directory = os.path.dirname(current)
            default_value = os.path.basename(current)

        path = hou.ui.selectFile(
            start_directory=start_directory,
            pattern="*.json",
            default_value=default_value,
            chooser_mode=hou.fileChooserMode.Write
        )

        if not path:
            return

        ext = os.path.splitext(path)[1]

        if not ext:
            path = "{}.json".format(path)

        self.setPath(path)

    def enable(self, enable):
        """Set the UI element's enabled state."""
        self.field.setEnabled(enable)
        self.button.setEnabled(enable)

    def getPath(self):
        """Get the text."""
        return self.field.text()

    def setPath(self, path):
        """Set the path."""
        self.field.setText(path)


class FilterWidget(QtWidgets.QWidget):
    """This class represents a Filter widget."""

    def __init__(self, parent=None):
        super(FilterWidget, self).__init__(parent)

        layout = QtWidgets.QHBoxLayout()
        self.setLayout(layout)

        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QtWidgets.QLabel("Filter"))

        self.field = QtWidgets.QLineEdit()
        layout.addWidget(self.field)

        self.field.setToolTip("Filter the list of AOVs by name.")


class HelpButton(QtWidgets.QPushButton):
    """Generic Help button."""

    def __init__(self, name, parent=None):
        super(HelpButton, self).__init__(
            hou.qt.createIcon("BUTTONS_help"),
            "",
            parent=parent
        )

        self._name = name

        self.setToolTip("Show Help.")
        self.setIconSize(QtCore.QSize(14, 14))
        self.setMaximumSize(QtCore.QSize(14, 14))
        self.setFlat(True)

        self.clicked.connect(self.displayHelp)

    # =========================================================================
    # METHODS
    # =========================================================================

    def displayHelp(self):
        """Display help page."""
        # Look for an existing, float help browser.
        for pane_tab in hou.ui.paneTabs():
            if isinstance(pane_tab, hou.HelpBrowser):
                if pane_tab.isFloating():
                    browser = pane_tab
                    break

        # Didn't find one, so create a new floating browser.
        else:
            desktop = hou.ui.curDesktop()
            browser = desktop.createFloatingPaneTab(hou.paneTabType.HelpBrowser)

        browser.displayHelpPath("/aov_manager/{}".format(self._name))


class MenuFieldMode(object):
    """Mode settings for MenuFields."""

    Replace = 0
    Toggle = 1


class MenuField(QtWidgets.QWidget):
    """This class represents a crappy attempt at a Replace/Toggle style
    string menu.

    """

    def __init__(self, menu_items, mode=MenuFieldMode.Replace, parent=None):
        super(MenuField, self).__init__(parent)

        layout = QtWidgets.QHBoxLayout()
        self.setLayout(layout)

        layout.setSpacing(1)
        layout.setContentsMargins(0, 0, 0, 0)

        # =====================================================================

        self.field = QtWidgets.QLineEdit()
        layout.addWidget(self.field)

        # =====================================================================

        button = QtWidgets.QPushButton()
        layout.addWidget(button)

        button.setProperty("menu", True)

        menu = QtWidgets.QMenu(button)

        for item in menu_items:
            label, value = item

            action = menu.addAction(label)

            if mode == MenuFieldMode.Replace:
                action.triggered.connect(
                    lambda val=value: self.set(val)
                )

            elif mode == MenuFieldMode.Toggle:
                action.triggered.connect(
                    lambda val=value: self.toggle(val)
                )

        button.setMenu(menu)

    # =========================================================================
    # METHODS
    # =========================================================================

    def set(self, value):
        """Set the field to a value."""
        self.field.setText(value)

    def toggle(self, value):
        """Toggle a value in the field."""
        text = self.value()

        if value in text:
            text = text.replace(value, "")

            self.set(text.strip())

        else:
            if not text:
                text = value

            else:
                text = "{} {}".format(text, value)

            self.set(text)

    def value(self):
        """The field value."""
        return self.field.text()


class StatusMessageWidget(QtWidgets.QWidget):
    """This class represents an status notification widget."""

    Error = 0
    Warning = 1
    Info = 2

    def __init__(self, parent=None):
        super(StatusMessageWidget, self).__init__(parent)

        self._error_mappings = {}
        self._warning_mappings = {}
        self._info_mappings = {}

        self.setContentsMargins(0, 0, 0, 0)

        layout = QtWidgets.QHBoxLayout()
        self.setLayout(layout)

        layout.setContentsMargins(0, 0, 0, 0)

        self.info_pixmap = hou.qt.createIcon("DIALOG_info").pixmap(24, 24)
        self.warning_pixmap = hou.qt.createIcon("DIALOG_warning").pixmap(24, 24)
        self.error_pixmap = hou.qt.createIcon("DIALOG_error").pixmap(24, 24)

        # =====================================================================

        self.icon = QtWidgets.QLabel()
        layout.addWidget(self.icon)

        self.icon.setFixedSize(24, 24)
        self.icon.setPixmap(self.info_pixmap)
        self.icon.hide()

        # =====================================================================

        self.display = QtWidgets.QLabel()
        layout.addWidget(self.display)

        self.setFixedHeight(24)

    # =========================================================================
    # METHODS
    # =========================================================================

    def addError(self, level, msg):
        """Add an error message at a specific level."""
        self._error_mappings[level] = msg
        self.updateDisplay()

    def addInfo(self, level, msg):
        """Add a display message at a specific level."""
        self._info_mappings[level] = msg
        self.updateDisplay()

    def addWarning(self, level, msg):
        """Add a warning message at a specific level."""
        self._warning_mappings[level] = msg
        self.updateDisplay()

    def clear(self, level):
        """Clear all notifications for a level."""
        self.clearError(level)
        self.clearWarning(level)
        self.clearInfo(level)

    def clearError(self, level):
        """Clear any error messages at a specific level."""
        if level in self._error_mappings:
            del self._error_mappings[level]

        self.updateDisplay()

    def clearInfo(self, level):
        """Clear any info messages at a specific level."""
        if level in self._info_mappings:
            del self._info_mappings[level]

        self.updateDisplay()

    def clearWarning(self, level):
        """Clear any warning messages at a specific level."""
        if level in self._warning_mappings:
            del self._warning_mappings[level]

        self.updateDisplay()

    def getMessage(self):
        """Get the current error/warning/info value, if any."""
        if self._error_mappings:
            highest = sorted(self._error_mappings.keys())[0]

            self.icon.setPixmap(self.error_pixmap)
            return self._error_mappings[highest]

        elif self._warning_mappings:
            highest = sorted(self._warning_mappings.keys())[0]

            self.icon.setPixmap(self.warning_pixmap)
            return self._warning_mappings[highest]

        elif self._info_mappings:
            highest = sorted(self._info_mappings.keys())[0]

            self.icon.setPixmap(self.info_pixmap)
            return self._info_mappings[highest]

        return ""

    def updateDisplay(self):
        """Update the display items."""
        error = self.getMessage()

        # Ensure everything is shown and the message is correct.
        if error:
            self.display.setText(error)
            self.display.show()
            self.icon.show()

        # Clear existing messages and hide the elements.
        else:
            self.display.clear()
            self.display.hide()
            self.icon.hide()


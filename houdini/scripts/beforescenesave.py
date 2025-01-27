"""Perform any registered before scene save events."""

# =============================================================================
# IMPORTS
# =============================================================================

# Houdini Toolbox Imports
from ht.events import SceneEvents, run_event


# =============================================================================

run_event(SceneEvents.PreSave, kwargs)  # pylint: disable=undefined-variable


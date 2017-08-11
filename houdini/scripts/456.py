"""Perform tasks when a .hip file is loaded."""

# =============================================================================
# IMPORTS
# =============================================================================

# Houdini Toolbox Imports
from ht.events import SceneEvents, runEvent

# =============================================================================
# FUNCTIONS
# =============================================================================

def main():
    """Main function."""
    runEvent(SceneEvents.Load)

# =============================================================================

main()


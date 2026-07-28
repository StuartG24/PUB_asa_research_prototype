#
# Utility Functions
#

# ---------------------------------------------------------------------------
#
# Logging
# with a global logging DEBUG level flag
# Levels are DEBUG, INFO, WARNING
# Output changed from stderr to stdout so that is in line with any other print output

""" Custom application logging 
Use in .py and .pynb
- import logging
- log = logging.getLogger(__name__)
Levels are 
- DEBUG (Default)
- INFO
- WARNING

A local overide of the app debug level
- from asa._tools.custom_logging import setup_logging
- logging.getLogger("[file path and name]").setLevel(logging.DEBUG)
"""

import logging
import sys


def setup_logging(*, level: int | str = "DEBUG"):
    # Attach ONE handler to the root logger (→ stdout), set the format, and set the
    # root threshold to WARNING so third-party libs stay quiet. force=True clears any
    # handlers already installed, so re-running a notebook cell won't stack duplicates.
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s: %(name)s.%(funcName)s.line_%(lineno)d - %(message)s",
        stream=sys.stdout,
        force=True,
    )

    # Raise the app's own loggers; third-party libs stay at the root WARNING default.
    # Each module logs via getLogger(__name__), so set the level on common ancestors, inheritance do rest:
    #   "asa"      → every asa.* module (cli, session, …)
    #   "__main__" → entry points run as a script/notebook

    for name in ("asa", "__main__"):
        logging.getLogger(name).setLevel(level)

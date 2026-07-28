"""asa — research prototype for a basic Artificial Social Agent.

Exposes the session at the top level, so callers write ``from asa import ASASession``.
"""

from importlib.metadata import version

from asa.session import ASASession, FurhatUnreachable

# Read the version from the installed metadata, not hardcoded that can drift from pyproject.toml.
__version__ = version("asa-research-prototype")

# Publish the calls
__all__ = ["ASASession", "FurhatUnreachable", "__version__"]

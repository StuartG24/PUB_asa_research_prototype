"""asa — research prototype for a basic Artificial Social Agent.

Exposes the demo greeter at the top level, so callers write ``from asa import Greeter``.
"""

from importlib.metadata import version

from asa.greeter import Greeter

# Read the version from the installed metadata, not hardcoded that can drift from pyproject.toml.
__version__ = version("asa-research-prototype")

# Publish the calls
__all__ = ["Greeter", "__version__"]

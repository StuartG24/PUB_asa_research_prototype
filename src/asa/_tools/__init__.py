"""Internal development utilities — not part of the public asa API.

Deliberately private (the leading underscore): these are for use from notebooks and the
occasional script during development, and carry no stability promise. Nothing here is
re-exported from ``asa/__init__.py``, so ``from asa import ...`` will never reach them.

Import the specific tool you want rather than adding re-exports here, e.g.::

    from asa._tools.depreport import report
"""

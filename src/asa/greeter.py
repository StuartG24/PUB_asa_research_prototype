#
# Greeter Class Placeholder
#


"""A minimal hello-world class — placeholder until real ASA code arrives."""


class Greeter:
    """Produce a friendly greeting.

    Parameters
    ----------
    name:
        Who to greet. Defaults to ``"World"``.
    """

    def __init__(self, name: str = "World") -> None:
        self.name = name

    def greet(self) -> str:
        """Return the greeting string, e.g. ``"Hello, World!"``."""
        return f"Hello, {self.name}!"

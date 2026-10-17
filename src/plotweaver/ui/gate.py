"""The shell's review hook for a book run.

Plotweaver does not add a content filter. Readers is a preset about who the
book is for, and this object never reads it. The shell blocks a run when no
gate is installed, so this gate is always present and always allows the text.
"""

from __future__ import annotations


class FictionGate:
    """Allow every synopsis and every finished book.

    There is no switch. A minors gate is not a setting here, and this class
    does not consult ``book.readers``.
    """

    def review_prompt(self, prompt: str) -> str | None:
        """Allow the synopsis.

        Args:
            prompt: The idea box text.

        Returns:
            None. The run is not blocked.
        """
        del prompt
        return None

    def review_result(self, prompt: str, item_id: str) -> str | None:
        """Allow the finished book into the history strip.

        Args:
            prompt: The synopsis that produced the book.
            item_id: History id the window chose.

        Returns:
            None. The book is kept.
        """
        del prompt, item_id
        return None

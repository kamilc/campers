"""Selection dataclass for text range representation."""

from dataclasses import dataclass


@dataclass
class Selection:
    """Represents a text selection range in a log widget.

    Parameters
    ----------
    start : tuple[int, int]
        Start position as (line, column) tuple
    end : tuple[int, int]
        End position as (line, column) tuple

    Attributes
    ----------
    start : tuple[int, int]
        Start position as (line, column) tuple
    end : tuple[int, int]
        End position as (line, column) tuple
    """

    start: tuple[int, int]
    end: tuple[int, int]

    @property
    def normalized(self) -> tuple[tuple[int, int], tuple[int, int]]:
        """Return normalized selection with start before end.

        Returns
        -------
        tuple[tuple[int, int], tuple[int, int]]
            Tuple of (start, end) with start <= end
        """
        if self.start <= self.end:
            return self.start, self.end
        return self.end, self.start

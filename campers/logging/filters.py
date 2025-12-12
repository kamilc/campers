"""Logging filters for stream routing."""

import logging

from campers.constants import STREAM_TYPE_STDERR, STREAM_TYPE_STDOUT


class StreamRoutingFilter(logging.Filter):
    """Filter that routes log records based on stream extra parameter.

    Parameters
    ----------
    stream_type : str
        Stream type to allow: "stdout" or "stderr"

    Raises
    ------
    ValueError
        If stream_type is not "stdout" or "stderr"
    """

    def __init__(self, stream_type: str) -> None:
        """Initialize filter.

        Parameters
        ----------
        stream_type : str
            Stream type to allow: "stdout" or "stderr"

        Raises
        ------
        ValueError
            If stream_type is not "stdout" or "stderr"
        """
        super().__init__()
        if stream_type not in (STREAM_TYPE_STDOUT, STREAM_TYPE_STDERR):
            raise ValueError(
                f"Invalid stream_type: '{stream_type}'. "
                f"Must be '{STREAM_TYPE_STDOUT}' or '{STREAM_TYPE_STDERR}'"
            )
        self.stream_type = stream_type

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log records by stream type.

        Parameters
        ----------
        record : logging.LogRecord
            Log record to filter

        Returns
        -------
        bool
            True if record should be emitted by this handler
        """
        record_stream = getattr(record, "stream", None)

        if record_stream is None:
            return self.stream_type == STREAM_TYPE_STDERR

        return record_stream == self.stream_type

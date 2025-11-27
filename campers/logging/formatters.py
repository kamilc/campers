"""Logging formatters for stream routing."""

import logging


class StreamFormatter(logging.Formatter):
    """Logging formatter that prepends stream tags based on extra parameter."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with stream prefix if present.

        Parameters
        ----------
        record : logging.LogRecord
            Log record to format

        Returns
        -------
        str
            Formatted log message with optional stream prefix
        """
        msg = super().format(record)
        stream = getattr(record, "stream", None)

        if stream == "stdout":
            return f"[stdout] {msg}"
        elif stream == "stderr":
            return f"[stderr] {msg}"

        return msg

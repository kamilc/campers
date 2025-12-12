"""Logging formatters for stream routing."""

import logging


class StreamFormatter(logging.Formatter):
    """Logging formatter that returns just the message without prefixes."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record.

        Stream routing is handled by StreamRoutingFilter, so the formatter
        just returns the formatted message without any prefix.

        Parameters
        ----------
        record : logging.LogRecord
            Log record to format

        Returns
        -------
        str
            Formatted log message
        """
        return super().format(record)

#!/usr/bin/env python3
# /// script
# dependencies = [
#   "boto3>=1.40.0",
#   "PyYAML>=6.0",
#   "fire>=0.7.0",
#   "textual>=0.47.0",
# ]
# ///

"""Moondock - EC2 remote development tool."""

import fire


class Moondock:
    """Main CLI interface for moondock."""

    def hello(self) -> str:
        """Test command to validate Fire CLI works.

        Returns
        -------
        str
            Version and status message confirming skeleton is ready.

        """
        return "moondock v0.1.0 - skeleton ready"


def main() -> None:
    """Entry point for Fire CLI.

    This function initializes the Fire CLI interface by passing the Moondock
    class to Fire, which automatically generates CLI commands from the class
    methods. The function should be called when the script is executed directly.

    Notes
    -----
    Fire automatically maps class methods to CLI commands and handles argument
    parsing, help text generation, and command routing.

    """
    fire.Fire(Moondock)


if __name__ == "__main__":
    main()

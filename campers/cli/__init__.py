"""CLI argument parsing and handling."""

from __future__ import annotations

from campers.cli.parsing import (
    apply_cli_overrides,
    normalize_ports_config,
    parse_ignore_patterns,
    parse_include_vcs,
    parse_port_parameter,
)

__all__ = [
    "apply_cli_overrides",
    "normalize_ports_config",
    "parse_port_parameter",
    "parse_include_vcs",
    "parse_ignore_patterns",
]

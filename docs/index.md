# Campers

<p align="center">
  <img src="assets/campers.png" alt="Campers" width="400">
</p>

**Campers** is a command-line tool for managing remote development environments on AWS EC2. It handles the full lifecycle of cloud development machines: provisioning instances, synchronizing files, forwarding ports, and executing commands.

## Features

- **Instance Management**: Launch, stop, start, and destroy EC2 instances with a single command
- **File Synchronization**: Bidirectional sync between local and remote directories using Mutagen
- **Port Forwarding**: Automatic SSH tunnels for accessing remote services (Jupyter, databases, etc.)
- **Ansible Provisioning**: Declarative, idempotent instance setup with reusable playbooks
- **Environment Forwarding**: Securely forward local environment variables to remote instances
- **Named Configurations**: Define multiple "camps" for different workloads (dev, jupyter, gpu)
- **Variable Interpolation**: DRY configuration with reusable variables

## Quick Install

```bash
pip install campers
```

Or run directly without installation using [uv](https://docs.astral.sh/uv/):

```bash
uvx campers run
uvx campers list
```

## Quick Start

```bash
campers init      # Generate a configuration file
campers run       # Launch an instance with defaults
campers run jupyter  # Launch a named camp
campers list      # List running instances
campers stop dev  # Stop an instance (preserves data)
campers destroy dev  # Destroy an instance
```

## How It Works

1. **Define camps** in `campers.yaml` - named configurations for different workloads
2. **Run `campers run`** - provisions an EC2 instance, syncs files, forwards ports
3. **Work remotely** - your local files sync bidirectionally with the instance
4. **Exit** - instance stops (or terminates) automatically, preserving your work

## Next Steps

- [Getting Started](getting-started.md) - Installation and your first camp
- [Configuration](configuration.md) - Full reference for `campers.yaml`
- [Commands](commands.md) - All CLI commands explained
- [Examples](examples.md) - Real-world configuration recipes

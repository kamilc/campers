# Campers

<p align="center">
  <img src="docs/assets/campers.png" alt="Campers" width="400">
</p>

<p align="center">
  <strong>Remote development environments on AWS EC2</strong>
</p>

<p align="center">
  <a href="https://kamilc.github.io/campers">Documentation</a> •
  <a href="https://kamilc.github.io/campers/getting-started/">Getting Started</a> •
  <a href="https://kamilc.github.io/campers/examples/">Examples</a>
</p>

---

Campers is a command-line tool for managing remote development environments on AWS EC2. It handles the full lifecycle of cloud development machines: provisioning instances, synchronizing files, forwarding ports, and executing commands.

## Features

- **Instance Management**: Launch, stop, start, and destroy EC2 instances with a single command
- **File Synchronization**: Bidirectional sync between local and remote directories using Mutagen
- **Port Forwarding**: Automatic SSH tunnels for accessing remote services (Jupyter, databases, etc.)
- **Ansible Provisioning**: Declarative, idempotent instance setup with reusable playbooks
- **Environment Forwarding**: Securely forward local environment variables to remote instances
- **Named Configurations**: Define multiple "camps" for different workloads (dev, jupyter, gpu)

## Quick Start

```bash
# Install
pip install campers

# Or run with uv (no install needed)
uvx campers run

# Generate config and launch
campers init
campers run
```

## Documentation

Full documentation is available at **[kamilc.github.io/campers](https://kamilc.github.io/campers)**

- [Getting Started](https://kamilc.github.io/campers/getting-started/) - Installation and first camp
- [Configuration](https://kamilc.github.io/campers/configuration/) - Full YAML reference
- [Commands](https://kamilc.github.io/campers/commands/) - CLI reference
- [Examples](https://kamilc.github.io/campers/examples/) - Real-world recipes

## License

MIT

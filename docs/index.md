# Campers

<p align="center">
  <img src="assets/campers.png" alt="Campers" width="400">
</p>

<h3 align="center">
  Local development experience. Remote cloud resources.
</h3>

**Campers** is a command-line tool that bridges the gap between your local machine and the cloud. It manages ephemeral AWS instances that feel like `localhost`.

<p align="center">
  <img src="assets/infographic.jpg" alt="Campers Workflow Infographic" width="100%">
</p>

## Why Campers?

- **Infinite Compute:** Offload heavy compilation (C++/Rust), AI model training, or microservice stacks to high-powered cloud instances.
- **Local Experience:** Your code stays on your laptop. You use your own VS Code, Vim, or IDE. Campers syncs changes instantly.
- **Data Compliance:** Keep PII and sensitive data in a compliant cloud region without it ever touching your laptop.
- **Cost Control:** Instances are disposable. Spin them up for a task, destroy them when done.

## Key Features

- **Mutagen Sync**: Real-time, bidirectional file synchronization (sub-20ms latency).
- **Auto-Port Forwarding**: Access remote web apps and Jupyter notebooks via `localhost`.
- **Ansible Provisioning**: Configure instances with standard Ansible playbooks.
- **TUI Dashboard**: Monitor logs, sync status, and instance health in a beautiful terminal interface.

## Quick Install

```bash
pip install campers
```

Or run directly without installation using [uv](https://docs.astral.sh/uv/):

```bash
uvx campers run
```

## Next Steps

- [Getting Started](getting-started.md) - Zero-to-hero guide
- [Configuration](configuration.md) - Full reference for `campers.yaml`
- [Commands](commands.md) - CLI reference
- [Examples](examples.md) - Real-world recipes (Data Science, Web, Systems)
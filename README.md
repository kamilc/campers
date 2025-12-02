# Campers

<p align="center">
  <img src="docs/assets/campers.png" alt="Campers" width="400">
</p>

Campers is a command-line tool that manages disposable remote development environments on the cloud (currently AWS EC2). It allows you to offload heavy computation to the cloud while keeping your local development workflow intact.

It bridges the gap between your local machine and a cloud instance by handling provisioning, file synchronization, and network tunneling automatically.

## How you use it

The goal of Campers is to make a remote cloud instance feel like localhost.

Imagine you are working on a resource-intensive project, like a large microservices stack or a deep learning model. Your local machine is struggling with heat and memory limits.

With Campers, the workflow looks like this:

1.  **Configuration**: You add a `campers.yml` file to your project root. This defines the hardware you need (e.g., an instance type like `p3.2xlarge`), the setup steps, and which ports to forward.

2.  **Spin Up**: You run `campers run` in your terminal.
    In the background, Campers provisions the instance, configures it (via shell scripts or Ansible), and establishes a real-time, two-way file sync using Mutagen.

3.  **Development**: You stay on your laptop.
    *   You edit code in your local editor (VS Code, Vim, etc.). Changes are synced instantly to the cloud instance.
    *   You run your application on the remote instance.
    *   You access the application via `localhost` in your browser. Campers tunnels the traffic through SSH automatically.

4.  **Stop or Destroy**:
    *   **Stop**: If you simply close Campers (Ctrl+C), the instance is stopped but preserved. Storage is kept, so you can resume work later by running `campers run` again. You only pay for storage while stopped.
    *   **Destroy**: To completely remove the instance and stop all costs, run `campers destroy`.

## Use Cases

**Data Science & Pipelines**
Ideal for ad-hoc data science projects. Run resource-intensive data pipelines or train models on high-end cloud hardware.

It also solves **data residency** challenges. Many organizations strictly prohibit storing PII on developer laptops. By spinning up a camp in a compliant cloud region, you can develop against real datasets without ever downloading sensitive data to your local machine.

**Isolated Environments**
Instead of cluttering your local machine with databases and system dependencies, you can define a clean, reproducible environment for each project. If the environment breaks, you simply destroy it and create a new one.

**Heavy Compilation**
If you are compiling large C++ or Rust projects, you can provision a high-core instance (like a `c6a.24xlarge`) for the duration of the build. You get the build speed of a workstation without maintaining the hardware.

## Features

- **Mutagen Sync**: Uses Mutagen for high-performance, conflict-aware file synchronization.
- **Automatic Port Forwarding**: Tunnels remote ports to your local machine based on your configuration.
- **Ansible Integration**: Supports running Ansible playbooks to configure the instance on startup.
- **Cost Control**: Encourages an ephemeral workflow where instances are destroyed when not in use.
- **TUI Dashboard**: A terminal interface to monitor logs, sync status, and instance health.

## Quick Start

```bash
# Install via pip
pip install campers

# Or run instantly with uv (recommended)
uvx campers run

# Initialize a configuration in your current directory
campers init

# Spin up your camp
campers run
```

## Documentation

Full documentation is available at **[kamilc.github.io/campers](https://kamilc.github.io/campers)**

- [Getting Started](https://kamilc.github.io/campers/getting-started/)
- [Configuration Reference](https://kamilc.github.io/campers/configuration/)
- [CLI Commands](https://kamilc.github.io/campers/commands/)
- [Examples](https://kamilc.github.io/campers/examples/)

## License

MIT

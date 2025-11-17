# Moondock Test Suite

This directory contains the complete test suite for the Moondock project, organized into unit tests and integration tests (BDD).

## Directory Structure

```
tests/
├── unit/                          # Unit tests and test utilities
│   ├── test_*.py                  # Unit test files (pytest)
│   ├── conftest.py                # Pytest configuration and fixtures
│   ├── harness/                   # Test harness implementations
│   │   ├── __init__.py
│   │   ├── base.py                # Base harness class
│   │   ├── dry_run.py             # DryRunHarness implementation
│   │   ├── local_stack.py         # LocalStackHarness implementation
│   │   └── ...
│   └── fakes/                     # Fake implementations for testing
│       ├── __init__.py
│       ├── ec2.py                 # Fake EC2 implementations
│       └── ...
├── integration/                   # BDD integration tests
│   ├── features/                  # Gherkin feature files
│   │   ├── *.feature              # Feature specifications
│   │   ├── steps/                 # Step implementations
│   │   │   ├── __init__.py
│   │   │   ├── *_steps.py         # Step definition files
│   │   │   └── ...
│   │   ├── support/               # Support files for BDD
│   │   └── environment.py         # Behave environment configuration
│   ├── behave.ini                 # Behave configuration
│   └── environment.py             # (symlink to features/environment.py)
└── README.md                      # This file

## Testing Strategy

The test suite is organized into two complementary testing approaches:

### Unit Tests (`tests/unit/`)

Unit tests verify individual components in isolation using pytest. These tests are fast and run against mock/fake implementations to verify business logic and component behavior without external dependencies.

**Characteristics:**
- Fast execution (~35 seconds for ~381 tests)
- Run against mocked/fake AWS services
- Test individual units in isolation
- Use pytest fixtures from conftest.py
- Include harness tests for the test infrastructure itself

**Key Components:**

#### Harness System
The test harness provides a pluggable architecture for different testing environments:

- **DryRunHarness**: Validates AWS API calls without executing them
- **LocalStackHarness**: Runs against LocalStack for local AWS simulation
- **PilotExtension**: Extends harness functionality for TUI testing

#### Fake Implementations
Located in `tests/unit/fakes/`, these provide mock AWS service implementations:
- EC2 instance management
- SSH key handling
- Port allocation and forwarding
- Security group operations

### Integration Tests (`tests/integration/`)

Integration tests use Behave (BDD framework) to test end-to-end scenarios. These tests verify that components work together correctly and that user-visible behavior matches specifications.

**Characteristics:**
- Slower execution (~15-20 minutes full run)
- Test complete user workflows
- Run against real or simulated AWS resources
- Written in Gherkin syntax for readability
- Include dry-run support for validation without side effects

**Test Coverage:**
- ~28 feature files
- ~190 scenarios
- CLI command interactions
- EC2 lifecycle management
- SSH connectivity and tunneling
- Data synchronization
- Configuration management
- TUI interactions

## Running Tests

### Quick Validation (Recommended During Development)

```bash
just test-fast
```

This runs:
1. Unit tests with fail-fast (`pytest -x`)
2. BDD scenarios with stop on first failure (`behave --stop`)

Expected completion: ~1-2 minutes

### Full Unit Tests

```bash
just unit-test
```

Or directly:

```bash
uv run pytest tests/unit
```

Options:
- `-v` or `--verbose`: Show test names
- `-x`: Stop on first failure (fail-fast)
- `-k PATTERN`: Run only tests matching pattern
- `--lf`: Run last failed tests
- `-m MARK`: Run tests with specific marker

Examples:

```bash
uv run pytest tests/unit -v
uv run pytest tests/unit -x
uv run pytest tests/unit -k "harness"
uv run pytest tests/unit::test_cli.py::test_main_help
```

### Full BDD Tests

```bash
just bdd-test
```

Or directly:

```bash
uv run behave tests/integration
```

Options:
- `--dry-run`: Parse features and steps without executing
- `--tags=@tag_name`: Run only scenarios with specific tag
- `--name=pattern`: Run only scenarios matching name
- `-f json -o output.json`: Generate JSON report
- `--summary`: Show scenario summary

Examples:

```bash
uv run behave tests/integration --dry-run
uv run behave tests/integration --tags=@ec2
uv run behave tests/integration --name="launch instance"
uv run behave tests/integration features/ec2_launch.feature
```

### Full Test Suite

```bash
just test
```

This runs both unit and BDD tests sequentially. **Note:** This takes ~1 hour and is typically run before final code review, not during development.

## Test Configuration

### Pytest Configuration

Located in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests/unit"]
norecursedirs = ["tmp", ".git", ".venv", "__pycache__"]
```

### Behave Configuration

Located in `tests/integration/behave.ini`:

```ini
[behave]
paths = features/
capture_hooks = false
```

Key settings:
- `paths`: Directory containing feature files (relative to behave.ini location)
- `capture_hooks`: Disabled to work around behave 1.3.3 cleanup issues
  (See: `tmp/debug/replace-coiled/test-infrastructure-improvements/DEBUGGING_REPORT.md`)

## Test Architecture

### Conftest and Fixtures

`tests/unit/conftest.py` provides pytest fixtures including:

- `tmp_dir`: Temporary directory for test artifacts
- `mock_aws`: AWS service mocks
- `harness`: Test harness instances
- Environment setup/teardown hooks

### Behave Environment

`tests/integration/features/environment.py` provides:

- Before/after hooks for scenario setup and teardown
- Context initialization
- Resource cleanup
- Diagnostics collection

Failure diagnostics are automatically written to:
```
tmp/behave/<scenario_name>/diagnostics/
```

## Writing New Tests

### Adding a Unit Test

1. Create file in `tests/unit/test_<component>.py`
2. Import fixtures from conftest
3. Write test functions starting with `test_`
4. Use type hints and docstrings

Example:

```python
def test_ec2_instance_launch(mock_aws: MockEC2) -> None:
    instance = mock_aws.create_instance("test-instance")
    assert instance.state == "running"
```

### Adding a BDD Scenario

1. Add feature file in `tests/integration/features/<feature>.feature`
2. Use Gherkin syntax (Given/When/Then)
3. Implement steps in `tests/integration/features/steps/<feature>_steps.py`
4. Run with `uv run behave tests/integration features/<feature>.feature`

Example feature:

```gherkin
Feature: EC2 Instance Management
  Scenario: Launch instance with custom configuration
    Given the moondock CLI is available
    When I run: moondock init --size t3.micro
    Then the instance should be in state "running"
```

Corresponding steps:

```python
@given("the moondock CLI is available")
def step_cli_available(context: Context) -> None:
    context.cli = MoondockCLI()

@when("I run: {command}")
def step_run_command(context: Context, command: str) -> None:
    context.result = context.cli.run(command)

@then('the instance should be in state "{state}"')
def step_check_state(context: Context, state: str) -> None:
    assert context.result.state == state
```

### Test Organization Best Practices

1. **One concept per test**: Each test should verify a single behavior
2. **Clear naming**: Test names should describe what is being tested
3. **Use fixtures**: Leverage pytest fixtures for common setup
4. **No test coupling**: Tests should be independent and runnable in any order
5. **Minimal mocking**: Mock external dependencies, not implementation details
6. **Document complex tests**: Add docstrings explaining the test scenario

## Troubleshooting

### Import Errors

If you get import errors during test discovery:

```bash
uv run pytest tests/unit --collect-only
```

This shows what pytest found and any import errors.

### BDD Discovery Issues

Check that behave finds all scenarios:

```bash
uv run behave tests/integration --dry-run
```

This parses features and steps without executing.

### Timeout Issues

If BDD tests timeout, check:
1. Is LocalStack running? (`docker ps`)
2. Are there hanging processes? (`ps aux | grep python`)
3. Check diagnostics: `tmp/behave/<scenario_name>/diagnostics/`

### Test Isolation Problems

If tests fail when run together but pass individually:

1. Check for shared state in fixtures
2. Verify resource cleanup in teardown hooks
3. Review conftest.py `@pytest.fixture(scope=...)` settings
4. Check environment.py `@after.each` scenario cleanup

### Performance Issues

To profile slow tests:

```bash
uv run pytest tests/unit --durations=10
```

Shows 10 slowest tests.

## Performance Metrics

Baseline performance (on M-series Mac):

| Test Type | Count | Duration | Per Test |
|-----------|-------|----------|----------|
| Unit tests | 381 | ~35s | ~90ms |
| BDD dry-run | 190 scenarios | ~2-3min | ~0.8s |
| BDD full run | 190 scenarios | ~15-20min | ~5-6s |

## CI/CD Integration

When running in CI/CD:

1. **Run unit tests**: `uv run pytest tests/unit --junitxml=results.xml`
2. **Check formatting**: `uv run ruff format tests/unit --check`
3. **Lint**: `uv run ruff check tests/unit`
4. **Run BDD (conditional)**: Only for final validation or scheduled runs

## Continuous Improvement

When adding new tests:

1. Verify test is discoverable: `--collect-only` or `--dry-run`
2. Ensure it fails before you fix the code
3. Verify it passes after you fix the code
4. Check it doesn't break other tests: `just test-fast`
5. Add documentation if it tests complex behavior

When refactoring tests:

1. Keep test logic simple and clear
2. Move reusable test code to fixtures/steps
3. Update this documentation if structure changes
4. Run full validation: `just test-fast`

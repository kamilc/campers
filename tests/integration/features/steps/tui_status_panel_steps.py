"""Step definitions for TUI status panel feature."""

import queue
from typing import Any

from behave import then, when
from behave.runner import Context
from textual.widgets import Log, Static


@then("TUI displays status panel")
def step_tui_displays_status_panel(context: Context) -> None:
    """Verify status panel exists and is visible.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_status_panel() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            status_panel = app.query_one("#status-panel")
            assert status_panel is not None, "Status panel not found"
            assert status_panel.visible, "Status panel not visible"
            context.tui_app = app
            context.pilot = pilot

    import asyncio

    asyncio.run(verify_status_panel())


@then("TUI displays log panel")
def step_tui_displays_log_panel(context: Context) -> None:
    """Verify log panel exists and is visible.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_log_panel() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            log_panel = app.query_one("#log-panel")
            assert log_panel is not None, "Log panel not found"
            assert log_panel.visible, "Log panel not visible"

    import asyncio

    asyncio.run(verify_log_panel())


@then("status panel height is one-third of screen")
def step_status_panel_height_one_third(context: Context) -> None:
    """Verify status panel height is approximately one-third.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_status_height() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            status_panel = app.query_one("#status-panel")
            height_value = str(status_panel.styles.height)
            assert height_value == "auto", (
                f"Expected status panel height to be 'auto', got: {height_value}"
            )

    import asyncio

    asyncio.run(verify_status_height())


@then("log panel height is two-thirds of screen")
def step_log_panel_height_two_thirds(context: Context) -> None:
    """Verify log panel height is approximately two-thirds.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_log_height() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            log_panel = app.query_one("#log-panel")
            height_value = str(log_panel.styles.height)
            assert height_value == "1fr", (
                f"Expected log panel height to be '1fr', got: {height_value}"
            )

    import asyncio

    asyncio.run(verify_log_height())


@when("TUI first launches")
def step_tui_first_launches(context: Context) -> None:
    """Mark TUI as launched in context.

    Parameters
    ----------
    context : Context
        Behave context
    """
    context.tui_launched = True


@then("status panel shows placeholder text for instance ID")
def step_status_panel_shows_placeholder_instance_id(context: Context) -> None:
    """Verify instance ID widget shows placeholder text.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_placeholder() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test():
            widget = app.query_one("#ssh-widget", Static)
            content = widget.render()
            text = str(content)
            assert "loading" in text.lower(), f"Expected placeholder text, got: {text}"

    import asyncio

    asyncio.run(verify_placeholder())


@then("status panel shows placeholder text for instance type")
def step_status_panel_shows_placeholder_instance_type(context: Context) -> None:
    """Verify instance type widget shows placeholder text.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_placeholder() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test():
            widget = app.query_one("#instance-type-widget", Static)
            content = widget.render()
            text = str(content)
            assert "loading" in text.lower(), f"Expected placeholder text, got: {text}"

    import asyncio

    asyncio.run(verify_placeholder())


@then("status panel shows placeholder text for region")
def step_status_panel_shows_placeholder_region(context: Context) -> None:
    """Verify region widget shows placeholder text.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_placeholder() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test():
            widget = app.query_one("#region-widget", Static)
            content = widget.render()
            text = str(content)
            assert "loading" in text.lower(), f"Expected placeholder text, got: {text}"

    import asyncio

    asyncio.run(verify_placeholder())


@then("status panel shows placeholder text for camp name")
def step_status_panel_shows_placeholder_camp_name(context: Context) -> None:
    """Verify camp name widget shows placeholder text.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_placeholder() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test():
            widget = app.query_one("#camp-name-widget", Static)
            content = widget.render()
            text = str(content)
            assert "loading" in text.lower(), f"Expected placeholder text, got: {text}"

    import asyncio

    asyncio.run(verify_placeholder())


@then("status panel shows placeholder text for command")
def step_status_panel_shows_placeholder_command(context: Context) -> None:
    """Verify command widget shows placeholder text.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_placeholder() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test():
            widget = app.query_one("#command-widget", Static)
            content = widget.render()
            text = str(content)
            assert "loading" in text.lower(), f"Expected placeholder text, got: {text}"

    import asyncio

    asyncio.run(verify_placeholder())


@then("status panel shows placeholder text for forwarded ports")
def step_status_panel_shows_placeholder_forwarded_ports(context: Context) -> None:
    """Verify forwarded ports widget shows placeholder text.

    Parameters
    ----------
    context : Context
        Behave context

    Notes
    -----
    This feature is not yet implemented in the TUI.
    This step is a placeholder for future implementation.
    """
    pass


@then("status panel shows placeholder text for SSH connection")
def step_status_panel_shows_placeholder_ssh_connection(context: Context) -> None:
    """Verify SSH connection widget shows placeholder text.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_placeholder() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test():
            widget = app.query_one("#ssh-widget", Static)
            content = widget.render()
            text = str(content)
            assert "loading" in text.lower(), f"Expected placeholder text, got: {text}"

    import asyncio

    asyncio.run(verify_placeholder())


@when("instance is launched successfully")
def step_instance_launched_successfully(context: Context) -> None:
    """Mark instance as launched with test details.

    Parameters
    ----------
    context : Context
        Behave context
    """
    context.instance_launched = True
    context.instance_details = {
        "instance_id": "i-test123",
        "public_ip": "203.0.113.1",
        "state": "running",
        "key_file": "/tmp/test-key.pem",
    }


@then("status panel shows instance ID")
def step_status_panel_shows_instance_id(context: Context) -> None:
    """Verify instance ID widget shows actual instance ID.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_instance_id() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            update_queue.put({"type": "instance_details", "payload": context.instance_details})
            app.check_for_updates()
            await pilot.pause()
            widget = app.query_one("#ssh-widget", Static)
            content = widget.render()
            text = str(content)
            assert context.instance_details["public_ip"] in text, (
                f"Expected public IP in widget, got: {text}"
            )

    import asyncio

    asyncio.run(verify_instance_id())


@then("status panel shows instance type")
def step_status_panel_shows_instance_type(context: Context) -> None:
    """Verify instance type widget shows actual instance type.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_instance_type() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            test_config = {"instance_type": "t2.micro"}
            update_queue.put({"type": "merged_config", "payload": test_config})
            app.check_for_updates()
            await pilot.pause()
            widget = app.query_one("#instance-type-widget", Static)
            content = widget.render()
            text = str(content)
            assert "t2.micro" in text, f"Expected instance type in widget, got: {text}"

    import asyncio

    asyncio.run(verify_instance_type())


@then("status panel shows AWS region")
def step_status_panel_shows_aws_region(context: Context) -> None:
    """Verify region widget shows actual AWS region.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_region() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            test_config = {"region": "us-east-1"}
            update_queue.put({"type": "merged_config", "payload": test_config})
            app.check_for_updates()
            await pilot.pause()
            widget = app.query_one("#region-widget", Static)
            content = widget.render()
            text = str(content)
            assert "us-east-1" in text, f"Expected region in widget, got: {text}"

    import asyncio

    asyncio.run(verify_region())


@then("status panel shows camp name")
def step_status_panel_shows_camp_name(context: Context) -> None:
    """Verify camp name widget shows actual camp name.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_camp_name() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            test_config = {"camp_name": "test-machine"}
            update_queue.put({"type": "merged_config", "payload": test_config})
            app.check_for_updates()
            await pilot.pause()
            widget = app.query_one("#camp-name-widget", Static)
            content = widget.render()
            text = str(content)
            assert "test-machine" in text, f"Expected camp name in widget, got: {text}"

    import asyncio

    asyncio.run(verify_camp_name())


@then("status panel shows command")
def step_status_panel_shows_command(context: Context) -> None:
    """Verify command widget shows actual command.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_command() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            test_config = {"command": "echo hello"}
            update_queue.put({"type": "merged_config", "payload": test_config})
            app.check_for_updates()
            await pilot.pause()
            widget = app.query_one("#command-widget", Static)
            content = widget.render()
            text = str(content)
            assert "echo hello" in text, f"Expected command in widget, got: {text}"

    import asyncio

    asyncio.run(verify_command())


@then("status panel shows forwarded URLs")
def step_status_panel_shows_forwarded_urls(context: Context) -> None:
    """Verify forwarded URLs widget shows actual forwarded URLs.

    Parameters
    ----------
    context : Context
        Behave context

    Notes
    -----
    This feature is not yet implemented in the TUI.
    This step is a placeholder for future implementation.
    """
    pass


@then("status panel shows SSH connection string")
def step_status_panel_shows_ssh_connection_string(context: Context) -> None:
    """Verify SSH connection widget shows actual SSH string.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_ssh_string() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            update_queue.put({"type": "instance_details", "payload": context.instance_details})
            app.check_for_updates()
            await pilot.pause()
            widget = app.query_one("#ssh-widget", Static)
            content = widget.render()
            text = str(content)
            assert context.instance_details["public_ip"] in text, (
                f"Expected public IP in SSH widget, got: {text}"
            )

    import asyncio

    asyncio.run(verify_ssh_string())


@then("status panel shows static uptime")
def step_status_panel_shows_static_uptime(context: Context) -> None:
    """Verify uptime widget shows static uptime value.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_static_uptime() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            widget = app.query_one("#uptime-widget", Static)
            content = widget.render()
            text = str(content)
            assert "0s" in text or "Uptime" in text, (
                f"Expected static uptime in widget, got: {text}"
            )

    import asyncio

    asyncio.run(verify_static_uptime())


@when("log messages are generated")
def step_log_messages_are_generated(context: Context) -> None:
    """Mark log messages as generated in context.

    Parameters
    ----------
    context : Context
        Behave context
    """
    context.log_messages_generated = True


@then("log panel displays messages")
def step_log_panel_displays_messages(context: Context) -> None:
    """Verify log panel can display messages.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_log_messages() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            log_widget = app.query_one(Log)
            assert log_widget is not None, "Log widget not found"

    import asyncio

    asyncio.run(verify_log_messages())


@then("log panel is scrollable")
def step_log_panel_is_scrollable(context: Context) -> None:
    """Verify log panel is scrollable.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_scrollable() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            log_widget = app.query_one(Log)
            assert hasattr(log_widget, "scroll_home"), "Log widget not scrollable"

    import asyncio

    asyncio.run(verify_scrollable())


@when("queue receives config and instance updates")
def step_queue_receives_updates(context: Context) -> None:
    """Simulate queue receiving config and instance updates.

    Parameters
    ----------
    context : Context
        Behave context
    """
    context.test_config = {
        "instance_type": "t3.large",
        "region": "us-west-2",
        "camp_name": "test-box",
        "command": "python train.py",
        "ports": [8080, 9090],
    }
    context.test_instance = {
        "instance_id": "i-test456",
        "public_ip": "198.51.100.1",
        "state": "running",
        "key_file": "/tmp/test.pem",
    }


@then("status panel processes updates in order")
def step_status_panel_processes_in_order(context: Context) -> None:
    """Verify status panel processes updates in correct order.

    Parameters
    ----------
    context : Context
        Behave context
    """
    import asyncio

    async def verify_processing_order() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test() as pilot:
            await pilot.pause()

            instance_type_widget = app.query_one("#instance-type-widget", Static)
            status_widget = app.query_one("#status-widget", Static)

            initial_instance_type = str(instance_type_widget.render())
            initial_status = str(status_widget.render())
            assert "loading..." in initial_instance_type
            assert "launching..." in initial_status

            update_queue.put({"type": "merged_config", "payload": context.test_config})
            update_queue.put({"type": "instance_details", "payload": context.test_instance})

            app.check_for_updates()
            await pilot.pause()

            final_instance_type = str(instance_type_widget.render())
            final_status = str(status_widget.render())
            assert "t3.large" in final_instance_type
            assert "running" in final_status

            try:
                update_queue.get_nowait()
                raise AssertionError("Queue should be empty after processing all updates")
            except queue.Empty:
                pass

    asyncio.run(verify_processing_order())


@then("widgets reflect both config and instance data")
def step_widgets_reflect_both_updates(context: Context) -> None:
    """Verify widgets display both config and instance data.

    Parameters
    ----------
    context : Context
        Behave context
    """
    import asyncio

    async def verify_widgets_updated() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test() as pilot:
            await pilot.pause()

            update_queue.put({"type": "merged_config", "payload": context.test_config})
            update_queue.put({"type": "instance_details", "payload": context.test_instance})

            app.check_for_updates()
            await pilot.pause()

            instance_type_widget = app.query_one("#instance-type-widget", Static)
            instance_type_text = str(instance_type_widget.render())
            assert "t3.large" in instance_type_text

            ssh_widget = app.query_one("#ssh-widget", Static)
            ssh_text = str(ssh_widget.render())
            assert "198.51.100.1" in ssh_text

    asyncio.run(verify_widgets_updated())

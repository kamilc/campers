"""Unit tests for ResourceRegistry service."""

from tests.harness.services.resource_registry import ResourceRegistry


class TestResourceRegistryBasic:
    """Test basic registration and cleanup."""

    def test_register_and_cleanup_single_resource(self) -> None:
        """Test registering and cleaning up a single resource."""
        registry = ResourceRegistry()
        cleanup_called = []

        def dispose(handle: str) -> None:
            cleanup_called.append(handle)

        registry.register("test-kind", "test-handle", dispose, label="test-label")
        assert len(registry.resources) == 1

        registry.cleanup_all()
        assert cleanup_called == ["test-handle"]

    def test_cleanup_reverse_creation_order(self) -> None:
        """Test cleanup happens in reverse creation order."""
        registry = ResourceRegistry()
        order = []

        def make_dispose(name: str):
            def dispose(handle: str) -> None:
                order.append(name)

            return dispose

        registry.register("kind1", "handle1", make_dispose("first"), label="1")
        registry.register("kind2", "handle2", make_dispose("second"), label="2")
        registry.register("kind3", "handle3", make_dispose("third"), label="3")

        registry.cleanup_all()

        assert order == ["third", "second", "first"]

    def test_cleanup_continues_on_exception(self) -> None:
        """Test cleanup continues even if a disposal raises exception."""
        registry = ResourceRegistry()
        order = []

        def make_dispose(name: str, should_fail: bool = False):
            def dispose(handle: str) -> None:
                order.append(name)
                if should_fail:
                    raise ValueError(f"Disposal failed for {name}")

            return dispose

        registry.register("kind1", "handle1", make_dispose("first"), label="1")
        registry.register("kind2", "handle2", make_dispose("second", should_fail=True), label="2")
        registry.register("kind3", "handle3", make_dispose("third"), label="3")

        registry.cleanup_all()

        assert order == ["third", "second", "first"]

    def test_empty_registry_cleanup(self) -> None:
        """Test cleanup on empty registry doesn't raise."""
        registry = ResourceRegistry()
        registry.cleanup_all()

    def test_multiple_resources_same_kind(self) -> None:
        """Test registering multiple resources of same kind."""
        registry = ResourceRegistry()
        cleanup_called = []

        def make_dispose(name: str):
            def dispose(handle: str) -> None:
                cleanup_called.append(name)

            return dispose

        registry.register("container", "c1", make_dispose("container1"), label="c1")
        registry.register("container", "c2", make_dispose("container2"), label="c2")
        registry.register("container", "c3", make_dispose("container3"), label="c3")

        registry.cleanup_all()

        assert cleanup_called == ["container3", "container2", "container1"]


class TestResourceRegistryWithDependencies:
    """Test resource dependencies (deferred functionality)."""

    def test_register_with_dependencies(self) -> None:
        """Test registering resource with dependencies."""
        registry = ResourceRegistry()

        def dispose(_: str) -> None:
            pass

        registry.register(
            "resource",
            "handle1",
            dispose,
            label="resource1",
            dependencies=["resource2"],
        )

        assert registry.resources[0]["dependencies"] == ["resource2"]

    def test_register_without_dependencies(self) -> None:
        """Test registering resource without dependencies."""
        registry = ResourceRegistry()

        def dispose(_: str) -> None:
            pass

        registry.register("resource", "handle1", dispose, label="resource1")

        assert registry.resources[0]["dependencies"] == []


class TestResourceRegistryMetadata:
    """Test resource metadata."""

    def test_resource_metadata_preserved(self) -> None:
        """Test all resource metadata is preserved."""
        registry = ResourceRegistry()

        def dispose(_: str) -> None:
            pass

        registry.register(
            kind="test-kind",
            handle="test-handle",
            dispose_fn=dispose,
            label="test-label",
            dependencies=["dep1"],
        )

        resource = registry.resources[0]
        assert resource["kind"] == "test-kind"
        assert resource["handle"] == "test-handle"
        assert resource["dispose_fn"] is dispose
        assert resource["label"] == "test-label"
        assert resource["dependencies"] == ["dep1"]

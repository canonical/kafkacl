#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Requirer-side event handling and charm config management for Kafka Connect integrator charms."""

import json
import logging
from abc import ABC, abstractmethod
from functools import cached_property
from typing import Any, Mapping, Optional, cast

from ops.charm import CharmBase, RelationBrokenEvent
from ops.framework import Object
from ops.model import Relation

from .config import BaseConfigFormatter
from .connect import ConnectClient
from .helpers import DataInterfacesHelpers
from .lib.charms.data_platform_libs.v0.data_interfaces import (
    DataPeerUnitData,
    IntegrationCreatedEvent,
    IntegrationEndpointsChangedEvent,
    KafkaConnectRequirerData,
    KafkaConnectRequirerEventHandlers,
)
from .models import (
    MULTICONNECTOR_PREFIX,
    ClientContext,
    ConnectApiError,
    IntegratorMode,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class BasePluginServer(ABC):
    """Base interface for plugin server service."""

    plugin_url: str

    def __init__(self, *args, **kwargs):
        pass

    @abstractmethod
    def start(self) -> None:
        """Starts the plugin server service."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stops the plugin server service."""
        ...

    @abstractmethod
    def configure(self) -> None:
        """Makes all necessary configurations to start the server service."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Checks that the plugin server is active and healthy."""
        ...


class BaseIntegrator(ABC, Object):
    """Basic interface for handling Kafka Connect Requirer side events and functions."""

    name: str
    formatter: type[BaseConfigFormatter]
    plugin_server: type[BasePluginServer]
    mode: IntegratorMode = "source"

    CONFIG_SECRET_FIELD = "config"
    CONNECT_REL = "connect-client"
    PEER_REL = "peer"

    def __init__(
        self,
        /,
        charm: CharmBase,
        plugin_server_args: Optional[list] = [],
        plugin_server_kwargs: Mapping[str, Any] = {},
    ):
        super().__init__(charm, f"integrator-{self.name}")

        for field in ("name", "formatter", "plugin_server"):
            if not getattr(self, field, None):
                raise AttributeError(
                    f"{field} not defined on BaseIntegrator interface, did you forget to set the {field} class variable?"
                )

        self.charm = charm
        plugin_server_args = plugin_server_args or []
        self.server = self.plugin_server(*plugin_server_args, **plugin_server_kwargs)
        self.plugin_url = self.server.plugin_url
        self.config = charm.config
        self.mode: IntegratorMode = cast(IntegratorMode, self.config.get("mode", self.mode))
        self.helpers: DataInterfacesHelpers = DataInterfacesHelpers(self.charm)

        self._connector_names: list[str] = []

        # init handlers
        self.rel_name = self.CONNECT_REL
        self.requirer = KafkaConnectRequirerEventHandlers(self.charm, self._requirer_interface)

        # register basic listeners for common hooks
        self.framework.observe(self.requirer.on.integration_created, self._on_integration_created)
        self.framework.observe(
            self.requirer.on.integration_endpoints_changed, self._on_integration_endpoints_changed
        )
        self.framework.observe(
            self.charm.on[self.rel_name].relation_broken, self._on_relation_broken
        )

    @property
    def _peer_relation(self) -> Optional[Relation]:
        """Peer `Relation` object."""
        return self.model.get_relation(self.PEER_REL)

    @property
    def _connect_client_relation(self) -> Optional[Relation]:
        """connect-client `Relation` object."""
        return self.model.get_relation(self.CONNECT_REL)

    @cached_property
    def _requirer_interface(self) -> KafkaConnectRequirerData:
        """`connect-client` requirer data interface."""
        return KafkaConnectRequirerData(
            self.model, relation_name=self.CONNECT_REL, plugin_url=self.plugin_url
        )

    @cached_property
    def _peer_unit_interface(self) -> DataPeerUnitData:
        """Peer unit data interface."""
        return DataPeerUnitData(
            self.model,
            relation_name=self.PEER_REL,
            additional_secret_fields=[self.CONFIG_SECRET_FIELD],
        )

    @cached_property
    def _client_context(self) -> ClientContext:
        """Kafka Connect client data populated from relation data."""
        return ClientContext(
            self.charm.model.get_relation(self.CONNECT_REL), self._requirer_interface
        )

    @cached_property
    def _client(self) -> ConnectClient:
        """Kafka Connect client for handling REST API calls."""
        return ConnectClient(self._client_context, self.connector_unique_name)

    # Public properties

    @property
    def connector_unique_name(self) -> str:
        """Returns connectors' unique name used on the REST interface."""
        if not self._connect_client_relation:
            return ""

        relation_id = self._connect_client_relation.id
        return f"{self.name}_r{relation_id}_{self.model.uuid.replace('-', '')}"

    @property
    def started(self) -> bool:
        """Returns True if connector is started, False otherwise."""
        if self._peer_relation is None:
            return False

        return bool(
            self._peer_unit_interface.fetch_my_relation_field(self._peer_relation.id, "started")
        )

    @started.setter
    def started(self, val: bool) -> None:
        if self._peer_relation is None:
            return

        if val:
            self._peer_unit_interface.update_relation_data(
                self._peer_relation.id, data={"started": "true"}
            )
        else:
            self._peer_unit_interface.delete_relation_data(
                self._peer_relation.id, fields=["started"]
            )

    @property
    def dynamic_config(self) -> dict[str, Any]:
        """Returns dynamic connector configuration, set during runtime inside hooks or method calls."""
        if self._peer_relation is None:
            return {}

        return json.loads(
            self._peer_unit_interface.as_dict(self._peer_relation.id).get(
                self.CONFIG_SECRET_FIELD, "{}"
            )
        )

    @property
    def connector_names(self) -> list[str]:
        """Return a list of connector names that the integrator should create."""
        connectors = []
        for name in self.dynamic_config.keys():
            if name.startswith(MULTICONNECTOR_PREFIX):
                connectors.append(name)
        return connectors

    # Public methods

    def configure(self, config: dict[str, Any] | list[dict[str, Any]]) -> None:
        """Dynamically configure the connector with provided `config` dictionary.

        Configuration provided using this method will override default config and config provided
        by juju runtime (i.e. defined using the `BaseConfigFormmatter` interface).
        All configuration provided using this method are persisted using juju secrets.
        Each call would update the previous provided configuration (if any), mimicking the
        `dict.update()` behavior.

        Args:
            config (dict[str, Any] | list[dict[str, Any]]):
                - If a single dict is provided, updates the configuration for a single connector.
                - If a list of dicts is provided, it will create multiple connector. Each dict in
                  the list represents a separate connector configuration. A "name" key should be
                  used to help differentiate connector names.
        """
        if self._peer_relation is None:
            return

        updated_config = self.dynamic_config.copy()

        # Single configuration
        if isinstance(config, dict):
            updated_config.update(config)

        # Multiple configurations
        if isinstance(config, list):
            for connector_config in config:
                try:
                    connector_id = f"{MULTICONNECTOR_PREFIX}_{connector_config['name']}_{self.connector_unique_name}"
                except KeyError:
                    logger.error(
                        "List of connectors should provide a 'name' key to differentiate them"
                    )
                    raise

                # Remove "name" key so it's not part of the config passed to the JSON afterwards
                connector_config.pop("name")
                updated_config[connector_id] = connector_config

        self._peer_unit_interface.update_relation_data(
            self._peer_relation.id, data={self.CONFIG_SECRET_FIELD: json.dumps(updated_config)}
        )

    def start_connector(self) -> None:
        """Starts the connectors."""
        if self.started:
            logger.info("Connector has already started")
            return

        self.setup()

        # We have more than one connector to be executed. If list is empty, this is skipped
        for connector_name in self.connector_names:
            try:
                self._client.start_connector(
                    connector_config=self.formatter.to_dict(
                        charm_config=self.config, mode="source"
                    )
                    | self.dynamic_config[connector_name],
                    connector_name=connector_name,
                )
            except ConnectApiError as e:
                logger.error(f"Connector start failed, details: {e}")
                return

        # Single connector case
        if not self.connector_names:
            try:
                self._client.start_connector(
                    self.formatter.to_dict(charm_config=self.config, mode="source")
                    | self.dynamic_config
                )
            except ConnectApiError as e:
                logger.error(f"Connector start failed, details: {e}")
                return

        self.started = True

    def maybe_resume_connector(self) -> None:
        """Restarts/resumes the connector if it's in STOPPED state."""
        # TODO: resume should cover multiple connectors existing
        if self.connector_status != TaskStatus.STOPPED:
            return

        try:
            self._client.resume_connector()
        except ConnectApiError as e:
            logger.error(f"Unable to restart/resume the connector, details: {e}")
            return

    def patch_connector(self) -> None:
        """Updates the connector(s) configuration.

        Will override the existing configuration for the connector.
        """
        if not self.started:
            logger.info("Connector is not started yet, skipping update.")
            return

        self.setup()

        # We have more than one connector to be executed. If list is empty, this is skipped
        for connector_name in self.connector_names:
            try:
                self._client.patch_connector(
                    connector_config=self.formatter.to_dict(
                        charm_config=self.config, mode="source"
                    )
                    | self.dynamic_config[connector_name],
                    connector_name=connector_name,
                )
            except ConnectApiError as e:
                logger.error(f"Connector start failed, details: {e}")
                return

        # Single connector case
        if not self.connector_names:
            try:
                self._client.patch_connector(
                    self.formatter.to_dict(charm_config=self.config, mode="source")
                    | self.dynamic_config
                )
            except ConnectApiError as e:
                logger.error(f"Connector start failed, details: {e}")
                return

        self.started = True

    @property
    def task_status(self) -> TaskStatus:
        """Returns connector task status."""
        if not self.started:
            return TaskStatus.UNASSIGNED

        # TODO: status should be handled in a more complex way than this
        if self.connector_names:
            return self._client.task_status(connector_name=self.connector_names[0])

        return self._client.task_status()

    @property
    def connector_status(self) -> TaskStatus:
        """Returns connector status."""
        return self._client.connector_status()

    # Abstract methods

    @property
    @abstractmethod
    def ready(self) -> bool:
        """Should return True if all conditions for startig the connector is met, including if all client relations are setup successfully."""
        ...

    @abstractmethod
    def setup(self) -> None:
        """Should perform all necessary actions before connector is started."""
        ...

    @abstractmethod
    def teardown(self) -> None:
        """Should perform all necessary cleanups after connector is stopped."""
        ...

    # Event handlers

    def _on_integration_created(self, event: IntegrationCreatedEvent) -> None:
        """Handler for `integration_created` event."""
        if not self.server.health_check() or not self.ready:
            logging.debug("Integrator not ready yet, deferring integration_created event...")
            event.defer()
            return

        logger.info(f"Starting {self.name} connector...")
        self.start_connector()

        if not self.started:
            event.defer()

    def _on_integration_endpoints_changed(self, _: IntegrationEndpointsChangedEvent) -> None:
        """Handler for `integration_endpoints_changed` event."""
        pass

    def _on_relation_broken(self, _: RelationBrokenEvent) -> None:
        """Handler for `relation-broken` event."""
        self.teardown()
        self.started = False

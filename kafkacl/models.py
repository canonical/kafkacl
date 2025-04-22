#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Model definitions module."""

from enum import Enum
from typing import Literal

from ops.model import Relation

from .lib.charms.data_platform_libs.v0.data_interfaces import (
    KafkaConnectRequirerData,
)


class ConnectClientError(Exception):
    """Exception raised when Kafka Connect client could not be instantiated."""


class ConnectApiError(Exception):
    """Exception raised when Kafka Connect REST API call fails."""


IntegratorMode = Literal["source", "sink"]


class TaskStatus(str, Enum):
    """Enum for Connectors and Tasks status representation."""

    UNASSIGNED = "UNASSIGNED"
    PAUSED = "PAUSED"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class ClientContext:
    """Object representing Kafka Connect client relation data."""

    def __init__(
        self,
        relation: Relation | None,
        data_interface: KafkaConnectRequirerData,
    ):
        self.relation = relation
        self.data_interface = data_interface
        self.relation_data = self.data_interface.as_dict(self.relation.id) if self.relation else {}

    def __bool__(self) -> bool:
        """Boolean evaluation based on the existence of self.relation."""
        try:
            return bool(self.relation)
        except AttributeError:
            return False

    @property
    def plugin_url(self) -> str:
        """Returns the client's plugin-url REST endpoint."""
        if not self.relation:
            return ""

        return self.relation_data.get("plugin-url", "")

    @property
    def username(self) -> str:
        """Returns the Kafka Connect client username."""
        if not self.relation:
            return ""

        return self.relation_data.get("username", "")

    @property
    def endpoints(self) -> str:
        """Returns Kafka Connect endpoints set for the client."""
        if not self.relation:
            return ""

        return self.relation_data.get("endpoints", "")

    @property
    def password(self) -> str:
        """Returns the Kafka Connect client password."""
        if not self.relation:
            return ""

        return self.relation_data.get("password", "")

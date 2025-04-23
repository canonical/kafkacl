#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Test integrator implementation for FileStream source/sink connectors."""

from kafkacl import BaseConfigFormatter, BaseIntegrator, ConfigOption
from ops.charm import CharmBase
from server import SimplePluginServer
from typing_extensions import override


class ConfigFormatter(BaseConfigFormatter):
    """Config formatter for FileStream Connector."""

    file_path = ConfigOption(
        json_key="file",
        default="/var/snap/charmed-kafka/common/var/log/connect/test.jsonl",
        mode="both",
    )

    topic = ConfigOption(
        json_key="topic",
        default="test",
        mode="source",
    )

    # non-configurable options
    topic_partitions = ConfigOption(
        json_key="topic.creation.default.partitions", default=10, configurable=False
    )
    topic_replication_factor = ConfigOption(
        json_key="topic.creation.default.replication.factor", default=-1, configurable=False
    )
    tasks_max = ConfigOption(json_key="tasks.max", default=1, configurable=False)
    key_converter = ConfigOption(
        json_key="key.converter",
        default="org.apache.kafka.connect.storage.StringConverter",
        configurable=False,
        mode="sink",
    )
    value_converter = ConfigOption(
        json_key="value.converter",
        default="org.apache.kafka.connect.json.JsonConverter",
        configurable=False,
    )


class Integrator(BaseIntegrator):
    """Basic implementation for FileStream Connector."""

    name = "test-integrator"
    formatter = ConfigFormatter
    plugin_server = SimplePluginServer

    CONNECT_REL = "connect-client"

    def __init__(self, /, charm: CharmBase, plugin_server_args=[], plugin_server_kwargs={}):
        super().__init__(charm, plugin_server_args, plugin_server_kwargs)

    @override
    def setup(self) -> None:
        connector_class = (
            "org.apache.kafka.connect.file.FileStreamSourceConnector"
            if self.mode == "source"
            else "org.apache.kafka.connect.file.FileStreamSinkConnector"
        )
        self.configure({"connector.class": connector_class})
        pass

    @override
    def teardown(self):
        pass

    @property
    @override
    def ready(self):
        return self.helpers.check_data_interfaces_ready([self.CONNECT_REL])

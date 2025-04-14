#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Objects which abstract away charm & Apache Kafka Connect task configuration."""

import logging
from typing import Any, Literal, cast

from ops.model import ConfigData
from pydantic import BaseModel

from .models import IntegratorMode

logger = logging.getLogger(__name__)

YAML_TYPE_MAPPER = {str: "string", int: "int", bool: "boolean"}


class ConfigOption(BaseModel):
    """Model for defining mapping between charm config and connector config.

    To define a config mapping, following properties could be used:

        json_key (str, required): The counterpart key in connector JSON config. If `mode` is set to "none", this would be ignored and could be set to any arbitrary value.
        default (Any, required): The default value for this config option.
        mode (Literal["both", "source", "sink", "none"], optional): Defaults to "both". The expected behaviour of each mode are as following:
            - both: This config option would be used in both source and sink connector modes.
            - source: This config option would be used ONLY in source connector mode.
            - sink: This config option would be used ONLY in sink connector mode.
            - none: This is not a connector config, but rather a charm config. If set to none, this option would not be used to configure the connector.
        configurable (bool, optional): Whether this option is configurable via charm config. Defaults to True.
        description (str, optional): A brief description of this config option, which will be added to the charm's `config.yaml`.
    """

    json_key: str  # Config key in the Connector configuration JSON
    default: Any  # Default value
    mode: Literal[
        "both", "source", "sink", "none"
    ] = "both"  # Whether this is a generic config or source/sink-only.
    configurable: bool = True  # Whether this option is configurable using charm config or not
    description: str = ""


class BaseConfigFormatter:
    """Object used for mapping charm config keys to connector JSON configuration keys and/or setting default configuration values.

    Mapping of charm config keys to JSON config keys is provided via `ConfigOption` class variables.

    Example: To map `topic` charm config to `connector.config.kafka.topic` in the connector JSON config, one should provide:

        topic = ConfigOption(json_key="connector.config.kafka.topic", default="some-topic", description="...")

    Default static configuration values should be provided by setting `configurable=False` in `ConfigOption` and providing a `default` value

    Note: dynamic configuration based on relation data should be done by calling BaseIntegrator.configure() method either inside hooks or during BaseIntegrator.setup().
    Dynamic config would override static config if provided.
    """

    mode = ConfigOption(
        json_key="na",
        default="source",
        description='Integrator mode, either "source" or "sink"',
        mode="none",
    )

    @classmethod
    def fields(cls) -> list[str]:
        """Returns a list of non-special class variables."""
        return [v for v in dir(cls) if not callable(getattr(cls, v)) and not v.startswith("__")]

    @classmethod
    def to_dict(cls, charm_config: ConfigData, mode: IntegratorMode) -> dict:
        """Serializes a given charm `ConfigData` object to a Python dictionary based on predefined mappings/defaults."""
        ret = {}
        for k in cls.fields():
            option = cast(ConfigOption, getattr(cls, k))

            if option.mode == "none":
                # This is not a connector config option
                continue

            if option.mode != "both" and option.mode != mode:
                # Source/sink-only config, skip
                continue

            if option.configurable and k in charm_config:
                ret[option.json_key] = charm_config[k]
                continue

            ret[option.json_key] = option.default

        return ret

    @classmethod
    def to_config_yaml(cls) -> dict[str, Any]:
        """Returns a dict compatible with charmcraft `config.yaml` format."""
        config = {"options": {}}
        options = config["options"]

        for _attr in dir(cls):

            if _attr.startswith("__"):
                continue

            attr = getattr(cls, _attr)

            if isinstance(attr, ConfigOption):
                option = cast(ConfigOption, attr)

                if not option.configurable:
                    continue

                options[_attr] = {
                    "default": option.default,
                    "type": YAML_TYPE_MAPPER.get(type(option.default), "string"),
                }

                if option.description:
                    options[_attr]["description"] = option.description

        return config

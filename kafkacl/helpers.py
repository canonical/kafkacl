#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper classes and methods."""

import logging
from collections.abc import MutableMapping
from typing import Iterable

from ops.charm import CharmBase

from .lib.charms.data_platform_libs.v0.data_interfaces import (
    RequirerData,
)

logger = logging.getLogger(__name__)


class DataInterfacesHelpers:
    """Helper methods for handling relation data."""

    def __init__(self, charm: CharmBase):
        self.charm = charm

    def fetch_all_relation_data(self, relation_name: str) -> MutableMapping:
        """Returns a MutableMapping of all relation data available to the unit on `relation_name`, either via databag or secrets."""
        relation = self.charm.model.get_relation(relation_name=relation_name)

        if relation is None:
            return {}

        return RequirerData(self.charm.model, relation_name).as_dict(relation.id)

    def check_data_interfaces_ready(
        self,
        relation_names: list[str],
        check_for: Iterable[str] = ("endpoints", "username", "password"),
    ):
        """Checks if all data interfaces are ready, i.e. all the fields provided in `check_for` argument has been set on the respective relations.

        Args:
            relation_names (list[str]): List of relation names to check.
            check_for (Iterable[str], optional): An iterable of field names to check for their existence in relation data. Defaults to ("endpoints", "username", "password").
        """
        for relation_name in relation_names:

            if not (_data := self.fetch_all_relation_data(relation_name)):
                return False

            for key in check_for:
                if not _data.get(key, ""):
                    logger.info(
                        f"Data interfaces readiness check: relation {relation_name} - {key} not set yet."
                    )
                    return False

        return True

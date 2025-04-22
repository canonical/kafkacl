#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Connect Client implementation."""

import logging
from functools import cached_property

import requests
from requests.auth import HTTPBasicAuth

from .models import ClientContext, ConnectApiError, ConnectClientError, TaskStatus

logger = logging.getLogger(__name__)


class ConnectClient:
    """Client object used for interacting with Kafka Connect REST API."""

    def __init__(self, client_context: ClientContext, connector_name: str):
        self.client_context = client_context
        self.connector_name = connector_name

    @cached_property
    def endpoint(self) -> str:
        """Returns the first valid Kafka Connect endpoint.

        Raises:
            ConnectClientError: if no valid endpoints are available

        Returns:
            str: Full URL of Kafka Connect endpoint, e.g. http://host:port
        """
        _endpoints = self.client_context.endpoints.split(",")

        if len(_endpoints) < 1:
            raise ConnectClientError("No connect endpoints available.")

        return _endpoints[0]

    def request(
        self,
        method: str = "GET",
        api: str = "",
        verbose: bool = True,
        **kwargs,
    ) -> requests.Response:
        """Makes a request to Kafka Connect REST endpoint and returns the response.

        Args:
            method (str, optional): HTTP method. Defaults to "GET".
            api (str, optional): Specific Kafka Connect API, e.g. "connector-plugins" or "connectors". Defaults to "".
            verbose (bool, optional): Whether should enable verbose logging or not. Defaults to True.
            kwargs: Keyword arguments which will be passed to `requests.request` method.

        Raises:
            ConnectApiError: If the REST API call is unsuccessful.

        Returns:
            requests.Response: Response object.
        """
        url = f"{self.endpoint}/{api}"

        auth = HTTPBasicAuth(self.client_context.username, self.client_context.password)

        try:
            # TODO: FIXME: use tls-ca to verify the cert.
            response = requests.request(method, url, verify=False, auth=auth, **kwargs)
        except Exception as e:
            raise ConnectApiError(f"Connect API call /{api} failed: {e}")

        if verbose:
            logging.debug(f"{method} - {url}: {response.content}")

        return response

    def start_connector(self, connector_config: dict, connector_name: str | None = None) -> None:
        """Starts a connector by posting `connector_config` to the `connectors` endpoint.

        Raises:
            ConnectApiError: If unsuccessful.
        """
        _json = {
            "name": connector_name or self.connector_name,
            "config": connector_config,
        }
        response = self.request(method="POST", api="connectors", json=_json)

        if response.status_code == 201:
            return

        if response.status_code == 409 and "already exists" in response.json().get("message", ""):
            logger.info("Connector has already been submitted, skipping...")
            return

        logger.error(response.content)
        raise ConnectApiError(f"Unable to start the connector, details: {response.content}")

    def resume_connector(self, connector_name: str | None = None) -> None:
        """Resumes a connector task by PUTting to the `connectors/<CONNECTOR-NAME>/resume` endpoint.

        Raises:
            ConnectApiError: If unsuccessful.
        """
        response = self.request(
            method="PUT", api=f"connectors/{connector_name or self.connector_name}/resume"
        )

        if response.status_code == 202:
            return

        logger.error(response.content)
        raise ConnectApiError(f"Unable to resume the connector, details: {response.content}")

    def stop_connector(self, connector_name: str | None = None) -> None:
        """Stops a connector at connectors/[CONNECTOR-NAME|connector-name]/stop endpoint.

        Raises:
            ConnectApiError: If unsuccessful.
        """
        response = self.request(
            method="PUT", api=f"connectors/{connector_name or self.connector_name}/stop"
        )

        if response.status_code != 204:
            raise ConnectApiError(f"Unable to stop the connector, details: {response.content}")

    def delete_connector(self, connector_name: str | None = None) -> None:
        """Deletes a connector at connectors/[CONNECTOR-NAME|connector-name] endpoint.

        Raises:
            ConnectApiError: If unsuccessful.
        """
        response = self.request(
            method="DELETE", api=f"connectors/{connector_name or self.connector_name}"
        )

        if response.status_code != 204:
            raise ConnectApiError(f"Unable to remove the connector, details: {response.content}")

    def patch_connector(self, connector_config: dict, connector_name: str | None = None) -> None:
        """Patches a connector by PATCHting `connector_config` to the `connectors/<CONNECTOR-NAME>` endpoint.

        Raises:
            ConnectApiError: If unsuccessful.
        """
        response = self.request(
            method="PATCH",
            api=f"connectors/{connector_name or self.connector_name}/config",
            json=connector_config,
        )

        if response.status_code == 200:
            logger.debug(
                f"Connector {connector_name or self.connector_name} patched: {connector_config}"
            )
            return

        logger.error(response.content)
        raise ConnectApiError(f"Unable to patch the connector, details: {response.content}")

    def task_status(self, connector_name: str | None = None) -> TaskStatus:
        """Returns the task status of a connector."""
        connector_name = connector_name or self.connector_name

        response = self.request(method="GET", api=f"connectors/{connector_name}/tasks", timeout=10)

        if response.status_code not in (200, 404):
            logger.error(f"Unable to fetch tasks status, details: {response.content}")
            return TaskStatus.UNKNOWN

        if response.status_code == 404:
            return TaskStatus.UNASSIGNED

        tasks = response.json()

        if not tasks:
            return TaskStatus.UNASSIGNED

        task_id = tasks[0].get("id", {}).get("task", 0)
        status_response = self.request(
            method="GET",
            api=f"connectors/{connector_name}/tasks/{task_id}/status",
            timeout=10,
        )

        if status_response.status_code == 404:
            return TaskStatus.UNASSIGNED

        if status_response.status_code != 200:
            logger.error(f"Unable to fetch tasks status, details: {status_response.content}")
            return TaskStatus.UNKNOWN

        state = status_response.json().get("state", "UNASSIGNED")
        return TaskStatus(state)

    def connector_status(self) -> TaskStatus:
        """Returns the connector status."""
        try:
            response = self.request(
                method="GET", api=f"connectors/{self.connector_name}/status", timeout=10
            )
        except ConnectApiError as e:
            logger.error(e)
            return TaskStatus.UNKNOWN

        if response.status_code not in (200, 404):
            logger.error(f"Unable to fetch connector status, details: {response.content}")
            return TaskStatus.UNKNOWN

        if response.status_code == 404:
            return TaskStatus.UNASSIGNED

        status_response = response.json()

        state = status_response.get("connector", {}).get("state", "UNASSIGNED")
        return TaskStatus(state)

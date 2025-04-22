#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging

import pytest
from pytest_operator.plugin import OpsTest

from helpers import (
    APP_NAME,
    CONNECT_APP,
    CONNECT_CHANNEL,
    FILE_CONNECTOR_PATH,
    KAFKA_APP,
    KAFKA_CHANNEL,
    PLUGIN_RESOURCE_KEY,
    assert_messages_produced,
    create_source_file,
)

logger = logging.getLogger(__name__)


SOURCE_FILE_PATH = "/var/snap/charmed-kafka/common/var/log/connect/test.jsonl"
NO_TEST_RECORDS = 153


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_deploy_cluster(ops_test: OpsTest):
    """Deploys kafka-connect charm along kafka (in KRaft mode)."""
    await asyncio.gather(
        ops_test.model.deploy(
            CONNECT_APP,
            application_name=CONNECT_APP,
            channel=CONNECT_CHANNEL,
            num_units=1,
            series="jammy",
        ),
        ops_test.model.deploy(
            KAFKA_APP,
            channel=KAFKA_CHANNEL,
            application_name=KAFKA_APP,
            num_units=1,
            series="jammy",
            config={"roles": "broker,controller"},
        ),
    )

    await ops_test.model.add_relation(CONNECT_APP, KAFKA_APP)

    async with ops_test.fast_forward(fast_interval="60s"):
        await ops_test.model.wait_for_idle(
            apps=[CONNECT_APP, KAFKA_APP], timeout=3000, status="active"
        )


@pytest.mark.abort_on_fail
async def test_deploy_source_app(ops_test: OpsTest, test_app_charm):

    await ops_test.model.deploy(
        test_app_charm,
        application_name=APP_NAME,
        resources={PLUGIN_RESOURCE_KEY: FILE_CONNECTOR_PATH},
        config={
            "mode": "source",
            "file_path": SOURCE_FILE_PATH,
            "topic": "source_test",
        },
    )

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], idle_period=30, timeout=1800, status="blocked"
    )


@pytest.mark.abort_on_fail
async def test_activate_source_app(ops_test: OpsTest):
    """Checks source integrator becomes active after related with MySQL."""
    # our source mysql integrator need a mysql_client relation to unblock:
    await ops_test.model.add_relation(APP_NAME, CONNECT_APP)
    async with ops_test.fast_forward(fast_interval="60s"):
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME, CONNECT_APP], idle_period=60, timeout=600, status="active"
        )


@pytest.mark.abort_on_fail
async def test_source_connector_pushed_to_kafka(ops_test: OpsTest):

    await create_source_file(ops_test, SOURCE_FILE_PATH, NO_TEST_RECORDS)

    await asyncio.sleep(120)

    await assert_messages_produced(
        ops_test, KAFKA_APP, topic="source_test", no_messages=NO_TEST_RECORDS
    )

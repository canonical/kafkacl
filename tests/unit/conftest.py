#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path

import pytest
import yaml
from ops.testing import Context, State
from tests.app_charm.src.charm import TestIntegratorCharm

CHARM_PATH = "tests/app_charm"
CONFIG = yaml.safe_load(Path(f"{CHARM_PATH}/config.yaml").read_text())
METADATA = yaml.safe_load(Path(f"{CHARM_PATH}/metadata.yaml").read_text())


@pytest.fixture()
def base_state():
    state = State(leader=True)

    return state


@pytest.fixture()
def ctx() -> Context:
    ctx = Context(TestIntegratorCharm, meta=METADATA, config=CONFIG, unit_id=0)
    return ctx

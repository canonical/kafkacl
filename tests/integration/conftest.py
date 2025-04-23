#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import glob
import os
import shutil
import subprocess

import pytest
from pytest_operator.plugin import OpsTest

from helpers import APP_CHARM_PATH, PACKAGE_NAME


@pytest.fixture
async def test_app_charm(ops_test: OpsTest, tmp_path):
    """Builds the test app charm and returns the built charm path."""
    charm_build_path = tmp_path / "test-charm"
    charm_build_path.mkdir()
    os.system(f"cp -R {APP_CHARM_PATH}/* {charm_build_path}/")
    subprocess.check_output("charmcraft clean", shell=True, cwd=charm_build_path)

    built_packages = glob.glob("./dist/*.tar.gz")
    dest_path = f"{charm_build_path}/{PACKAGE_NAME}.tar.gz"

    if not built_packages:
        raise Exception("Can't find built lib package.")

    shutil.copy(built_packages[0], dest_path)
    charm = await ops_test.build_charm(charm_build_path)
    yield charm

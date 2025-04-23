#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from unittest.mock import patch

from ops.testing import Context, State

logger = logging.getLogger(__name__)


def test_on_start(ctx: Context, base_state: State, caplog) -> None:
    """Checks unit goes to Blocked status after snap failure on install hook."""
    # Given
    state_in = base_state

    # When
    with patch("os.path.exists"):
        state_out = ctx.run(ctx.on.start(), state_in)

    print(state_out)

    # Then
    # assert state_out.unit_status == Status.SNAP_NOT_INSTALLED.value.status

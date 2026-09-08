from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from pytest import TempPathFactory


@pytest.fixture(scope="session", autouse=True)
def isolate_application_data(
    tmp_path_factory: TempPathFactory,
) -> Iterator[None]:
    previous = os.environ.get("LOCALAPPDATA")
    os.environ["LOCALAPPDATA"] = str(tmp_path_factory.mktemp("local-app-data"))
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = previous

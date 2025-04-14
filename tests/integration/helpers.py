import json
import random
import re
import shutil
import string
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import kafka
import requests
from ops.model import Unit
from pytest_operator.plugin import OpsTest

APP_CHARM_PATH = "./tests/app_charm"
APP_NAME = "integrator-app"
FILE_CONNECTOR_PATH = "./tests/resources/FileConnector.tar"
PACKAGE_NAME = "kafkacl"

CONNECT_APP = "kafka-connect"
CONNECT_CHANNEL = "latest/edge"
KAFKA_APP = "kafka"
KAFKA_CHANNEL = "3/edge"
PLUGIN_RESOURCE_KEY = "connect-plugin"


@dataclass
class CommandResult:
    return_code: int | None
    stdout: str
    stderr: str


@dataclass
class DatabaseFixtureParams:
    """Data model for database test data fixture requests."""

    app_name: str
    db_name: str
    no_tables: int = 1
    no_records: int = 1000


@contextmanager
def local_tmp_folder(name: str = "tmp"):
    if (tmp_folder := Path.cwd() / name).exists():
        shutil.rmtree(tmp_folder)
    tmp_folder.mkdir()

    yield tmp_folder

    shutil.rmtree(tmp_folder)


async def load_implementation(ops_test: OpsTest, unit: Unit, implementation_name: str):
    """Dynamically load an integrator implementation on specified unit."""
    unit_name_with_dash = unit.name.replace("/", "-")
    base_path = f"/var/lib/juju/agents/unit-{unit_name_with_dash}/charm/src"

    ret_code, _, _ = await ops_test.juju(
        "ssh",
        unit.name,
        f"sudo cp {base_path}/implementations/{implementation_name}.py {base_path}/integrator.py",
    )

    assert not ret_code


async def run_command_on_unit(
    ops_test: OpsTest, unit: Unit, command: str | list[str]
) -> CommandResult:
    """Runs a command on a given unit and returns the result."""
    command_args = command.split() if isinstance(command, str) else command
    return_code, stdout, stderr = await ops_test.juju("ssh", f"{unit.name}", *command_args)

    return CommandResult(return_code=return_code, stdout=stdout, stderr=stderr)


async def get_unit_ipv4_address(ops_test: OpsTest, unit: Unit) -> str | None:
    """A safer alternative for `juju.unit.get_public_address()` which is robust to network changes."""
    _, stdout, _ = await ops_test.juju("ssh", f"{unit.name}", "hostname -i")
    ipv4_matches = re.findall(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", stdout)

    if ipv4_matches:
        return ipv4_matches[0]

    return None


def download_file(url: str, dst_path: str):
    """Downloads a file from given `url` to `dst_path`."""
    response = requests.get(url, stream=True)
    with open(dst_path, mode="wb") as file:
        for chunk in response.iter_content(chunk_size=10 * 1024):
            file.write(chunk)


async def get_secret_data(ops_test: OpsTest, label_pattern: str) -> dict:
    """Gets data content of the secret matching the provided label pattern."""
    _, raw, _ = await ops_test.juju("secrets", "--format", "json")

    secrets_json = json.loads(raw)

    matching_secrets = [
        s for s in secrets_json if re.match(label_pattern, secrets_json[s]["label"])
    ]

    if not matching_secrets:
        raise Exception(f"CNo secrets matching {label_pattern} found!")

    secret_id = matching_secrets[0]

    _, secret_raw, _ = await ops_test.juju(
        "show-secret", "--reveal", "--format", "json", secret_id
    )
    secret_json = json.loads(secret_raw)

    return secret_json[secret_id]["content"]["Data"]


async def assert_messages_produced(
    ops_test: OpsTest, kafka_app: str, topic: str = "test", no_messages: int = 1
) -> None:
    """Asserts `no_messages` has been produced to `topic`."""
    data = await get_secret_data(ops_test, r"kafka-client\.[0-9]+\.user\.secret")

    username = data["username"]
    password = data["password"]
    server = await get_unit_ipv4_address(ops_test, ops_test.model.applications[kafka_app].units[0])

    consumer = kafka.KafkaConsumer(
        topic,
        bootstrap_servers=f"{server}:9092",
        sasl_mechanism="SCRAM-SHA-512",
        sasl_plain_username=username,
        sasl_plain_password=password,
        auto_offset_reset="earliest",
        security_protocol="SASL_PLAINTEXT",
        consumer_timeout_ms=5000,
    )

    messages = []
    for msg in consumer:
        messages.append(msg.value)

    assert len(messages) == no_messages


async def create_source_file(ops_test: OpsTest, path: str, no_records: int = 10):
    """Creates a source data file at provided path on the Kafka Connect worker unit containing `no_records` sample data."""
    connect_unit = ops_test.model.applications[CONNECT_APP].units[0]
    messages = []

    for i in range(no_records):
        random_title = "".join([random.choice(string.ascii_letters) for _ in range(16)])
        random_int = random.randint(10, 1000)
        messages.append(
            json.dumps(
                {"id": i + 1, "title": random_title, "count": random_int}, separators=(",", ":")
            )
        )

    res = await run_command_on_unit(
        ops_test,
        connect_unit,
        "; ".join([f"echo '{msg}' | sudo tee -a {path}" for msg in messages]),
    )
    assert not res.return_code

# Copyright 2024-2025 LMCache Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse


from lmcache.config import GlobalConfig
from lmcache.logging import init_logger
from lmcache.storage_backend.connector.base_connector import (
    RemoteConnector, RemoteConnectorDebugWrapper)
from lmcache.storage_backend.connector.lm_connector import LMCServerConnector
from lmcache.storage_backend.connector.redis_connector import (
    RedisConnector, RedisSentinelConnector)

logger = init_logger(__name__)


@dataclass
class ParsedRemoteURL:
    """
    The parsed URL of the format:
    <connector_type>://<username>:<password>@<host>:<port>,...
    Each entry may have its own credentials.
    """

    connector_type: str
    hosts: List[str]
    ports: List[int]
    usernames: List[Optional[str]]
    passwords: List[Optional[str]]


def parse_remote_url(url: str) -> ParsedRemoteURL:
    """
    Parses the remote URL into its constituent parts.

    Raises:
        ValueError: If the URL is invalid.
    """
    # Split once to get the scheme (connector type) and the rest

    hosts = []
    ports = []
    usernames = []
    passwords = []
    schemes = []

    for conn in url.split(","):
        pattern = r"(?P<scheme>[^:]+)://(?P<body>.+)"
        m = re.match(pattern, url)
        if not m:
            raise ValueError(f"Invalid remote url {url}")

        parsed = urlparse(conn)
        if not parsed.hostname or not parsed.port:
            raise ValueError(f"Invalid host:port pair in remote url {url}")
        schemes.append(parsed.scheme)
        hosts.append(parsed.hostname)
        ports.append(parsed.port)
        usernames.append(parsed.username)
        passwords.append(parsed.password)

    if len(set(schemes)) > 1:
        raise ValueError(f"Multiple connector types in remote url {url}")

    return ParsedRemoteURL(
        connector_type=set(schemes).pop(),
        hosts=hosts,
        ports=ports,
        usernames=usernames,
        passwords=passwords,
    )

def CreateConnector(url: str, device=None) -> RemoteConnector:
    """
    Creates the corresponding remote connector from the given URL.
    """
    m = re.match(r"(.*)://(.*):(\d+)", url)
    if m is None:
        raise ValueError(f"Invalid remote url {url}")

    parsed_url = parse_remote_url(url)
    num_hosts = len(parsed_url.hosts)

    connector: Optional[RemoteConnector] = None

    match parsed_url.connector_type:
        case "redis":
            if num_hosts == 1:
                host, port = parsed_url.hosts[0], parsed_url.ports[0]
                username = parsed_url.usernames[0]
                password = parsed_url.passwords[0]
                connector = RedisConnector(host, port, username, password)
            else:
                raise ValueError(
                    f"Redis connector only supports a single host, but got url:"
                    f" {url}")

        case "redis-sentinel":
            connector = RedisSentinelConnector(
                list(
                    zip(parsed_url.hosts,
                        map(int, parsed_url.ports),
                        strict=False)))

        case "lm":
            if num_hosts == 1:
                host, port = parsed_url.hosts[0], parsed_url.ports[0]
                connector = LMCServerConnector(host, port)
            else:
                raise ValueError(
                    f"LM connector only supports a single host, but got url:"
                    f" {url}")

        case _:
            raise ValueError(
                f"Unknown connector type {parsed_url.connector_type} "
                f"(url is: {url})")

    return (connector if not GlobalConfig.is_debug() else
            RemoteConnectorDebugWrapper(connector))

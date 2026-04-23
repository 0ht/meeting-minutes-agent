"""One-off admin: list / delete Foundry agents in the project.

Usage:
    python cleanup_foundry_agents.py list
    python cleanup_foundry_agents.py delete-all
    python cleanup_foundry_agents.py delete-by-name <name>

Auth: AzureCliCredential (run `az login` first).
"""
from __future__ import annotations

import sys

from azure.ai.agents import AgentsClient
from azure.identity import AzureCliCredential

ENDPOINT = (
    "https://aif-mtgminutes-dev.services.ai.azure.com/api/projects/proj-mtgminutes-dev"
)


def _client() -> AgentsClient:
    return AgentsClient(
        endpoint=ENDPOINT,
        credential=AzureCliCredential(process_timeout=60),
    )


def list_agents() -> None:
    c = _client()
    agents = list(c.list_agents())
    print(f"Found {len(agents)} agents:")
    for a in agents:
        print(f"  - {a.id}  name={a.name}  model={getattr(a, 'model', '?')}")


def delete_all() -> None:
    c = _client()
    agents = list(c.list_agents())
    print(f"Deleting {len(agents)} agents...")
    for a in agents:
        c.delete_agent(a.id)
        print(f"  deleted {a.id} ({a.name})")


def delete_by_name(name: str) -> None:
    c = _client()
    agents = [a for a in c.list_agents() if getattr(a, "name", None) == name]
    print(f"Deleting {len(agents)} agents named '{name}'...")
    for a in agents:
        c.delete_agent(a.id)
        print(f"  deleted {a.id}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        list_agents()
    elif cmd == "delete-all":
        delete_all()
    elif cmd == "delete-by-name" and len(sys.argv) > 2:
        delete_by_name(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(1)

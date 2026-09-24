from __future__ import annotations

from .delegate import delegate_backend

BACKEND = delegate_backend(
    engine="devin",
    cli_cmd="devin-delegate",
    title="devin-delegate",
    include_workspace=True,
)

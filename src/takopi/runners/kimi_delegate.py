from __future__ import annotations

from .delegate import delegate_backend

BACKEND = delegate_backend(engine="kd", cli_cmd="kimi-delegate", title="kimi-delegate")

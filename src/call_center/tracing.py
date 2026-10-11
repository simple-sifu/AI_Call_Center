"""LangSmith tracing toggle.

LangSmith reads only ``os.environ``, while settings may come from ``.env``. This exports
the tracing settings when tracing is requested and a key is present, and forces tracing
off otherwise, so a stray shell variable cannot enable it without a key.
"""

import os
import sys
from collections.abc import MutableMapping

from call_center.config import Settings, env_names

# Every name langsmith reads for the tracing flag; all are written so none can override.
TRACING_FLAGS: tuple[str, ...] = tuple(env_names("langsmith_tracing"))


def configure_tracing(settings: Settings, environ: MutableMapping[str, str] | None = None) -> bool:
    """Turn LangSmith tracing on or off in ``environ``; return whether it is on."""
    env = os.environ if environ is None else environ
    key = settings.langsmith_api_key
    if settings.langsmith_tracing and key is not None:
        for flag in TRACING_FLAGS:
            env[flag] = "true"
        env["LANGSMITH_API_KEY"] = key.get_secret_value()
        if settings.langsmith_project:
            env["LANGSMITH_PROJECT"] = settings.langsmith_project
        return True
    for flag in TRACING_FLAGS:
        env[flag] = "false"
    if settings.langsmith_tracing:
        print(
            "warning: LangSmith tracing requested but no API key is set "
            "(LANGSMITH_API_KEY / LANGCHAIN_API_KEY); tracing is off",
            file=sys.stderr,
        )
    return False


def flush_traces() -> None:
    """Block until queued traces are sent, so a short-lived CLI run is not lost."""
    from langchain_core.tracers.langchain import wait_for_all_tracers

    wait_for_all_tracers()

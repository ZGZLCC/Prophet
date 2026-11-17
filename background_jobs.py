"""Process-wide background work shared by the native API."""

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable


_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="prophet-job")


def submit(function: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Future:
    return _EXECUTOR.submit(function, *args, **kwargs)

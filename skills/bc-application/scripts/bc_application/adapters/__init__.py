"""University policy/binding adapters; factual data remains shared."""
from .uc import UCAdapter
from .mit import MITAdapter
from .common_app import CommonAppAdapter


def get_adapter(system: str):
    if system == "uc":
        return UCAdapter()
    if system == "mit":
        return MITAdapter()
    if system == "common_app":
        return CommonAppAdapter()
    raise ValueError("university_adapter_unavailable")

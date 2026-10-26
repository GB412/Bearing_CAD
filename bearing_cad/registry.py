"""Builder routing only; bearing model implementations belong in later PRs."""
from __future__ import annotations

from typing import Protocol

from .contracts import AssemblyModel, BearingRequest, BearingType, ContractError


class Builder(Protocol):
    def build(self, request: BearingRequest) -> AssemblyModel: ...


class BuilderRegistry:
    def __init__(self) -> None:
        self._builders: dict[BearingType, Builder] = {}

    def register(self, kind: BearingType, builder: Builder) -> None:
        if not isinstance(kind, BearingType) or kind in self._builders:
            raise ValueError("Invalid or duplicate builder registration")
        self._builders[kind] = builder

    def build(self, request: BearingRequest) -> AssemblyModel:
        builder = self._builders.get(request.bearing_type)
        if builder is None:
            raise ContractError("NOT_SUPPORTED", "/bearing_type", "CAD builder not yet implemented")
        return builder.build(request)

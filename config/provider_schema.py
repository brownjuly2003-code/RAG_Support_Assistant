from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROVIDER_REGISTRY_PATH = PROJECT_ROOT / "config" / "providers.yml"
_REGISTRY_CACHE: dict[Path, "ProviderRegistry"] = {}


class ProviderCapabilities(BaseModel):
    supports_tool_use: bool = False
    supports_structured_output: bool = False
    supports_vision: bool = False


class ProviderRateLimits(BaseModel):
    requests_per_minute: int = Field(default=0, ge=0)
    tokens_per_minute: int = Field(default=0, ge=0)


class ProviderDefaultModels(BaseModel):
    fast: str
    strong: str


class ProviderModel(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    input_price_per_1m_tokens: float = Field(default=0.0, ge=0.0)
    output_price_per_1m_tokens: float = Field(default=0.0, ge=0.0)


class ProviderConfig(BaseModel):
    id: str
    label: str
    kind: str
    enabled: bool = True
    api_key_env: str | None = None
    default_models: ProviderDefaultModels
    capabilities: ProviderCapabilities = Field(default_factory=ProviderCapabilities)
    rate_limits: ProviderRateLimits = Field(default_factory=ProviderRateLimits)
    models: list[ProviderModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_models(self) -> "ProviderConfig":
        if not self.models:
            raise ValueError(f"provider '{self.id}' must define at least one model")

        known_names = {model.name for model in self.models}
        known_aliases: set[str] = set()
        for model in self.models:
            duplicates = known_aliases.intersection(model.aliases)
            if duplicates:
                duplicate = sorted(duplicates)[0]
                raise ValueError(
                    f"provider '{self.id}' contains duplicate model alias '{duplicate}'"
                )
            known_aliases.update(model.aliases)

        if self.default_models.fast not in known_names:
            raise ValueError(
                f"provider '{self.id}' default fast model '{self.default_models.fast}' "
                "is not present in models"
            )
        if self.default_models.strong not in known_names:
            raise ValueError(
                f"provider '{self.id}' default strong model '{self.default_models.strong}' "
                "is not present in models"
            )
        return self

    def resolve_model(self, name_or_alias: str) -> ProviderModel | None:
        for model in self.models:
            if model.name == name_or_alias or name_or_alias in model.aliases:
                return model
        return None


class RoutingTarget(BaseModel):
    provider: str
    model: str


class RoutingProfile(BaseModel):
    description: str
    fast: RoutingTarget
    strong: RoutingTarget


class ProviderModelResolution(BaseModel):
    provider: str
    model: str
    input_price_per_1m_tokens: float
    output_price_per_1m_tokens: float


class ProviderRegistry(BaseModel):
    default_profile: str
    providers: list[ProviderConfig] = Field(default_factory=list)
    routing_profiles: dict[str, RoutingProfile] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_registry(self) -> "ProviderRegistry":
        provider_ids = [provider.id for provider in self.providers]
        if len(provider_ids) != len(set(provider_ids)):
            raise ValueError("provider ids must be unique")

        if self.default_profile not in self.routing_profiles:
            raise ValueError(
                f"default_profile '{self.default_profile}' is not defined in routing_profiles"
            )

        for profile_name, profile in self.routing_profiles.items():
            self._validate_target(profile_name, "fast", profile.fast)
            self._validate_target(profile_name, "strong", profile.strong)
        return self

    def _validate_target(self, profile_name: str, slot: str, target: RoutingTarget) -> None:
        provider = self.get_provider(target.provider)
        if provider is None:
            raise ValueError(
                f"routing_profiles.{profile_name}.{slot}.provider '{target.provider}' is undefined"
            )
        if provider.resolve_model(target.model) is None:
            raise ValueError(
                f"routing_profiles.{profile_name}.{slot}.model '{target.model}' "
                f"is undefined for provider '{target.provider}'"
            )

    def provider_ids(self) -> list[str]:
        return [provider.id for provider in self.providers]

    def get_provider(self, provider_id: str) -> ProviderConfig | None:
        for provider in self.providers:
            if provider.id == provider_id:
                return provider
        return None

    def get_profile(self, profile_name: str) -> RoutingProfile:
        return self.routing_profiles[profile_name]

    def resolve_model(self, name_or_alias: str) -> ProviderModelResolution:
        for provider in self.providers:
            resolved = provider.resolve_model(name_or_alias)
            if resolved is None:
                continue
            return ProviderModelResolution(
                provider=provider.id,
                model=resolved.name,
                input_price_per_1m_tokens=resolved.input_price_per_1m_tokens,
                output_price_per_1m_tokens=resolved.output_price_per_1m_tokens,
            )
        raise KeyError(f"unknown provider model alias: {name_or_alias}")


def load_provider_registry(
    path: str | Path | None = None,
    *,
    reload: bool = False,
) -> ProviderRegistry:
    target = Path(path or DEFAULT_PROVIDER_REGISTRY_PATH).resolve()
    if not reload and target in _REGISTRY_CACHE:
        return _REGISTRY_CACHE[target]

    payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    try:
        registry = ProviderRegistry.model_validate(payload)
    except ValidationError:
        raise
    _REGISTRY_CACHE[target] = registry
    return registry


__all__ = [
    "DEFAULT_PROVIDER_REGISTRY_PATH",
    "ProviderCapabilities",
    "ProviderConfig",
    "ProviderDefaultModels",
    "ProviderModel",
    "ProviderModelResolution",
    "ProviderRateLimits",
    "ProviderRegistry",
    "RoutingProfile",
    "RoutingTarget",
    "load_provider_registry",
]

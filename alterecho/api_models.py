"""Public contracts use participant A/B, independent of the actual provider."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Participant(Input):
    profile_id: str = Field(min_length=1, max_length=200)
    model: str = Field(default="", max_length=200)


class Configuration(Input):
    topic: str | None = Field(default=None, min_length=1, max_length=20000)
    mode: Literal["free", "debate", "blind"] | None = None
    first: Literal["A", "B"] | None = None
    max_turns: int | None = Field(default=None, ge=1, le=10000)
    delay: float | None = Field(default=None, ge=0, le=3600)
    timeout: float | None = Field(default=None, gt=0, le=3600)
    participants: dict[Literal["A", "B"], Participant] | None = None
    roles: dict[Literal["A", "B"], str] | None = None
    positions: dict[Literal["A", "B"], str] | None = None
    codex_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"] | None = None
    ollama_keep_alive: Literal[-1, 0, "5m", "10m"] | None = None
    ollama_unload_on_exit: bool | None = None
    num_ctx: int | None = Field(default=None, ge=512, le=2097152)
    num_predict: int | None = Field(default=None, ge=1, le=100000)
    api_max_output_tokens: int | None = Field(default=None, ge=1, le=100000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    ollama_options: dict | None = None


class RunRequest(Input):
    configuration: Configuration = Field(default_factory=Configuration)
    confirm_paid: bool = False
    demo: bool = False


class ResumeRequest(Input):
    max_turns: int = Field(ge=1, le=10000)
    num_ctx: int | None = Field(default=None, ge=512, le=2097152)
    confirm_paid: bool = False


class Profile(Input):
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    provider: Literal["codex", "ollama", "openai", "openrouter"]
    model: str = Field(default="", max_length=200)
    # These are references/configuration, never secret values. A caller cannot
    # select an executable; Codex binaries are controlled by the server owner.
    url: str = Field(default="", max_length=300)
    api_key_env: str = Field(default="", max_length=100)


class ProfilesRequest(Input):
    profiles: list[Profile] = Field(min_length=1, max_length=100)

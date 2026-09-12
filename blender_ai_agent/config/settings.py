"""
AgentConfig — Step 10.2
============================
Hinglish: User-configurable settings — provider choice, limits,
permissions. CRITICAL RULE: API keys yahan STORE nahi hote — sirf
environment variable NAME store hota hai, actual key kabhi nahi.
"""

import os
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class ProviderConfig:
    """Hinglish: Provider ka naam + settings — API key kabhi direct nahi, sirf env var name."""
    name: str = "mock"
    model_name: str = "mock-model"
    temperature: float = 0.7
    api_key_env_var: str = ""  # e.g. "OPENAI_API_KEY" — actual key nahi

    def get_api_key(self) -> str:
        """Hinglish: Runtime pe environment se padhta hai — kabhi hardcode/log/store nahi hota."""
        if not self.api_key_env_var:
            return ""
        return os.environ.get(self.api_key_env_var, "")


@dataclass
class PermissionConfig:
    """Hinglish: Kaunse permission levels ko confirmation chahiye — Step 10.17 security ka hissa."""
    python_execution_allowed: bool = False
    destructive_write_requires_confirmation: bool = True


@dataclass
class AgentConfig:
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    permissions: PermissionConfig = field(default_factory=PermissionConfig)
    max_steps: int = 20
    max_retries: int = 3
    vision_enabled: bool = True
    logging_level: str = "INFO"

    def __post_init__(self):
        if self.max_steps <= 0:
            raise ValueError("AgentConfig.max_steps must be positive")
        if self.max_retries < 0:
            raise ValueError("AgentConfig.max_retries must be non-negative")

    @classmethod
    def from_dict(cls, data: Dict) -> "AgentConfig":
        """Hinglish: Spec ke YAML-jaisa nested dict se config banata hai."""
        provider_data = data.get("provider", {})
        model_data = data.get("model", {})
        agent_data = data.get("agent", {})
        permissions_data = data.get("permissions", {})
        vision_data = data.get("vision", {})

        provider = ProviderConfig(
            name=provider_data if isinstance(provider_data, str) else provider_data.get("name", "mock"),
            model_name=model_data.get("name", "mock-model"),
            temperature=model_data.get("temperature", 0.7),
            api_key_env_var=provider_data.get("api_key_env_var", "") if isinstance(provider_data, dict) else "",
        )

        permissions = PermissionConfig(
            python_execution_allowed=permissions_data.get("python_execution", False),
            destructive_write_requires_confirmation=(
                permissions_data.get("destructive_write", "confirmation") == "confirmation"
            ),
        )

        return cls(
            provider=provider,
            permissions=permissions,
            max_steps=agent_data.get("max_steps", 20),
            max_retries=agent_data.get("max_retries", 3),
            vision_enabled=vision_data.get("enabled", True),
        )
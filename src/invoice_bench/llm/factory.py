"""LLM factory (decision D3: the LangChain chat-model interface is the provider adapter).

Default route: OpenRouter (`langchain-openrouter`), with upstream provider pinned in config/models.yaml.
Any other provider string falls back to `init_chat_model` (install that provider's LangChain package first).
"""
from __future__ import annotations

from pathlib import Path

import yaml
from langchain_core.language_models.chat_models import BaseChatModel


def load_model_cfg(name: str = "m2", path: str | Path = "config/models.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text())[name]


def get_chat_model(cfg: dict, cache=None) -> BaseChatModel:
    if cfg["provider"] == "openrouter":
        from langchain_openrouter import ChatOpenRouter
        kw = {"model": cfg["model"], "max_tokens": cfg.get("max_output_tokens", 800), "max_retries": cfg.get("max_retries", 2),
              "openrouter_provider": cfg.get("openrouter_provider"), "app_title": cfg.get("app_title"),
              "reasoning": cfg.get("reasoning"), "cache": cache}
        if cfg.get("temperature") is not None:
            kw["temperature"] = cfg["temperature"]
        return ChatOpenRouter(**{k: v for k, v in kw.items() if v is not None})
    from langchain.chat_models import init_chat_model
    kw = {"max_tokens": cfg.get("max_output_tokens", 800)}
    if cfg.get("temperature") is not None:
        kw["temperature"] = cfg["temperature"]
    return init_chat_model(f"{cfg['provider']}:{cfg['model']}", cache=cache, **kw)

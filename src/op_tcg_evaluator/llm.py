from langchain_anthropic import ChatAnthropic

from op_tcg_evaluator.config import get_settings


def get_chat_model() -> ChatAnthropic:
    settings = get_settings()
    return ChatAnthropic(
        model=settings.anthropic_model,
        api_key=settings.anthropic_api_key,
    )

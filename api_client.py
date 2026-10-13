"""Клиент LLM API — обёртка над ``llm.LLMClient``.

Принимает параметры ``temperature`` и ``max_tokens``, логирует
отправляемые параметры, токены и ориентировочную стоимость.

Пример:
    >>> from api_client import ApiClient
    >>> api = ApiClient()
    >>> result = await api.ask("Привет, мир", temperature=0.7, max_tokens=512)
    >>> print(result.content)
"""

from __future__ import annotations

import logging
from typing import Any

from llm import ChatMessage, ChatResult, LLMClient, LLMConfigError, LLMError

logger = logging.getLogger(__name__)


class ApiError(LLMError):
    """Ошибка обращения к API с информацией о параметрах запроса."""

    def __init__(self, message: str, *, params: dict[str, Any]) -> None:
        self.params = params
        super().__init__(message)


class ApiClient:
    """Обёртка над ``llm.LLMClient`` с параметрами и логированием.

    Args:
        model: Модель для запросов. ``None`` — модель из ``.env``.
        default_temperature: Температура по умолчанию.
        default_max_tokens: Max tokens по умолчанию.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        default_temperature: float = 0.7,
        default_max_tokens: int = 1024,
    ) -> None:
        self._client = LLMClient()
        self._model = model
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens

    # ------------------------------------------------------------------
    # Основной метод
    # ------------------------------------------------------------------

    def ask(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> ChatResult:
        """Отправляет сообщения в модель и возвращает ответ.

        Args:
            messages: Список сообщений формата ``{"role": ..., "content": ...}``.
            temperature: Температура генерации (используется default, если None).
            max_tokens: Максимальное число токенов ответа (используется default, если None).
            model: Модель для этого запроса (используется self._model, если None).

        Returns:
            ``ChatResult`` с полем ``content``, ``usage`` (токены) и ``model``.

        Raises:
            ApiError: при ошибке API или если список сообщений пуст.
        """
        temp = temperature if temperature is not None else self._default_temperature
        max_tok = max_tokens if max_tokens is not None else self._default_max_tokens
        model_name = model or self._model

        # Формируем лог-сообщение с отправляемыми параметрами
        payload_summary = {
            "model": model_name,
            "temperature": temp,
            "max_tokens": max_tok,
            "messages": len(messages),
        }
        logger.info("Запрос к LLM: %s", payload_summary)

        # Создаём объекты ChatMessage из словарей
        chat_messages = [ChatMessage(role=m["role"], content=m["content"]) for m in messages]

        try:
            result = self._client.chat(
                chat_messages,
                model=model_name,
                temperature=temp,
                extra_payload={"max_tokens": max_tok},
            )
        except LLMConfigError as exc:
            logger.error("Ошибка конфигурации (params=%s): %s", payload_summary, exc)
            raise ApiError(str(exc), params=payload_summary) from exc
        except LLMError as exc:
            logger.error("Ошибка LLM (params=%s): %s", payload_summary, exc)
            raise ApiError(str(exc), params=payload_summary) from exc

        # Логируем результат: токены и стоимость
        self._log_result(payload_summary, result)

        return result

    # ------------------------------------------------------------------
    # Утилиты
    # ------------------------------------------------------------------

    @staticmethod
    def estimate_cost(
        usage: dict[str, Any] | None,
        *,
        price_input: float = 104.0,
        price_output: float = 413.0,
    ) -> float:
        """Оценивает стоимость запроса по тарифам ProxyAPI.

        Args:
            usage: Словарь ``{"prompt_tokens": ..., "completion_tokens": ...}``.
            price_input: Цена ввода за 1М токенов (руб.).
            price_output: Цена вывода за 1М токенов (руб.).

        Returns:
            Ориентировочная стоимость в рублях (0.0 если usage отсутствует).
        """
        if usage is None:
            return 0.0
        prompt = usage.get("prompt_tokens", 0) or 0
        completion = usage.get("completion_tokens", 0) or 0
        return (prompt * price_input + completion * price_output) / 1_000_000

    @staticmethod
    def format_cost(cost: float) -> str:
        """Форматирует стоимость в строку для отображения пользователю."""
        if cost < 0.005:
            return f"<0.01 ₽"
        return f"{cost:.2f} ₽"

    def _log_result(self, params: dict[str, Any], result: ChatResult) -> None:
        """Логирует результат запроса: токены, модель, стоимость."""
        usage = result.usage or {}
        prompt_tokens = usage.get("prompt_tokens", "?")
        completion_tokens = usage.get("completion_tokens", "?")
        total_tokens = usage.get("total_tokens", "?")

        cost = self.estimate_cost(usage)

        logger.info(
            "Ответ LLM: %s | tokens: prompt=%s completion=%s total=%s | "
            "≈ %s",
            params["model"],
            prompt_tokens,
            completion_tokens,
            total_tokens,
            self.format_cost(cost),
        )

    def close(self) -> None:
        """Закрывает клиент."""
        self._client.close()


__all__ = ("ApiClient", "ApiError")

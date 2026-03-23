from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BillingPort(Protocol):
    """Заглушка оплаты / подписок до интеграции Т-Банка."""

    def subscription_message(self) -> str: ...
    def invite_friend_message(self, *, max_user_id: int) -> str: ...


class StubBillingService:
    def subscription_message(self) -> str:
        return (
            "Подписка и оплата подключаются через Т-Банк — раздел в разработке.\n"
            "Когда будет готово, здесь появится кнопка оплаты."
        )

    def invite_friend_message(self, *, max_user_id: int) -> str:
        return (
            "Пригласить друга: отправьте ему ссылку на этого бота в MAX.\n"
            f"(Ваш id в системе: {max_user_id} — для тестов начислений позже.)"
        )

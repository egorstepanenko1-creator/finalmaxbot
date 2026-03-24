"""Готовые черновики для шаблонов (consumer / business). Не секреты — только текст."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateItem:
    slug: str
    button_label: str
    """greeting | image | vk"""
    flow_kind: str
    draft: str
    hint: str


CONSUMER_TEMPLATES: tuple[TemplateItem, ...] = (
    TemplateItem(
        slug="birthday",
        button_label="День рождения",
        flow_kind="greeting",
        draft=(
            "Поздравление для **мамы** с днём рождения, **70 лет**, тёплый домашний тон, "
            "пожелания здоровья и радости, без сложных слов."
        ),
        hint="Тёплый тон, 3–6 коротких предложений + пожелание в конце.",
    ),
    TemplateItem(
        slug="holiday",
        button_label="Праздник (Новый год и др.)",
        flow_kind="greeting",
        draft=(
            "Новогоднее поздравление для **семьи**, добрый тон, упомянуть **здоровье** и **уют дома**, "
            "без канцелярита, для людей 60+."
        ),
        hint="Празднично, но просто; можно заменить праздник в тексте.",
    ),
    TemplateItem(
        slug="flowers_card",
        button_label="Открытка с цветами",
        flow_kind="image",
        draft=(
            "Нежная открытка: **букет полевых цветов** в вазе, светлый фон, мягкий свет, "
            "стиль акварели, надпись «С любовью» мелко в углу."
        ),
        hint="Светлая палитра, без мелкого шума на фоне.",
    ),
    TemplateItem(
        slug="family",
        button_label="Семейное поздравление",
        flow_kind="greeting",
        draft=(
            "Поздравление **внука с окончанием школы**, гордость за семью, пожелание **удачи** "
            "и **спокойствия** родителям, простой язык."
        ),
        hint="Акцент на семье и гордости, без жаргона.",
    ),
    TemplateItem(
        slug="universal",
        button_label="Универсальное «с праздником»",
        flow_kind="greeting",
        draft=(
            "Короткое поздравление «С праздником!» для **коллеги по даче**: добрый тон, пожелание "
            "**здоровья** и **хорошей погоды**, 4–5 предложений."
        ),
        hint="Универсально; замените «коллеги по даче» на своё.",
    ),
)

BUSINESS_TEMPLATES: tuple[TemplateItem, ...] = (
    TemplateItem(
        slug="sale",
        button_label="Распродажа",
        flow_kind="vk",
        draft=(
            "**Распродажа до конца недели**: скидка **20%** на всю обувь, адрес магазина и часы работы, "
            "призыв зайти сегодня, дружелюбный тон."
        ),
        hint="Короткий пост: выгода, срок, адрес/контакт, призыв.",
    ),
    TemplateItem(
        slug="new_arrivals",
        button_label="Новинки",
        flow_kind="vk",
        draft=(
            "**Привезли новую коллекцию** весенних пальто, размеры **48–58**, "
            "фото витрины приветствуется в посте текстом «ждём в гости», адрес."
        ),
        hint="Акцент на новизне и размерном ряду.",
    ),
    TemplateItem(
        slug="service_promo",
        button_label="Услуга / запись",
        flow_kind="vk",
        draft=(
            "**Запись на стрижку и окрашивание** — свободные окна **на этой неделе**, "
            "телефон для записи, напоминание про **мастера Анну**."
        ),
        hint="Услуга + срочность + контакт.",
    ),
    TemplateItem(
        slug="holiday_promo",
        button_label="Праздничная акция",
        flow_kind="vk",
        draft=(
            "**К 8 Марта** — подарочный сертификат **1000 ₽** при покупке от **3000 ₽**, "
            "действует до **10 марта**, адрес салона."
        ),
        hint="Праздник + условия акции + дедлайн.",
    ),
    TemplateItem(
        slug="vk_short",
        button_label="Короткий анонс",
        flow_kind="vk",
        draft=(
            "**Сегодня работаем до 20:00.** Свежая выпечка к вечеру. Ждём вас по адресу: "
            "(впишите улицу). #нашгород"
        ),
        hint="2–4 предложения; замените адрес и хештег.",
    ),
)

_CONSUMER_BY_SLUG = {t.slug: t for t in CONSUMER_TEMPLATES}
_BUSINESS_BY_SLUG = {t.slug: t for t in BUSINESS_TEMPLATES}


def get_consumer_template(slug: str) -> TemplateItem | None:
    return _CONSUMER_BY_SLUG.get(slug)


def get_business_template(slug: str) -> TemplateItem | None:
    return _BUSINESS_BY_SLUG.get(slug)

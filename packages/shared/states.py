"""Состояния state machine (M3). Значения — стабильные строковые константы."""

IDLE = "idle"

CONSUMER_AWAIT_QUESTION = "consumer.await_question"
CONSUMER_AWAIT_IMAGE_PROMPT = "consumer.await_image_prompt"
CONSUMER_AWAIT_GREETING_PROMPT = "consumer.await_greeting_prompt"

BUSINESS_AWAIT_VK_POST_PROMPT = "business.await_vk_post_prompt"
BUSINESS_AWAIT_IMAGE_PROMPT = "business.await_image_prompt"

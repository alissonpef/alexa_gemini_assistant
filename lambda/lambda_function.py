"""Entrypoint principal da AWS Lambda para a Skill Alexa GeminiChat."""

import logging

from ask_sdk_core.skill_builder import SkillBuilder
from handlers import (
    CancelOrStopIntentHandler,
    CatchAllExceptionHandler,
    ChatIntentHandler,
    HelpIntentHandler,
    LaunchRequestHandler,
    SessionEndedRequestHandler,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Registro ordenado de Request Handlers e Exception Handlers no SkillBuilder
sb = SkillBuilder()
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(ChatIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_exception_handler(CatchAllExceptionHandler())

lambda_handler = sb.lambda_handler()

"""Entrypoint principal da AWS Lambda para a Skill Alexa GeminiChat."""

import logging

from ask_sdk_core.skill_builder import SkillBuilder
from handlers import (
    CancelOrStopIntentHandler,
    CatchAllExceptionHandler,
    ChatIntentHandler,
    ClearHistoryIntentHandler,
    FallbackIntentHandler,
    HelpIntentHandler,
    LaunchRequestHandler,
    RepeatIntentHandler,
    SessionEndedRequestHandler,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Registro ordenado de Request Handlers e Exception Handlers no SkillBuilder
sb = SkillBuilder()
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(ClearHistoryIntentHandler())
sb.add_request_handler(RepeatIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(ChatIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_exception_handler(CatchAllExceptionHandler())

lambda_handler = sb.lambda_handler()

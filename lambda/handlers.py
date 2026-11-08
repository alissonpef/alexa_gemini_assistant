"""Handlers de requisições e exceções da Alexa (ASK SDK)."""

import logging

import ask_sdk_core.utils as ask_utils
from ask_sdk_core.dispatch_components import (
    AbstractExceptionHandler,
    AbstractRequestHandler,
)

try:
    from ask_sdk_model.ui import SimpleCard
except ImportError:
    SimpleCard = None

import config
import gemini_client
from session_manager import (
    atualizar_historico,
    obter_atributos_sessao,
    obter_historico,
    reiniciar_conversa,
)
from text_utils import (
    extrair_texto_gemini,
    limpar_texto_para_fala,
    normalizar_comando,
)

logger = logging.getLogger(__name__)


def _adicionar_card(response_builder, titulo, conteudo):
    """Adiciona um SimpleCard para dispositivos com tela (Echo Show, Fire TV) e app Alexa."""
    if SimpleCard is not None and hasattr(response_builder, "set_card"):
        try:
            response_builder.set_card(SimpleCard(title=titulo, content=conteudo))
        except (AttributeError, TypeError, ValueError) as err:
            logger.debug("Não foi possível anexar card visual: %s", err)
    return response_builder


class LaunchRequestHandler(AbstractRequestHandler):
    """Handler para abertura da Skill (LaunchRequest)."""

    def can_handle(self, handler_input):
        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        api_key = config.GOOGLE_API_KEY or config.carregar_api_key()
        if not api_key:
            speak_output = (
                "A chave da API do Google não foi encontrada. "
                "Configure a variável GOOGLE API KEY no arquivo ponto env."
            )
            return (
                handler_input.response_builder.speak(speak_output)
                .set_should_end_session(True)
                .response
            )

        session_attr = obter_atributos_sessao(handler_input)
        reiniciar_conversa(session_attr)

        speak_output = "Modo inteligente ativado. Como posso te ajudar?"
        session_attr["ultima_resposta"] = speak_output

        builder = handler_input.response_builder.speak(speak_output).ask(
            "Qual é a sua pergunta?"
        )
        _adicionar_card(builder, "Assistente Gemini", speak_output)
        return builder.response


class ChatIntentHandler(AbstractRequestHandler):
    """Handler principal para perguntas e comandos livres do usuário."""

    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("ChatIntent")(handler_input)

    def handle(self, handler_input):
        slots = (
            getattr(handler_input.request_envelope.request.intent, "slots", None) or {}
        )
        slot_query = slots.get("query")
        query = getattr(slot_query, "value", None) if slot_query else None
        if query:
            query = query.strip()

        if not query:
            return (
                handler_input.response_builder.speak(
                    "Não entendi a sua pergunta. Pode repetir?"
                )
                .ask("O que você gostaria de saber?")
                .response
            )

        session_attr = obter_atributos_sessao(handler_input)
        comando_norm = normalizar_comando(query)

        # 1. Intercepta comandos naturais de encerramento ("não", "só isso", "obrigado", "sair")
        if comando_norm in config.COMANDOS_ENCERRAR:
            return (
                handler_input.response_builder.speak(
                    "Até logo! Quando precisar, é só chamar."
                )
                .set_should_end_session(True)
                .response
            )

        # 2. Intercepta pedido para repetir a última resposta (0ms, sem gastar cota da API)
        if comando_norm in config.COMANDOS_REPETIR:
            ultima = session_attr.get("ultima_resposta")
            if ultima:
                fala = f"Claro, repetindo: {ultima}"
            else:
                fala = "Ainda não respondi nenhuma pergunta nesta sessão. O que você gostaria de saber?"
            return (
                handler_input.response_builder.speak(fala)
                .ask("Alguma outra pergunta?")
                .response
            )

        # 3. Intercepta pedido para limpar histórico / iniciar novo assunto
        if comando_norm in config.COMANDOS_LIMPAR:
            reiniciar_conversa(session_attr)
            fala = (
                "Histórico da conversa apagado! Sobre o que você quer conversar agora?"
            )
            session_attr["ultima_resposta"] = fala
            return (
                handler_input.response_builder.speak(fala)
                .ask("Qual é a sua pergunta?")
                .response
            )

        # 4. Intercepta pedido de ajuda
        if comando_norm in config.COMANDOS_AJUDA:
            fala = (
                "Você pode me fazer qualquer pergunta e eu responderei usando inteligência artificial. "
                "Diga nova conversa para mudar de assunto, repetir para ouvir de novo, ou sair para encerrar. "
                "O que você gostaria de perguntar?"
            )
            return (
                handler_input.response_builder.speak(fala)
                .ask("Qual é a sua pergunta?")
                .response
            )

        historico = obter_historico(session_attr)
        historico.append({"role": "user", "parts": [{"text": query}]})

        response = gemini_client.chamar_gemini({"contents": historico})

        if response and response.status_code == 200:
            try:
                response_data = response.json()
            except ValueError:
                response_data = {}

            texto_bruto = extrair_texto_gemini(response_data)
            if texto_bruto:
                speak_output = limpar_texto_para_fala(texto_bruto)
                historico.append({"role": "model", "parts": [{"text": texto_bruto}]})
                atualizar_historico(session_attr, historico)
                session_attr["ultima_resposta"] = speak_output
            else:
                historico.pop()
                atualizar_historico(session_attr, historico)
                speak_output = "Não consegui formular uma resposta para isso. Pode tentar perguntar de outra forma?"
        else:
            if historico and historico[-1].get("role") == "user":
                historico.pop()
            atualizar_historico(session_attr, historico)

            erro_api = gemini_client.obter_ultimo_erro()
            if erro_api == "chave_invalida":
                speak_output = "Sua chave da API do Google parece ser inválida ou não tem permissão. Verifique o arquivo ponto env."
            elif erro_api == "cota_ou_servidor":
                speak_output = "O serviço de inteligência artificial está sobrecarregado ou atingiu o limite de uso. Tente novamente em instantes."
            else:
                speak_output = "Não obtive resposta da inteligência artificial a tempo. Tente fazer uma pergunta mais direta."

        builder = handler_input.response_builder.speak(speak_output).ask(
            "Alguma outra pergunta?"
        )
        _adicionar_card(builder, f"Pergunta: {query}", speak_output)
        return builder.response


class HelpIntentHandler(AbstractRequestHandler):
    """Handler para pedidos nativos de ajuda (AMAZON.HelpIntent)."""

    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        speak_output = (
            "Esta skill conecta a Alexa ao Google Gemini. "
            "Basta fazer qualquer pergunta diretamente. "
            "Você também pode dizer nova conversa para limpar o histórico, "
            "repetir para ouvir a última resposta, ou sair para encerrar. "
            "Como posso te ajudar agora?"
        )
        return (
            handler_input.response_builder.speak(speak_output)
            .ask("Qual é a sua pergunta?")
            .response
        )


class CancelOrStopIntentHandler(AbstractRequestHandler):
    """Handler unificado para Cancel, Stop e NavigateHome."""

    def can_handle(self, handler_input):
        return (
            ask_utils.is_intent_name("AMAZON.CancelIntent")(handler_input)
            or ask_utils.is_intent_name("AMAZON.StopIntent")(handler_input)
            or ask_utils.is_intent_name("AMAZON.NavigateHomeIntent")(handler_input)
        )

    def handle(self, handler_input):
        return (
            handler_input.response_builder.speak("Até logo!")
            .set_should_end_session(True)
            .response
        )


class SessionEndedRequestHandler(AbstractRequestHandler):
    """Handler obrigatório para encerramento de sessão da Alexa (evita erro quando a sessão expira por silêncio)."""

    def can_handle(self, handler_input):
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        reason = getattr(handler_input.request_envelope.request, "reason", None)
        logger.info("Sessão encerrada. Motivo: %s", reason)
        return handler_input.response_builder.response


class CatchAllExceptionHandler(AbstractExceptionHandler):
    """Tratamento genérico de exceções para evitar que a Skill caia abruptamente."""

    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        logger.error("Exceção não tratada na Skill: %s", exception)
        try:
            if ask_utils.is_request_type("SessionEndedRequest")(handler_input):
                return handler_input.response_builder.response
        except (AttributeError, TypeError) as err:
            logger.debug("Erro ao verificar SessionEndedRequest: %s", err)

        speak_output = "Desculpe, ocorreu um erro interno na skill. Tente novamente."
        return (
            handler_input.response_builder.speak(speak_output)
            .ask("Pode repetir a sua pergunta?")
            .response
        )

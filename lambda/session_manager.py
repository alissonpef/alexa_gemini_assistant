"""Gerenciamento de estado da sessão da Alexa e janela deslizante do histórico de conversação."""

import logging

from config import MAX_HISTORICO_TURNOS

logger = logging.getLogger(__name__)


def limitar_historico(contents, max_turnos=None):
    """Mantém apenas os últimos turnos da conversa e garante alternância válida entre 'user' e 'model'."""
    if max_turnos is None:
        max_turnos = MAX_HISTORICO_TURNOS
    if not contents or not isinstance(contents, list):
        return []

    mensagens_validas = []
    for item in contents:
        if (
            isinstance(item, dict)
            and item.get("role") in ("user", "model")
            and item.get("parts")
        ):
            mensagens_validas.append(item)

    max_mensagens = max(2, max_turnos * 2)
    if len(mensagens_validas) > max_mensagens:
        mensagens_validas = mensagens_validas[-max_mensagens:]

    # A API do Gemini exige que o primeiro item em 'contents' tenha role == 'user'
    while mensagens_validas and mensagens_validas[0].get("role") != "user":
        mensagens_validas.pop(0)

    # Garante que não existam duas mensagens consecutivas do mesmo role
    historico_limpo = []
    for msg in mensagens_validas:
        if historico_limpo and historico_limpo[-1].get("role") == msg.get("role"):
            historico_limpo[-1] = msg
        else:
            historico_limpo.append(msg)

    return historico_limpo


def obter_atributos_sessao(handler_input):
    """Obtém o dicionário de atributos da sessão da Alexa com fallback seguro."""
    try:
        if handler_input and getattr(handler_input, "attributes_manager", None):
            attrs = handler_input.attributes_manager.session_attributes
            if isinstance(attrs, dict):
                return attrs
    except (AttributeError, TypeError) as err:
        logger.debug("Não foi possível acessar session_attributes: %s", err)
    return {}


def reiniciar_conversa(session_attr):
    """Reinicia o histórico de conversação na sessão atual."""
    if isinstance(session_attr, dict):
        session_attr["history"] = []


def obter_historico(session_attr):
    """Recupera o histórico isolado da sessão atual da Alexa."""
    if isinstance(session_attr, dict):
        historico = session_attr.get("history")
        if isinstance(historico, list):
            return list(historico)
    return []


def atualizar_historico(session_attr, historico):
    """Sincroniza o histórico atualizado e podado na sessão atual."""
    historico_podado = limitar_historico(historico)
    if isinstance(session_attr, dict):
        session_attr["history"] = list(historico_podado)
    return historico_podado

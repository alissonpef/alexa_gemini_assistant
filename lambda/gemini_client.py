"""Cliente HTTP resiliente e otimizado para a API Google Gemini com Keep-Alive, rotação de modelos e cache."""

import copy
import logging
import time
from datetime import date

import config
import requests
from requests.adapters import HTTPAdapter
from session_manager import limitar_historico

logger = logging.getLogger(__name__)

# Sessão HTTP persistente com Keep-Alive para economizar handshake TCP/TLS (150ms–400ms por chamada)
HTTP_SESSION = requests.Session()
_adapter = HTTPAdapter(pool_connections=4, pool_maxsize=4, max_retries=0)
HTTP_SESSION.mount("https://", _adapter)
HTTP_SESSION.mount("http://", _adapter)

headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# Estado do roteador inteligente de modelos (persistido entre invocações quentes do AWS Lambda)
indice_modelo_atual = 0
_modelo_confirmado = False
_modelos_inexistentes = set()
_modelos_sem_thinking = {"gemini-3.5-flash-lite"}
_modelos_cooldown = {}
_catalogo_sincronizado = False
_ultimo_erro_api = None

# Rastreamento de taxa em memória (RPM e RPD)
_historico_rpm = {}  # modelo -> list[float timestamps nos últimos 60s]
_historico_rpd = {}  # modelo -> {"data": date, "contagem": int}


def obter_ultimo_erro():
    """Retorna o código do último erro ocorrido na chamada à API ('chave_invalida', 'cota_ou_servidor', 'timeout')."""
    return _ultimo_erro_api


def _atingiu_limite_taxa(modelo, agora):
    """Verifica proativamente se o modelo atingiu sua cota de RPM ou RPD antes de gastar chamada de rede."""
    limites = config.QUOTAS_MODELOS.get(modelo)
    if not limites:
        return False

    # 1. Checa limite de RPM (Requisições por Minuto)
    rpm_max = limites.get("rpm", 5)
    timestamps = _historico_rpm.get(modelo, [])
    # Poda chamadas com mais de 60 segundos
    timestamps_ativos = [t for t in timestamps if agora - t < 60.0]
    _historico_rpm[modelo] = timestamps_ativos
    if len(timestamps_ativos) >= rpm_max:
        logger.warning(
            "Modelo %s atingiu limite de %s RPM (%s requisições no último minuto). Pulando...",
            modelo,
            rpm_max,
            len(timestamps_ativos),
        )
        return True

    # 2. Checa limite de RPD (Requisições por Dia)
    rpd_max = limites.get("rpd", 20)
    hoje = date.today()
    info_dia = _historico_rpd.get(modelo)
    if info_dia and info_dia.get("data") == hoje:
        if info_dia.get("contagem", 0) >= rpd_max:
            logger.warning(
                "Modelo %s atingiu limite diário de %s RPD (%s hoje). Pulando...",
                modelo,
                rpd_max,
                info_dia.get("contagem"),
            )
            return True
    else:
        _historico_rpd[modelo] = {"data": hoje, "contagem": 0}

    return False


def _registrar_sucesso_modelo(modelo, agora):
    """Registra uma requisição bem-sucedida para o controle de RPM e RPD do modelo."""
    # Atualiza RPM
    timestamps = _historico_rpm.setdefault(modelo, [])
    timestamps.append(agora)
    _historico_rpm[modelo] = [t for t in timestamps if agora - t < 60.0]

    # Atualiza RPD
    hoje = date.today()
    info_dia = _historico_rpd.setdefault(modelo, {"data": hoje, "contagem": 0})
    if info_dia.get("data") != hoje:
        info_dia["data"] = hoje
        info_dia["contagem"] = 0
    info_dia["contagem"] += 1


def montar_payload(contents, incluir_thinking=True):
    """Monta o payload otimizado para a API Gemini com systemInstruction, generationConfig e thinkingConfig."""
    gen_config = {
        "maxOutputTokens": config.GEMINI_MAX_TOKENS,
        "temperature": config.GEMINI_TEMPERATURE,
    }
    if incluir_thinking and config.GEMINI_THINKING_BUDGET >= 0:
        gen_config["thinkingConfig"] = {"thinkingBudget": config.GEMINI_THINKING_BUDGET}

    return {
        "systemInstruction": {"parts": [{"text": config.INSTRUCAO_SISTEMA}]},
        "contents": limitar_historico(contents),
        "generationConfig": gen_config,
    }


def _sincronizar_catalogo_modelos(api_key, tempo_restante):
    """Consulta rapidamente a lista de modelos disponíveis na conta após o primeiro 404 para pular modelos inexistentes."""
    global _catalogo_sincronizado
    if _catalogo_sincronizado or tempo_restante <= 1.8:
        return

    _catalogo_sincronizado = True
    try:
        req_headers = dict(headers)
        if api_key:
            req_headers["x-goog-api-key"] = api_key
        res = HTTP_SESSION.get(
            f"{config.GEMINI_API_BASE_URL}?pageSize=100",
            headers=req_headers,
            timeout=(0.8, min(1.2, tempo_restante - 0.5)),
        )
        if res.status_code != 200:
            return
        dados = res.json()
        if not isinstance(dados, dict) or not isinstance(dados.get("models"), list):
            return

        modelos_suportados = set()
        for m in dados["models"]:
            if not isinstance(m, dict):
                continue
            nome = m.get("name", "")
            metodos = m.get("supportedGenerationMethods", ["generateContent"])
            if nome and "generateContent" in metodos:
                modelos_suportados.add(nome.replace("models/", ""))

        if not modelos_suportados:
            return

        algum_da_lista_existe = any(
            m in modelos_suportados for m in config.MODELOS_GEMINI
        )
        if algum_da_lista_existe:
            for m in config.MODELOS_GEMINI:
                if m not in modelos_suportados:
                    _modelos_inexistentes.add(m)
            logger.info(
                "Catálogo sincronizado. Modelos indisponíveis ignorados: %s",
                _modelos_inexistentes,
            )
    except (requests.RequestException, ValueError, KeyError) as err:
        logger.debug("Não foi possível sincronizar catálogo de modelos: %s", err)


def _erro_chave_invalida(response):
    """Verifica se o erro retornado pela API indica chave inválida ou sem permissão."""
    if response.status_code in (401, 403):
        return True
    if response.status_code == 400:
        try:
            texto = response.text or ""
            if "API_KEY_INVALID" in texto or "API key not valid" in texto:
                return True
        except (AttributeError, ValueError, TypeError) as err:
            logger.debug("Erro ao verificar corpo de erro 400: %s", err)
    return False


def _erro_thinking_nao_suportado(response):
    """Verifica se um erro 400 ocorreu porque o modelo não aceita o parâmetro thinkingConfig."""
    if response.status_code == 400:
        try:
            texto = (response.text or "").lower()
            if (
                "thinking" in texto
                or "invalid_argument" in texto
                or "invalid argument" in texto
            ):
                return True
        except (AttributeError, ValueError, TypeError) as err:
            logger.debug("Erro ao verificar erro de thinkingConfig: %s", err)
    return False


def chamar_gemini(payload, api_key_override=None):
    """Percorre os modelos respeitando o limite máximo de tempo da Alexa com cache inteligente de disponibilidade."""
    global indice_modelo_atual, _modelo_confirmado, _ultimo_erro_api
    _ultimo_erro_api = None

    api_key = api_key_override or config.GOOGLE_API_KEY or config.carregar_api_key()
    modelos = config.MODELOS_GEMINI
    total_modelos = len(modelos)
    inicio = time.monotonic()

    if isinstance(payload, dict) and "contents" in payload:
        payload_base = montar_payload(payload["contents"], incluir_thinking=True)
        if "systemInstruction" in payload:
            payload_base["systemInstruction"] = payload["systemInstruction"]
        if "generationConfig" in payload:
            payload_base["generationConfig"] = copy.deepcopy(
                payload["generationConfig"]
            )
    else:
        payload_base = copy.deepcopy(payload)

    req_headers = dict(headers)
    if api_key:
        req_headers["x-goog-api-key"] = api_key

    tentativas_realizadas = 0

    for offset in range(total_modelos):
        agora = time.monotonic()
        tempo_decorrido = agora - inicio
        tempo_restante = config.ALEXA_TIMEOUT_BUDGET - tempo_decorrido

        # Se o tempo estiver quase esgotado, faz uma última tentativa rápida num modelo leve disponível
        if tempo_restante <= 1.2:
            if tempo_restante > 0.4:
                modelo_emergencia = (
                    "gemini-3.5-flash-lite"
                    if "gemini-3.5-flash-lite" not in _modelos_inexistentes
                    else modelos[-1]
                )
                logger.warning(
                    "Tempo limite da Alexa quase atingido (%.2fs restantes). Tentando %s.",
                    tempo_restante,
                    modelo_emergencia,
                )
                url_emergencia = (
                    f"{config.GEMINI_API_BASE_URL}/{modelo_emergencia}:generateContent"
                )
                try:
                    res = HTTP_SESSION.post(
                        url_emergencia,
                        json=payload_base,
                        headers=req_headers,
                        timeout=(0.6, max(0.5, tempo_restante)),
                    )
                    if res.status_code == 200:
                        _registrar_sucesso_modelo(modelo_emergencia, time.monotonic())
                        return res
                except requests.RequestException as err:
                    logger.debug("Tentativa de emergência falhou: %s", err)
            _ultimo_erro_api = "timeout"
            break

        idx = (indice_modelo_atual + offset) % total_modelos
        modelo = modelos[idx]

        # Pula imediatamente modelos que já retornaram 404 nesta instância do Lambda
        if modelo in _modelos_inexistentes:
            continue

        # Pula modelos em cooldown temporário (429 / 503 recente), a menos que todos estejam em cooldown
        expira_cooldown = _modelos_cooldown.get(modelo, 0.0)
        if expira_cooldown > agora and offset < total_modelos - 1:
            continue

        # Checa proativamente se o modelo atingiu sua cota de RPM ou RPD antes de gastar requisição de rede
        if _atingiu_limite_taxa(modelo, agora) and offset < total_modelos - 1:
            continue

        if modelo in _modelos_sem_thinking and isinstance(payload_base, dict):
            gen_sem_thinking = {
                k: v
                for k, v in payload_base.get("generationConfig", {}).items()
                if k != "thinkingConfig"
            }
            payload_modelo = {**payload_base, "generationConfig": gen_sem_thinking}
        else:
            payload_modelo = payload_base

        url = f"{config.GEMINI_API_BASE_URL}/{modelo}:generateContent"
        tentativas_realizadas += 1

        limite_leitura = 3.8 if (_modelo_confirmado and offset == 0) else 2.5
        timeout_leitura = min(limite_leitura, max(0.8, tempo_restante - 0.2))
        timeout_conexao = min(1.5, timeout_leitura)

        try:
            response = HTTP_SESSION.post(
                url,
                json=payload_modelo,
                headers=req_headers,
                timeout=(timeout_conexao, timeout_leitura),
            )

            # Caso o modelo não aceite thinkingConfig, remove o parâmetro e tenta o mesmo modelo imediatamente
            if (
                _erro_thinking_nao_suportado(response)
                and modelo not in _modelos_sem_thinking
            ):
                _modelos_sem_thinking.add(modelo)
                if isinstance(payload_base, dict):
                    gen_sem_thinking = {
                        k: v
                        for k, v in payload_base.get("generationConfig", {}).items()
                        if k != "thinkingConfig"
                    }
                    payload_modelo = {
                        **payload_base,
                        "generationConfig": gen_sem_thinking,
                    }
                tempo_restante_retry = config.ALEXA_TIMEOUT_BUDGET - (
                    time.monotonic() - inicio
                )
                if tempo_restante_retry > 1.0:
                    response = HTTP_SESSION.post(
                        url,
                        json=payload_modelo,
                        headers=req_headers,
                        timeout=(
                            min(1.2, tempo_restante_retry),
                            min(2.5, tempo_restante_retry - 0.1),
                        ),
                    )

            if response.status_code == 200:
                indice_modelo_atual = idx
                _modelo_confirmado = True
                _modelos_cooldown.pop(modelo, None)
                _registrar_sucesso_modelo(modelo, time.monotonic())
                logger.info(
                    "Sucesso usando o modelo: %s (em %.2fs)",
                    modelo,
                    time.monotonic() - inicio,
                )
                return response

            if _erro_chave_invalida(response):
                logger.error(
                    "Chave da API do Google inválida ou sem permissão (Status %s).",
                    response.status_code,
                )
                _ultimo_erro_api = "chave_invalida"
                break

            if response.status_code == 404:
                logger.warning(
                    "Modelo %s não encontrado (404). Marcando como indisponível.",
                    modelo,
                )
                _modelos_inexistentes.add(modelo)
                _modelo_confirmado = False
                tempo_restante_pos_404 = config.ALEXA_TIMEOUT_BUDGET - (
                    time.monotonic() - inicio
                )
                _sincronizar_catalogo_modelos(api_key, tempo_restante_pos_404)
                continue

            if response.status_code in (429, 500, 502, 503, 504):
                logger.warning(
                    "Modelo %s temporariamente indisponível (Status %s). Aplicando cooldown e tentando próximo...",
                    modelo,
                    response.status_code,
                )
                # No caso de 429 (Resource Exhausted), se for cota diária ou por minuto, aplica cooldown
                _modelos_cooldown[modelo] = (
                    time.monotonic() + config.COOLDOWN_ERRO_SEGUNDOS
                )
                _ultimo_erro_api = "cota_ou_servidor"
                continue

            if response.status_code == 400:
                logger.warning("Erro 400 no modelo %s. Tentando próximo...", modelo)
                continue

            logger.error(
                "Erro inesperado na API com %s: Status %s", modelo, response.status_code
            )
            break

        except requests.exceptions.RequestException as err:
            logger.warning(
                "Timeout/erro de rede no modelo %s: %s. Tentando próximo...",
                modelo,
                type(err).__name__,
            )
            _modelos_cooldown[modelo] = time.monotonic() + 15.0
            _ultimo_erro_api = "timeout"
            continue

    if tentativas_realizadas == 0 and _modelos_inexistentes:
        _modelos_inexistentes.clear()

    return None

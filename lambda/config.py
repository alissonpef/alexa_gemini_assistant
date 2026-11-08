"""Módulo de configuração, variáveis de ambiente e constantes da Skill."""

import logging
import os

logger = logging.getLogger(__name__)

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def carregar_variaveis_env():
    """Lê arquivos .env (na pasta lambda/ ou na raiz do projeto) sem depender de bibliotecas externas."""
    valores = {}
    diretorio_atual = os.path.dirname(os.path.abspath(__file__))
    caminhos_candidatos = [
        os.path.join(diretorio_atual, ".env"),
        os.path.join(os.path.dirname(diretorio_atual), ".env"),
    ]

    for env_path in caminhos_candidatos:
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for linha in f:
                        linha = linha.strip()
                        if not linha or linha.startswith("#"):
                            continue
                        if linha.startswith("export "):
                            linha = linha[7:].strip()
                        if "=" in linha:
                            chave, valor = linha.split("=", 1)
                            chave = chave.strip()
                            valor = valor.strip().strip('"').strip("'")
                            if chave and chave not in valores:
                                valores[chave] = valor
            except OSError as err:
                logger.warning(
                    "Não foi possível ler arquivo .env em %s: %s", env_path, err
                )
    return valores


_ENV_CACHE = carregar_variaveis_env()


def obter_config(chave, padrao=""):
    """Obtém uma configuração do ambiente do sistema ou do cache do arquivo .env."""
    valor = os.environ.get(chave)
    if valor is not None and valor.strip() != "":
        return valor.strip().strip('"').strip("'")
    return _ENV_CACHE.get(chave, padrao)


def obter_int(chave, padrao):
    """Obtém uma configuração inteira com fallback seguro."""
    try:
        return int(obter_config(chave, str(padrao)))
    except (ValueError, TypeError):
        return padrao


def obter_float(chave, padrao):
    """Obtém uma configuração float com fallback seguro."""
    try:
        return float(obter_config(chave, str(padrao)))
    except (ValueError, TypeError):
        return padrao


def carregar_api_key():
    """Obtém a GOOGLE_API_KEY do ambiente ou do arquivo .env."""
    key = obter_config("GOOGLE_API_KEY")
    if key:
        return key
    return carregar_variaveis_env().get("GOOGLE_API_KEY", "")


# Parâmetros globais de execução e limites da Alexa
GOOGLE_API_KEY = carregar_api_key()
GEMINI_MAX_TOKENS = obter_int("GEMINI_MAX_TOKENS", 500)
GEMINI_TEMPERATURE = obter_float("GEMINI_TEMPERATURE", 0.6)
GEMINI_THINKING_BUDGET = obter_int("GEMINI_THINKING_BUDGET", 0)
ALEXA_TIMEOUT_BUDGET = obter_float("ALEXA_TIMEOUT_BUDGET", 6.4)
MAX_HISTORICO_TURNOS = obter_int("MAX_HISTORY_TURNS", 6)
MAX_CARACTERES_FALA = 1500
COOLDOWN_ERRO_SEGUNDOS = 60.0

# Quotas e limites do plano do usuário no Google AI Studio:
# RPM: Requests Per Minute | RPD: Requests Per Day
# Modelos Lite oferecem 500 RPD e 15 RPM (25x mais cota diária que os 20 RPD do Flash regular)
QUOTAS_MODELOS = {
    "gemini-3.5-flash-lite": {
        "rpm": obter_int("QUOTA_GEMINI_3_5_FLASH_LITE_RPM", 15),
        "rpd": obter_int("QUOTA_GEMINI_3_5_FLASH_LITE_RPD", 500),
    },
    "gemini-3.1-flash-lite": {
        "rpm": obter_int("QUOTA_GEMINI_3_1_FLASH_LITE_RPM", 15),
        "rpd": obter_int("QUOTA_GEMINI_3_1_FLASH_LITE_RPD", 500),
    },
    "gemini-3.6-flash": {
        "rpm": obter_int("QUOTA_GEMINI_3_6_FLASH_RPM", 5),
        "rpd": obter_int("QUOTA_GEMINI_3_6_FLASH_RPD", 20),
    },
    "gemini-3.8-flash": {
        "rpm": obter_int("QUOTA_GEMINI_3_8_FLASH_RPM", 5),
        "rpd": obter_int("QUOTA_GEMINI_3_8_FLASH_RPD", 20),
    },
    "gemini-3.7-flash": {
        "rpm": obter_int("QUOTA_GEMINI_3_7_FLASH_RPM", 5),
        "rpd": obter_int("QUOTA_GEMINI_3_7_FLASH_RPD", 20),
    },
    "gemini-3.5-flash": {
        "rpm": obter_int("QUOTA_GEMINI_3_5_FLASH_RPM", 5),
        "rpd": obter_int("QUOTA_GEMINI_3_5_FLASH_RPD", 20),
    },
}

# Lista de modelos reais validados na API v1beta, ordenada estrategicamente por cota e latência:
# 1º: Modelos Lite (500 RPD / 15 RPM) -> maior cota diária, menor latência, não esgotam fácil.
# 2º: Modelos Flash regulares (20 RPD / 5 RPM) -> retaguarda inteligente ordenada por velocidade.
MODELOS_GEMINI = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash",
]

_modelo_custom = obter_config("GEMINI_MODEL", "")
if _modelo_custom and _modelo_custom not in MODELOS_GEMINI:
    MODELOS_GEMINI.insert(0, _modelo_custom)
elif _modelo_custom in MODELOS_GEMINI:
    MODELOS_GEMINI.remove(_modelo_custom)
    MODELOS_GEMINI.insert(0, _modelo_custom)

INSTRUCAO_SISTEMA = (
    "Você é uma assistente de voz inteligente integrada à Alexa, falando em português do Brasil. "
    "Suas respostas serão lidas em voz alta, portanto siga estas regras: "
    "1. Responda de forma curta, direta e natural, em no máximo 2 ou 3 frases (a menos que o usuário peça detalhes). "
    "2. NUNCA use formatação Markdown, asteriscos (*), hashtags (#), crases (`), blocos de código, tabelas ou links. "
    "3. Prefira frases corridas e fluidas em vez de listas com marcadores. "
    "4. Vá direto ao ponto sem introduções desnecessárias."
)

# Conjuntos de comandos de voz naturais (interceptados em 0ms sem gastar chamada de API)
COMANDOS_ENCERRAR = {
    "nao",
    "obrigado",
    "obrigada",
    "so isso",
    "era so isso",
    "mais nada",
    "nada",
    "nada obrigado",
    "nada obrigada",
    "nao obrigado",
    "nao obrigada",
    "valeu",
    "encerrar",
    "sair",
    "parar",
    "fechar",
    "cancelar",
    "tchau",
    "ate logo",
    "ate mais",
    "pode fechar",
    "desligar",
    "fim",
}

COMANDOS_REPETIR = {
    "repete",
    "repetir",
    "repita",
    "pode repetir",
    "repete por favor",
    "o que voce disse",
    "fala de novo",
    "diga novamente",
    "nao ouvi",
    "nao entendi",
}

COMANDOS_LIMPAR = {
    "limpar",
    "limpar conversa",
    "limpar historico",
    "apagar historico",
    "nova conversa",
    "novo assunto",
    "novo chat",
    "esqueca tudo",
    "reiniciar",
    "reiniciar conversa",
    "comecar de novo",
    "comecar do zero",
}

COMANDOS_AJUDA = {
    "ajuda",
    "me ajuda",
    "como funciona",
    "como usar",
    "o que voce faz",
    "comandos",
}

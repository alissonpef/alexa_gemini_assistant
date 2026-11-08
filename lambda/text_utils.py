"""Funções puras de processamento de texto, sanitização para voz (SSML) e extração de resposta."""

import logging
import re
import unicodedata

from config import MAX_CARACTERES_FALA

logger = logging.getLogger(__name__)

# Expressões regulares pré-compiladas para menor latência na AWS Lambda
_RE_NAO_ALFANUM = re.compile(r"[^\w\s]")
_RE_ESPACOS = re.compile(r"\s+")
_RE_BLOCO_CODIGO = re.compile(r"```[\s\S]*?```")
_RE_CODIGO_INLINE = re.compile(r"`([^`]*)`")
_RE_LINK_MD = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_RE_URL = re.compile(r"https?://\S+")
_RE_CABECALHO_MD = re.compile(r"(?m)^\s*#{1,6}\s+")
_RE_CITACAO_MD = re.compile(r"(?m)^\s*>\s+")
_RE_LISTA_MD = re.compile(r"(?m)^\s*[-*+•]\s+")
_RE_FORMATACAO_MD = re.compile(r"[*_~#`|]")


def normalizar_comando(texto):
    """Normaliza texto para comparação de comandos de voz (minúsculas, sem acentos e sem pontuação)."""
    if not texto:
        return ""
    texto_nfd = unicodedata.normalize("NFD", texto.lower().strip())
    sem_acentos = "".join(ch for ch in texto_nfd if unicodedata.category(ch) != "Mn")
    sem_pontuacao = _RE_NAO_ALFANUM.sub(" ", sem_acentos)
    return _RE_ESPACOS.sub(" ", sem_pontuacao).strip()


def limpar_texto_para_fala(texto):
    """Remove Markdown, URLs e caracteres inválidos de SSML/XML para leitura fluida e segura na Alexa."""
    if not texto:
        return ""

    # Remove blocos de código cercados por crases
    limpo = _RE_BLOCO_CODIGO.sub(" ", texto)
    # Remove crases inline mantendo o conteúdo
    limpo = _RE_CODIGO_INLINE.sub(r"\1", limpo)
    # Converte links Markdown [texto](url) apenas no texto
    limpo = _RE_LINK_MD.sub(r"\1", limpo)
    # Remove URLs soltas
    limpo = _RE_URL.sub("", limpo)
    # Remove cabeçalhos Markdown (#, ##, ###)
    limpo = _RE_CABECALHO_MD.sub("", limpo)
    # Remove indicadores de citação Markdown (> no início da linha)
    limpo = _RE_CITACAO_MD.sub("", limpo)
    # Remove marcadores de lista no início de linhas (- , * , + , • )
    limpo = _RE_LISTA_MD.sub("", limpo)
    # Remove caracteres de formatação Markdown restantes
    limpo = _RE_FORMATACAO_MD.sub("", limpo)

    # Substitui caracteres reservados do XML/SSML que causam erro na Alexa
    limpo = limpo.replace("&", " e ")
    limpo = limpo.replace("<", " menor que ")
    limpo = limpo.replace(">", " maior que ")

    # Transforma quebras de linha em pausas naturais de pontuação
    linhas = [linha.strip() for linha in limpo.splitlines() if linha.strip()]
    partes_formatadas = []
    for linha in linhas:
        if linha and linha[-1] not in ".!?:;,":
            linha += "."
        partes_formatadas.append(linha)
    limpo = " ".join(partes_formatadas)

    # Remove espaços duplicados
    limpo = _RE_ESPACOS.sub(" ", limpo).strip()

    # Trunca de forma segura na última frase caso ultrapasse o limite recomendado de fala
    if len(limpo) > MAX_CARACTERES_FALA:
        corte = limpo[:MAX_CARACTERES_FALA]
        ultimo_ponto = max(corte.rfind("."), corte.rfind("!"), corte.rfind("?"))
        if ultimo_ponto > MAX_CARACTERES_FALA // 2:
            limpo = corte[: ultimo_ponto + 1]
        else:
            limpo = corte.rstrip() + "..."

    return limpo


def extrair_texto_gemini(response_data):
    """Extrai o texto de resposta do JSON do Gemini com segurança, ignorando blocos de raciocínio interno (thought)."""
    if not isinstance(response_data, dict):
        return None

    candidates = response_data.get("candidates")
    if not candidates or not isinstance(candidates, list):
        bloqueio = response_data.get("promptFeedback", {}).get("blockReason")
        if bloqueio:
            logger.warning("Prompt bloqueado pelo filtro de segurança: %s", bloqueio)
            return "Por questões de segurança da plataforma, não posso responder a essa pergunta."
        return None

    primeiro_candidato = candidates[0] if isinstance(candidates[0], dict) else {}
    finish_reason = primeiro_candidato.get("finishReason", "")
    content = primeiro_candidato.get("content", {})
    parts = content.get("parts", []) if isinstance(content, dict) else []

    textos_finais = []
    textos_fallback = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        texto_parte = part.get("text")
        if texto_parte and isinstance(texto_parte, str):
            if part.get("thought") is True:
                textos_fallback.append(texto_parte.strip())
            else:
                textos_finais.append(texto_parte.strip())

    texto_combinado = " ".join(t for t in textos_finais if t).strip()
    if texto_combinado:
        return texto_combinado

    if finish_reason in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST"):
        return "Por questões de segurança, não posso responder a essa solicitação. Tente perguntar de outra forma."

    texto_fb = " ".join(t for t in textos_fallback if t).strip()
    return texto_fb if texto_fb else None

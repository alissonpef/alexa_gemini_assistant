<a id="readme-top"></a>

<!-- PROJECT SHIELDS -->
<div align="center">

[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![License: MIT][license-shield]][license-url]
[![LinkedIn][linkedin-shield]][linkedin-url]

</div>

<!-- PROJECT HEADER -->
<br />
<div align="center">
  <h1 align="center">Gemini Echo (Alexa Gemini Assistant)</h1>

  <p align="center">
    <strong>Integração de alta performance entre a Alexa e os modelos Google Gemini, com anti-timeout de 8s, gestão inteligente de quotas (RPM/RPD) e comandos de voz instantâneos em 0ms.</strong>
    <br />
    <em>Skill Alexa-hosted em Python com arquitetura modular limpa, tolerância a falhas com fallback automático entre modelos, sanitização SSML para fala natural e conformidade total com o linter Ruff.</em>
    <br />
    <br />
    <a href="#começando--inicialização">Começando</a>
    &middot;
    <a href="#passo-a-passo-completo-de-instalação-e-configuração">Guia de Instalação</a>
    &middot;
    <a href="#variáveis-de-ambiente-e-configurações-lambdaenv">Configurações (.env)</a>
    &middot;
    <a href="#estrutura-do-repositório">Estrutura do Projeto</a>
    &middot;
    <a href="#arquitetura-e-regras-de-qualidade">Arquitetura em Camadas</a>
  </p>
</div>

<!-- ÍNDICE -->
<details>
  <summary><strong>Índice de Navegação</strong></summary>
  <ol>
    <li>
      <a href="#sobre-o-projeto">Sobre o Projeto</a>
      <ul>
        <li><a href="#o-problema">O Problema</a></li>
        <li><a href="#a-solução">A Solução</a></li>
        <li><a href="#principais-funcionalidades">Principais Funcionalidades</a></li>
        <li><a href="#construído-com">Construído Com</a></li>
      </ul>
    </li>
    <li><a href="#começando--inicialização">Começando / Inicialização</a></li>
    <li><a href="#passo-a-passo-completo-de-instalação-e-configuração">Passo a Passo de Instalação e Configuração</a></li>
    <li><a href="#variáveis-de-ambiente-e-configurações-lambdaenv">Variáveis de Ambiente e Configurações (.env)</a></li>
    <li><a href="#estrutura-do-repositório">Estrutura do Repositório</a></li>
    <li><a href="#execução-e-comandos-da-stack">Execução e Comandos da Stack</a></li>
    <li><a href="#arquitetura-e-regras-de-qualidade">Arquitetura e Regras de Qualidade</a></li>
    <li><a href="#contribuindo">Contribuindo</a></li>
    <li><a href="#licença">Licença</a></li>
    <li><a href="#contato">Contato</a></li>
    <li><a href="#agradecimentos">Agradecimentos</a></li>
  </ol>
</details>

---

## Sobre o Projeto

### O Problema

A integração direta entre assistentes de voz (Alexa) e grandes modelos de linguagem (LLMs) frequentemente resulta em falhas frustrantes para o usuário final:

1. **Timeout Fatal de 8 Segundos:** O serviço de voz da Amazon (*Alexa Voice Service - AVS*) descarta qualquer requisição que não responda em até 8s. Modelos avançados ou que executam raciocínio interno (*thinking tokens*) demoram de 3 a 7 segundos para começar a gerar, ultrapassando o limite e fazendo a Alexa dizer: *"Houve um problema com a resposta da skill solicitada"*.
2. **Esgotamento Rápido de Quotas Diárias (HTTP 429):** Modelos como `Gemini 3.8 Flash` ou `3.6 Flash` no plano gratuito do Google AI Studio oferecem apenas **20 requisições por dia (RPD)** e **5 por minuto (RPM)**. Em poucas perguntas, a cota esgota e a skill para de funcionar.
3. **Incompatibilidade de Síntese de Voz (SSML Quebrado):** LLMs respondem com formatação Markdown (`**`, `*`, `#`, blocos de código) e caracteres reservados do XML/SSML (`&`, `<`, `>`). A Alexa tenta ler asteriscos literalmente ou descarta o áudio por erro de sintaxe XML.
4. **Perda de Contexto e Loops Infinitos:** Falta de gestão de histórico de conversação ou loops onde a Alexa pergunta *"Alguma outra pergunta?"* e, ao ouvir *"Não"*, envia a palavra *"Não"* para o Gemini em vez de encerrar.

### A Solução

O **Gemini Echo (Alexa Gemini Assistant)** é uma reengenharia completa da Skill Alexa-hosted em Python, estruturada em arquitetura modular limpa:

* **Garantia Anti-Timeout (< 6.4s):** Pool de conexões HTTP persistentes (`Keep-Alive`), orçamento estrito de tempo de 6.4s e desativação de tokens de pensamento (`thinkingBudget: 0`) para respostas formuladas em menos de 2 segundos.
* **Roteamento Inteligente com Gestão de Quotas (RPM/RPD):** Fila de modelos que prioriza versões **Flash-Lite (3.5 e 3.1)** com **500 requisições diárias (25x mais)** e **15 req/minuto (3x mais)**. Modelos que atingem o limite são pulados proativamente em 0ms antes de gerar erro 429.
* **Comandos Locais Instantâneos em 0ms:** Respostas locais para encerrar (*"não, obrigado"*, *"só isso"*), repetir a última resposta (*"pode repetir?"*) e limpar histórico (*"nova conversa"*) sem consumir chamadas da API do Google.
* **Sanitização Rigorosa para Voz e Telas:** Filtro de Markdown, escape de caracteres especiais SSML e geração de `SimpleCard` para telas de dispositivos Echo Show, Fire TV e app Alexa.

### Principais Funcionalidades

- **Baixa Latência & Keep-Alive:** Economia de 150ms a 400ms por requisição reutilizando conexões TCP/TLS com o endpoint do Google.
- **Roteamento Resiliente com Fallback:** Rotação automática entre `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.6-flash`, `gemini-3.8-flash`, `gemini-3.7-flash` e `gemini-3.5-flash`, com cache para modelos 404 e cooldown de sobrecarga (503/429).
- **Memória de Conversa com Janela Deslizante:** Contexto multi-turno isolado por sessão no `session_attributes` da Alexa com poda automática (`MAX_HISTORY_TURNS = 6`) para evitar saturação de tokens.
- **Encerramento Automático Inteligente:** Fechamento gracioso da sessão por comandos naturais de voz (*"sair"*, *"obrigado"*) ou automaticamente por inatividade da Alexa após ~15s de silêncio (reprompt timeout nativo).
- **SSML Seguro:** Converte símbolos matemáticos e pontuações para fala natural fluida sem travar o parser da Amazon.

### Construído Com

- [![Python][python-shield]][python-url]
- [![Ruff][ruff-shield]][ruff-url]
- [![Google Gemini][gemini-shield]][gemini-url]
- [![Alexa Skills Kit][alexa-shield]][alexa-url]

<p align="right">(<a href="#readme-top">voltar ao topo</a>)</p>

---

## Começando / Inicialização

### Passo a Passo Completo de Instalação e Configuração

#### 1. Gerar a Chave de API no Google AI Studio
1. Acesse o [Google AI Studio](https://aistudio.google.com/) e faça login com sua conta Google.
2. Clique em **Get API key** -> **Create API key** e copie a chave gerada.

#### 2. Criar a Skill no Alexa Developer Console
1. Acesse o [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask) e faça login com a mesma conta Amazon vinculada à sua Alexa.
2. Clique em **Create Skill** e preencha:
   * **Name your Skill:** `Modo Gemini` (ou escolha um nome de sua preferência, ex: `GeminiGPT`).
   * **Primary locale:** `Portuguese (BR)`.
   * **Choose a type of experience:** `Other` -> `Custom`.
   * **Hosting services:** `Alexa-hosted (Python)`.
   * **Hosting region:** Pode deixar o padrão `US East (N. Virginia)` e clique em **Next**.

#### 3. Importar o Repositório do GitHub
1. Na tela de Templates, clique no botão **Import Skill** (canto superior direito).
2. Cole a URL do repositório: [https://github.com/alissonpef/alexa_gemini_assistant.git](https://github.com/alissonpef/alexa_gemini_assistant.git) e confirme.
3. Aguarde a finalização da importação (se for redirecionado para a página geral da Amazon Developer, clique em *Alexa Skills Kit* e abra a sua Skill na lista).

#### 4. Configurar o Nome de Invocação e Modelo de Interação (Build)
1. Na aba **Build**, vá no menu lateral esquerdo em **Invocations** -> **Skill Invocation Name**.
2. Digite o nome para chamar a skill em letras minúsculas (ex: `modo inteligente` ou `assistente inteligente`). Clique em **Save**.
3. No menu lateral esquerdo, vá em **Interaction Model** -> **JSON Editor**.
4. Copie o conteúdo do arquivo [`interactionModels/custom/pt-BR.json`](interactionModels/custom/pt-BR.json) deste repositório e cole no editor da Alexa (ele contém as intenções com frases comuns como *"o que é..."*, *"como funciona..."*, além dos comandos nativos para repetir, novo assunto e encerramento).
5. Clique em **Save Model** e em seguida realize o Build da Skill clicando em **Build Skill** (canto superior direito), aguardando o aviso de conclusão.

#### 5. Inserir a Chave de API e o Código (Code)
Ao finalizar o build, vá para a aba **Code**:
1. Dentro da pasta `lambda` (no menu esquerdo de arquivos), clique em **New File**, crie um arquivo chamado `.env` e adicione a linha com a API key gerada:
   ```shell
   GOOGLE_API_KEY=SuaApiKeyGoogleAI
   ```
2. Certifique-se de que a estrutura modular do código esteja presente na pasta `lambda/`:
   * `lambda_function.py` (entrypoint da AWS Lambda com registro de handlers)
   * `config.py` (configurações, timeouts e quotas de RPM/RPD)
   * `gemini_client.py` (cliente HTTP Keep-Alive, rotação e monitor de quotas)
   * `handlers.py` (handlers de intenções da Alexa e suporte visual a Echo Show)
   * `session_manager.py` (memória de conversa com janela deslizante de turnos)
   * `text_utils.py` (limpeza SSML e formatação de voz)
   * `requirements.txt` (dependências: `ask-sdk-core`, `requests`, `urllib3<2.0.0`)
3. Clique em **Save** e então em **Deploy** (canto superior direito).

#### 6. Teste da Skill (Test)
Ao finalizar o _deploy_, vá para a aba **Test**:
1. Em **Skill testing is enabled in**, mude de *Off* para **Development**.
2. Para usar comandos de voz aceite a requisição de uso do microfone pelo site, e para falar clique e segure o ícone de mic, e solte para enviar (ou digite diretamente no Alexa Simulator).
3. Use o comando de ativação configurado para iniciar a Skill (ex: *"abrir modo inteligente"* seguido da sua pergunta) e pronto, você está interagindo com o Gemini pela Alexa!

A Skill já estará disponível em todos os dispositivos Alexa vinculados à sua conta.

---

### Variáveis de Ambiente e Configurações (`lambda/.env`)

Você pode personalizar o comportamento da Skill ajustando as variáveis no `.env`:

| Variável | Padrão | Descrição |
| :--- | :---: | :--- |
| `GOOGLE_API_KEY` | *(Obrigatório)* | Sua chave de API obtida no Google AI Studio. |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Modelo principal priorizado no topo da fila de execução. |
| `GEMINI_MAX_TOKENS` | `500` | Limite máximo de tokens por resposta. |
| `GEMINI_TEMPERATURE` | `0.6` | Criatividade da resposta (0.0 mais focado, 1.0 mais criativo). |
| `GEMINI_THINKING_BUDGET` | `0` | `0` desativa thinking interno para máxima velocidade de resposta. |
| `ALEXA_TIMEOUT_BUDGET` | `6.4` | Tempo limite interno em segundos antes do timeout da Alexa (8s). |
| `MAX_HISTORY_TURNS` | `6` | Quantidade de turnos recentes preservados na memória da conversa. |
| `QUOTA_GEMINI_3_5_FLASH_LITE_RPM` | `15` | Limite de requisições por minuto para o Gemini 3.5 Flash Lite. |
| `QUOTA_GEMINI_3_5_FLASH_LITE_RPD` | `500` | Limite de requisições por dia para o Gemini 3.5 Flash Lite. |
| `QUOTA_GEMINI_3_8_FLASH_RPM` | `5` | Limite de requisições por minuto para o Gemini 3.8 Flash. |
| `QUOTA_GEMINI_3_8_FLASH_RPD` | `20` | Limite de requisições por dia para o Gemini 3.8 Flash. |

<p align="right">(<a href="#readme-top">voltar ao topo</a>)</p>

---

## Estrutura do Repositório

Arquitetura real mantida no projeto:

```text
├── .github/
│   └── workflows/
│       └── ci.yml           # Pipeline CI (Lint e Format check com uv e Ruff)
├── interactionModels/
│   └── custom/
│       └── pt-BR.json       # Modelo de interação Alexa (slots, intents e samples de voz)
├── lambda/
│   ├── lambda_function.py   # Entrypoint do AWS Lambda (SkillBuilder e registro de handlers)
│   ├── config.py            # Variáveis de ambiente, limites de quota (RPM/RPD) e prompts
│   ├── gemini_client.py     # Cliente HTTP Keep-Alive, rotação de modelos e rate limiter
│   ├── handlers.py          # Handlers de intenções, ciclo de vida da Alexa e SimpleCard
│   ├── session_manager.py   # Gestão de estado na sessão e janela deslizante de histórico
│   ├── text_utils.py        # Limpeza de Markdown, URLs e sanitização SSML para fala
│   └── requirements.txt     # Dependências Python (ask-sdk-core, requests, urllib3<2.0.0)
├── .env.example             # Template documentado de variáveis de ambiente
├── .gitignore               # Arquivos locais e caches protegidos
├── LICENSE                  # Licença de uso do software (MIT)
├── skill.json               # Manifesto da Skill Alexa
└── README.md                # Apresentação do projeto e catálogo operacional
```

<p align="right">(<a href="#readme-top">voltar ao topo</a>)</p>

---

## Execução e Comandos da Stack

Comandos do dia a dia utilizados na stack do projeto (com **uv** e **Ruff**) para manutenção, linting e formatação:

```bash
# 1. Instalar dependências da Skill via uv
uv pip install --system -r lambda/requirements.txt

# 2. Executar linters e checagem de formatação com o Ruff (via uvx)
uvx ruff check .
uvx ruff format --check .

# 3. Aplicar correções automáticas de linter e formatação
uvx ruff check --fix .
uvx ruff format .
```

<p align="right">(<a href="#readme-top">voltar ao topo</a>)</p>

---

## Arquitetura e Regras de Qualidade

Este repositório é ancorado em dois princípios fundamentais:

1. **Clean Architecture Modular em Camadas:**
   - **Camada de Apresentação Alexa ([`handlers.py`](lambda/handlers.py)):** Trata a interação por voz, eventos de sessão, `SimpleCard` e tratamento global de exceções. Não acessa bibliotecas de IA diretamente.
   - **Camada de Domínio e Estado ([`session_manager.py`](lambda/session_manager.py)):** Gerencia o ciclo de vida do histórico, alternância de turnos (`user` / `model`) e janela deslizante (`MAX_HISTORY_TURNS`).
   - **Camada de Infraestrutura e Integração ([`gemini_client.py`](lambda/gemini_client.py)):** Encapsula chamadas HTTP persistentes, cálculo de timeouts seguros da Alexa, roteamento de quotas (RPM/RPD) e controle de parâmetros (`thinkingConfig`).
   - **Funções Puras ([`text_utils.py`](lambda/text_utils.py)):** Módulos determinísticos para sanitização de SSML, extração de texto de JSON e normalização de comandos de voz.
2. **Piso de Qualidade Inegociável:**
   - Zero erros de sintaxe ou execução (`0 errors`).
   - Zero warnings ou erros de linter com o Ruff (`0 warnings`).
   - Nenhuma credencial ou arquivo `.env` commitado no versionamento.

<p align="right">(<a href="#readme-top">voltar ao topo</a>)</p>

---

## Contribuindo

Contribuições são bem-vindas! Siga o fluxo abaixo:

1. Faça um Fork do projeto
2. Crie uma branch para sua modificação (`git checkout -b feature/MinhaFeature`)
3. Valide o piso de qualidade rodando o Ruff (`uvx ruff check .` e `uvx ruff format --check .`)
4. Faça commit atômico das alterações (`git commit -m 'feat: add XYZ support'`)
5. Envie para o seu fork (`git push origin feature/MinhaFeature`)
6. Abra um **Pull Request**

### Contribuidores:

<a href="https://github.com/alissonpef/alexa_gemini_assistant/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=alissonpef/alexa_gemini_assistant" alt="Contribuidores do Projeto" />
</a>

<p align="right">(<a href="#readme-top">voltar ao topo</a>)</p>

---

## Licença

Distribuído sob a licença **MIT**. Consulte o arquivo [LICENSE](LICENSE) para obter mais informações.

<p align="right">(<a href="#readme-top">voltar ao topo</a>)</p>

---

## Contato

**Alisson Pereira Ferreira**

- E-mail: [alissonpef@gmail.com](mailto:alissonpef@gmail.com)
- LinkedIn: [linkedin.com/in/alisson-pereira-ferreira](https://www.linkedin.com/in/alisson-pereira-ferreira/)
- GitHub: [@alissonpef](https://github.com/alissonpef)

Link do Repositório: [https://github.com/alissonpef/alexa_gemini_assistant](https://github.com/alissonpef/alexa_gemini_assistant)

<p align="right">(<a href="#readme-top">voltar ao topo</a>)</p>

---

## Agradecimentos

Este projeto foi construído e enriquecido sobre referências essenciais da comunidade:

- **Machally** — Pelo repositório original [`Machally/skill-alexa-geminiChat`](https://github.com/Machally/skill-alexa-geminiChat), base pioneira que deu origem a esta integração.
- **Scintilla Hub** — Pelo canal no YouTube ([@scintillahub](https://www.youtube.com/@scintillahub)) e tutoriais dedicados à integração de assistentes virtuais.
- **Othneil Drew** — Pelo modelo consagrado do [Best-README-Template](https://github.com/othneildrew/Best-README-Template/tree/main).

<p align="right">(<a href="#readme-top">voltar ao topo</a>)</p>

---

<div align="center">

Made with ❤️ by **[Alisson Pereira Ferreira](https://github.com/alissonpef)**

</div>

---

<!-- MARKDOWN SHIELDS & URL REFERENCES -->

[contributors-shield]: https://img.shields.io/github/contributors/alissonpef/alexa_gemini_assistant.svg?style=for-the-badge
[contributors-url]: https://github.com/alissonpef/alexa_gemini_assistant/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/alissonpef/alexa_gemini_assistant.svg?style=for-the-badge
[forks-url]: https://github.com/alissonpef/alexa_gemini_assistant/network/members
[stars-shield]: https://img.shields.io/github/stars/alissonpef/alexa_gemini_assistant.svg?style=for-the-badge
[stars-url]: https://github.com/alissonpef/alexa_gemini_assistant/stargazers
[issues-shield]: https://img.shields.io/github/issues/alissonpef/alexa_gemini_assistant.svg?style=for-the-badge
[issues-url]: https://github.com/alissonpef/alexa_gemini_assistant/issues
[license-shield]: https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge
[license-url]: LICENSE
[linkedin-shield]: https://img.shields.io/badge/-LinkedIn-black.svg?style=for-the-badge&logo=linkedin&colorB=555
[linkedin-url]: https://www.linkedin.com/in/alisson-pereira-ferreira/
[python-shield]: https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white
[python-url]: https://www.python.org/
[gemini-shield]: https://img.shields.io/badge/Google_Gemini-API_v1beta-4285F4?style=for-the-badge&logo=google&logoColor=white
[gemini-url]: https://ai.google.dev/
[alexa-shield]: https://img.shields.io/badge/Amazon_Alexa-Skills_Kit-00CAFF?style=for-the-badge&logo=amazonalexa&logoColor=white
[alexa-url]: https://developer.amazon.com/alexa/console/ask
[ruff-shield]: https://img.shields.io/badge/Linter-Ruff-D7FF64?style=for-the-badge&logo=ruff&logoColor=black
[ruff-url]: https://docs.astral.sh/ruff/

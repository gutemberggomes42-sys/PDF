# Hospedar na Render (sem servidor local)

Este guia publica seu backend Flask (com ffmpeg) na Render, usando este repositório Git como fonte.

## 1) Subir o projeto para o GitHub

- Crie um repositório no GitHub
- Faça upload do projeto (incluindo `Dockerfile` e `render.yaml`)

## 2) Criar o serviço na Render

- Acesse https://render.com/
- New → Blueprint
- Conecte sua conta do GitHub
- Selecione o repositório
- A Render vai ler o `render.yaml` e criar o serviço automaticamente

## 3) Configurar URL fixa e domínio (opcional)

- Após o deploy, você terá uma URL tipo `https://nova-pasta.onrender.com`
- Se quiser, aponte um domínio seu em Settings → Custom Domains

## 4) Variáveis de ambiente (opcional)

Por padrão, o `render.yaml` desliga login (`REQUIRE_AUTH=0`) para facilitar o primeiro deploy.

Se você quiser ativar login via Firebase depois:

- Settings → Environment
- Defina `REQUIRE_AUTH=1`
- Defina também os valores do Firebase (conforme sua configuração):
  - `FIREBASE_PROJECT_ID`
  - `FIREBASE_SERVICE_ACCOUNT_FILE` (normalmente é melhor usar “Secret File” na Render)
  - `FIREBASE_STORAGE_BUCKET` (se usar Storage)

## Banco PostgreSQL (recomendado)

Se você criou um Postgres na Render, configure a variável de ambiente:

- `DATABASE_URL` = string de conexão do Postgres

Não coloque essa URL no Git. Configure somente no painel da Render em:

- Settings → Environment → Add Environment Variable

## 5) Pastas e banco persistentes

A Render cria um disco em `/data`:
- uploads: `/data/uploads`
- áudio: `/data/audio`
- cache: `/data/cache`
- SQLite: `/data/app_data.db`

Isso evita perder arquivos e conversões quando o container reinicia.

## 6) Ajustar o app Android para usar a URL da nuvem

No app Android (WebView), em vez de digitar IP do PC:
- Use a URL da Render (ex.: `https://SEUAPP.onrender.com/`)

Você pode travar uma URL padrão no código se preferir (em vez de pedir toda vez).

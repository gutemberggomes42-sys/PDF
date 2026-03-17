# Hospedar na Railway (sem servidor local)

Este guia coloca seu backend Flask online na Railway usando o repositório do GitHub.

## 1) Criar o projeto

1. Entre em https://railway.app e faça login (GitHub).
2. Clique em **New Project**.
3. Clique em **Deploy from GitHub repo**.
4. Selecione o repositório `gutemberggomes42-sys/PDF`.

## 2) Criar o banco Postgres (opcional, recomendado)

1. Dentro do projeto, clique **New** → **Database** → **Add PostgreSQL**.
2. Abra o serviço do Postgres e copie a variável `DATABASE_URL`.

## 3) Configurar variáveis do serviço Web

1. Abra o serviço Web (o que está rodando o seu app).
2. Vá em **Variables**.
3. Adicione:
   - `DATABASE_URL` (se estiver usando Postgres)
   - `REQUIRE_AUTH=0` (para não exigir login no começo)

## 4) Gerar o domínio público

1. Abra o serviço Web.
2. Vá em **Settings**.
3. Clique em **Generate Domain** (ou “Domains” → “Generate”).
4. Abra a URL gerada e teste.

## 5) Android

No app Android, use a URL pública da Railway (com `/` no final), por exemplo:

- `https://SEU-DOMINIO.up.railway.app/`

## Observações

- Não coloque `DATABASE_URL` no Git. Configure só nas variáveis da Railway.
- Se você usou uma URL `postgres.railway.internal`, ela funciona apenas dentro da Railway.

# Gerar APK (Android) e AAB (Play Store)

Este repositório já inclui um app Android em [android_app](file:///c:/Users/gutem/OneDrive/Desktop/Nova%20pasta/android_app) que abre o sistema em um WebView.

## Pré-requisitos

- Android Studio (recomendado)
- JDK 17 (o Android Studio já vem com JDK embutido; use o “Embedded JDK”)
- Android SDK instalado pelo Android Studio

## 1) Abrir o projeto Android

- Abra o Android Studio
- File → Open… → selecione a pasta `android_app`
- Aguarde sincronizar (Gradle Sync)

## 2) Configurar a URL do servidor dentro do app

Por padrão o app abre o servidor em produção (Railway).

Para trocar, no app, pressione e segure (toque longo) e informe a URL desejada.

- Emulador Android: `http://10.0.2.2:5000/`
- Celular na mesma rede (servidor no PC): `http://SEU_IP:5000/` (ex.: `http://192.168.0.10:5000/`)

## 3) Gerar APK (para instalar e testar)

No Android Studio:

- Build → Build Bundle(s) / APK(s) → Build APK(s)

O APK gerado fica em:

- `android_app/app/build/outputs/apk/debug/app-debug.apk` (debug)

## 3.1) Build automático (GitHub Actions)

Se você preferir gerar o APK sem abrir Android Studio:

- Actions → workflow “Android Debug APK” → Run workflow
- Baixe o artifact “app-debug-apk”

## 4) Gerar AAB (para Play Store)

No Android Studio:

- Build → Generate Signed Bundle / APK…
- Selecione “Android App Bundle”
- Crie/seleciona um keystore e avance
- Selecione o build type `release`
- Finish

O AAB gerado fica em:

- `android_app/app/build/outputs/bundle/release/app-release.aab`

## 5) Assinatura (obrigatória para publicar)

Você precisa de um **keystore** (arquivo .jks). Guarde a senha e o arquivo em local seguro.

No assistente “Generate Signed Bundle / APK” você consegue:

- “Create new…” para criar o keystore
- Escolher “Key alias” e senhas

## 6) Ajustar versão (Play Store)

Antes de enviar atualização para a Play Store, incremente:

- `versionCode` (sempre aumenta: 2, 3, 4…)
- `versionName` (ex.: 1.1, 1.2…)

Arquivo:

- [android_app/app/build.gradle](file:///c:/Users/gutem/OneDrive/Desktop/Nova%20pasta/android_app/app/build.gradle)

## Observações importantes

- Para Play Store, prefira rodar seu servidor em **HTTPS** e apontar o app para essa URL.
- O AndroidManifest está com `usesCleartextTraffic="true"` para permitir HTTP em rede local. Para produção, o ideal é HTTPS.

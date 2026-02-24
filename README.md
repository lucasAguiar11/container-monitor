# Container Monitor Bot

Bot do Telegram que monitora containers Docker e envia alertas quando CPU/memória ultrapassam limites ou quando um container cai.

## Setup

### 1. Criar bot no Telegram

1. Abra o [@BotFather](https://t.me/BotFather) no Telegram
2. Envie `/newbot` e siga as instruções
3. Copie o token gerado

### 2. Descobrir seu User ID

Existem duas formas:

**Opção A** — Suba o bot sem `ALLOWED_USERS` e envie `/id`

**Opção B** — Use o [@userinfobot](https://t.me/userinfobot) no Telegram

### 3. Configurar variáveis

```bash
cp .env.example .env
```

Edite o `.env`:

```env
TELEGRAM_TOKEN=123456:ABC-DEF          # Token do BotFather
ALLOWED_USERS=123456789,987654321      # User IDs separados por vírgula
CONTAINERS=portal                 # Containers separados por vírgula
CPU_LIMIT=50                           # Alerta se CPU > 50%
MEM_LIMIT=70                           # Alerta se MEM > 70%
INTERVALO=30                           # Checa a cada 30 segundos
COOLDOWN=300                           # Espera 5 min entre alertas repetidos
```

### 4. Subir

```bash
docker compose up -d --build
```

### 5. Ativar no Telegram

Abra o chat com seu bot e envie `/start`.

## Comandos

| Comando   | Acao                        |
| --------- | --------------------------- |
| `/start`  | Ativa alertas               |
| `/stop`   | Pausa alertas               |
| `/status` | Status atual dos containers |
| `/id`     | Mostra seu user ID          |

## Alertas

- **Container caiu** — avisa quando para de responder
- **Container voltou** — avisa quando volta ao normal
- **CPU alta** — avisa quando ultrapassa o limite
- **Memoria alta** — avisa quando ultrapassa o limite

O cooldown evita spam de mensagens repetidas.

## Logs

```bash
docker logs -f docker-monitor-bot
```

## Parar

```bash
docker compose down
```

## Monitorar multiplos containers

No `.env`:

```env
CONTAINERS=portal,rate-layer-app,web-authn
```

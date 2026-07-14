# Roteiro para o Cliente – Buddmeyer Vision v2.0

Guia para configuração do CLP, logs e resolução de problemas no ambiente do cliente.

---

## 1. Como iniciar a aplicação

- **Atalho:** `Iniciar Realtec Vision.command` (macOS) ou `Iniciar_Realtec_Vision.sh` (Linux).
- **Terminal:**
  ```bash
  source venv/bin/activate
  python realtec_vision_buddmeyer/main.py
  ```

A janela abre com as abas **Operação**, **Configuração** e **Diagnósticos**.

---

## 2. Configurar o IP do CLP

O IP é lido do ficheiro de configuração **no momento da conexão**.

1. Aba **Configuração** → secção **CLP**.
2. Informe **IP** (ex.: `192.168.1.10`) e **porta** (`44818`).
3. Clique **Salvar** (ou Arquivo → Salvar Configurações).
4. Inicie a operação ou conecte ao CLP (▶ na Operação).

**Regra:** alterou IP → **salvar** → **conectar de novo**.

---

## 3. Logs

| Local | Caminho |
|-------|---------|
| Ficheiro | `realtec_vision_buddmeyer/logs/realtec_vision.log` |
| Interface | Aba **Diagnósticos** |

| Mensagem | Significado |
|----------|-------------|
| `config_saved` | Configurações gravadas (inclui IP/porta) |
| `cip_connecting` | Tentativa de conexão — mostra IP/porta usados |
| `cip_connected` | Conexão estabelecida |
| `cip_simulated_mode` | Modo simulado (CLP real indisponível) |
| `cip_error` | Erro CIP — IP, porta e tag no log |
| `inference_diagnostic` | Estado da inferência (scores, frames) |

---

## 4. “Conectado, mas erro ao enviar tag”

1. Anote a mensagem na tela (console de eventos).
2. Procure `cip_error` em `realtec_vision.log`.
3. No **Sysmac Studio**, confirme variáveis globais com os **mesmos nomes**:
   - `VisionCtrl_VisionReady`, `PRODUCT_DETECTED`, `CENTROID_X`, `CENTROID_Y`
   - `CENTROID_ANGLE`, `OBJECT_AREA` (segmentação)
4. Verifique publicação **EtherNet/IP** das variáveis.

Se os nomes no CLP forem diferentes, ajuste a secção `tags:` em `config/config.yaml`, salve e reconecte.

---

## 5. Validar configuração (teste automatizado)

Para confirmar que o sistema carrega o IP do config:

```bash
cd realtec_vision_buddmeyer
python -m pytest tests/test_config_settings.py -v
```

Ou verifique manualmente no log: após salvar, `config_saved` deve mostrar o IP novo; ao conectar, `cip_connecting` deve usar o mesmo IP.

---

## 6. Resumo rápido

| Ação | Passos |
|------|--------|
| Alterar IP | Configuração → IP → **Salvar** → reconectar |
| Ver IP usado | Log `cip_connecting` |
| Erro de tag | Log `cip_error` + Sysmac Studio |
| Sem detecções | Log `inference_diagnostic`; calibrar confiança na Configuração |

---

## 7. Suporte

Informe ao suporte:

- Mensagem de erro completa
- Trecho do log com `config_saved`, `cip_connecting`, `cip_error`
- Versão do sistema (aba Diagnósticos)

Documentação técnica: [docs/REFERENCE.md](docs/REFERENCE.md) e [docs/TAG_CONTRACT.md](docs/TAG_CONTRACT.md).

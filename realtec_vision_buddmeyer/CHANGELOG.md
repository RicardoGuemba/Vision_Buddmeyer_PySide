# Changelog

## [Unreleased] – Documentação e diagnóstico de inferência

### Adicionado

- **docs/OVERVIEW.md**, **docs/REFERENCE.md**, **docs/GUIA_OPERADOR.md** — nova hierarquia de documentação (alto/baixo nível).
- Diagnóstico de inferência (`inference_diagnostic`), warm-up USB, testes associados.

### Removido

- **DOCUMENTACAO_COMPLETA.md**, **CAMPOS_POR_ABA.md**, **USO_E_ABAS.md** — substituídos pela nova documentação.
- **TUTORIAL_OPENCODE.md** — conteúdo não relacionado ao projeto.

### Alterado

- **README.md**, **ROTEIRO_CLIENTE.md**, **PROJECT_RULES.md** — alinhados ao pipeline Mask2Former.
- **TAG_CONTRACT.md** — tags `CENTROID_ANGLE` e `OBJECT_AREA`.
- **CLONE_BOX_PC.md** — URL do repositório GitHub atualizada.

### Nota histórica

Entradas anteriores que referem `scripts/test_cip_config_reload.py` descrevem um script já removido; use `pytest tests/test_config_settings.py` para validar recarregamento de config.

---

### Removido (higienização)

- **coord_sync**, **robot_integration:** Módulos placeholder não utilizados em runtime.
- **scripts/test_*.py**, **verificar_modelo.bat:** Scripts de teste manuais redundantes com pytest.
- **installer:** READMEs duplicados, build_complete_installer, install_complete, .bat.
- **models/README_MODELO.md:** Consolidado em README.md.

### Adicionado

- **Stream MJPEG:** Detecções desenhadas no frame; get_local_ip melhorado para macOS; busy loop corrigido.

---

## Correções de comunicação e fluxo básico PC ↔ CLP

### Corrigido

- **Erro `NSeries has no attribute close`:** `disconnect()` agora verifica se o método existe (`close_explicit` ou `close`) antes de chamar; se não existir, apenas descarta a referência.
- **Recursão no processamento de estado:** Adicionado flag `_processing` no `RobotController` para serializar chamadas a `_process_current_state()`, evitando concorrência e estouro de pilha.
- **VisionReady duplicado:** Removida chamada a `set_vision_ready(True)` no `_handle_initializing()` do RobotController; agora é feito apenas uma vez na `OperationPage._connect_plc_and_start_robot()`.

### Adicionado

- **Handshake básico:** Antes de enviar X/Y, verifica se CLP está conectado, não está degradado, e opcionalmente lê `RobotReady`.
- **VisionReady no ciclo completo:** Seta `VisionReady=True` ao iniciar e `VisionReady=False` ao parar (novo método `_shutdown_plc_connection()`).
- **Log aprimorado:** Log de status do CLP ao enviar centroide; log de transição inclui `duration_s`.

---

## Alinhamento ao PRD PC ↔ CLP e melhorias (anterior)

### Adicionado (PRD)

- **docs/TAG_CONTRACT.md:** Contrato de tags documentado e versionado (RF/RNF), com mapeamento PRD ↔ implementação atual.
- **robot_control no config:** Seção `robot_control` com `ack_timeout`, `pick_timeout`, `place_timeout` configuráveis (RNF-02).
- **CIP:** `io_retries` (tentativas de leitura/escrita por operação) e `auto_reconnect` (reconexão automática quando degradado).
- **Reconexão automática:** Ao ficar DEGRADED (muitos erros), agenda tentativa de reconexão após `retry_interval` (RNF-02).
- **Retry em read/write:** Leitura e escrita de tags com até `io_retries` tentativas e log `cip_read_retry`/`cip_write_retry`.
- **UI (RF-06):** Painel de status exibe "Último erro" e "Latência CIP (ms)" (latência a partir de `cip_response_time`).
- **Log de transição:** `state_transition` passa a incluir `duration_s` no estado anterior (observabilidade).

### Alterado

- **RobotController:** Timeouts (ack, pick, place) lidos do config; ao iniciar recarrega `robot_control`.
- **StatusPanel:** Novos campos último erro e latência CIP; setters `set_last_error`, `set_latency_ms`.
- **OperationPage:** Erros CIP e robô atualizam último erro no painel; timer de FPS também atualiza latência CIP.
- **config.yaml:** Incluídas seções `robot_control` e parâmetros CIP `io_retries`, `auto_reconnect`.

---

## Correção IP/CLP e roteiro cliente (anterior)

### Corrigido

- **IP do CLP não atualizava após alterar na tela:** o backend usava o IP carregado apenas na inicialização. Agora, a cada tentativa de **conexão**, a aplicação recarrega IP, porta e timeout do arquivo de configuração (e da UI após salvar). Assim, alterar o IP na Configuração, salvar e conectar passa a usar o IP novo.
- **Rastreio por log:**
  - Ao **salvar** configurações: log `config_saved` com `cip_ip`, `cip_port` e caminho do arquivo.
  - Ao **conectar** ao CLP: log `cip_connecting` com IP, porta, timeout e modo simulado usados.
  - Em **erros CIP** (conexão ou tag): log `cip_error` com IP, porta, tag (quando aplicável) e mensagem de erro.

### Adicionado

- **ROTEIRO_CLIENTE.md:** guia para o cliente com:
  - Como iniciar a aplicação.
  - Como configurar o IP do CLP (salvar e depois conectar).
  - Onde ficam os logs e o que procurar (`config_saved`, `cip_connecting`, `cip_error`).
  - O que fazer quando “diz conectado mas dá erro ao enviar tag”.
  - Como executar o teste de recarregamento de config (`test_cip_config_reload.py`).
- **Script de teste** `scripts/test_cip_config_reload.py`: verifica se, ao conectar, o sistema usa o IP atual do config (pode ser executado a partir da pasta do projeto ou de `realtec_vision_buddmeyer`).
- Referência ao **ROTEIRO_CLIENTE.md** no README principal.

### Alterações técnicas

- `communication/cip_client.py`:
  - Novo método `_reload_connection_config()` para recarregar IP/porta/timeout do config.
  - `connect()` chama `_reload_connection_config()` antes de conectar e registra `cip_connecting`.
  - `_handle_error()` passa a receber `tag_name` opcional e registra `cip_error` com IP, porta e tag.
- `ui/pages/configuration_page.py`: ao salvar configurações, registra `config_saved` com `cip_ip` e `cip_port`.

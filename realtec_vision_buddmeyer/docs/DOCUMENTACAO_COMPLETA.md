# Documentação Completa – Buddmeyer Vision System v2.0

Documento único com visão geral, features, UI, arquitetura e manual de manutenção.

---

## Índice

1. [Visão do todo](#1-visão-do-todo)
2. [Features e seus códigos](#2-features-e-seus-códigos)
3. [UI](#3-ui)
4. [Arquitetura](#4-arquitetura)
5. [Manual de manutenção](#5-manual-de-manutenção)

---

## 1. Visão do todo

### 1.1 Objetivo

Sistema desktop **macOS, Linux/Ubuntu e Windows** para **automação de expedição (pick-and-place)** de embalagens, integrando:

- **Visão**: detecção em tempo real com modelos DETR/RT-DETR (Hugging Face).
- **Comunicação industrial**: CLP Omron NX102 via CIP/EtherNet-IP (biblioteca aphyt).
- **Interface**: PySide6 com 3 abas (Operação, Configuração, Diagnósticos).
- **Fontes de vídeo**: arquivo (MP4/AVI/MOV), USB, RTSP, GigE.
- **Modo simulado**: desenvolvimento e testes sem CLP real.

### 1.2 Fluxo de dados resumido

```
Fonte de vídeo → StreamManager (QThread) → Frame Buffer
     → Pré-processamento (ROI, brilho/contraste)
     → InferenceEngine (QThread) → RT-DETR → Postprocess (NMS, filtros)
     → DetectionEvent → RobotController (máquina de estados)
     → CIPClient → TAGs CLP (centroide, confiança, ACK, pick/place)
     → UI (sinais Qt) atualiza vídeo, status, eventos e métricas
```

### 1.3 Como executar

- **macOS:** duplo-clique em **`Iniciar Realtec Vision.command`** (raiz do repo) ou no Terminal: `./Iniciar_Realtec_Vision.sh`. Ver [MACOS_SETUP.md](MACOS_SETUP.md).
- **Linux/Ubuntu:** no terminal: `./Iniciar_Realtec_Vision.sh`. Ver [UBUNTU_SETUP.md](UBUNTU_SETUP.md).

### 1.4 Tecnologias principais

| Camada        | Tecnologia                          |
|---------------|-------------------------------------|
| UI            | PySide6 6.6+ (Qt for Python)        |
| Config        | Pydantic Settings + YAML            |
| ML            | PyTorch 2+, Transformers, RT-DETR   |
| Imagem        | OpenCV 4.9+, Pillow, NumPy          |
| CLP           | aphyt 2.1.9+ (CIP/EtherNet-IP)      |
| Logging       | structlog                           |
| Async/UI      | qasync (opcional)                   |

---

## 2. Features e seus códigos

### 2.1 Entrada e configuração

| Feature | Arquivo(s) | Descrição |
|---------|------------|-----------|
| Ponto de entrada | `main.py` | Carrega config, logging e inicia `QApplication` + `MainWindow`; com qasync usa event loop assíncrono. |
| Configuração | `config/settings.py` | `Settings` (Pydantic) com submodelos: `StreamingSettings`, `DetectionSettings`, `PreprocessSettings`, `CIPSettings`, `RobotControlSettings`, `TagSettings`, `OutputSettings`. Carregamento via `Settings.from_yaml()` e cache em `get_settings()`. |
| Arquivo YAML | `config/config.yaml` | Define `streaming`, `detection`, `preprocess`, `cip`, `robot_control`, `tags`, `output`. |

### 2.2 Core e orquestração

| Feature | Arquivo | Descrição |
|---------|---------|-----------|
| Orquestração | `ui/main_window.py` + `ui/pages/operation_page.py` | `MainWindow` e `OperationPage` conectam StreamManager, InferenceEngine, CIPClient, RobotController; sinais e slots para UI. |

### 2.3 Streaming

| Feature | Arquivo | Descrição |
|---------|---------|-----------|
| Gerenciador | `streaming/stream_manager.py` | `StreamManager` (singleton): cria adaptador via `create_adapter()`, `FrameBuffer`, `StreamWorker` (QThread). Sinais: `frame_info_available`, `stream_started`, `stream_stopped`, `stream_error`. Métodos: `start()`, `stop()`, `pause()`, `resume()`, `change_source()`, `get_fps()`, `get_status()`. |
| Adaptadores | `streaming/source_adapters.py` | `SourceType` (VIDEO, USB, RTSP, GIGE); `BaseSourceAdapter` (open/read/close); `VideoFileAdapter`, `USBCameraAdapter`, `RTSPAdapter`, `GigECameraAdapter`; factory `create_adapter(settings)`. |
| Buffer | `streaming/frame_buffer.py` | `FrameBuffer` thread-safe com `FrameInfo` (frame, frame_id, timestamp). |
| Saúde | `streaming/stream_health.py` | `StreamHealth` / `HealthStatus` para monitoramento do stream. |

### 2.4 Pré-processamento

| Feature | Arquivo | Descrição |
|---------|---------|-----------|
| Pipeline | `preprocessing/preprocess_pipeline.py` | `PreprocessPipeline`: ROI (ROIManager), brilho/contraste (ImageTransforms), perfis (`PREPROCESS_PROFILES`: default, bright, dark, high_contrast, etc.); `process(frame)` retorna frame processado. |
| ROI | `preprocessing/roi_manager.py` | `ROIManager`, estrutura `ROI`. |
| Transformações | `preprocessing/transforms.py` | `ImageTransforms` (brilho, contraste, etc.). |

### 2.5 Detecção

| Feature | Arquivo | Descrição |
|---------|---------|-----------|
| Engine | `detection/inference_engine.py` | `InferenceEngine` (singleton): carrega modelo via `ModelLoader`, usa `InferenceWorker` (QThread), `PostProcessor`. Sinais: `detection_event` (DetectionEvent), `inference_started`, `inference_stopped`, `model_loaded`. `process_frame(frame, frame_id)` enfileira frame para o worker. |
| Modelo | `detection/model_loader.py` | `ModelLoader`: Hugging Face ou local (`models/`), device cpu/cuda/auto. |
| Validação | `detection/model_validator.py` | Validação do modelo carregado. |
| Pós-processamento | `detection/postprocess.py` | NMS, filtro de confiança, geração de centroides. |
| Eventos | `detection/events.py` | `BoundingBox`, `Detection`, `DetectionResult`, `DetectionEvent`; `DetectionEvent.from_result()` e `to_plc_data()` para envio ao CLP. |

### 2.6 Comunicação CIP

| Feature | Arquivo | Descrição |
|---------|---------|-----------|
| Cliente | `communication/cip_client.py` | `CIPClient` (singleton): conexão Omron NX via aphyt (`omron.n_series.NSeries`), leitura/escrita de TAGs com whitelist, reconexão automática, heartbeat. Sinais: `connected`, `disconnected`, `connection_error`, `state_changed`. `SimulatedPLC` com ciclo completo de pick-and-place (ACK, Pick, Place, CycleComplete) com delays simulados. Por default tenta CLP real; se falhar, cai para simulado. |
| Tags | `communication/tag_map.py` | `TagMap`: mapeamento nome lógico → nome físico no CLP (configurável em `config.yaml`). |
| Estado | `communication/connection_state.py` | `ConnectionState`, `ConnectionStatus`. |
| Contrato | `docs/TAG_CONTRACT.md` | Lista de TAGs escrita/leitura e semântica. |

### 2.7 Controle de robô

| Feature | Arquivo | Descrição |
|---------|---------|-----------|
| Controlador | `control/robot_controller.py` | `RobotController` (singleton): máquina de estados com handshake completo (Detecção -> Envio -> ACK -> Pick -> Place -> Ciclo). Suporta modo **manual** (aguarda autorização do operador via botão "Novo Ciclo") e **contínuo** (auto). Registra etapas do ciclo com timestamps e emite `cycle_summary` ao final. Sinais: `state_changed`, `cycle_completed`, `error_occurred`, `detection_sent`, `cycle_step`, `cycle_summary`. |
| Ciclos | `control/robot_controller.py` | `RobotController`: máquina de estados, ciclos pick-and-place, sinais `cycle_completed`, `cycle_summary`. |

### 2.8 Logging e métricas

| Feature | Arquivo | Descrição |
|---------|---------|-----------|
| Logger | `core/logger.py` | `setup_logging()`, `get_logger(name)` (structlog). |
| Métricas | `core/metrics.py` | `MetricsCollector`: FPS, latência, contadores, etc. |
| Exceções | `core/exceptions.py` | Exceções de domínio (StreamError, InferenceError, CIP*, RobotControlError, etc.). |

---

## 3. UI

### 3.1 Janela principal

**Arquivo:** `ui/main_window.py` — `MainWindow(QMainWindow)`:

- **Central:** `QTabWidget` com 3 abas (Operação, Configuração, Diagnósticos).
- **Menu:** Arquivo (Salvar Config, Sair), Sistema (Iniciar F5, Parar F6, Recarregar Modelo), Ajuda (Sobre).
- **Status bar:** Sistema (Rodando/Parado), FPS, CLP (Conectado/Desconectado/Simulado), timestamp; atualização por timer 500 ms.
- **Tema:** `ui/styles/industrial.qss` (Manual de Marca RTC); paleta #1b3a69, #14284c, #26477e, #c5c9ce, #e5e7eb.

### 3.2 Aba Operação

**Arquivo:** `ui/pages/operation_page.py` — `OperationPage`:

- **Layout:** splitter horizontal: à esquerda vídeo + grupo “Eventos”; à direita `StatusPanel`.
- **Vídeo:** `VideoWidget` — exibe frames e overlay de detecções; duplo clique ou F11 para tela cheia.
- **Eventos:** `EventConsole` — log de eventos em tempo real.
- **Status:** `StatusPanel` — estado do sistema, CLP, última detecção, ROI (região de interesse), latência CIP.
- **Controles:** combo “Fonte” (Arquivo/USB/RTSP/GigE), botão “Selecionar...”, Iniciar, Pausar/Retomar, Parar; "Modo Continuo" (checkbox), "Novo Ciclo" (botao); atalhos F5/F6/F11.
- **Ciclo pick-and-place:** handshake completo Visao -> CLP -> Robo (ACK, Pick, Place, CycleComplete). Modo manual (aguarda operador) ou continuo (auto). Console exibe resumo com etapas e timestamps.
- **CLP default real:** ao iniciar, tenta CLP real; se falhar, notifica e opera em simulado com robo virtual.
- **Logica:** inicia/para stream, inferencia, CIP e RobotController; comunica com CLP via handshake; atualiza UI via sinais.

### 3.3 Aba Configuração

**Arquivo:** `ui/pages/configuration_page.py` — `ConfigurationPage`:

- **Sub-abas:** Fonte de Vídeo, Modelo RT-DETR, Pré-processamento, Controle (CLP), Output.
- **Fonte:** tipo, caminho do vídeo, índice USB, URL RTSP, IP/porta GigE, loop.
- **Modelo:** caminho, device (CPU/CUDA/Auto), threshold de confiança, max detecções.
- **Pré-processamento:** perfil, brilho, contraste, ROI.
- **CLP:** IP, porta, timeout, modo simulado, “Testar Conexão”.
- **Output:** RTSP habilitado, porta, path.
- **Ações:** Restaurar Padrões, Salvar Configurações (persiste em `config.yaml`).

### 3.4 Aba Diagnósticos

**Arquivo:** `ui/pages/diagnostics_page.py` — `DiagnosticsPage`:

- **Sub-abas:** Visão Geral, Métricas, Logs, Sistema.
- **Visão Geral:** `StatusCard` para Stream, Detecção, CLP, Pré-processamento; health banner.
- **Métricas:** `MetricsChart` — FPS stream/inferência, latência, etc.
- **Logs:** `LogViewer` — filtros por nível e componente, exportar/limpar.
- **Sistema:** OS, Python, PyTorch, CUDA, versão do modelo; monitoramento de CPU (% processo), memória RAM (MB) e GPU VRAM em tempo real (requer `psutil`).

### 3.5 Widgets reutilizáveis

| Widget            | Arquivo                     | Função principal                                      |
|-------------------|-----------------------------|-------------------------------------------------------|
| VideoWidget       | `ui/widgets/video_widget.py` | Exibe frame, overlay de bbox/centroide, FPS           |
| Overlay de detecções | `ui/widgets/video_widget.py` | Desenho de bboxes e labels sobre o frame (integrado ao VideoWidget) |
| StatusPanel       | `ui/widgets/status_panel.py` | Status sistema/CLP, última detecção, ROI   |
| EventConsole      | `ui/widgets/event_console.py` | Lista de eventos em tempo real                    |
| MetricsChart      | `ui/widgets/metrics_chart.py` | Gráficos de métricas                              |
| LogViewer         | `ui/widgets/log_viewer.py` | Visualização e filtro de logs                     |

---

## 4. Arquitetura

### 4.1 Estrutura de diretórios

```
realtec_vision_buddmeyer/
├── main.py                 # Entrada
├── config/
│   ├── config.yaml
│   └── settings.py
├── core/
│   ├── logger.py
│   ├── metrics.py
│   └── exceptions.py
├── streaming/
│   ├── stream_manager.py   # Singleton + StreamWorker (QThread)
│   ├── source_adapters.py  # VIDEO, USB, RTSP, GIGE
│   ├── frame_buffer.py
│   └── stream_health.py
├── preprocessing/
│   ├── preprocess_pipeline.py
│   ├── roi_manager.py
│   ├── transforms.py
├── detection/
│   ├── inference_engine.py # Singleton + InferenceWorker (QThread)
│   ├── model_loader.py
│   ├── model_validator.py
│   ├── postprocess.py
│   └── events.py
├── communication/
│   ├── cip_client.py       # Singleton, aphyt
│   ├── tag_map.py
│   ├── connection_state.py
│   ├── cip_logger.py
│   └── exceptions.py
├── control/
│   ├── robot_controller.py # Singleton, máquina de estados
├── ui/
│   ├── main_window.py
│   ├── pages/              # operation, configuration, diagnostics
│   ├── widgets/            # video, overlay, status, console, chart, log
│   └── styles/
│       └── industrial.qss
├── models/
├── logs/
├── videos/
└── docs/
    ├── DOCUMENTACAO_COMPLETA.md  # Este documento
    └── TAG_CONTRACT.md
```

### 4.2 Padrões de design

- **Singleton:** Application, StreamManager, InferenceEngine, CIPClient, RobotController.
- **Observer:** Qt Signals/Slots entre stream → inferência → robot → CIP e UI.
- **Factory:** `create_adapter()` para tipo de fonte.
- **State machine:** `RobotController` com `RobotControlState` e `VALID_TRANSITIONS`.
- **Strategy:** perfis de pré-processamento; adaptadores de fonte.

### 4.3 Threading

- **StreamWorker** (QThread): loop de captura; emite `frame_captured` → FrameBuffer / downstream.
- **InferenceWorker** (QThread): recebe frame, roda modelo, emite `detection_ready` (DetectionResult).
- **CIP:** operações bloqueantes em `ThreadPoolExecutor` ou async para não bloquear UI.
- **UI:** apenas thread principal Qt; atualizações via sinais.

---

## 5. Manual de manutenção

### 5.1 Alterar fonte de vídeo ou parâmetros de stream

- **Onde:** `config/config.yaml` (seção `streaming`) e/ou aba Configuração → Fonte de Vídeo.
- **Código:** `config/settings.py` (`StreamingSettings`), `streaming/stream_manager.py` (`change_source()`), `streaming/source_adapters.py` (adaptadores e `create_adapter()`).
- **Manutenção:** ao adicionar novo tipo de fonte, criar novo adapter em `source_adapters.py`, registrar em `SourceType` e em `create_adapter()`; opcionalmente novo item no combo na Operation page.

### 5.2 Trocar modelo ou threshold de detecção

- **Onde:** `config/config.yaml` (`detection`) e aba Configuração → Modelo RT-DETR.
- **Código:** `config/settings.py` (`DetectionSettings`), `detection/model_loader.py`, `detection/inference_engine.py`, `detection/postprocess.py` (threshold).
- **Manutenção:** modelo local em `models/` (estrutura esperada em `models/README.md`); alterar `default_model` ou `model_path`; ajustar `confidence_threshold` e `max_detections`; recarregar via menu Sistema → Recarregar Modelo (com sistema parado).

### 5.3 Ajustar comunicação CLP (IP, porta, TAGs)

- **Onde:** `config/config.yaml` (`cip`, `tags`).
- **Código:** `config/settings.py` (`CIPSettings`, `TagSettings`), `communication/cip_client.py`, `communication/tag_map.py`.
- **Documento:** `docs/TAG_CONTRACT.md` — nomes lógicos e físicos das TAGs.
- **Manutenção:** alterar IP/porta em `cip`; renomear TAGs no CLP só na seção `tags` do YAML (nomes físicos). Modo simulado: `cip.simulated: true`. Testar conexão pela aba Configuração → Controle (CLP) → Testar Conexão.

### 5.4 Ajustar fluxo do robô (timeouts, estados)

- **Onde:** `config/config.yaml` (`robot_control`).
- **Código:** `control/robot_controller.py` (estados, transições, timeouts).
- **Manutenção:** alterar `ack_timeout`, `pick_timeout`, `place_timeout` no YAML. Para mudar lógica de estados: editar `RobotControlState`, `VALID_TRANSITIONS` e os handlers em `RobotController` (ex.: resposta a ACK, pick complete, place complete).

### 5.5 Pré-processamento (ROI, brilho, contraste, perfis)

- **Onde:** `config/config.yaml` (`preprocess`) e aba Configuração → Pré-processamento.
- **Código:** `preprocessing/preprocess_pipeline.py`, `preprocessing/roi_manager.py`, `preprocessing/transforms.py`.
- **Manutenção:** novos perfis em `PREPROCESS_PROFILES`; ajustes de ROI no pipeline; parâmetros de brilho/contraste nos transforms.

### 5.6 Logs e diagnósticos

- **Onde:** `config/config.yaml` (`log_level`, `log_file`).
- **Código:** `core/logger.py`, `core/metrics.py`, `ui/widgets/log_viewer.py`, `ui/widgets/metrics_chart.py`, `ui/pages/diagnostics_page.py`.
- **Manutenção:** mudar nível de log (INFO/DEBUG/WARNING); trocar arquivo de log; adicionar novas métricas em `MetricsCollector` e exibição em Diagnostics.

### 5.7 Erros comuns e onde olhar

| Sintoma              | Onde verificar |
|----------------------|----------------|
| Vídeo não inicia     | StreamManager, source_adapters (open/read), path em config, stream_health |
| Detecção não aparece | InferenceEngine, model_loader, postprocess (threshold), device (CUDA/CPU) |
| CLP não conecta      | cip_client (connect, timeout), tag_map, rede, modo simulado |
| Robô não avança      | robot_controller (estado atual, transições), TAGs de leitura (AuthorizeDetection, CycleStart, Pick/Place complete) |
| UI trava             | Garantir que trabalho pesado está em QThread/Executor; não fazer I/O bloqueante na thread da UI |

### 5.8 Testes e scripts

- **Scripts:** `scripts/` — `test_detection.py`, `test_integration_vision_plc.py`, `test_robot_plc.py`, `test_video_*.py`, `test_model_loading.py`, `test_cip_config_reload.py`, `check_model.py`.
- **Uso:** rodar com sistema parado para validar modelo, vídeo, CIP e reload de config.

---

**Versão do documento:** 1.0  
**Projeto:** Buddmeyer Vision System v2.0  
**Plataforma:** macOS 12+, Ubuntu 22.04+, Windows 10/11 | PySide6, PyTorch, aphyt (CIP)

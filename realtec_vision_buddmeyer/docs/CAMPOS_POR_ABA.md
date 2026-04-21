# Campos por Aba — Inventário para Simplificação

Este documento lista todos os campos de **digitação** (input) e **exibição** (display) de cada aba do sistema, com numeração hierárquica e **função** (para que serve) de cada item.

**Como usar:** Indique os números dos itens a serem deletados (ex.: 1.2.3, 2.3.5, 3.2).

---

## 1. Aba Operação

### 1.1. Área principal
- **1.1.1** Vídeo — Display — Exibe o stream com detecções e overlay de ROI  
  → **Função:** Renderiza frames em tempo real; aplica bounding boxes e centroide; permite visualizar o que a câmera captura e o que o modelo detecta.

- **1.1.2** Legenda da fonte — Display — Texto abaixo do vídeo (ex.: "Fonte: Arquivo de vídeo — Colcha.mp4")  
  → **Função:** Informa qual fonte de vídeo está ativa (arquivo, USB, RTSP, GigE, GenTL) para evitar confusão do operador.

- **1.1.3** Status atual — Display — Label da etapa atual do ciclo pick-and-place (ex.: "—", "Detectando", etc.)  
  → **Função:** Mostra em qual etapa do ciclo pick-and-place o sistema está (detecção, envio ao CLP, aguardando pick/place, etc.).

### 1.2. Barra de controles (inferior)
- **1.2.1** Fonte — Input (Combo) — Seletor: Arquivo de Vídeo, Câmera USB, Câmera GigE, Câmera GenTL  
  → **Função:** Define `source_type`; escolhe qual adaptador de vídeo será usado (`StreamManager.change_source`).

- **1.2.2** Selecionar... — Botão — Abre diálogo para selecionar arquivo de vídeo (visível só para fonte "Arquivo de Vídeo")  
  → **Função:** Abre `QFileDialog`; atualiza `streaming.video_path` e aplica via `change_source`; permite trocar o vídeo sem ir em Configuração.

- **1.2.3** Selecionar CTI... — Botão — Seleciona arquivo CTI GenTL (visível só para fonte GenTL)  
  → **Função:** Abre diálogo para escolher o arquivo `.cti` do driver GenTL (Harvester); define `streaming.gentl_cti_path`; necessário para câmeras Omron Sentech.

- **1.2.4** Ajustes da câmera... — Botão — Abre tela de ajustes GenTL (visível só para fonte GenTL)  
  → **Função:** Abre `GenTLCameraSettingsDialog`; permite ajustar Gain, ExposureTime e outros parâmetros GenICam em tempo real; usa `get_gentl_adapter()` e `set_gentl_feature()`.

- **1.2.5** ▶ Iniciar — Botão — Inicia o sistema  
  → **Função:** Chama `_start_system`; carrega modelo (se necessário), inicia stream e inferência, conecta ao CLP, inicia MJPEG (se habilitado); dispara o ciclo operacional completo.

- **1.2.6** ⏸ Pausar — Botão — Pausa o sistema  
  → **Função:** Chama `_toggle_pause`; pausa stream e inferência mantendo conexão CLP; permite retomar sem reiniciar.

- **1.2.7** ⏹ Parar — Botão — Para o sistema  
  → **Função:** Chama `_stop_system`; para stream, inferência, desconecta CLP, encerra MJPEG; retorna ao estado inicial.

- **1.2.8** Autorizar envio ao CLP — Botão — Modo manual: autoriza envio de coordenadas ao CLP (visível em certos estados)  
  → **Função:** Chama `_authorize_send_to_plc`; no modo manual, quando há detecção, o operador deve clicar para enviar centroide/confiança ao CLP e iniciar o ciclo; evita envio automático indesejado.

- **1.2.9** Modo Contínuo — Input (CheckBox) — Ciclos automáticos vs. aguardar "Novo Ciclo"  
  → **Função:** Define `RobotController` em modo contínuo ou manual; contínuo = ciclos seguem automaticamente; manual = aguarda "Novo Ciclo" após cada ciclo.

- **1.2.10** Novo Ciclo — Botão — Autoriza próximo ciclo (modo manual)  
  → **Função:** Chama `_authorize_new_cycle`; no modo manual, sinaliza ao `RobotController` que pode iniciar o próximo ciclo pick-and-place.

- **1.2.11** Sair — Botão — Encerra o sistema  
  → **Função:** Chama `_on_exit_clicked` → `_confirm_and_exit`; fecha a aplicação com confirmação.

### 1.3. Painel lateral (StatusPanel)
- **1.3.1** Estado (Sistema) — Display — Estado do sistema (RUNNING, PAUSED, STOPPED, ERROR)  
  → **Função:** Exibe o estado global; atualizado por `set_system_status`; ajuda a saber se o sistema está rodando, pausado ou parado.

- **1.3.2** Stream — Display — Status do stream (Ativo/Parado)  
  → **Função:** Indica se o `StreamManager` está capturando frames; atualizado por `set_stream_running`.

- **1.3.3** Detecção — Display — Status da inferência (Ativo/Parado)  
  → **Função:** Indica se o `InferenceEngine` está processando frames; atualizado por `set_inference_running`.

- **1.3.4** Conexão (CLP) — Display — Status da conexão CLP  
  → **Função:** Mostra estado CIP (Conectado, Simulado, Desconectado, etc.); atualizado por `set_connection_state`; essencial para saber se o CLP está acessível.

- **1.3.5** Robô — Display — Status do robô  
  → **Função:** Exibe status do robô (via `RobotController`); complementa o estado do ciclo.

- **1.3.6** Estado (Robô) — Display — Estado do ciclo (ex.: DETECTING, WAITING_ACK)  
  → **Função:** Mostra o estado interno do ciclo pick-and-place; atualizado por `set_robot_state`; permite acompanhar DETECTING, WAITING_SEND_AUTHORIZATION, SENDING_DATA, etc.

- **1.3.7** Último erro — Display — Texto do último erro  
  → **Função:** Exibe a última mensagem de erro (CLP, robô, visão); atualizado por `set_last_error`; auxilia diagnóstico rápido.

- **1.3.8** Latência CIP — Display — Latência em ms  
  → **Função:** Mostra tempo aproximado de resposta do CLP; atualizado por `set_latency_ms`; indica saúde da comunicação CIP.

- **1.3.9** Classe (Última Detecção) — Display — Nome da classe detectada  
  → **Função:** Exibe o label da última detecção (ex.: "Embalagem"); atualizado por `update_detection`; confirma o que o modelo viu.

- **1.3.10** Confiança (Última Detecção) — Display — Confiança da detecção  
  → **Função:** Exibe a confiança da última detecção (ex.: 95%); atualizado por `update_detection`; indica qualidade da detecção.

- **1.3.11** Centroide X — Display — Coordenada X do centroide (em mm: px × mm/px)  
  → **Função:** Exibe a coordenada X do centroide da última detecção; valor em mm (coord_px × roi_calibration_mm_per_px); enviada ao CLP como CENTROID_X; quando ROI ativo, coordenadas fora do ROI são clampadas ao ROI antes do envio; atualizado por `update_detection`.

- **1.3.12** Centroide Y — Display — Coordenada Y do centroide (em mm: px × mm/px)  
  → **Função:** Exibe a coordenada Y do centroide da última detecção; valor em mm (coord_px × roi_calibration_mm_per_px); enviada ao CLP como CENTROID_Y; quando ROI ativo, coordenadas fora do ROI são clampadas ao ROI antes do envio; atualizado por `update_detection`.

- **1.3.13** Ativar ROI — Input (CheckBox) — Liga/desliga ROI (coordenadas configuradas em Configuração → Imagem)  
  → **Função:** Liga ou desliga o ROI; quando ativo, exibe overlay verde no vídeo e **limita ao ROI** as coordenadas enviadas ao CLP (projeção euclidiana: centroides fora do ROI são substituídos pelo ponto mais próximo dentro do retângulo, evitando colisão da plataforma de pick com as laterais do container); coordenadas vêm de Configuração; emite `roi_changed` → `_on_roi_changed` atualiza `preprocess.roi`.

- **1.3.14** ROI X, Y, W, H — Input (SpinBox) — Coordenadas ROI — atualmente ocultos na UI (carregados de config)  
  → **Função:** Armazena coordenadas do ROI; carregadas de `preprocess.roi`; usadas por `ROIManager` (clamp de centroide, overlay); ocultos na UI (configuração em Configuração → Imagem).

### 1.4. Console de Eventos
- **1.4.1** Filtrar — Input (Combo) — Todos, Info, Sucesso, Aviso, Erro  
  → **Função:** Filtra quais níveis de evento são exibidos no console; reduz ruído quando só se quer ver erros ou avisos.

- **1.4.2** Limpar — Botão — Limpa o console  
  → **Função:** Chama `EventConsole.clear`; remove todos os eventos da memória e da tela; libera espaço visual.

- **1.4.3** Console — Display — Área de texto com eventos em tempo real  
  → **Função:** Exibe eventos do sistema (detecção, envio ao CLP, erros, etc.) via `add_event`; formata com timestamp e cor por nível; auxilia auditoria e debug.

---

## 2. Aba Configuração

### 2.1. Botões superiores
- **2.1.1** Restaurar Padrões — Botão — Restaura valores default  
  → **Função:** Chama `_reset_settings`; recria `StreamingSettings`, `DetectionSettings`, etc. com valores Pydantic default; recarrega a UI; não persiste até Salvar.

- **2.1.2** Salvar Configurações — Botão — Persiste no config.yaml  
  → **Função:** Chama `_save_settings`; grava todas as configurações da UI em `config/config.yaml` via `Settings.to_yaml`; persiste alterações.

- **2.1.3** Sair — Botão — Encerra o sistema  
  → **Função:** Chama `_on_exit_clicked`; fecha a aplicação (mesmo fluxo do menu Arquivo → Sair).

### 2.2. Sub-aba: Entrada
- **2.2.1** Caminho (Vídeo) — Display (read-only) — Caminho do arquivo de vídeo  
  → **Função:** Exibe `streaming.video_path`; usado quando `source_type=video`; o caminho é definido pelo botão Procurar.

- **2.2.2** Procurar... (Vídeo) — Botão — Seleciona arquivo de vídeo  
  → **Função:** Abre `QFileDialog`; define `streaming.video_path`; usado para fonte "Arquivo de Vídeo".

- **2.2.3** Loop do vídeo — Input (CheckBox) — Repetir vídeo ao final  
  → **Função:** Define `streaming.loop_video`; quando True, o `VideoFileAdapter` reinicia o vídeo ao chegar ao fim; útil para testes contínuos.

- **2.2.4** Índice (USB) — Input (SpinBox) — Índice da câmera USB (0–10)  
  → **Função:** Define `streaming.usb_camera_index`; passado ao `cv2.VideoCapture(index)`; 0 = primeira câmera.

- **2.2.5** IP (GigE) — Input (LineEdit) — IP da câmera GigE  
  → **Função:** Define `streaming.gige_ip`; usado pelo `GigECameraAdapter` para conectar a câmeras GigE Vision.

- **2.2.6** Porta (GigE) — Input (SpinBox) — Porta GigE (1–65535)  
  → **Função:** Define `streaming.gige_port`; porta de controle da câmera GigE (padrão 3956).

- **2.2.7** Arquivo CTI (GenTL) — Display (read-only) — Caminho do arquivo CTI  
  → **Função:** Exibe `streaming.gentl_cti_path`; o driver GenTL (ex.: Omron Sentech) é carregado desse arquivo `.cti`.

- **2.2.8** Procurar... (GenTL) — Botão — Seleciona arquivo CTI  
  → **Função:** Abre diálogo para escolher o arquivo `.cti`; define `streaming.gentl_cti_path`.

- **2.2.9** Índice da câmera (GenTL) — Input (SpinBox) — Índice na lista GenTL (0–10)  
  → **Função:** Define `streaming.gentl_device_index`; qual câmera na lista do Harvester (0 = primeira).

- **2.2.10** Dimensão máx. (px) (GenTL) — Input (SpinBox) — Máximo do lado maior em pixels (0–4096)  
  → **Função:** Define `streaming.gentl_max_dimension`; redimensiona o frame para reduzir carga em câmeras de alta resolução; 0 = sem limite (com segurança 1920).

- **2.2.11** FPS alvo (GenTL) — Input (DoubleSpinBox) — FPS alvo do stream (1–60)  
  → **Função:** Define `streaming.gentl_target_fps`; intervalo entre capturas no `StreamWorker`; valores menores reduzem carga em alta resolução.

- **2.2.12** Tamanho máximo (Buffer) — Input (SpinBox) — Tamanho do buffer de frames (1–100)  
  → **Função:** Define `streaming.max_frame_buffer_size`; tamanho do `FrameBuffer`; evita acúmulo excessivo quando a inferência é mais lenta que a captura.

### 2.3. Sub-aba: Detecção
- **2.3.1** Modelo — Input (Combo editável) — PekingU/rtdetr_r50vd, r101vd, facebook/detr-resnet-50/101  
  → **Função:** Define `detection.default_model`; ID do Hugging Face ou caminho; usado por `InferenceEngine.load_model` quando não há modelo local; fallback quando `model_path` não tem modelo válido.

- **2.3.2** Caminho local — Input (LineEdit) — Caminho para modelo local  
  → **Função:** Define `detection.model_path` (default: `model_best`); diretório com `config.json`, `preprocessor_config.json`, `task.json` e `model.safetensors`; prioridade sobre Hugging Face; usado por `ModelLoader.load` e `InferenceEngine._resolve_model_path`.

- **2.3.3** Procurar... (Modelo) — Botão — Seleciona diretório do modelo  
  → **Função:** Abre `QFileDialog.getExistingDirectory`; define o caminho do modelo local.

- **2.3.4** Device — Input (Combo) — auto, cuda, mps, cpu  
  → **Função:** Define `detection.device`; onde o modelo roda: auto (CUDA/MPS/CPU), cuda (NVIDIA), mps (Apple Silicon), cpu; usado por `ModelLoader._resolve_device`.

- **2.3.5** Confiança mín. — Input (Slider) — 0–100% (label exibe valor)  
  → **Função:** Define `detection.confidence_threshold`; detecções abaixo são descartadas; usado por `PostProcessor` e `InferenceEngine.set_confidence_threshold`; afeta qualidade vs. quantidade de detecções.

- **2.3.6** Máx. detecções — Input (SpinBox) — 1–100  
  → **Função:** Define `detection.max_detections`; limite de detecções retornadas por frame (após NMS); usado por `PostProcessor` e `InferenceEngine.set_max_detections`.

- **2.3.7** FPS inferência — Input (SpinBox) — 1–60  
  → **Função:** Define `detection.inference_fps`; intervalo entre inferências no `InferenceWorker`; controla carga da GPU/CPU vs. latência.

### 2.4. Sub-aba: Imagem
- **2.4.1** Coordenadas X, Y, W, H (ROI) — Input (DoubleSpinBox) — x, y, largura, altura [px]  
  → **Função:** Define `preprocess.roi`; região [x, y, largura, altura] em pixels; usada pelo `ROIManager` (clamp de coordenadas ao enviar ao CLP, overlay).

- **2.4.2** Centroide (mm/px) — Input (DoubleSpinBox) — mm/px (default 1)  
  → **Função:** Define `preprocess.roi_calibration_mm_per_px`; relação mm/px aplicada ao X,Y do centroide da detecção; coord_mm = coord_px * mm_per_px; ex.: 100 → px*100; usado na exibição e no envio ao CLP.

- **2.4.3** Padrão (25% área central) — Botão — Aplica ROI padrão  
  → **Função:** Chama `_set_default_roi`; aplica `DEFAULT_ROI_QUARTER_AREA` (ex.: 181, 101, 277, 277) em pixels.

- **2.4.4** Perfil — Input (Combo) — default, bright, dark, high_contrast, low_contrast, enhanced, smooth, sharp  
  → **Função:** Define `preprocess.profile`; valor persistido em config; reservado para uso futuro (brilho/contraste).

### 2.5. Sub-aba: CLP
- **2.5.1** IP do CLP — Input (LineEdit) — IP do controlador  
  → **Função:** Define `cip.ip`; endereço do CLP Omron NX para conexão CIP/EtherNet-IP; usado por `CIPClient` e `aphyt`.

- **2.5.2** Porta CIP — Input (SpinBox) — Porta CIP (1–65535)  
  → **Função:** Define `cip.port`; porta CIP padrão 44818; usada na conexão com o CLP.

- **2.5.3** Timeout — Input (DoubleSpinBox) — Timeout de conexão (s)  
  → **Função:** Define `cip.connection_timeout`; tempo máximo para estabelecer conexão TCP com o CLP; usado no teste de conexão e na conexão real.

- **2.5.4** Modo simulado — Input (CheckBox) — Simula conexão CIP  
  → **Função:** Define `cip.simulated`; quando True, usa `SimulatedPLC` em vez do CLP real; permite testes sem hardware; desabilita teste de conexão real.

- **2.5.5** Testar Conexão — Botão — Testa TCP com IP:porta  
  → **Função:** Chama `_test_plc_connection`; abre socket TCP para IP:porta com timeout; verifica se o CLP está acessível na rede; não usa protocolo CIP completo.

- **2.5.6** Intervalo (Reconexão) — Input (DoubleSpinBox) — Intervalo entre tentativas (s)  
  → **Função:** Define `cip.retry_interval`; tempo entre tentativas de reconexão automática quando a conexão fica DEGRADED; usado por `CIPClient._schedule_reconnect`.

- **2.5.7** Máx. tentativas (Reconexão) — Input (SpinBox) — 0–100  
  → **Função:** Define `cip.max_retries`; número máximo de tentativas de reconexão antes de desistir; usado por `CIPClient`.

- **2.5.8** Intervalo (Heartbeat) — Input (DoubleSpinBox) — Intervalo do heartbeat (s)  
  → **Função:** Define `cip.heartbeat_interval`; intervalo do timer que envia sinal VisionHeartbeat ao CLP; mantém o CLP ciente de que a visão está ativa; usado por `CIPClient._start_heartbeat`.

### 2.6. Sub-aba: Saída
- **2.6.1** Habilitar stream para navegador — Input (CheckBox) — Liga/desliga stream HTTP MJPEG  
  → **Função:** Define `output.rtsp_enabled`; quando True, inicia `MjpegServer` ao iniciar o sistema; permite visualizar o stream em um navegador (Chrome, Firefox, Edge) via URL HTTP.

- **2.6.2** Porta — Input (SpinBox) — Porta HTTP (1–65535)  
  → **Função:** Define `output.http_port`; porta do servidor MJPEG (padrão 8080); usada na URL do stream.

- **2.6.3** Path — Input (LineEdit) — Path do stream (ex.: /stream)  
  → **Função:** Define `output.http_path`; path da URL (ex.: /stream → http://IP:8080/stream); usado pelo `MjpegServer`.

- **2.6.4** URL (copiar/colar) — Display (read-only) — URL completa para o navegador  
  → **Função:** Exibe a URL completa (http://IP:porta/path) calculada por `_update_stream_url_display`; IP local obtido via socket; permite copiar e colar no navegador.

- **2.6.5** Copiar URL — Botão — Copia URL para área de transferência  
  → **Função:** Chama `_copy_stream_url`; copia a URL para o clipboard; exibe mensagem de confirmação.

---

## 3. Aba Diagnósticos

### 3.1. Sub-aba: Visão Geral
- **3.1.1** Stream FPS (card) — Display — FPS do stream + status (Ativo/Parado)  
  → **Função:** Exibe `StreamManager.get_fps()` e status; indica taxa de captura de frames; atualizado a cada 1s por `_update_stats`.

- **3.1.2** Inferência FPS (card) — Display — FPS inferência + latência (ms)  
  → **Função:** Calcula FPS a partir de `inference_time` (1000/ms); exibe latência da inferência; indica desempenho do modelo.

- **3.1.3** Detecções (card) — Display — Contador de detecções  
  → **Função:** Exibe `MetricsCollector.get_counter("detection_count")`; total de detecções desde o início; indica atividade do sistema.

- **3.1.4** Status CLP (card) — Display — Status da conexão CLP  
  → **Função:** Exibe `CIPClient.state.status`; indica se o CLP está conectado, simulado, desconectado, etc.; cor verde/vermelho conforme estado.

- **3.1.5** Ciclos (card) — Display — Contador de ciclos pick-and-place  
  → **Função:** Exibe `RobotController.cycle_count`; total de ciclos completados; indica produtividade.

- **3.1.6** Erros (card) — Display — Contador de erros  
  → **Função:** Exibe `MetricsCollector.get_counter("error_count")`; total de erros; cor vermelha se > 0; indica saúde do sistema.

- **3.1.7** Health Banner — Display — "Sistema funcionando normalmente" / "Sistema com alertas" / "Sistema parado"  
  → **Função:** Resumo visual do estado; verde = stream+inferência ativos e erros < 10; amarelo = alertas; cinza = parado; atualizado por `_update_stats`.

### 3.2. Sub-aba: Métricas
- **3.2.1** Gráfico FPS do Stream — Display — Gráfico de linha  
  → **Função:** Exibe série temporal de `stream_fps`; `MetricsChart` com métrica "stream_fps"; acompanha variação da taxa de captura.

- **3.2.2** Gráfico Tempo de Inferência — Display — Gráfico de linha (ms)  
  → **Função:** Exibe série de `inference_time`; indica latência por frame; ajuda a identificar picos ou degradação.

- **3.2.3** Gráfico Confiança de Detecção — Display — Gráfico de linha (%)  
  → **Função:** Exibe série de `detection_confidence`; acompanha qualidade das detecções ao longo do tempo.

- **3.2.4** Gráfico Tempo de Resposta CLP — Display — Gráfico de linha (ms)  
  → **Função:** Exibe série de `cip_response_time`; indica latência da comunicação CIP; ajuda a diagnosticar problemas de rede/CLP.

### 3.3. Sub-aba: Logs
- **3.3.1** Nível — Input (Combo) — Todos, INFO, WARNING, ERROR, DEBUG  
  → **Função:** Filtra linhas do log por nível; aplicado em `_apply_filters`; reduz ruído ao focar em erros ou avisos.

- **3.3.2** Buscar — Input (LineEdit) — Filtro por texto  
  → **Função:** Filtra linhas que contêm o texto digitado; aplicado em `_apply_filters`; permite buscar por tag, IP, etc.

- **3.3.3** Auto-refresh — Input (CheckBox) — Atualiza automaticamente  
  → **Função:** Define se o `LogViewer` recarrega o arquivo quando `QFileSystemWatcher` detecta mudança; mantém logs em tempo real.

- **3.3.4** Atualizar — Botão — Recarrega logs  
  → **Função:** Chama `_load_logs`; lê novamente o arquivo de log (últimas 1000 linhas); aplica filtros atuais.

- **3.3.5** Exportar — Botão — Exporta logs para arquivo  
  → **Função:** Chama `_export_logs`; abre `QFileDialog.getSaveFileName`; salva linhas filtradas em arquivo .txt; útil para análise externa.

- **3.3.6** Limpar — Botão — Limpa o viewer  
  → **Função:** Chama `_clear_logs`; limpa `_lines`, `_filtered_lines` e o viewer; não apaga o arquivo de log.

- **3.3.7** Viewer — Display — Área de texto com logs  
  → **Função:** Exibe linhas do arquivo `config.log_file`; formata com cores por nível (ERROR=vermelho, WARNING=amarelo, etc.); scroll automático para o final.

- **3.3.8** Status — Display — "Carregado: N linhas | Arquivo: ..."  
  → **Função:** Exibe quantidade de linhas carregadas e caminho do arquivo; ou mensagem de erro; atualizado após carregar/exportar/limpar.

### 3.4. Sub-aba: Sistema
- **3.4.1** OS — Display — platform.platform()  
  → **Função:** Exibe sistema operacional (ex.: Darwin-24.6.0-arm64); útil para suporte e documentação de bugs.

- **3.4.2** Python — Display — Versão do Python  
  → **Função:** Exibe versão do interpretador (ex.: 3.11.5); útil para verificar compatibilidade.

- **3.4.3** Arquitetura — Display — platform.machine()  
  → **Função:** Exibe arquitetura (ex.: arm64, x86_64); útil para identificar ambiente.

- **3.4.4** PyTorch — Display — Versão do PyTorch  
  → **Função:** Exibe versão do PyTorch; necessário para inferência DETR/RT-DETR.

- **3.4.5** CUDA Disponível — Display — Sim/Não  
  → **Função:** Exibe `torch.cuda.is_available()`; indica se GPU NVIDIA está disponível; cor verde/vermelho.

- **3.4.6** GPU — Display — Nome da GPU (se CUDA)  
  → **Função:** Exibe `torch.cuda.get_device_name(0)`; nome do dispositivo NVIDIA; útil para verificar hardware.

- **3.4.7** CUDA Version — Display — Versão CUDA (se disponível)  
  → **Função:** Exibe `torch.version.cuda`; versão do driver CUDA; útil para troubleshooting.

- **3.4.8** Carregado (Modelo) — Display — Sim/Não  
  → **Função:** Exibe se o modelo está carregado (`model_info.loaded`); indica prontidão para inferência.

- **3.4.9** Nome (Modelo) — Display — Nome do modelo  
  → **Função:** Exibe `model_info.name`; qual modelo está em uso (ex.: PekingU/rtdetr_r50vd ou caminho local).

- **3.4.10** Device (Modelo) — Display — cpu/cuda/mps  
  → **Função:** Exibe `model_info.device`; onde o modelo está rodando; útil para confirmar uso de GPU.

- **3.4.11** CPU (Recursos) — Display — Uso de CPU (%)  
  → **Função:** Exibe `psutil.Process().cpu_percent()`; uso de CPU do processo; atualizado a cada 1s; indica carga do sistema.

- **3.4.12** Memória (Recursos) — Display — Uso de memória (MB)  
  → **Função:** Exibe `process.memory_info().rss / 1024²`; memória RSS do processo em MB; indica consumo de RAM.

- **3.4.13** GPU (Recursos) — Display — Memória alocada/reservada (se CUDA)  
  → **Função:** Exibe `torch.cuda.memory_allocated` e `memory_reserved`; uso de VRAM; útil para verificar se há espaço para o modelo.

---

## Indicação para deleção

**Itens a deletar:** *(preencha os números, ex.: 1.1.2, 2.2.5, 2.2.6, 3.2)*

```
```

---

## Nota sobre deleção de grupos

Para remover **grupos inteiros** (sub-abas ou seções), use o número do grupo:
- **2.2** — Remove toda a sub-aba Entrada
- **2.3** — Remove toda a sub-aba Detecção
- **2.4** — Remove toda a sub-aba Imagem
- **2.5** — Remove toda a sub-aba CLP
- **2.6** — Remove toda a sub-aba Saída
- **3.1** — Remove sub-aba Visão Geral
- **3.2** — Remove sub-aba Métricas
- **3.3** — Remove sub-aba Logs
- **3.4** — Remove sub-aba Sistema
- **1.3** — Remove painel lateral inteiro
- **1.4** — Remove console de eventos inteiro

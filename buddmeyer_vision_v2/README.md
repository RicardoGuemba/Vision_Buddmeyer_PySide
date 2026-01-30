# Buddmeyer Vision System v2.0

Sistema de visão computacional para automação de expedição (pick-and-place) de embalagens.

## 📋 Características

- ✅ **Detecção em tempo real** usando modelos DETR/RT-DETR (Hugging Face)
- ✅ **Comunicação industrial** com CLP Omron NX102 via CIP/EtherNet-IP
- ✅ **Interface desktop PySide6** com 3 abas: Operação, Configuração, Diagnósticos
- ✅ **Múltiplas fontes de vídeo**: arquivos MP4, USB, RTSP, GigE
- ✅ **Sistema de logs** estruturado para rastreamento de detecções e erros
- ✅ **Modo simulado** para desenvolvimento sem CLP real

## 🖥️ Requisitos de Sistema

| Requisito | Valor |
|-----------|-------|
| Sistema Operacional | Windows 10 (build 1903+) ou Windows 11 |
| Python | 3.10 ou superior |
| GPU | NVIDIA RTX (opcional, recomendado) |
| RAM | Mínimo 8 GB (recomendado 16 GB) |
| Disco | 10 GB livres |

## 🚀 Instalação

### 1. Clone ou copie o projeto

```bash
cd C:\Vision_Buddmeyer_PySide
```

### 2. Crie um ambiente virtual

```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Instale as dependências

```bash
pip install -r buddmeyer_vision_v2/requirements.txt
```

### 4. (Opcional) Instale suporte a GPU NVIDIA

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

## 🎮 Execução

```bash
cd buddmeyer_vision_v2
python main.py
```

Ou:

```bash
python buddmeyer_vision_v2/main.py
```

## 📖 Roteiro para o cliente

Para uso no ambiente do cliente (configuração do CLP, logs e troubleshooting), consulte:

- **[ROTEIRO_CLIENTE.md](ROTEIRO_CLIENTE.md)** – passo a passo para configurar o IP do CLP, localizar logs e proceder em caso de erro de conexão ou envio de tag.

## 📁 Estrutura do Projeto

```
buddmeyer_vision_v2/
├── main.py                    # Ponto de entrada
├── requirements.txt           # Dependências
├── config/
│   ├── settings.py            # Pydantic Settings
│   └── config.yaml            # Configuração YAML
├── core/
│   ├── application.py         # Classe principal singleton
│   ├── logger.py              # Sistema de logging
│   ├── metrics.py             # Coleta de métricas
│   └── exceptions.py          # Exceções customizadas
├── streaming/
│   ├── stream_manager.py      # Gerenciador de stream
│   ├── source_adapters.py     # Adaptadores de fonte
│   ├── frame_buffer.py        # Buffer de frames
│   └── stream_health.py       # Health check
├── preprocessing/
│   ├── preprocess_pipeline.py # Pipeline de pré-processamento
│   ├── roi_manager.py         # Gerenciamento de ROI
│   └── transforms.py          # Transformações de imagem
├── detection/
│   ├── inference_engine.py    # Engine de inferência
│   ├── model_loader.py        # Carregador de modelos
│   ├── postprocess.py         # Pós-processamento
│   └── events.py              # Eventos de detecção
├── communication/
│   ├── cip_client.py          # Cliente CIP/EtherNet-IP
│   ├── tag_map.py             # Mapeamento de TAGs
│   └── connection_state.py    # Estado da conexão
├── control/
│   ├── robot_controller.py    # Máquina de estados do robô
│   └── cycle_processor.py     # Processador de ciclos
├── ui/
│   ├── main_window.py         # Janela principal
│   ├── pages/
│   │   ├── operation_page.py  # Aba Operação
│   │   ├── configuration_page.py # Aba Configuração
│   │   └── diagnostics_page.py   # Aba Diagnósticos
│   ├── widgets/
│   │   ├── video_widget.py    # Widget de vídeo
│   │   ├── status_panel.py    # Painel de status
│   │   ├── event_console.py   # Console de eventos
│   │   ├── metrics_chart.py   # Gráficos de métricas
│   │   └── log_viewer.py      # Visualizador de logs
│   └── styles/
│       └── industrial.qss     # Tema industrial
├── models/                    # Modelos de ML
├── logs/                      # Logs do sistema
└── videos/                    # Vídeos de teste
```

## ⚙️ Configuração

Edite o arquivo `config/config.yaml` para ajustar:

### Fonte de Vídeo

```yaml
streaming:
  source_type: video  # video, usb, rtsp, gige
  video_path: videos/test.mp4
  loop_video: true
```

### Modelo de Detecção

```yaml
detection:
  default_model: PekingU/rtdetr_r50vd
  confidence_threshold: 0.5
  device: auto  # cpu, cuda, auto
```

### Comunicação CLP

```yaml
cip:
  ip: 187.99.125.5
  port: 44818
  simulated: false  # true para modo simulado
```

## 🎯 Uso

### Aba Operação

1. Selecione a fonte de vídeo (arquivo, câmera USB, RTSP, GigE)
2. Clique em **▶ Iniciar** para começar
3. Visualize as detecções em tempo real no vídeo
4. Acompanhe o status no painel lateral
5. Clique em **⏹ Parar** para encerrar

### Atalhos de Teclado

| Atalho | Ação |
|--------|------|
| F5 | Iniciar sistema |
| F6 | Parar sistema |
| F11 | Fullscreen |
| Ctrl+Q | Sair |

### Aba Configuração

- Ajuste parâmetros de vídeo, modelo, pré-processamento
- Configure a conexão com o CLP
- Teste a conexão antes de operar

### Aba Diagnósticos

- Visualize métricas em tempo real
- Acompanhe logs do sistema
- Verifique informações do sistema

## 🔧 TAGs CLP

### TAGs de Escrita (Visão → CLP)

| Nome | Tipo | Descrição |
|------|------|-----------|
| PRODUCT_DETECTED | BOOL | Produto detectado |
| CENTROID_X | REAL | Coordenada X do centroide |
| CENTROID_Y | REAL | Coordenada Y do centroide |
| CONFIDENCE | REAL | Confiança (0-1) |
| DETECTION_COUNT | INT | Contador de detecções |

### TAGs de Leitura (CLP → Visão)

| Nome | Tipo | Descrição |
|------|------|-----------|
| ROBOT_ACK | BOOL | ACK do robô |
| ROBOT_READY | BOOL | Robô pronto |
| RobotStatus_PickComplete | BOOL | Pick completado |
| RobotStatus_PlaceComplete | BOOL | Place completado |

## 📊 Métricas de Performance

| Métrica | CPU | CUDA |
|---------|-----|------|
| FPS de Inferência | ≥ 15 | ≥ 30 |
| Latência de Detecção | < 500ms | < 100ms |
| Uso de Memória | < 8 GB | < 8 GB |

## 🐛 Troubleshooting

### CUDA não detectado

Verifique se os drivers NVIDIA estão instalados:
```bash
nvidia-smi
```

Instale o PyTorch com CUDA:
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### Erro de conexão CLP

1. Verifique se o IP e porta estão corretos
2. Verifique a conectividade de rede
3. Ative o modo simulado para testes: `cip.simulated: true`

### Modelo não carrega

1. Verifique conexão com internet (para download do Hugging Face)
2. Ou baixe o modelo manualmente para `models/`

## 📝 Licença

© 2025 Sistema de Automação Industrial

## 🔗 Referências

- [PySide6 Documentation](https://doc.qt.io/qtforpython/)
- [PyTorch](https://pytorch.org/docs/)
- [Hugging Face Transformers](https://huggingface.co/docs/transformers/)
- [RT-DETR Model](https://huggingface.co/PekingU/rtdetr_r50vd)
- [aphyt (CIP)](https://github.com/aphyt/aphyt)

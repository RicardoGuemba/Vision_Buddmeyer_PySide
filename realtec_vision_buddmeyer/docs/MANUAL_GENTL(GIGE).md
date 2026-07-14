# Manual – Câmera GenTL (Omron Sentech) e melhorias de desempenho

Documento que descreve tudo o que foi implementado e alterado para suporte à câmera **GenTL (Harvester / Omron Sentech)**, correções de travamento da UI e carregamento do modelo em segundo plano.

---

## Índice

1. [Visão geral do que foi feito](#1-visão-geral-do-que-foi-feito)
2. [Onde está a conexão de cada tipo de câmera](#2-onde-está-a-conexão-de-cada-tipo-de-câmera)
3. [Câmera GenTL (Omron Sentech)](#3-câmera-gentl-omron-sentech)
4. [Configuração e uso na interface](#4-configuração-e-uso-na-interface)
5. [Tela de ajustes da câmera GenTL](#5-tela-de-ajustes-da-câmera-gentl)
6. [Proteções e desempenho (evitar travamentos)](#6-proteções-e-desempenho-evitar-travamentos)
7. [Carregamento do modelo em segundo plano](#7-carregamento-do-modelo-em-segundo-plano)
8. [FPS e gargalos](#8-fps-e-gargalos)
9. [Referência rápida de arquivos](#9-referência-rápida-de-arquivos)
10. [Guia rápido – Câmera STC-MCS2041POE](#10-guia-rápido--câmera-stc-mcs2041poe)

---

## 1. Visão geral do que foi feito

| Item                                           | Descrição                                                                                                                                                                                                  |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Nova fonte GenTL**                     | Tipo de fonte "Câmera GenTL (Omron Sentech)" usando a biblioteca**Harvester** (GenICam/GenTL) e arquivo CTI do fabricante.                                                                            |
| **Configuração GenTL**                 | CTI path, índice da câmera,**dimensão máxima** (redimensionamento) e **FPS alvo** configuráveis na aba Configuração e na Operação ("Selecionar CTI...").                                |
| **Tela de ajustes da câmera GenTL**    | Com a fonte GenTL selecionada e o stream ativo, o botão **"Ajustes da câmera..."** abre um diálogo para gain, exposição (µs), ExposureAuto e GainAuto (GenICam).                         |
| **Proteção na abertura**               | Remoção do `fetch()` em `open()` do adaptador GenTL para não travar a UI ao obter um frame 20MP na thread principal. Dimensões passam a ser obtidas no primeiro `read()` na thread do worker.      |
| **Redimensionamento**                    | Frames grandes (ex.: 5472×3648) são redimensionados para um máximo configurável (ex.: 1920 px no lado maior) para não travar exibição e inferência. Limite de segurança mesmo com "Sem limite" (0). |
| **Cache no widget de vídeo**            | Conversão numpy → QImage → QPixmap e escala passam a ser cacheadas; só recalculadas quando o frame ou o tamanho do widget mudam, reduzindo trabalho na thread principal.                                 |
| **Carregamento do modelo em background** | Carregamento do modelo Mask2Former (`model_best/`) em uma **QThread**; botão "Carregando modelo..." e UI responsiva durante o carregamento. |
| **Logger**                               | Uso de `datetime.now(timezone.utc)` em vez de `datetime.utcnow()` para evitar DeprecationWarning.                                                                                                        |
| **Dependência**                         | Inclusão de**harvesters** em `requirements.txt` para suporte GenTL.                                                                                                                                 |

---

## 2. Onde está a conexão de cada tipo de câmera

### 2.1 Implementação da conexão (backend)

**Arquivo:** `realtec_vision_buddmeyer/streaming/source_adapters.py`

Cada tipo de câmera tem um **adaptador** que implementa `open()` e `read()`:

| Tipo                            | Classe                    | Como conecta                                                                                        |
| ------------------------------- | ------------------------- | --------------------------------------------------------------------------------------------------- |
| **Arquivo de vídeo**     | `VideoFileAdapter`      | `cv2.VideoCapture(caminho_do_arquivo)`                                                            |
| **USB**                   | `USBCameraAdapter`      | `cv2.VideoCapture(índice, cv2.CAP_DSHOW)` (Windows) ou fallback sem CAP_DSHOW                    |
| **RTSP**                  | `RTSPAdapter`           | `cv2.VideoCapture(url, cv2.CAP_FFMPEG)`                                                           |
| **GigE (genérico)**      | `GigECameraAdapter`     | Pipeline GStreamer (UDP/RTP/JPEG) ou `cv2.VideoCapture("gige://ip:porta")`                        |
| **GenTL (Omron Sentech)** | `GenTLHarvesterAdapter` | Harvester:`add_file(cti)`, `update()`, `create(índice)`, `start()`; frames via `fetch()` |

A **factory** que escolhe o adaptador é a função **`create_adapter()`** no mesmo arquivo (parâmetros: `source_type`, `video_path`, `camera_index`, `rtsp_url`, `gige_ip`, `gige_port`, `gentl_cti_path`, `gentl_device_index`, `gentl_max_dimension`, `gentl_target_fps`, `loop_video`).

### 2.2 Quem abre a fonte e roda o stream

**Arquivo:** `realtec_vision_buddmeyer/streaming/stream_manager.py`

- **`_start_with_current_settings()`**: chama `create_adapter(...)` com os parâmetros de `settings.streaming`, depois `adapter.open()` e cria o **StreamWorker** (QThread) que em loop chama `adapter.read()` e emite os frames.
- **`change_source(...)`**: atualiza tipo e parâmetros da fonte em memória; se o stream estava rodando, para e reinicia com as novas configurações.

### 2.3 Configuração (valores padrão e persistência)

**Arquivo:** `realtec_vision_buddmeyer/config/settings.py`

- **`StreamingSettings`**: `source_type`, `video_path`, `usb_camera_index`, `rtsp_url`, `gige_ip`, `gige_port`, `gentl_cti_path`, `gentl_device_index`, `gentl_max_dimension`, `gentl_target_fps`, `max_frame_buffer_size`, `loop_video`.
- Validação de `source_type` inclui `"gentl"`.

---

## 3. Câmera GenTL (Omron Sentech)

### 3.1 Conceito

- **GenTL** é o padrão GenICam para transporte (GigE Vision, USB3 Vision, etc.).
- A **Omron Sentech** fornece um driver (CTI) que o Harvester usa para falar com a câmera.
- O usuário informa o **caminho do arquivo .cti** (ex.: `C:\Program Files\Common Files\OMRON_SENTECH\GenTL\v1_5\StGenTL_MD_VC141_v1_5_x64.cti`) e o **índice** da câmera (0 = primeira).

### 3.2 Fluxo no código

1. **`GenTLHarvesterAdapter.open()`**

   - Carrega Harvester, `add_file(cti_path)`, `update()`, `create(device_index)`, `start()`.
   - **Não** faz `fetch()` aqui (evita travar a UI com um frame 20MP na thread principal).
2. **`GenTLHarvesterAdapter.read()`** (rodando na **StreamWorker**)

   - `fetch(timeout)` → buffer do Harvester.
   - `reshape` + `cvtColor` (mono → BGR se necessário).
   - **`_resize_if_needed()`**: se o frame exceder `max_dimension` (ou o limite de segurança 1920), redimensiona mantendo proporção.
   - Retorna `FrameInfo` com o frame já redimensionado.
3. **Logs**

   - `gentl_opened`: apenas `cti_path` e `device_index`.
   - `gentl_first_frame`: uma vez, com `native=(largura, altura)` e `output=(largura, altura)` após o resize.

### 3.3 Parâmetros configuráveis

| Parâmetro                    | Config / UI                     | Efeito                                                                                      |
| ----------------------------- | ------------------------------- | ------------------------------------------------------------------------------------------- |
| **gentl_cti_path**      | Caminho do arquivo .cti         | Driver GenTL usado pelo Harvester.                                                          |
| **gentl_device_index**  | Índice 0, 1, …                | Qual câmera na lista do Harvester.                                                         |
| **gentl_max_dimension** | 0–4096 px (0 = “Sem limite”) | Lado maior do frame após resize; 0 ainda aplica limite de segurança 1920.                 |
| **gentl_target_fps**    | 1–60 (ex.: 10 ou 15)           | FPS alvo do StreamWorker; o FPS real pode ser menor se o processamento por frame for lento. |

---

## 4. Configuração e uso na interface

### 4.1 Aba Configuração → Fonte de Vídeo

- **Tipo de Fonte:** inclui "Câmera GenTL (Omron Sentech)".
- Com GenTL selecionado aparecem:
  - **Arquivo CTI:** campo somente leitura + botão **"Procurar..."** para escolher o .cti.
  - **Índice da câmera:** 0–10.
  - **Dimensão máx. (px):** 0–4096 (0 exibido como "Sem limite").
  - **FPS alvo:** 1,0–60,0.
- **Salvar Configurações** grava no `config.yaml` (incluindo `gentl_cti_path`, `gentl_device_index`, `gentl_max_dimension`, `gentl_target_fps`).

### 4.2 Aba Operação

- **Fonte:** combo com "Câmera GenTL (Omron Sentech)".
- Com GenTL selecionado aparece o botão **"Selecionar CTI..."** para escolher o .cti **sem** ir à aba Configuração (valor fica em memória na sessão).
- Legenda abaixo do vídeo:
  - Com CTI selecionado: `Fonte: Câmera GenTL — nome_do_arquivo.cti`
  - Sem CTI: `Fonte: Câmera GenTL (Omron Sentech) — use 'Selecionar CTI...'`
- Ao clicar **Iniciar** com GenTL:
  - Se não houver CTI configurado, é exibida mensagem pedindo para usar "Selecionar CTI..." ou a Configuração.
  - Se o arquivo não existir, mensagem de erro orientando a selecionar de novo.
- Com GenTL selecionado aparece também o botão **"Ajustes da câmera..."**, que abre a tela de configurações da câmera (gain, exposição, auto). Ver [seção 5](#5-tela-de-ajustes-da-câmera-gentl).

### 4.3 Uso típico

1. Instalar dependência: `pip install harvesters` (já em `requirements.txt`).
2. **Configuração** (opcional, para persistir): Tipo "Câmera GenTL (Omron Sentech)", Procurar… → escolher o .cti, ajustar dimensão máx. e FPS alvo, Salvar.
3. **Operação**: Fonte "Câmera GenTL (Omron Sentech)", se necessário "Selecionar CTI...", depois **Iniciar**.
4. Com o stream ativo, use **"Ajustes da câmera..."** para ajustar gain, exposição e modos automáticos na câmera.

---

## 5. Tela de ajustes da câmera GenTL

Quando a fonte selecionada é **Câmera GenTL (Omron Sentech)**, na aba **Operação** aparece o botão **"Ajustes da câmera..."**. Essa tela permite ajustar parâmetros GenICam da câmera (gain, tempo de exposição, auto exposure, auto gain) enquanto o stream está ativo.

### 5.1 Quando usar

- **Requisito:** o stream deve estar **iniciado** com a câmera GenTL. Se você clicar em "Ajustes da câmera..." sem ter clicado em **Iniciar** antes, o sistema informa: *"Inicie o stream com a câmera GenTL (Omron Sentech) para poder ajustar gain, exposição e outros parâmetros."*
- Os ajustes são enviados diretamente à câmera via GenICam (node map). As câmeras Omron Sentech STC suportam, em geral, **Gain** (ex.: 0–22 dB), **ExposureTime** ou **ExposureTimeAbs** (µs), **ExposureAuto** e **GainAuto** (Off, Once, Continuous).

### 5.2 Conteúdo da tela

- **Exposição**
  - **Tempo (µs):** tempo de exposição em microssegundos (valor lido/escrito no nó `ExposureTimeAbs` ou `ExposureTime`, conforme suporte da câmera).
  - **Auto:** modo de exposição automática (Off, Once, Continuous), se a câmera expuser o nó `ExposureAuto`.
- **Ganho**
  - **Ganho:** valor numérico de gain (ex.: 0–22 para algumas STC).
  - **Auto:** modo de ganho automático (Off, Once, Continuous), se a câmera expuser o nó `GainAuto`.

Botões:

- **Atualizar da câmera:** lê os valores atuais da câmera e atualiza os campos da tela.
- **Aplicar:** envia os valores atuais dos campos para a câmera (e exibe confirmação).
- **Fechar:** fecha o diálogo (as alterações já aplicadas permanecem na câmera).

### 5.3 Onde está no código

- **Diálogo:** `ui/widgets/gentl_camera_settings_dialog.py` — classe `GenTLCameraSettingsDialog`; recebe o adaptador GenTL e usa `get_gentl_features()` e `set_gentl_feature()` do adaptador.
- **Adaptador GenTL:** em `streaming/source_adapters.py`, a classe `GenTLHarvesterAdapter` expõe:
  - `get_gentl_node_map()`: retorna o node map GenICam.
  - `get_gentl_features()`: lê Gain, ExposureTime/ExposureTimeAbs, ExposureAuto, GainAuto (apenas os que existirem no device).
  - `set_gentl_feature(name, value)`: define um nó por nome.
- **Stream manager:** `streaming/stream_manager.py` — método `get_gentl_adapter()` retorna o adaptador GenTL atual quando o stream está rodando com fonte GenTL.
- **Operação:** em `ui/pages/operation_page.py`, o botão "Ajustes da câmera..." chama `_open_gentl_camera_settings()`, que obtém o adaptador via `get_gentl_adapter()` e abre o diálogo.

---

## 6. Proteções e desempenho (evitar travamentos)

### 6.1 Nenhum fetch no `open()` GenTL

- **Problema:** Fazer `fetch()` em `open()` (na thread principal) para ler dimensões trazia um frame 5472×3648 e travava a UI.
- **Solução:** Em `open()` só se faz `create()`, `start()` e log. As dimensões são definidas no primeiro `read()` (na thread do worker). Log `gentl_first_frame` mostra resolução nativa e de saída.

### 6.2 Redimensionamento e limite de segurança

- Frames com lado maior que **max_dimension** (ou que 1920 quando max_dimension é 0) são redimensionados com `cv2.resize(..., INTER_AREA)`.
- **Limite de segurança:** mesmo com "Dimensão máx. = 0", o lado maior não ultrapassa 1920 px (constante `_SAFETY_MAX_DIMENSION` em `GenTLHarvesterAdapter`).

### 6.3 Cache no widget de vídeo

**Arquivo:** `realtec_vision_buddmeyer/ui/widgets/video_widget.py`

- **Problema:** Em cada `paintEvent` o frame era copiado (BGR→RGB), convertido para QImage e escalado para o tamanho do widget, sobrecarregando a thread principal.
- **Solução:** Cache de `QPixmap` (e tamanho do widget / shape do frame). A conversão e o escalonamento só são refeitos quando o frame ou o tamanho do widget mudam. Em `resizeEvent` o cache de tamanho é invalidado.

---

## 7. Carregamento do modelo em segundo plano

### 7.1 Objetivo

- Evitar que a UI trave durante o carregamento do modelo Mask2Former (pesos e pré-processador).

### 7.2 Implementação

**Arquivo:** `realtec_vision_buddmeyer/ui/pages/operation_page.py`

- **`_ModelLoaderWorker`** (QObject): em `run()` chama `inference_engine.load_model()` e emite **`finished(bool)`** (True = sucesso).
- O worker é movido para uma **QThread**; o thread é iniciado ao precisar carregar o modelo.

**Fluxo ao clicar Iniciar:**

1. Validações e início do **stream** (vídeo já aparece).
2. Se o modelo **já está carregado**: chama **`_finish_start_system_after_model(source_label)`** (inicia inferência, CLP, atualiza UI).
3. Se o modelo **não está carregado**:
   - Mensagem no console: "Carregando modelo de detecção... (aguarde)".
   - Botão "▶ Iniciar" vira **"Carregando modelo..."** e fica desabilitado.
   - Inicia a thread do worker e retorna (UI continua responsiva).
4. Quando o worker termina (**`_on_model_load_finished(success)`**):
   - Restaura o botão para "▶ Iniciar" e reabilita.
   - Se falhou: mensagem de erro e para o stream.
   - Se sucesso: "Modelo carregado." e **`_finish_start_system_after_model(source_label)`**.

**`_finish_start_system_after_model(source_label)`** concentra o que antes vinha depois do `load_model`: iniciar inferência, modo de ciclo, `_connect_plc_and_start_robot()`, `_is_running = True`, `_update_ui_state()` e mensagem de sucesso.

---

## 8. FPS e gargalos

### 8.1 Por que o FPS real pode ser ~4 com GenTL

- **gentl_target_fps** (ex.: 10) define o **máximo** desejado (intervalo entre capturas no StreamWorker).
- Cada frame exige: **fetch** (5472×3648) + **reshape** + **cvtColor** + **resize** para 1920 (ou menor). O **resize** de ~20 MP por frame é pesado na CPU.
- Se o tempo total por frame for ~250 ms, o FPS real fica ~4, independente do target_fps.

### 8.2 O que ajustar para aumentar FPS

1. **Dimensão máx. (px):** reduzir (ex.: 960 ou 640) para menos pixels no resize e mais FPS.
2. **Resolução nativa da câmera:** se a câmera permitir modo de menor resolução, menos dados por frame.
3. **(Opcional) Interpolação:** trocar `INTER_AREA` por `INTER_LINEAR` no `cv2.resize` do adaptador GenTL deixa o resize mais rápido, com pequena perda de qualidade.

---

## 9. Referência rápida de arquivos

| Arquivo                                  | Alterações / conteúdo                                                                                                                                                                                       |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **streaming/source_adapters.py**   | `SourceType.GENTL`, `GenTLHarvesterAdapter` (open sem fetch, read com resize, `get_gentl_features`/`set_gentl_feature`/`get_gentl_node_map` para ajustes), `create_adapter` com parâmetros GenTL, limite de segurança 1920. |
| **streaming/stream_manager.py**    | `change_source` e `_start_with_current_settings` com `gentl_*`, validação de CTI para GenTL, `get_gentl_adapter()` para a tela de ajustes, `create_adapter(..., gentl_max_dimension, gentl_target_fps)`. |
| **config/settings.py**             | `StreamingSettings`: `gentl_cti_path`, `gentl_device_index`, `gentl_max_dimension`, `gentl_target_fps`; `source_type` válido inclui `"gentl"`.                                                  |
| **ui/pages/configuration_page.py** | Combo com "Câmera GenTL (Omron Sentech)", grupo GenTL (CTI, índice, dimensão máx., FPS alvo), load/save e `_browse_gentl_cti`.                                                                           |
| **ui/pages/operation_page.py**     | Combo e legenda GenTL, botões "Selecionar CTI..." e "Ajustes da câmera...", validação de CTI ao iniciar, `_open_gentl_camera_settings`, `_ModelLoaderWorker`, carregamento do modelo em QThread. |
| **ui/widgets/video_widget.py**     | Cache de QPixmap/tamanho/shape; `_ensure_cached_pixmap()`, `resizeEvent` invalidando cache.                                                                                                                |
| **ui/widgets/gentl_camera_settings_dialog.py** | Diálogo "Ajustes da câmera GenTL": gain, exposição (µs), ExposureAuto, GainAuto; usa `get_gentl_features` e `set_gentl_feature` do adaptador. |
| **core/logger.py**                 | Timestamp com `datetime.now(timezone.utc)` em vez de `utcnow()`.                                                                                                                                           |
| **requirements.txt**               | Entrada `harvesters>=2.3.0`.                                                                                                                                                                                 |

---

## 10. Guia rápido – Câmera STC-MCS2041POE

Guia de configuração e uso da câmera **STC-MCS2041POE** (Omron Sentech) com Python e Harvester.

### 9.1 Arquitetura recomendada (produção)

```
Câmera STC-MCS2041POE
        ↓
Driver + GenTL (CTI)
        ↓
Harvesters (Python)
        ↓
OpenCV / IA / Automação
```

### 9.2 Pré-requisitos de hardware

- PC com **porta Ethernet Gigabit**
- Cabo **Ethernet Cat5e ou Cat6**
- Alimentação **PoE**:
  - Switch PoE **ou**
  - Injetor PoE
- Windows 10 ou 11 (64 bits)

### 9.3 Instalação de drivers e SDK

#### 9.3.1 Download

A Omron Sentech disponibiliza o SDK (drivers + GenTL + Viewer) no site oficial:

👉 https://sentech.co.jp/en/products/stc-mcs2041poe

O pacote inclui:

- Driver GigE Vision
- GenTL Producer (`.cti`)
- ST Viewer (software de visualização)
- Bibliotecas GenICam

> **Observação:** o download pode exigir cadastro.

#### 9.3.2 Instalação

1. Execute o instalador **como administrador**
2. Aceite os componentes padrão
3. Reinicie o computador após a instalação

### 9.4 Conexão física e rede

1. Conecte a câmera ao PC ou switch via **Ethernet**
2. Garanta que o **PoE esteja ativo**
3. Aguarde a câmera inicializar (LED ativo)

Configuração típica de IP (caso necessário):

- A câmera geralmente usa IP **link-local (169.254.x.x)**
- O PC deve estar na **mesma sub-rede**

### 9.5 Teste inicial com ST Viewer (recomendado)

Antes do Python, valide no software:

1. Abra o **ST Viewer**
2. A câmera **STC-MCS2041POE** deve aparecer na lista
3. Abra a câmera (acesso exclusivo)
4. Ative o **Live View**
5. Ajuste parâmetros básicos:
   - `TriggerMode = Off`
   - `AcquisitionMode = Continuous`
   - `PixelFormat = Mono8` (recomendado)

Se o vídeo aparecer, a instalação está correta.

### 9.6 Preparação do ambiente Python

#### 9.6.1 Criar ambiente virtual (opcional, recomendado)

```bash
python -m venv .venv
.venv\Scripts\activate
```

#### 9.6.2 Instalar dependências

```bash
pip install harvesters opencv-python numpy
```

### 9.7 Localização do arquivo CTI (GenTL)

Após instalar o SDK, o arquivo `.cti` normalmente fica em:

```text
C:\Program Files\Common Files\OMRON_SENTECH\GenTL\v1_5\StGenTL_MD_VC141_v1_5_x64.cti
```

Esse arquivo é obrigatório para que o Harvester consiga descobrir e abrir a câmera.

### 9.8 Código Python de exemplo (teste final)

O código abaixo:

- Descobre a câmera
- Abre a STC-MCS2041POE
- Exibe o vídeo ao vivo
- Encerra ao pressionar `q`

> **Importante:** feche o ST Viewer antes de rodar o script.

```python
from harvesters.core import Harvester
import cv2
import numpy as np

CTI_PATH = r"C:\Program Files\Common Files\OMRON_SENTECH\GenTL\v1_5\StGenTL_MD_VC141_v1_5_x64.cti"

def main():
    h = Harvester()
    h.add_file(CTI_PATH)
    h.update()

    if not h.device_info_list:
        raise RuntimeError("Nenhuma câmera encontrada")

    print("Câmeras encontradas:")
    for i, dev in enumerate(h.device_info_list):
        print(f"[{i}] {dev.display_name}")

    ia = h.create(0)
    ia.start()
    print("Aquisição iniciada. Pressione 'q' para sair.")

    try:
        while True:
            with ia.fetch(timeout=3000) as buffer:
                component = buffer.payload.components[0]
                image = component.data.reshape(
                    component.height,
                    component.width
                )
                cv2.imshow("STC-MCS2041POE - Teste", image)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
    finally:
        ia.stop()
        ia.destroy()
        cv2.destroyAllWindows()
        h.reset()

if __name__ == "__main__":
    main()
```

---

*Documento gerado com base nas alterações realizadas no sistema Buddmeyer Vision v2 para suporte GenTL (Omron Sentech) e melhorias de estabilidade e desempenho.*

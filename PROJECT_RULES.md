# Regras do Projeto — Realtec Vision Buddmeyer

## 1. Stack e padrões

- **UI:** PySide6 (Qt Widgets). Não usar Tkinter.
- **Arquitetura:** camadas por responsabilidade (`streaming/`, `detection/`, `communication/`, `control/`, `ui/`, `config/`, `core/`).
- **Logs:** dois trilhos — `realtec_vision.log` (app/infra/erros) e `process_trace.log` (eventos/transições via `realtec.trace.*`).
- **Integrações:** adapters para fontes de vídeo (`source_adapters.py`) e CLP (`cip_client.py`).

## 2. Estrutura atual (implementada)

```
ui/           → widgets e páginas PySide6
control/      → máquina de estados do robô
detection/    → inferência Mask2Former + eventos
streaming/    → captura e MJPEG
communication/→ CIP client e tag map
config/       → Pydantic settings + YAML
core/         → logging, métricas, exceções
```

**Dependências desejadas:**

- `ui` → `control`, `detection`, `streaming`, `communication`, `config`
- `control` → `communication`, `detection.events`
- `communication` e `streaming` não dependem de widgets Qt (exceto signals no client)

> **Nota:** `PROJECT_RULES` anteriormente descrevia layout feature-based (`ui_qt/state/application/domain`). Esse layout é **meta futura**; o código atual segue camadas por domínio técnico. Novas features devem respeitar a separação acima até migração explícita.

## 3. Threading (PySide6)

- GUI thread deve permanecer livre.
- Stream de câmera e inferência em `QThread` (`StreamWorker`, `InferenceWorker`).
- Polling CLP via timers/async no client; UI atualizada por signals/slots.

## 4. UI enxuta (ISA-101)

- Operação: estado, alarmes, conexões, ciclo, ROI.
- Contadores detalhados na aba **Diagnósticos**, não na Operação.
- Alarmes com destaque visual para condições anormais.

## 5. Logs estruturados

Campos obrigatórios quando aplicável: `ts`, `level`, `logger`, `feature`, `use_case`, `cycle_id`, `frame_id`, `error_code`, `message`.

Use `trace_event()` para transições de processo em `process_trace.log`.

## 6. Integração robô / CLP

- Orquestração: `control/robot_controller.py`
- Transporte: `communication/cip_client.py`
- Contrato de tags: `docs/TAG_CONTRACT.md`

## 7. Documentação

- Alto nível: `docs/OVERVIEW.md`
- Baixo nível: `docs/REFERENCE.md`
- Operador: `docs/GUIA_OPERADOR.md`
- Features novas: `docs/FEATURE_SPEC_TEMPLATE.md` → `docs/FEATURE_*.md`

## 8. Testes

Após alterações em Python: `python -m pytest tests/ -v` em `realtec_vision_buddmeyer/`.

# FEATURE: &lt;título curto em português ou inglês&gt;

> **Como usar:** copie este ficheiro para `docs/FEATURE_&lt;nome&gt;.md`, preencha os blocos e abra essa spec no chat (ou referencie com `@docs/FEATURE_...`) ao pedir implementação em Agent mode.

| Campo | Valor |
|--------|--------|
| **Autor** | |
| **Data** | AAAA-MM-DD |
| **Estado** | rascunho \| revisto \| implementado \| arquivado |
| **Issue / ticket** | (opcional) |

---

## 1. Contexto e problema

- **Situação atual:** o que o sistema faz hoje e onde dói (1–3 frases).
- **Utilizador afetado:** operador, integração CLP, manutenção, etc.
- **Porque agora:** prioridade ou gatilho (cliente, segurança, performance).

---

## 2. Objetivo

- **Objetivo principal:** uma frase mensurável (“reduzir falsos positivos em X%”, “expor tag Y no CLP”).
- **Não-objectivos (fora de escopo):** liste explicitamente o que **não** será feito nesta entrega (evita creep).

---

## 3. Requisitos funcionais

Numere cada requisito (RF-01, RF-02, …).

| ID | Descrição | Prioridade (P0/P1/P2) |
|----|-----------|------------------------|
| RF-01 | … | P0 |
| RF-02 | … | P1 |

Inclua fluxos em linguagem natural se ajudar (“quando o operador carrega em… o sistema deve…”).

---

## 4. Requisitos não-funcionais

- **Performance:** latência máxima aceitável, FPS, uso de CPU/GPU.
- **Segurança / robustez:** falha segura, timeouts, logs.
- **Compatibilidade:** versão Python, SO (Windows no box PC), hardware (câmera, CLP).
- **Observabilidade:** métricas, logs estruturados, rastreio de decisões.

---

## 5. Contratos e dados

- **Entradas / saídas:** formatos (imagens, tensores, tags CLP, eventos internos).
- **Configuração:** novas chaves em `config.yaml` / settings (nome, tipo, default).
- **Quebras de compatibilidade:** tags renomeadas, formatos antigos deprecados.

---

## 6. Desenho técnico (proposto)

- **Módulos a tocar:** pastas/ficheiros prováveis (`detection/`, `communication/`, `ui/`, …).
- **Abordagem:** algoritmo, biblioteca, alternativas descartadas em uma linha cada.
- **Diagrama (opcional):** fluxo simples em texto ou Mermaid.

Se ainda não souberes o desenho, escreve **“TBD — decidir com o agente na implementação”** e define critérios de aceitação fortes na secção 8.

---

## 7. UI / UX (se aplicável)

- O que muda no ecrã, textos, idioma, estados de erro visíveis ao operador.
- Atalhos ou ações perigosas (confirmação).

---

## 8. Critérios de aceitação (testáveis)

Liste **comportamentos verificáveis** — o desenvolvimento só fecha quando isto for verdade.

| ID | Critério | Como verificar (manual / teste auto) |
|----|----------|--------------------------------------|
| CA-01 | … | `pytest …` / passos na UI |
| CA-02 | … | … |

---

## 9. Plano de testes

- **Unitários:** ficheiros `tests/test_*.py` a criar ou alterar.
- **Integração / smoke:** script, câmera, CLP simulado.
- **Regressão:** o que **não** pode quebrar (lista curta).

---

## 10. Riscos e dependências

| Risco | Mitigação |
|-------|-----------|
| … | … |

- **Dependências externas:** modelos, firmware CLP, rede.

---

## 11. Checklist pós-implementação

- [ ] Config documentada ou default seguro
- [ ] Testes adicionados / verdes
- [ ] `CHANGELOG` ou nota de release (se a equipa usar)
- [ ] Revisão por par (ou auto-revisto com checklist acima)

---

## 12. Referências

- Issues, ADRs, normas internas, links Hugging Face / Omron, conversas de email (opcional).

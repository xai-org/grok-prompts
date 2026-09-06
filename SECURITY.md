# Security Architecture and Responsible Disclosure

## Prompt-Level Safety: Known Limitations

All safety guardrails in this repository operate exclusively through text in the model's context window. This is a **fundamental architectural constraint** of transformer-based language models: there is no cryptographic, out-of-band, or inference-layer mechanism that enforces safety independently of the model's own attention.

The prompt hardening in this repository (unified `<policy>` blocks, anti-injection notices, retrieved-content sandboxing guidance) represents the best achievable mitigation **within the prompt layer**. The following limitations remain and require engineering solutions at the inference or serving layer:

---

## Open Architectural Gaps

### 1. Self-Referential Enforcement
The model being asked to resist manipulation is the same model being manipulated. Safety instructions compete with adversarial user text in the same attention space. No prompt instruction can provide a hard guarantee of winning that competition.

**Recommended mitigation**: Input-side and output-side classifiers that run outside the LLM's attention window, applied as pre-filters and post-filters at the serving layer.

### 2. Prompt Injection via Retrieved Content
Web search results, OCR output, file uploads, and PDFs may contain text that mimics system instructions. Prompt-level sandboxing (labeling such content as `[data]`) reduces risk but cannot eliminate it.

**Recommended mitigation**: Structural privilege separation at the inference layer — treating system-turn content and user-turn content with different trust levels that are enforced by the runtime, not by text conventions. Some inference frameworks (e.g., those based on structured chat formats with role-level access control) support this natively.

### 3. Multi-Turn Persona Drift
Sufficiently long conversations may gradually shift the model's effective behavior away from stated policy through incremental, individually-innocuous interactions.

**Recommended mitigation**: Periodic re-injection of the policy block at the inference layer on a per-turn basis, not just at conversation start.

### 4. Cross-Variant Attack Surface
Historically, different prompt variants in this repository used different safety formats (`##` markdown, `<policy>` XML, inline prose, no block). A caller who identified the active variant could tailor attacks to the weakest one.

**Status**: Resolved in this PR — all variants now use a canonical `<policy>` block with a consistent disallowed-activities list.

---

## Responsible Disclosure

Security concerns about xAI's products should be reported to:

- **Email**: security@x.ai
- **Bug bounty**: https://x.ai/security

Please do not file prompt-injection exploits or working jailbreaks as public GitHub issues. File them via the above channels with a 90-day disclosure timeline.

---

## References

- [Perez & Ribeiro, 2022 — Prompt Injection Attacks against GPT-3](https://arxiv.org/abs/2302.12173)
- [Greshake et al., 2023 — Indirect Prompt Injection in LLM-Integrated Applications](https://arxiv.org/abs/2302.12173)
- [OWASP Top 10 for LLMs — LLM01: Prompt Injection](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [Anthropic Constitutional AI — critique/revision phase separation](https://arxiv.org/abs/2212.08073)

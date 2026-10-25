# RoBAS geometry migration guidelines

- This repository already ships functioning sliding journal-bearing geometry. Do not break its public API, its exact B-Rep sections, or its drawing exports.
- Treat the authorized RoBAS directory from ROBAS_SOURCE_DIR as read-only. Never commit raw C# sources, assets, proprietary Eyeshot binaries, license files or extracted ZIP content.
- CadQuery/OCCT is the authoritative geometry kernel. STL is a derived display mesh; Three.js never defines manufacturing B-Rep.
- All geometric request dimensions in the new interface are millimetres. Carefully document and test every RoBAS metre-to-millimetre conversion.
- Every rolling-element family needs topology and STEP roundtrip tests; number, pitch circle, envelope and interference checks. Do not fudge or silently substitute a box, cylinder or mesh when a raceway is expected.
- Codex must not alter scripts/codex_controller.py, config/migration_queue.json, tests/test_codex_controller.py or .github/workflows/codex-controller.yml. Treat them as operator-owned control-plane assets.
- Agent-generated artifacts are always DRAFT. No parameter is implicitly approved by the user.
- When a formula or design rule is ambiguous, flag a blocking issue rather than guessing.
- Development tasks are intentionally scoped MIG-01 through MIG-09. Never implement a later task before its prerequisites.

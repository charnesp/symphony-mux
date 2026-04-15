# TDD

Chaque bloc ci-dessous suit **RED → GREEN → (REFACTOR)** : ne pas écrire de code de production avant le test qui échoue pour la bonne raison. Pas d’exception (voir `AGENTS.md`).

## 1. Configuration and validation

- [x] 1.1 **RED** — Écrire des tests unitaires sur des fragments YAML `agent-gate` (cas valides + invalides : `default_transition` manquant, cible non-`gate`, `rework_to` interdit, cible inconnue, multi-workflow). Les tests **doivent échouer** tant que le parsing / `validate_config` ne gère pas `agent-gate`.
- [x] 1.2 **GREEN** — Étendre le parsing (`StateConfig` / `config.py`) pour `type: agent-gate`, `default_transition`, `transitions`.
- [x] 1.3 **GREEN** — Implémenter les règles `validate_config` jusqu’à ce que tous les tests du §1.1 passent.
- [x] 1.4 **REFACTOR** — Nettoyer en gardant les tests verts.

## 2. Routing parse helper

- [x] 2.1 **RED** — Tests unitaires d’extraction du JSON `transition` depuis les marqueurs `<<<STOKOWSKI_ROUTE>>>` / `<<<END_STOKOWSKI_ROUTE>>>` (présent, absent, JSON mal formé) et de la résolution avec un `StateConfig` mocké (clé inconnue → fallback `default_transition`). Échec attendu sans implémentation.
- [x] 2.2 **GREEN** — Implémenter l’extracteur (module dédié ou voisin de `reporting.py`).
- [x] 2.3 **REFACTOR** — Nettoyer en gardant les tests verts.

## 3. Orchestrator integration

- [x] 3.1 **RED** — Tests (mocks Linear / client) pour : routage réussi → `_safe_transition` avec la bonne clé, pas de commentaire d’erreur de routage ; rapport `<stokowski:report>` posté (ou chemin unique sans double post avec `_post_work_report`) ; erreur de routage → commentaire explicatif + `_safe_transition(..., default_transition)` ; non-régression `agent` / `gate`. Échec attendu sans branche `agent-gate`.
- [x] 3.2 **GREEN** — Brancher `_on_worker_exit` / `_transition` et la publication des commentaires selon `design.md`.
- [x] 3.3 **REFACTOR** — Nettoyer en gardant les tests verts.

## 4. Prompt lifecycle

- [x] 4.1 **RED** — Tests sur `assemble_prompt` (ou helper lifecycle) : pour un état `agent-gate`, le texte assemble **doit** mentionner les clés de transition, le format `<<<STOKOWSKI_ROUTE>>>`, et l’obligation de `<stokowski:report>`. Échec attendu sans extension du lifecycle.
- [x] 4.2 **GREEN** — Étendre `prompt.py` / lifecycle jusqu’aux tests verts.
- [x] 4.3 **REFACTOR** — Nettoyer en gardant les tests verts.

## 5. Documentation and verification

- [x] 5.1 Documenter `agent-gate` dans `CLAUDE.md` et ajouter un extrait dans `workflow.example.yaml` (chemins `prompt:` + exemple de transitions).
- [x] 5.2 `uv run pytest` sur la suite concernée ; `stokowski --dry-run` si la config d’exemple est mise à jour.

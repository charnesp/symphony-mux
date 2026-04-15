## Why

Aujourd’hui, après un état **agent** réussi, Stokowski enchaîne toujours avec la transition fixe `complete`. On ne peut pas router automatiquement vers deux états distincts (par ex. correction vs validation humaine) selon le résultat d’une review agent. Un type d’étape **agent-gate** comble ce trou : un tour d’agent avec prompt dédié, puis choix du prochain état à partir d’une sortie structurée, sans attendre une action humaine sur les états Linear `gate_approved` / `rework`.

## What Changes

- Introduire un nouveau type d’état `agent-gate` dans la machine d’états (YAML + `StateConfig`), avec un champ **`prompt:`** pointant vers un **fichier `.md` dédié** (même modèle que les états `agent` : instructions de scène + global/lifecycle injectés par Stokowski).
- Après succès du runner, parser une sortie structurée (format à figer en design) et invoquer **une** transition nommée parmi celles déclarées sur l’état (au lieu de toujours `complete`) ; publier aussi un **rapport** (`<stokowski:report>`) en commentaire Linear pour expliquer le choix de branche.
- Valider en config que chaque transition d’un `agent-gate` pointe vers un état existant et qu’il existe une transition de secours (`default_transition`) **obligatoire** dont la cible est un état **`type: gate`** (validation humaine). Si la sortie de routage est absente, invalide ou incohérente, Stokowski **poste un commentaire sur le ticket Linear** qui décrit la nature de l’erreur, puis applique `default_transition` pour basculer vers cette validation humaine.
- Étendre le contexte lifecycle / prompt pour lister les branches possibles et le contrat de réponse attendu.
- **BREAKING** : aucun si les workflows existants n’utilisent pas `type: agent-gate` ; les configs inchangées restent sur `complete` pour les états `agent`.

## Capabilities

### New Capabilities

- `workflow-agent-gate`: Comportement runtime d’un état `agent-gate` — exécution d’un tour agent, extraction de la décision, **commentaire Linear de rapport** expliquant le choix, transition vers l’état cible ; en erreur de routage, commentaire Linear explicite puis transition vers le gate défini par `default_transition`.

### Modified Capabilities

- `workflow-config`: Extension du schéma d’état (`type: agent-gate`), règles de validation des transitions nommées et cohérence avec les cibles.

## Impact

- **Côté opérateur** — au moins un **nouveau fichier markdown de prompt** (ex. `prompts/.../review-route.md`) référencé par `prompt:` sur l’état `agent-gate`, distinct des prompts des autres états `agent` du même workflow.
- `stokowski/config.py` — parsing, `StateConfig`, `validate_config` (y compris `prompt` obligatoire pour `agent-gate`, aligné sur `agent`).
- `stokowski/orchestrator.py` — `_on_worker_exit` / `_transition` : branchement sur type `agent-gate`, nom de transition dynamique, commentaires Linear (rapport de choix + erreur de routage) en coordination avec `reporting.py` pour éviter les doublons avec `_post_work_report`.
- `stokowski/prompt.py` — chargement du `.md` de scène comme pour `agent` ; extension du **lifecycle** injecté pour lister les branches et le format de routage (ce n’est pas un second fichier opérateur, c’est du contenu généré).
- `workflow.example.yaml` — exemple optionnel d’un flux review → agent-gate → deux chemins **avec** chemin `prompt:` vers un `.md` d’exemple.
- Tests unitaires pour parsing, validation YAML, orchestration (mocks), contenu du commentaire d’erreur de routage, et assemblage de prompt pour `agent-gate`.

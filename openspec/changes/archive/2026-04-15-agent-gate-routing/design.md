## Context

Les états `agent` passent toujours à la cible de `transitions.complete`. Les états `gate` attendent un humain sur Linear (`review` → `gate_approved` ou `rework`). Il manque un mode « une décision machine après un tour d’agent » pour router vers des états différents (ex. findings → correction, sinon validation humaine).

## Goals / Non-Goals

**Goals:**

- Nouveau `type: agent-gate` : un tour de runner (même stack que `agent` : Claude / Codex / Mux, hooks, prompts).
- Après succès du processus, choisir **exactement une** transition déclarée dans `transitions:` (clés autres que `complete` — pas de collision sémantique avec `agent`).
- Contrat de sortie stable, parsable de façon déterministe depuis `full_output` (comme le work report existant).
- Validation YAML : toutes les cibles existent ; en cas de parse KO : commentaire Linear explicite + transition vers un **gate** humain (via `default_transition`).

**Non-Goals:**

- Plusieurs tours dans le même état `agent-gate` sans re-dispatch (reste « un tour par dispatch » comme pour `agent` en mode state machine).
- Remplacer les gates humains ou les fusionner avec `agent-gate`.
- UI web dédiée au-delà de l’exposition déjà existante de l’état courant.

## Decisions

### 1. Format de la décision dans la sortie agent

**Choix :** deux livrables distincts dans la sortie texte du runner :

1. **Routage machine** — bloc JSON délimité par marqueurs uniques, par exemple :

```text
<<<STOKOWSKI_ROUTE>>>
{"transition": "<nom_de_transition>"}
<<<END_STOKOWSKI_ROUTE>>>
```

2. **Rapport explicatif pour Linear** — le même mécanisme que les états `agent` : contenu entre **`<stokowski:report>...</stokowski:report>`** (déjà supporté par `extract_report` / `format_report_comment`). Ce rapport est **posté en commentaire sur le ticket** pour expliquer au lecteur **pourquoi** cette branche a été choisie (findings, absence de problème, synthèse de la review, etc.). Le prompt `agent-gate` **doit** exiger ce bloc en plus du bloc de routage.

**Orchestration du commentaire :** après résolution de la transition (succès parse), Stokowski extrait le rapport et publie le commentaire Linear (même pipeline que les work reports, éventuellement enrichi en métadonnées pour indiquer le nom de la transition retenue et le fait qu’il s’agit d’un `agent-gate`).

**Pourquoi :** le routage reste parsable de façon déterministe ; le commentaire garde une trace lisible pour l’humain au prochain gate, sans mélanger JSON de contrôle et prose dans un seul bloc.

**Alternatives :** tout mettre dans le JSON de routage (`report` multiligne échappé) — fragile pour les LLM ; fichier dans le workspace — hors stdout et plus difficile à auditer sur Linear.

### 2. Schéma YAML

**Choix :** même surface qu’un état `agent` pour l’exécution (`prompt`, `linear_state`, `runner`, overrides optionnels), avec :

- `type: agent-gate`
- `transitions:` : dictionnaire **nom → état cible** (ex. `has_findings: correct-review`, `clean: human-validation`). Pas de clé obligatoire `complete`.
- `default_transition:` (string) — **obligatoire** : clé présente dans `transitions` ; sa cible **doit** être un état `type: gate` (validation humaine). Utilisée si le bloc de routage est absent, le JSON est invalide, ou si `transition` ne correspond à aucune clé de `transitions`.

**Pourquoi :** toute défaillance de routage automatique est visible sur le ticket et délègue explicitement à un humain au lieu d’un fallback silencieux vers un autre état agent.

**Alternative rejetée :** fallback silencieux vers un état non-gate — masque les erreurs de format et contourne la revue humaine attendue.

### 3. Orchestration

**Choix :** dans le chemin succès post–`run_turn`, si `state_cfg.type == "agent-gate"` :

1. Parser `attempt.full_output` pour obtenir `transition`.
2. Si parse OK et la clé est dans `state_cfg.transitions` → `chosen_key = transition`.
3. Sinon → `chosen_key = default_transition` **et** poster sur Linear un commentaire lisible qui indique la **catégorie** d’erreur (enveloppe absente, JSON invalide, clé inconnue, etc.) et, si utile, un extrait court ou le message d’erreur technique (sans fuite de secrets ; tronquer si nécessaire).
4. Extraire `<stokowski:report>...</stokowski:report>` lorsque `chosen_key` a été résolu sans erreur de parse machine (étape 2) ; **poster ce rapport** sur le ticket (explication du choix de branche). Si le rapport est absent malgré un routage réussi, réutiliser le comportement « no report » existant ou un commentaire minimal indiquant l’absence de rapport et la transition choisie — à trancher en implémentation en restant cohérent avec les états `agent`.
5. Appeler `_safe_transition(issue, chosen_key)` au lieu de `"complete"`.

**Ordre et `_post_work_report` :** aujourd’hui `_on_worker_exit` déclenche déjà `_post_work_report` pour tout run réussi avec `full_output`. Pour `agent-gate`, il faut **éviter un double commentaire** : soit adapter le chemin existant pour cet état (un seul commentaire = rapport `<stokowski:report>` + métadonnées de transition / type `agent-gate`), soit court-circuiter le post générique quand `type == agent-gate` et centraliser publication du rapport et de la route dans la branche dédiée.

Les incohérences de config (ex. `default_transition` ne pointe pas vers un `gate`) sont rejetées à la validation YAML, pas au runtime.

### 4. Prompt / lifecycle

**Choix :** étendre la section lifecycle (ou équivalent dans `assemble_prompt`) pour les états `agent-gate` : lister les transitions disponibles + rappeler le format `<<<STOKOWSKI_ROUTE>>>` **et** l’obligation du bloc `<stokowski:report>` pour documenter le choix dans les commentaires du ticket.

### 5. Compatibilité

**Choix :** `validate_config` rejette `type: agent-gate` sans `default_transition` ou sans au moins une entrée dans `transitions` ; rejette aussi si la cible de `default_transition` n’est pas `type: gate`. Les champs `rework_to` / `max_rework` sont interdits sur `agent-gate` (réservés aux `gate`).

## Risks / Trade-offs

| Risque | Mitigation |
|--------|------------|
| L’agent oublie le bloc | Commentaire + gate humain ; prompt explicite + exemple dans `workflow.example.yaml` |
| Collusion de noms avec futures extensions | Préfixe `STOKOWSKI_ROUTE` dédié |
| Commentaire trop verbeux ou sensible | Tronquer l’extrait ; ne pas coller de secrets depuis l’output |

## Migration Plan

- Déploiement : uniquement pour les workflows qui ajoutent explicitement `agent-gate`.
- Rollback : retirer l’état `agent-gate` du YAML et revenir à un enchaînement `agent` → `gate` humain.

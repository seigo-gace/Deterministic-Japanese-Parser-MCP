# Dictionaries

`system/` contains the versioned defaults distributed by the project. `user/` contains local overrides and starts empty.

```text
dictionaries/
├── system/
│   ├── metaphors/
│   │   ├── 01_operations_security.json
│   │   ├── 02_development_change.json
│   │   ├── 03_quality_validation.json
│   │   ├── 04_project_execution.json
│   │   ├── 05_scope_governance.json
│   │   ├── 06_risk_decision.json
│   │   ├── 07_analysis_problem_solving.json
│   │   ├── 08_communication_organization.json
│   │   ├── 09_system_information.json
│   │   ├── 10_process_workflow.json
│   │   ├── 11_control_reversibility.json
│   │   ├── 12_general.json
│   │   └── manifest.json
│   ├── rules/                  # one YAML file per intent type
│   ├── synonyms.yaml
│   └── task_templates.yaml
└── user/
    ├── metaphor.json
    ├── rules.yaml
    ├── synonyms.yaml
    └── task_templates.yaml
```

## Rules

- System entries are project-authored and versioned.
- Generated proposals never merge automatically.
- A metaphor surface or alias may belong to only one canonical entry.
- Every new expression needs an interpretation, context, domain, version, and Gold Corpus case.
- Run `python tools/validator.py` and `pytest` after every change.

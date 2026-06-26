# Worklog

## 2026-06-26 22:05 – composer – Entra-Credentials vereinheitlichen (MS_APP_*)

- Done:
  - `MS_APP_TENANT_ID`, `MS_APP_CLIENT_ID`, `MS_APP_CLIENT_SECRET` als einziger Credential-Satz eingeführt
  - `BOT_*`/`GRAPH_*`-Credential-Variablen und Graph-zu-Bot-Fallback entfernt
  - Backend-Services, Admin-Readiness, Frontend-Labels und Tests angepasst
  - `.env.example`, README und `docs/graph-autocomplete-spike.md` aktualisiert
- Next:
  - Lokale `.env` auf neue Variablennamen prüfen (nicht committen)
- Blockers:
  - none
- Branch/PR:
  - branch: none
  - PR: none
- Files touched:
  - backend/app/core/config.py
  - backend/app/services/teams_bot.py
  - backend/app/services/graph_targets.py
  - backend/app/routers/admin.py
  - backend/tests/test_admin_readiness_api.py
  - backend/tests/test_graph_targets.py
  - backend/tests/test_teams_targets_api.py
  - frontend/src/App.tsx
  - frontend/src/types.ts
  - .env.example
  - README.md
  - docs/graph-autocomplete-spike.md
  - docs/CHANGELOG.md
- Test notes:
  - commands: `python3 -m py_compile`, `pytest`, `npm run build`
  - endpoints: `/api/v1/admin/readiness`
  - UI path: Settings > Readiness
  - Changelog updated: yes (Changed)
- Follow-ups:
  - none

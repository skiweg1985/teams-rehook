# Feature Ideas Backlog

Kurzliste fuer moegliche Weiterentwicklungen von Teams Rehook.

## High-interest ideas

1. **Observability Dashboard**
   Live-Status fuer Deliveries, OAuth health, retries, latency, failed targets und readiness trends.

2. **AI Message Rewriter**
   Webhook-Payloads automatisch in kurze, lesbare Teams-Nachrichten fuer Ops, Management oder Customer-safe Updates umformulieren.

3. **Inbound-to-Workflow Loop**
   Replies und Aktionen aus Teams zurueck ins System holen, z. B. Ack, Retry, Escalate oder Close.

## Additional product ideas

4. **Action Buttons with real workflow effects**
   Direkt in Teams: Acknowledge, Assign, Retry, Escalate, Open ticket.

5. **Message Enrichment**
   Alerts automatisch mit Runbook, Dashboard-Link, Owner, Service-Status oder Logs anreichern.

6. **Noise Collapse / Alert Grouping**
   Mehrere aehnliche Events zu einer intelligenten Sammelmeldung verdichten.

7. **Digest Mode**
   Low-priority Signale in 5-min oder 15-min Batches senden statt sofort.

8. **Audience-aware formatting**
   Dieselbe Nachricht automatisch unterschiedlich fuer Ops, Mgmt oder Customer-Success darstellen.

9. **Incident Timeline / Causality View**
   Einzelne Events zu einer Incident-Story oder Timeline zusammenbauen.

10. **Delivery Simulation Mode**
    Vor Go-live testen, wo eine Nachricht landen wuerde und wie sie aussehen wuerde.

11. **Two-way Sync with ticketing systems**
    Teams-Aktionen aktualisieren Jira, Linear oder andere Ticketsysteme und umgekehrt.

12. **Escalation by Silence**
    Wenn niemand reagiert, nach X Minuten automatisch DM, anderer Channel oder weiterer Empfaenger.

13. **Operator Inbox**
    Zentrale Queue fuer fehlgeschlagene, unsichere oder freizugebende Deliveries.

14. **Semantic Dedup**
    Inhaltlich aehnliche Meldungen erkennen, nicht nur identische IDs oder Payloads.

15. **LLM-powered Intent Routing**
    Unstrukturierte Webhooks automatisch dem richtigen Ziel, Template oder Workflow zuordnen.

## Notes

- Dieses Dokument ist bewusst leichtgewichtig und fuer fruehe Produktideen gedacht.
- Reife Kandidaten sollten spaeter als eigene GitHub Issues mit Scope, Nutzen und offenen Fragen uebernommen werden.

# Feature Ideas Backlog

This is a lightweight backlog for possible Teams Rehook improvements. Items here are ideas, not committed roadmap items.

## High-Interest Ideas

1. **Observability Dashboard**
   Live status for deliveries, OAuth health, retries, latency, failed targets, and readiness trends.

2. **AI Message Rewriter**
   Transform webhook payloads into short, readable Teams messages for operations, management, or customer-safe updates.

3. **Inbound-to-Workflow Loop**
   Bring replies or actions from Teams back into source workflows, for example acknowledge, retry, escalate, or close.

## Additional Product Ideas

4. **Action Buttons With Workflow Effects**
   Direct Teams actions such as acknowledge, assign, retry, escalate, or open ticket.

5. **Message Enrichment**
   Add runbook links, dashboard links, owner information, service status, or logs to incoming alerts.

6. **Noise Collapse / Alert Grouping**
   Collapse similar events into one grouped notification.

7. **Digest Mode**
   Send low-priority signals in 5-minute or 15-minute batches instead of immediately.

8. **Audience-Aware Formatting**
   Render the same event differently for operations, management, or customer success audiences.

9. **Incident Timeline / Causality View**
   Combine related events into an incident story or timeline.

10. **Delivery Simulation Mode**
    Preview where a message would land and how it would look before go-live.

11. **Two-Way Sync With Ticketing Systems**
    Sync Teams actions with Jira, Linear, or similar ticketing tools.

12. **Escalation By Silence**
    Escalate to another user, chat, or channel when nobody reacts within a configured time window.

13. **Operator Inbox**
    Central queue for failed, uncertain, or approval-gated deliveries.

14. **Semantic Deduplication**
    Detect semantically similar messages, not only identical payloads or IDs.

15. **LLM-Powered Intent Routing**
    Route unstructured webhooks to the right Teams target, template, or workflow.

## Notes

- Mature candidates should become scoped issues with value, constraints, risks, and acceptance criteria.
- Do not document ideas from this file as available features until code or tests support them.

# PRD: Teams Rehook

## 1. Kontext / Problem

Bestehende Microsoft Teams Incoming Webhooks bzw. Office 365 Connector-Webhooks sind kein verlaesslicher langfristiger Integrationsweg fuer betriebliche Benachrichtigungen. Gleichzeitig sind Teams Workflows bzw. Power Automate fuer diesen Zweck nur bedingt geeignet, weil sie haeufig an Benutzer, Owner oder benutzernahe Identitaeten gekoppelt sind.

Teams Rehook adressiert dieses Problem als servicefaehiger Relay-Ansatz: Quellsysteme senden an stabile Relay-URLs, waehrend Teams-Ziele zentral im Relay verwaltet werden.

Aktuell relevante Quellsysteme sind unter anderem:

- macmon
- Firewalls
- PRTG
- weitere Monitoring- oder Operations-Systeme

## 2. Produktziel

Teams Rehook soll ein zentraler, intern betriebener Teams Webhook Relay Service werden. Der Dienst nimmt Webhook-Requests entgegen, normalisiert Payloads und sendet daraus Teams-Nachrichten ueber Bot Framework oder eine konfigurierte Microsoft-Graph-Delivery.

Das Produktziel ist:

- zentrale Annahme von Webhook-Requests
- stabile Relay-URLs fuer Quellsysteme
- zentrale Verwaltung von Webhook-zu-Teams-Ziel-Mappings
- servicefaehiger Betrieb ohne personengebundene Zielarchitektur
- nachvollziehbares Logging von Annahme, Routing und Zustellung
- sichere URL-Rotation fuer Relay-Ziele
- klare Operations-Oberflaeche fuer Setup, Tests, Readiness und Fehleranalyse

## 3. Aktueller Status

Teams Rehook ist ein implementierter MVP im Evaluation-Status. Der Kernflow ist vorhanden:

`source webhook -> relay URL -> route -> configured Teams target -> delivery test/logs`

Bereits umgesetzt:

- FastAPI-Backend mit SQLAlchemy, Sessions, CSRF-Schutz und Bootstrap-Admin
- Docker-Compose-Stack mit Postgres, Backend, Frontend und HAProxy
- authentifizierte Admin-Oberflaeche mit Dashboard, Webhooks, Messages, Users, Settings und System logs
- stabile Relay-URLs pro Webhook-Route
- URL-Regeneration mit sofortiger Invalidierung alter URLs
- Aktiv-/Inaktiv-Status pro Route
- Payload Generator fuer Text- und Adaptive-Card-Beispielpayloads
- Bot-Conversation-Capture aus eingehenden Teams Bot Activities
- Teams-Bot-Slash-Commands fuer Registrierung, URL-Abfrage, Aktivierung, Deaktivierung, Loeschung und Info
- Auswahl bekannter Teams-Bot-Unterhaltungen beim Anlegen einer Route
- manuelle Fallback-Felder fuer Bot service URL und conversation ID
- Microsoft-Graph-Suche und Namensauflösung fuer Teams-Ziele, sofern konfiguriert
- Graph-Delivery ueber eine delegierte Service-User-Verbindung fuer geeignete Graph-Ziele
- Mock-Delivery-Modus fuer lokale Validierung
- Real-Delivery-Modus ueber Bot Framework Credentials oder Graph-Delivery-Konfiguration je Route
- Delivery Logs mit normalisiertem Payload, Request-Metadaten, Zustellantwort und Fehlern
- Log-Retention und manuelle Cleanup-Funktion
- Settings-/Readiness-Ansicht fuer nicht geheime Betriebs-, Credential-, Token- und Integrationszustaende

## 4. Zielgruppen

- Administratoren, die Relay-Routen und Teams-Ziele verwalten
- Betriebsteams, die Webhook-Zustellungen pruefen und Fehler analysieren
- Projektverantwortliche, die die Eignung als Standardweg fuer Teams-Benachrichtigungen bewerten

## 5. Funktionale Anforderungen

Teams Rehook muss folgende Funktionen bereitstellen:

- eingehende Webhook-Requests ueber route-spezifische URLs annehmen
- unbekannte, deaktivierte, leere, ungueltige oder zu grosse Requests kontrolliert ablehnen
- Payloads aus Text, JSON-Objekten, JSON-Arrays und Adaptive-Card-Aktivitaeten annehmen
- Payloads auf ein internes Nachrichtenformat normalisieren
- Webhook-Routen mit Name, Delivery Backend, Aktivstatus, Teams-Ziel und Relay-URL verwalten
- Relay-URLs generieren, kopieren und rotieren
- Teams Bot Conversations aus eingehenden Bot Activities erfassen
- bekannte Conversations als Route-Ziel auswählbar machen
- manuelle Zielkonfiguration erlauben, wenn eine gueltige Bot Framework Conversation Reference bereits bekannt ist
- Graph-Zielsuche und Graph-Namensauflösung verwenden, wenn Graph-Credentials verfuegbar sind
- klar vermitteln, dass ein Graph-Ziel nur sendbar ist, wenn der passende Bot- oder Graph-Delivery-Kontext bereit ist
- Payload-Beispiele fuer einfache Textnachrichten und Adaptive-Card-Aktivitaeten erzeugen
- Teams-Bot-Commands fuer route-nahe Administration aus einem installierten Teams-Kontext bereitstellen
- Testnachrichten pro Route senden
- Zustellungen, Fehler und abgelehnte Requests nachvollziehbar loggen
- Dashboard-Signale fuer fehlgeschlagene, abgelehnte, inaktive und ungetestete Routen anzeigen
- Readiness fuer Bot, Graph Lookup, Graph Delivery, OAuth-Tokenabruf, Delivery Mode, Runtime-URLs, Payload-Limit und Log-Retention anzeigen
- API-Key-geschuetzten JSON-Monitoring-Status fuer externe Polling-Systeme bereitstellen
- Rolling Delivery Windows fuer `5m`, `15m` und `1h` bereitstellen

## 6. Nicht-funktionale Anforderungen

- Bot-Credentials, Client Secrets, Route Tokens und Conversation IDs duerfen nicht unnoetig im UI oder in Logs offengelegt werden.
- Readiness-Ausgaben duerfen nur Konfigurations- und Health-Zustaende, keine Secret-Werte, Tokens, Header oder rohen Auth-Antworten enthalten.
- Monitoring-Ausgaben duerfen keine Relay-URLs, Route Tokens, Bot Service URLs, Conversation IDs, OAuth-Tokens, Secrets oder rohen Auth-Antworten enthalten.
- Session-aendernde und administrative Requests muessen gegen CSRF geschuetzt bleiben.
- Der Mock-Modus muss lokale Tests ohne echte Teams-Zustellung erlauben.
- Der Real-Modus muss fehlende Bot-Credentials eindeutig als nicht bereit anzeigen.
- Logs muessen zeitlich begrenzt aufbewahrt und bereinigbar sein.
- Die UI muss fuer wiederholte Operator-Aufgaben schnell scanbar, ruhig und handlungsorientiert bleiben.
- Bestehende Quellsysteme sollen moeglichst nur ihre Ziel-URL aendern muessen.

## 7. Architektur

Teams Rehook folgt einem pragmatischen Relay-Ansatz:

1. Ein Quellsystem sendet einen Webhook-Request an eine Relay-URL.
2. Das Backend findet die Route ueber den geheimen Route Token Hash.
3. Route, Aktivstatus und Payload werden validiert.
4. Der Payload wird normalisiert.
5. Im Mock-Modus wird die Zustellung simuliert.
6. Im Real-Modus sendet das konfigurierte Delivery Backend ueber Bot Framework an die gespeicherte Conversation oder ueber Microsoft Graph an das gespeicherte Graph-Ziel.
7. Das Ergebnis wird als Delivery Event gespeichert.

Microsoft Graph ist fuer Suche und Namensauflösung sowie fuer Graph-Delivery-Routen relevant. Graph-Suchergebnisse beweisen noch keine Sendeberechtigung; deshalb muss jede Route mit **Send test** validiert werden.

Der V1-Monitoring-Endpunkt ist JSON/status-orientiert und fuer externe Polling-Systeme per API Key geschuetzt. Prometheus/OpenMetrics-Ausgabe bleibt ein spaeterer Follow-up.

## 8. Akzeptanzkriterien fuer den aktuellen MVP

Der MVP ist fuer die weitere Evaluation geeignet, wenn:

- die Anwendung lokal per Docker Compose startet,
- ein Admin sich anmelden und Routen verwalten kann,
- mindestens eine Teams Bot Conversation erfasst oder manuell hinterlegt werden kann,
- eine Webhook-Route erstellt und getestet werden kann,
- eine reale oder simulierte Zustellung nachvollziehbar geloggt wird,
- abgelehnte und fehlgeschlagene Requests mit Fehlerursache sichtbar sind,
- Relay-URLs kopiert und rotiert werden koennen,
- Dashboard und Empty States Operatoren zum naechsten sinnvollen Schritt fuehren,
- Settings die Readiness fuer Bot, Graph, Tokenabruf und Runtime-Konfiguration ohne Secrets anzeigt,
- ein Monitoring-System Delivery-Degradation ueber einen stabilen JSON-Endpunkt ohne UI-Scraping erkennen kann,
- README und PRD den aktuellen Produktstand konsistent beschreiben.

## 9. Bekannte Limitierungen

- Der MVP ersetzt noch keine vollstaendige produktive Betriebsplattform.
- Hochverfuegbarkeit, Backup/Restore, Monitoring, Alerting und SLOs sind noch separat festzulegen.
- Mandanten-/Organisationsmodell ist minimal und fuer die Evaluation ausgelegt.
- Die Users-Ansicht listet vorhandene Benutzer; Einladung, Anlage und Bearbeitung von Benutzern sind im aktuellen UI nicht umgesetzt.
- Graph-Berechtigungen und Admin Consent muessen tenant-spezifisch geklaert werden.
- Ein Graph-Suchergebnis ist keine Garantie fuer Bot-Sendeberechtigung.
- Der Bot muss im Zielkontext installiert sein und mindestens eine gueltige Conversation Reference liefern.
- Nicht alle historischen Incoming-Webhook-Payloads sind garantiert 1:1 abbildbar.
- Secret-Rotation, Betriebshandbuch und Ownership muessen vor Produktivbetrieb finalisiert werden.

## 10. Offene Produktfragen

- Welche Quellsysteme werden zuerst migriert?
- Welche Teams-Kontexte duerfen als Ziel genutzt werden?
- Welche Graph-Permissions werden organisatorisch akzeptiert?
- Welche Retention- und Audit-Anforderungen gelten produktiv?
- Welche Betriebsverantwortung uebernimmt Teams Rehook nach der Evaluation?
- Wird ein Queue-/Retry-Modell fuer temporaere Teams- oder Bot-Framework-Fehler benoetigt?

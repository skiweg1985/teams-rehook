# PRD: Teams Webhook Relay Service

## 1. Kontext / Problem

Bestehende Microsoft Teams Incoming Webhooks bzw. Office 365 Connector-Webhooks sind nicht mehr zuverlässig als langfristiger Integrationsweg nutzbar. Dadurch entsteht ein Risiko für bestehende webhook-basierte Benachrichtigungen, die heute in Teams-Kanäle zugestellt werden.

Aktuell bekannte betroffene Quellen sind unter anderem:

- macmon
- Firewalls
- PRTG

Weitere bestehende Nutzungen sind noch nicht vollständig inventarisiert. Die offizielle Alternative über Teams Workflows bzw. Power Automate ist für den Einsatzzweck nur bedingt geeignet, weil sie stark an Benutzer, Owner oder benutzernahe Identitäten gekoppelt ist. Für betriebliche Benachrichtigungen wird dagegen ein servicefähiger, nicht personenbezogen abhängiger Ansatz benötigt.

## 2. Zielbild

Ziel ist ein zentraler Teams Webhook Relay Service, der eingehende Webhook-Requests aus internen oder quellseitigen Systemen entgegennimmt und an eine geeignete Teams-Zielintegration weiterleitet.

Für den Prototyp wird vorrangig die vorhandene Teams App mit Bot als Zielintegration evaluiert. Der Bot wurde ursprünglich als Chatbot konzipiert, kann aber technisch als servicefähiger Sender für Benachrichtigungen genutzt werden, sofern er in die relevanten Teams-Kontexte schreiben darf.

Der Relay Service soll perspektivisch einen einheitlichen technischen Ansatz für Teams-Benachrichtigungen schaffen:

- zentrale Annahme von Webhook-Requests
- konfigurierbares Routing eingehender Webhook-URLs zu definierten Teams-Zielkanälen
- Verwaltung des Webhook-zu-Zielkanal-Mappings im Relay Service statt in den Quellsystemen
- servicefähiger Betrieb ohne personengebundene Ownership als Zielarchitektur
- einheitliche Stelle für Logging, Fehlerbehandlung und spätere Erweiterungen

## 3. Ziele

- Technische Machbarkeit eines zentralen Relay Service prüfen.
- Eignung als möglicher Standardweg zur Ablösung bestehender Teams-Webhooks bewerten.
- Personenbezogene Abhängigkeiten bei Teams-Benachrichtigungen reduzieren.
- Routing, Logging und Fehlerbehandlung für Teams-Benachrichtigungen zentralisieren.
- Aufwand für die Umstellung bestehender Quellen exemplarisch bewerten.
- Bestehende Webhook-Aufrufer möglichst ohne fachliche Anpassung weiterbetreiben, indem primär die Ziel-URL auf den Relay Service geändert wird.
- Fachliche Zieländerungen zentral im Relay Service ermöglichen, ohne bestehende Quellsysteme anpassen zu müssen.
- Vorhandene Teams App/Bot-Integration als primären Versandweg für den Prototyp bewerten.

## 4. Nicht-Ziele

- Keine vollständige Produktivlösung im ersten Schritt.
- Keine vollständige Ablösung aller bestehenden Quellen im Prototyp.
- Keine finale Festlegung auf die endgültige Teams-Zieltechnik, sofern diese im Prototyp erst evaluiert wird.
- Kein vollständiges Enterprise-Hardening im ersten Schritt.
- Keine vollständige Inventarisierung aller bestehenden Webhook-Nutzungen als Bestandteil des Prototyps.
- Keine Neuentwicklung einer separaten Teams App, solange der vorhandene Bot für den Prototyp ausreichend nutzbar ist.

## 5. Funktionale Anforderungen

Der Prototyp soll mindestens folgende Funktionen abdecken:

- HTTP-Endpoint zur Annahme eingehender Webhook-Requests.
- Unterstützung mehrerer eingehender Webhook-URLs oder Webhook-Identitäten.
- Kompatibilitätsmodus für bestehende Incoming-Webhook-Requests, damit vorhandene Payload-Strukturen aus Bestandsanwendungen weiter angenommen werden können.
- Einfache Authentisierung oder Zugriffsbeschränkung für Testquellen, soweit für den Prototyp erforderlich.
- Konfigurierbares Routing von eingehenden Requests zu definierten Teams-Zielkanälen.
- UI zur Verwaltung des Mappings von eingehendem Webhook zu Teams-Zielkanal.
- Anzeige und Bearbeitung einfacher Webhook-Routen im UI, z. B. Name, Quellsystem, Relay-URL, Teams-Ziel, Aktivstatus und Zieltyp.
- Hinterlegung eines Teams-Bot-Ziels je Route, mindestens mit sprechendem Zielnamen und technischer Zielreferenz.
- Autocomplete-Suche für Teams-Ziele im UI, damit Administratoren Teams, Kanäle oder Benutzer über Microsoft Graph suchen und auswählen können, statt technische IDs manuell einzutragen.
- Speicherung der ausgewählten Zielreferenz mit Anzeigename und technischen Identifikatoren, z. B. Team-ID, Channel-ID oder User-ID.
- Möglichkeit, eine konfigurierte Zielroute per Testnachricht zu validieren.
- Unterstützung einfacher Nachrichtentypen, z. B. Textnachricht mit Quelle, Titel, Status und Detailtext.
- Normalisierung unterschiedlicher Quellpayloads auf ein internes Nachrichtenformat, ohne dass Bestandsquellen im ersten Schritt zwingend ihre Request-Struktur ändern müssen.
- Versand normalisierter Nachrichten als Bot-Framework-Activity über den vorhandenen Teams Bot.
- Nachvollziehbares Logging von Annahme, Routing-Entscheidung, Zustellversuch und Ergebnis.
- Fehlerbehandlung bei ungültigen Requests, unbekannten Routen und Zustellfehlern zur Teams-Zielintegration.
- Einfache Konfigurierbarkeit für Testquellen wie macmon, Firewall-Events oder PRTG.

## 6. Nicht-funktionale Anforderungen

- Einfacher und wartbarer Betrieb des Prototyps.
- Servicefähige technische Identität als Zielarchitektur.
- Keine Bindung der Zielarchitektur an einen persönlichen Benutzeraccount.
- Bot-Credentials und Secrets dürfen nicht im UI oder in versionierten Konfigurationsdateien gespeichert werden.
- OAuth-Zugriffstoken für den Bot Framework Connector müssen serverseitig verwaltet und bis kurz vor Ablauf wiederverwendet werden.
- Access Tokens, Client Secrets und vergleichbare sensible Werte dürfen nicht im Frontend, in Logs oder in fachlichen Routing-Daten erscheinen.
- Nachvollziehbare Konfiguration der Testquellen und Zielrouten.
- UI-Änderungen am Routing müssen für den Testbetrieb nachvollziehbar bleiben.
- Geringer Betriebsaufwand für Aufbau, Test und Anpassung des Prototyps.
- Ausreichende Transparenz für Fehlersuche im Testbetrieb.
- Keine unnötige Komplexität bei Persistenz, Queueing oder Mandantentrennung, solange diese für die Machbarkeitsbewertung nicht erforderlich ist.

## 7. Architekturidee / Lösungsansatz

Der Prototyp folgt einem pragmatischen Relay-Ansatz:

1. Quellsysteme senden Webhook-Requests an einen HTTP-Endpoint des Relay Service.
2. Das Relay ermittelt anhand der Webhook-URL oder Webhook-Identität die konfigurierte Zielroute.
3. Das Relay validiert Request, Route und Payload.
4. Das Relay erkennt bekannte Bestandsformate und normalisiert den Payload auf ein internes Nachrichtenformat.
5. Das Relay holt mit den Bot-Credentials ein Zugriffstoken für den Bot Framework Connector.
6. Das Relay sendet die Nachricht als Bot-Framework-Activity an die im Relay konfigurierte Teams-Zielreferenz.
7. Das Relay protokolliert Annahme, Routing, Zustellstatus und Fehler.

Für den Prototyp kann die Teams-Zielreferenz zunächst technisch hinterlegt werden, z. B. als Bot-Framework-Service-URL und Conversation-ID aus einer bereits bekannten Bot-Konversation. Perspektivisch soll die Zielerfassung im UI verständlicher werden, damit Administratoren fachliche Zielnamen verwalten können und technische Zielwerte nicht frei zusammensuchen müssen.

Der initiale Zieladapter ist ein Teams-Bot-Adapter:

- Er verwendet die vorhandene App-/Bot-Registrierung.
- Er authentisiert sich mit Client Credentials gegen den Bot Framework Connector.
- Er verwaltet Zugriffstoken serverseitig, cached gültige Tokens und erneuert sie erst bei Ablauf oder kurz davor.
- Er sendet einfache Text- oder Card-Activities an eine konfigurierte Conversation.
- Er kapselt Bot-spezifische Details, damit das Relay intern weiterhin mit einem normalisierten Nachrichtenformat arbeiten kann.

Für die Zielauswahl im UI soll zusätzlich Microsoft Graph als Such- und Verzeichnisintegration genutzt werden. Graph dient dabei zur Suche nach Teams, Kanälen und Benutzern; der eigentliche Nachrichtenversand erfolgt im Prototyp weiterhin über den Teams-Bot-Adapter. Da ein gefundenes Graph-Ziel nicht automatisch bedeutet, dass der Bot dort senden darf, muss die Route nach der Auswahl per Testnachricht validiert werden.

Die Verwaltung der Routen erfolgt im UI des Relay Service. Quellsysteme kennen nur ihre jeweilige Relay-Webhook-URL; die Zuordnung zu Teams-Zielkanälen wird zentral im Relay gepflegt.

Die vorhandene Teams App mit Bot ist der bevorzugte Prototyp-Pfad. Graph-basierte Integration oder andere Microsoft-365-Integrationswege bleiben Vergleichs- oder Fallback-Optionen, falls der Bot-Weg technische oder organisatorische Grenzen zeigt.

## 8. Bewertungsfragen für den Prototyp

- Ist ein zentraler Relay Service technisch praktikabel?
- Lässt sich eine Teams-Integration ohne problematische Personenabhängigkeit sinnvoll anbinden?
- Kann der vorhandene Teams Bot als servicefähiger Sender für Relay-Benachrichtigungen genutzt werden?
- Kann der Bot zuverlässig in die relevanten Zielkanäle schreiben?
- Wie wird der technische Absender in Teams dargestellt und ist diese Darstellung akzeptabel?
- Wie hoch ist der Umstellungsaufwand für bestehende Quellen wie macmon, Firewalls und PRTG?
- Können bestehende Webhook-Requests mit reiner URL-Umstellung weiterverwendet werden?
- Ist die Verwaltung des Webhook-zu-Zielkanal-Mappings im UI ausreichend einfach und nachvollziehbar?
- Ist eine Graph-basierte Autocomplete-Suche nach Teams, Kanälen und Benutzern mit vertretbaren Berechtigungen umsetzbar?
- Lässt sich nach Auswahl eines Graph-Ziels zuverlässig validieren, ob der Bot dort tatsächlich senden kann?
- Welche Payload-Unterschiede der Quellen müssen bereits im Prototyp berücksichtigt werden?
- Welche offenen Punkte und Risiken bleiben für einen späteren Produktivbetrieb?

## 9. Akzeptanzkriterien für den Prototyp

Der Prototyp gilt als erfolgreich evaluiert, wenn:

- ein lauffähiger Relay-Service erstellt wurde,
- mindestens ein Beispiel-Webhook im bestehenden Request-Format entgegengenommen werden konnte,
- mindestens eine Nachricht erfolgreich an Teams weitergeleitet wurde,
- die Weiterleitung im Prototyp über den vorhandenen Teams Bot getestet wurde,
- für die getestete Quelle nur die Webhook-Ziel-URL angepasst werden musste,
- mindestens eine Webhook-Route im UI angelegt oder geändert und für die Zustellung genutzt werden konnte,
- mindestens ein Teams-Ziel im UI gesucht, ausgewählt und per Testnachricht validiert werden konnte,
- Annahme, Routing und Zustellergebnis nachvollziehbar geloggt wurden,
- fehlerhafte Requests oder Zustellfehler kontrolliert behandelt wurden,
- offene Punkte und Risiken dokumentiert wurden,
- eine Einschätzung zur Eignung als servicefähige Standardlösung vorliegt.

## 10. Bekannte Risiken / offene Punkte

- Teams-seitige Authentisierung, App-, Bot- oder Graph-Berechtigungen sind noch zu klären.
- Der vorhandene Bot wurde ursprünglich für einen anderen Zweck gebaut; seine Eignung als Benachrichtigungssender muss validiert werden.
- Für Kanalzustellung müssen geeignete Conversation-Referenzen bzw. Zieladressen verfügbar sein.
- Graph-Suche und Bot-Versand haben unterschiedliche Berechtigungs- und Zugriffsvoraussetzungen; ein gefundenes Ziel ist nicht automatisch ein erreichbares Sendeziel.
- Tenantweite Suche nach Teams, Kanälen oder Benutzern kann zusätzliche Microsoft-Graph-Berechtigungen und Admin Consent erfordern.
- Fehler im Token-Lifecycle oder Secret Handling können zu Zustellfehlern oder Sicherheitsrisiken führen.
- Die Darstellung des technischen Absenders in Teams kann fachlich oder organisatorisch relevant sein.
- Unterschiedliche Quellpayloads können Mapping- und Normalisierungsaufwand verursachen.
- Nicht alle bisherigen Incoming-Webhook-Payloads lassen sich möglicherweise 1:1 in die neue Teams-Zielintegration übertragen.
- Bereits sichtbare oder geteilte Bot-Secrets müssen rotiert und künftig sicher verwaltet werden.
- Governance, Betrieb, Ownership und Verantwortlichkeiten für den Relay Service sind noch festzulegen.
- Die Inventarisierung bestehender Webhook-Nutzungen ist noch unvollständig.
- Microsoft-365- und Teams-Plattformänderungen können die gewählte Zielintegration beeinflussen.
- Anforderungen an Monitoring, Alerting, Skalierung und Hochverfügbarkeit sind für eine Produktivlösung separat zu bewerten.

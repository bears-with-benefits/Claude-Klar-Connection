# Klar Channel-Data Connector

Ein kleiner MCP-Server, der die Klar-API (getklar.com) für Claude als
**Custom Connector** nutzbar macht — nötig, weil Claudes Cloud-Sandbox
(Chats und geplante Aufgaben) nur eine feste, kleine Liste von Domains
direkt erreichen kann (z.B. npm, pypi) und api.getklar.com nicht dazugehört.
Diese Einschränkung lässt sich nicht per Admin-Einstellung aufheben — daher
dieser Umweg über einen eigenen, dauerhaft laufenden Server.

Sobald dieser Server läuft und als Custom Connector registriert ist, läuft
der Aufruf über Anthropics eigene Connector-Infrastruktur statt über die
blockierte Sandbox — das funktioniert dann auch aus einer geplanten
täglichen Aufgabe heraus, unabhängig davon ob ein Laptop an oder aus ist.

## Was der Server macht

Ein Tool: `get_channel_attribution(start_date, end_date, metric, window)` —
ruft `GET /public/attribution` bei Klar auf und liefert pro Kanal und Tag:
`channelName`, `orders`, `netRevenue`, `grossRevenue`, `cost`, `clicks`,
`impressions`.

Der Slack-Post selbst läuft NICHT über diesen Server, sondern über den
bereits bei Havea installierten offiziellen Slack-Connector — dieser Server
kümmert sich nur um Klar.

## Vor dem Deployen — wichtig

1. **API-Key rotieren.** Der Klar-Key, der beim Setup mehrfach in den
   Claude-Chat eingegeben wurde (`klar_pk_...c590`, in Klar unter dem Namen
   "Reporting Elli" gelistet), steht jetzt im Chatverlauf. Bitte in Klar
   (Account Settings → API Keys) diesen Key **revoken** und einen **neuen**
   erzeugen, und nur den neuen Wert unten als `KLAR_API_TOKEN` verwenden.
   Den Key niemals in den Code committen — immer als
   Umgebungsvariable/Secret setzen.

2. **Auth-Flow ist bestätigt** (live gegen den echten Havea-Klar-Account
   getestet, 25.08.2026): der Dashboard-Key funktioniert NICHT direkt als
   Bearer-Token (ergab 401). Er muss zuerst gegen `POST
   /public/auth/token` eingetauscht werden — mit dem Key in einem Header
   namens exakt `token` (nicht `Authorization`). Das ist im Code bereits so
   umgesetzt. Einzige verbleibende Unsicherheit: der genaue Feldname des
   zurückgegebenen Access-Tokens in der Antwort (Code probiert
   `accessToken`, `access_token`, `token` der Reihe nach — bei Bedarf nach
   dem ersten echten Testlauf in `server.py` anpassen).

## Lokal testen

```bash
pip install -r requirements.txt
export KLAR_API_TOKEN="<neuer Klar-Token>"
python server.py
```

Der Server lauscht dann auf `http://0.0.0.0:8000` (Streamable-HTTP-MCP-
Transport). Mit einem MCP-Testclient (z.B. `mcp dev` aus dem `mcp[cli]`-
Paket, oder Claude selbst nach Registrierung) den Tool-Call
`get_channel_attribution` mit einem bekannten Datum ausprobieren.

## Deployen

Jede Plattform, die einen dauerhaft laufenden Python-Prozess mit einer
öffentlichen HTTPS-URL hostet, funktioniert — z.B. ein kleiner Server bei
Havea, Fly.io, Render, Railway, oder ein Container hinter einem bestehenden
Reverse Proxy. Wichtig:

- `KLAR_API_TOKEN` (und ggf. `KLAR_AUTH_MODE`) als Secret/Umgebungsvariable
  setzen, nie im Code.
- Die Plattform muss TLS terminieren (Claude-Connectors brauchen HTTPS).
- Den Server dauerhaft laufen lassen (kein Cold-Start-Problem, da die
  tägliche Aufgabe jederzeit anfragen kann).

## Als Custom Connector registrieren

In den Havea-Claude-Admin-Einstellungen (dort, wo auch die bestehenden
Custom Connectors wie "BWB Promo Codes Shopify upload" eingerichtet sind):
neuen Custom Connector anlegen, die HTTPS-URL des deployten Servers
eintragen, Name z.B. "Klar Channel Data".

## Danach: Scheduled Task in Claude

Sobald der Connector registriert und aktiviert ist, kann in Claude ein
täglicher Scheduled Task (09:00 Uhr Europe/Berlin) angelegt werden, der:

1. `get_channel_attribution` für den Vortag aufruft (dieser Connector)
2. die Zahlen in eine kurze Slack-Nachricht formatiert
3. über den offiziellen Slack-Connector in **#daily-updates-eee** postet

Dieser letzte Schritt (Scheduled Task anlegen) kann direkt im Chat mit
Claude gemacht werden, sobald der Connector aktiv ist — einfach Bescheid
geben.

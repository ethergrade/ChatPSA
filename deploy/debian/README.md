# ChatPSA su Debian

## Architettura raccomandata

Esporre ChatPSA soltanto dietro un reverse proxy HTTPS con login OIDC (per
esempio Microsoft Entra ID tramite oauth2-proxy). Il proxy deve essere l'unico
processo capace di raggiungere ChatPSA e deve inoltrare:

- `X-Forwarded-Email`: email verificata dell'agente;
- `X-Forwarded-User`: nome verificato dell'agente;
- `X-ChatPSA-Proxy-Secret`: valore uguale a `CHATPSA_PROXY_SHARED_SECRET`.

Questa identità viene usata per audit e approvazioni. Non fidarsi di questi
header quando ChatPSA è direttamente raggiungibile dagli utenti.

## Preparazione

1. Installare Docker Engine e il plugin Compose sulla macchina Debian.
2. Copiare o clonare il repository in una directory dedicata.
3. Creare `.env` dal modello `.env.example` e compilare i valori localmente.
4. Creare `knowledge/tenant/` e trasferire solo la knowledge privata approvata.
5. Impostare almeno:

   - `CHATPSA_AUTH_MODE=proxy`;
   - `CHATPSA_PROXY_SHARED_SECRET` con un valore casuale lungo;
   - `CHATPSA_APPROVER_EMAILS` con le email verificate degli approvatori;
   - `CHATPSA_ALLOWED_HOSTS` e `CHATPSA_ALLOWED_ORIGINS`;
   - parametri SMTP per notificare le richieste.

Per un avvio interno provvisorio senza OIDC è disponibile la modalità `token`.
Configurare due segreti diversi: `CHATPSA_ACCESS_TOKEN` per gli amministratori e
`CHATPSA_AGENT_ACCESS_TOKEN` per gli agenti. Il secondo non può acquisire il
ruolo approvatore né dichiarare un'identità personale: usa uno storico
condiviso. Per storici personali configurare token univoci nella mappa
server-side `CHATPSA_AGENT_IDENTITIES_JSON` oppure usare OIDC.

## Avvio

Eseguire dalla cartella del progetto:

```bash
docker compose up -d --build
docker compose ps
```

Di default la porta è pubblicata solo su `127.0.0.1:8765`, così il traffico
passa obbligatoriamente dal reverse proxy. I database della coda approvazioni e
dello storico chat sono conservati nel volume `chatpsa-data`. Lo storico è
rinominabile ma non eliminabile tramite l'applicazione.

## Regola di sicurezza

L'approvazione registra una decisione, ma non abilita automaticamente i tool di
scrittura. L'esecuzione remota sarà aggiunta soltanto per serializer validati,
con conferma specifica, snapshot, read-back e diff.

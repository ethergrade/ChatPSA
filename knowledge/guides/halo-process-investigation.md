---
id: halo-process-investigation
title: Indagine di un processo HaloPSA
summary: Percorso guidato per correlare ticket, tipo, stato, workflow, outcome e regole.
tags: halopsa, ticket, workflow, status, outcome, ticket rule, email rule
---
# Catena di indagine

Partire dal ticket e correlare, quando disponibili, Ticket Type, Status,
Workflow, step corrente, Outcome, Ticket Rules, Email Rules, SLA e template.
Controllare in particolare:

- workflow inattivi o non in uso;
- step iniziali o finali mancanti;
- step non terminali privi di azioni;
- azioni duplicate o legacy ancora presenti nei dati;
- transizioni verso step inesistenti;
- differenze tra workflow del ticket e workflow previsto dal Ticket Type;
- criteri, precedenza e outcome delle regole;
- riferimenti interrotti e dipendenze prima di una modifica.

Le letture HaloPSA sono snapshot temporali. Una modifica deve essere descritta
con piano, impatto e diff e deve restare disabilitata finché non è approvata.

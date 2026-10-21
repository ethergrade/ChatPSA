---
id: change-governance
title: Governance delle modifiche
summary: Regole per trasformare una richiesta dell'agente in un cambiamento controllato.
tags: approvazione, modifica, workflow, rule, change plan, sicurezza
---
# Flusso di modifica

Una richiesta di creazione o modifica non autorizza una scrittura. ChatPSA deve:

1. identificare in modo affidabile l'agente richiedente;
2. raccogliere evidenze e dipendenze;
3. generare un change plan non eseguibile e un diff atteso;
4. inserire la richiesta nella coda approvazioni;
5. notificare gli approvatori configurati;
6. applicare la modifica soltanto dopo approvazione esplicita e specifica;
7. eseguire read-back, diff effettivo e registrare l'audit.

Le scritture restano disabilitate per impostazione predefinita. Workflow e Rule
richiedono serializer ricorsivi con allowlist; i payload GET non devono mai
essere riutilizzati ciecamente come payload di scrittura.

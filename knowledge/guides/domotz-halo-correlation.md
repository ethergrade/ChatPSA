---
id: domotz-halo-correlation
title: Correlazione Domotz e HaloPSA
summary: Metodo per investigare alert e dispositivi Domotz insieme ai ticket HaloPSA.
tags: domotz, halopsa, alert, device, offline, rete
---
# Correlazione operativa

Per un dispositivo offline o un alert ricorrente:

1. verificare stato dell'agent Domotz, alert aperti, orari e severità;
2. identificare il dispositivo usando solo attributi necessari all'indagine;
3. cercare il ticket HaloPSA associato e ricostruirne stato e workflow;
4. confrontare timestamp di alert, apertura ticket, notifiche e transizioni;
5. distinguere un problema di monitoraggio da un problema reale del dispositivo;
6. verificare deduplicazione, acknowledgement, chiusura e riapertura automatica;
7. proporre una correzione soltanto dopo aver identificato la regola responsabile.

Non mostrare chiavi API, token o payload grezzi. Le API Domotz sono usate in
sola lettura e i risultati vengono filtrati tramite allowlist.

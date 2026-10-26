# Verifica dell’internazionalizzazione

[English](VERIFICATION-I18N.md) | **Italiano**

Revisione locale del **26 ottobre 2026**, successiva al tag locale 1.1.0. Queste verifiche precedono il successivo commit/tag 1.2.0 autorizzato. Nessun push, release remota, installazione di servizi o pubblicazione nel registry. Provider simulati, senza inferenze reali o consumo di quote.

## Architettura implementata

- Catalogo JSON inglese di riferimento e italiano in `alterecho/locales/`, condivisi da Python e Svelte: scoperta automatica, fallback inglese, parametri, plurali e formattazione locale di numeri/date.
- Rilevamento delle preferenze ordinate del browser, override locale persistente e aggiornamento reattivo, anche di modali/toast/errori, senza ricreare SSE o tradurre dati della conversazione.
- Rilevamento sistema/ambiente CLI, `--lang`, `ALTERECHO_LANG`, preferenza locale `client-language.json` e traduzione di help/menu/diagnostica/watch/errori di gestione.
- Dettagli server inglesi con codici/parametri aggiuntivi; endpoint, enumerazioni e contratto `detail` conservati. Parametri redatti e diagnostica esterna sconosciuta invariata.
- README, guide utente/architettura/deployment/release/traduzioni, changelog e provenienza immagini con inglese principale e corrispettivi italiani. Documenti e screenshot storici conservati.
- Cataloghi inclusi in wheel/sdist/standalone/Docker; Vite incorpora gli stessi JSON senza servizi di traduzione o server Node in produzione.

## Prove effettive

| Verifica | Risultato |
| --- | --- |
| Suite Python Windows/Python 3.12 | **161 test superati** |
| Test cataloghi/locale/CLI | 11 inclusi nella suite: duplicati/chiavi/parametri, fallback, rilevamento Windows/Linux/macOS simulato, precedenza, preferenze locali, help/watch, dati invariati, serializzazione ed errori compatibili |
| Frontend Vitest | **18 test superati**, compreso controllo dei testi/componenti e riferimenti ai cataloghi |
| Svelte/TypeScript e Vite | Zero errori/warning; build riuscita con entrambi i cataloghi |
| Browser con Vite dev | **16 test superati** desktop/telefono emulato: rilevamento, fallback, persistenza, contesti indipendenti, modali/moduli/SSE, posizione di lettura e argomento/testo originali invariati |
| Standalone Windows | Ricostruito e provato fuori dal checkout: help EN/IT, foreground/background senza console separata, down, CLI HTTP/Web, demo, persistenza e shutdown superati |
| Docker Linux AMD64 | Build/esecuzione locale: CLI EN/IT, cataloghi inclusi, Codex versione/help, nonroot/OCI/foreground/health/API/Web/demo, SIGTERM e persistenza dopo riavvio superati |
| Wheel/sdist | Build, contenuti e installazioni separate in nuovi virtualenv superati: help EN/IT, cataloghi, CLI HTTP, risorse Web, demo e persistenza dopo riavvio fuori dal checkout |

Le catture inglesi desktop/mobile dei test sono state ispezionate visivamente; gli screenshot originali della documentazione restano invariati. Entrambi i cataloghi sono inclusi nello standalone Windows e nell’immagine Linux AMD64 ricostruiti; gli smoke test finali sono passati anche dopo l’allineamento al frontend compilato.

Le regressioni corrette includono la conservazione dei metadati di traduzione durante `deepcopy`/serializzazione degli eventi e la collocazione del selettore lingua fuori dalla sovrapposizione della navigazione mobile. Il test dello scroll attende l’applicazione della rotella prima del confronto, senza allentare il requisito di conservazione della posizione.

Una ripetizione durante build parallele ha incontrato un timeout HTTP del server gestito; l’istanza demo di prova è stata arrestata tramite il suo canale privato e il caso isolato è passato. Una distinta condizione di avvio a freddo nella fixture Codex è stata corretta applicando il limite di generazione di 0,5 secondi soltanto dopo la preparazione del protocollo. Limite/assert della generazione e timeout di produzione non sono stati aumentati. La successiva esecuzione completa seriale ha superato tutti i 161 test, senza disabilitarne alcuno.

La suite completa mantiene test di storici/configurazioni precedenti, quattro provider simulati, sessioni/checkpoint Codex, memoria Ollama prudente, sicurezza, lifecycle, export e release. Prompt/default ed involucro degli export restano invariati; sono localizzati presentazione ed errori applicativi. Bootstrap di sviluppo e future note del manutentore usano l’inglese.

## Limiti e verifiche rimaste

- API locale Windows e rilevamento Linux/macOS coperti da test unitari; nessuna nuova installazione nativa Linux/macOS o dei relativi servizi.
- Docker AMD64 verifica il runtime Linux. Non sono state ripetute le build i18n Docker ARM64 o standalone nativi Linux/macOS; le prove precedenti non certificano questi nuovi artefatti.
- Mobile è emulazione Chromium, non smartphone/tablet fisico o Safari.
- Gli screenshot mantengono il testo italiano originale, dichiarato nella documentazione inglese. I documenti storici 0.3 rimangono in italiano come archivio, non come guide attuali.
- La persistenza browser dipende dal local storage; se bloccato, la scelta vale per la sessione e non diventa mai impostazione condivisa.
- Nessuna inferenza reale, autenticazione provider, deployment TLS pubblico o pubblicazione GitHub/GHCR verificata.
- La preparazione del commit/tag 1.2.0 è successiva a queste prove runtime. Il precedente `v1.1.0` locale è archiviato fuori dallo spazio dei tag per non pubblicarlo durante il push della versione scelta.

[Guida all’implementazione](I18N.it.md) · [Guida utente](GUIDA.md) · [Verifica release](VERIFICA-RELEASE.md).

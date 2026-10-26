# Verifica AlterEcho 1.1

[English](VERIFICATION-1.1.md) | **Italiano**

Verifiche locali del **26 ottobre 2026**, eseguite prima del commit e del tag locale della 1.1.0 autorizzati successivamente; pacchetti e immagini sono stati costruiti solo localmente, senza push, pubblicazioni o release remote. Il [resoconto originale 1.0](VERIFICA-1.0.md) rimane disponibile come documento storico.

## Architettura e comportamento

Rimane un solo motore nel server FastAPI/Uvicorn. CLI Rich e Svelte usano le medesime API e SSE. Codex con ChatGPT, Ollama, OpenAI API e OpenRouter restano nel backend; autenticazione, origini/host, checkpoint, profili e JSON schema 1 sono conservati.

- `serve` / `serve --detach`: processo separato dalla sessione, nessuna finestra/browser, log persistenti, lease di avvio, verifica HTTP autenticata e identità casuale dell’istanza. Il PID esposto è quello dell’applicazione, anche con il launcher Python Windows. Un watchdog arresta le istanze non confermate dal launcher.
- `serve --foreground`: stesso programma sotto Uvicorn, Ctrl+C o supervisore. Docker/systemd/launchd/WinSW sono aggiornati a questa opzione.
- `down`: canale di controllo locale loopback con segreto separato dalle API; verifica l’istanza sulla stessa connessione prima dell’arresto. Nessun segnale a PID memorizzati, nessuna terminazione forzata, nessun endpoint HTTP di spegnimento remoto. Shutdown salva le task prima di drenare SSE; timeout espliciti in caso di blocco.
- `watch`: messaggi già completi una sola volta, un riquadro Rich aggiornabile durante il turno, output completo senza ridisegni per pipe/file, recupero per cursore e indice. Un GET attivo senza cursore non viene applicato prima del replay: evita di duplicare il testo già nello snapshot. `watch`, `resume` ed `export` condividono la risoluzione degli ID.
- Chat: header compatto, colonna centrale, messaggi A verde acqua/B viola, Markdown progressivo sanitizzato, copia, dettagli espandibili e strumenti in menu. Auto-scroll coordinato con layout/rAF, disattivazione alla lettura sopra, freccia flottante, posizione conservata durante la navigazione. Componenti stabili da partial a risposta completa; niente campo di chat manuale.
- Modelli: select alimentate dal catalogo del singolo profilo, filtro per cataloghi grandi, cache durante le modifiche, aggiornamento esplicito, gestione offline/vuoto/modelli rimossi. Cambio profilo conserva il modello selezionato e richiede una scelta esplicita se incompatibile. Ragionamento Codex limitato ai livelli dichiarati. Il server verifica ancora il catalogo prima di generare.
- Modali: riepiloghi di avvio/ripresa/eliminazione, conferma esplicita dei costi, focus iniziale su Annulla, focus contenuto, Escape e ripristino del focus. Le notifiche sono toast; nessun `confirm`, `alert` o `prompt` nativo.

## Risultati eseguiti

Correzione successiva dell’avvio Windows: `DETACHED_PROCESS` faceva ignorare `CREATE_NO_WINDOW`, permettendo al redirector Python di aprire una console separata. L’avvio usa ora `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP` e `STARTUPINFO` con `SW_HIDE`. `serve` senza opzioni rimane l’avvio background predefinito; `--detach` è soltanto un alias. Vedi le [regole dei flag Windows](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags).

Verifica mirata della correzione: **11 test di gestione processi** e **29 test CLI** superati su Windows; lo smoke test dello standalone ricostruito è superato. Le prove detached verificano anche la console del PID effettivo con un helper Win32 isolato: nessuna console visibile, server disponibile dopo l’uscita del launcher e arresto ordinato con `down`. Le verifiche precedenti nella tabella rimangono il resoconto della revisione 1.1, non una nuova esecuzione completa della matrice.

| Verifica | Risultato |
| --- | --- |
| Baseline prima delle modifiche | 119 test Python superati |
| Suite Python Windows / Python 3.12 | **136 test superati**; successive verifiche mirate CLI/watch: **35 superati** |
| Processi e watch nel runtime Linux Docker | **17 test superati**, compresi detached, down, crash, metadati obsoleti, host fidati, watchdog e SSE collegato |
| Svelte/TypeScript | **0 errori, 0 warning** |
| Frontend Vitest | **11 test superati**: sanitizzazione, SSE frammentato UTF-8/CRLF, replay e deduplicazione, cataloghi |
| Playwright / Chromium su Windows | **12 test superati**, viewport desktop e smartphone emulato |
| Vite | Build degli statici riuscita |
| Wheel/sdist 1.1.0 | Build e controllo risorse/import della CLI installata fuori dal checkout riusciti |
| Standalone Windows | Build e smoke test riusciti: foreground, detached, down, HTTP CLI, statici dopo uscita del launcher, demo e persistenza |
| Docker Linux | Build multistage riuscita; UID 10001, foreground, health/Web/API, demo, stop SIGTERM e persistenza dopo restart verificati |
| Servizi | Template aggiornati; nessuna installazione/attivazione eseguita |

Le prove Playwright usano il backend reale HTTP/SSE `tests/browser_server.py`, con provider esclusivamente simulati e directory temporanee. Coprono streaming lungo, interruzione di rete, posizione stabile, freccia, PageUp/Home, eventi touch sintetici, rotazione del viewport, cronologie da 50/100 messaggi con tabelle e codice, temi chiaro/scuro, modelli non disponibili e modali. Il test dei costi verifica anche `confirm_paid` nella richiesta e la nuova conferma per la ripresa; Annulla resta l’azione iniziale nelle eliminazioni.

Non sono state effettuate inferenze reali né letti token/chiavi dei provider. I dati personali e gli storici dell’utente non sono stati spostati o riscritti. Container e volumi temporanei di smoke test sono stati rimossi; le immagini locali e gli artefatti in `dist/` rimangono disponibili.

## CI precedente e correzione dei percorsi

È stata letta l’[esecuzione CI della 1.0](https://github.com/giovannirob/AlterEcho/actions/runs/40119953017): Ubuntu 3.11–3.13 e Docker superati; Windows/macOS falliti nei test Python. I log dei due job esaminati mostrano nove confronti di percorsi falliti ciascuno: nomi brevi Windows `RUNNER~1` rispetto a `runneradmin`, e `/var` rispetto a `/private/var` su macOS. Le radici temporanee dei test interessati vengono ora risolte canonicamente prima di costruire configurazioni e aspettative; nessun test disabilitato o eliminato.

La successiva revisione della distribuzione separa la CI ordinaria dal workflow di release: Playwright usa Vite in sviluppo, senza build distribuibili né upload di artifact nella CI ordinaria. I risultati aggiornati, inclusa la suite da 150 test Python, sono nel [resoconto della pipeline](VERIFICA-RELEASE.md). **La CI con queste modifiche 1.1 non è stata eseguita in remoto**, perché non è stato effettuato un push. Il successo delle piattaforme native Windows/macOS nella futura CI non viene anticipato.

## File e componenti

- Processo/server: nuovi `alterecho/managed.py`; modifiche a `cli.py`, `server.py`, `server_settings.py`.
- Streaming CLI: nuovo `alterecho/watching.py`; modifiche a `client.py`, `ui.py`, indice turno in `coordinator.py`.
- Frontend: `ConversationView.svelte`, `MessageBubble.svelte`, `ModelSelector.svelte`, `ConfirmDialog.svelte`, `Toast.svelte`, `catalog.ts`, `conversation.ts`, `chat.css`; aggiornati `App.svelte`, `ConfigForm.svelte`, `api.ts`, CSS e statici compilati.
- Test: `test_managed.py`, `test_watch.py`, `browser_server.py`, test frontend e Playwright; correzione delle fixture in `test_cli_ui.py` / `test_document_paths.py`.
- Distribuzione: versioni 1.1.0, manifest, Dockerfile/ignore, template dei tre OS, script di verifica, workflow CI e lock npm.
- Documentazione: README, GUIDA, ARCHITETTURA, deployment, questo report e immagini di verifica. I tre screenshot originali 1.0 sono conservati.

## Comandi riproducibili

```sh
python -m unittest discover -q
cd web
npm ci
npm run check
npm test
npm run build
npx playwright install chromium
npm run test:e2e
cd ..
python -m build --no-isolation
python deploy/check-package.py
python -m PyInstaller --noconfirm deploy/alterecho.spec
python deploy/check-standalone.py
docker build -t alterecho:1.1-local .
```

Installazione locale dal wheel: `python -m pip install "dist/alterecho-1.1.0-py3-none-any.whl[server]"`. Poi `alterecho serve`, `alterecho status`, `alterecho` o `alterecho web`, e `alterecho down` per arrestare l’istanza locale gestita. Con porta diversa configura `--server URL` nei client; `--host/--port` configurano l’ascolto del server. Per servizi e Compose rimane l’arresto tramite supervisore. Percorsi dei log, token e deployment sono nella [guida](GUIDA.md) e in [deploy/README.md](../deploy/README.md).

## Screenshot

Catture reali dell’app durante i test, con contenuti simulati: [chat desktop](images/1.1/chat-desktop.png), [chat mobile chiara](images/1.1/chat-mobile-light.png), [modale](images/1.1/conferma.png), [selezione modelli](images/1.1/nuova-conversazione.png). Non rappresentano generazioni o prestazioni di provider reali. [Provenienza](images/README.md).

## Limiti e verifiche non eseguite

- Nessuna installazione nativa Linux/macOS né collaudo dei servizi systemd/launchd/WinSW; Linux è verificato in Docker. Nessuna attivazione di servizio automatico.
- Playwright usa Chromium con emulazione smartphone e touch sintetico: nessun dispositivo fisico, trackpad fisico, Safari, Firefox o tablet reale collaudato. La rotazione è un cambio di viewport emulato.
- Nessun test con credenziali, autenticazione account o generazioni reali Codex/Ollama/OpenAI/OpenRouter; rimangono i test mock di tutti e quattro gli adapter.
- Nessun deployment pubblico HTTPS, reverse proxy reale o VPN collaudato in questa revisione.
- Un token amministrativo condiviso e un processo server; nessun sistema utenti/ruoli. `serve` detached non sostituisce un supervisore per il riavvio al boot o dopo un crash.
- Replay SSE limitato in memoria, recupero canonico al cambio epoch; crash richiede ripresa esplicita. Cronologie molto oltre 100 messaggi non profilate; non introdotta virtualizzazione della lista.
- Log detached in append, senza rotazione automatica. Posizioni della chat in memoria browser, senza persistenza dopo un reload completo.
- Standalone costruito e verificato solo su Windows. Il processo detached onefile usa un’estrazione indipendente come indicato dalla [documentazione PyInstaller](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#using-sys-executable-to-spawn-subprocesses-that-outlive-the-application-process-implementing-application-restart).

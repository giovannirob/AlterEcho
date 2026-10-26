# Verifica locale AlterEcho 1.0

[English](VERIFICATION-1.0.md) | **Italiano**

Data: 24 ottobre 2026. Checkout iniziale: main, commit `5ffcb601` (Git locale: `5ffcb60`). Nessun commit, push, pubblicazione, installazione o attivazione di servizi di sistema. Gli storici/configurazioni personali non sono stati migrati o modificati per i test.

## Risultato e architettura

È implementato un unico server Python headless con FastAPI/Uvicorn. SessionManager possiede tutte le task; Coordinator è l'unico ciclo di generazione ed emette eventi strutturati senza Rich. CLI Rich e Web UI Svelte/TypeScript usano `/api/v1` e SSE. Nessun motore alternativo in `cli.py`, `client.py` o `ui.py`; anche demo e diagnostica passano dal server.

Sono conservati Codex con ChatGPT, Ollama, ChatAPIAdapter OpenAI/OpenRouter, AdapterCatalog e snapshot dei profili. A/B è il contratto pubblico, mentre i JSON precedenti mantengono gli slot storici e schema 1. Sono mantenuti checkpoint Codex, partial, keep_alive=-1, unload prudente ed export HTML offline.

## Verifiche eseguite

| Verifica | Esito osservato |
| --- | --- |
| Suite iniziale sul checkout originale | 100 test superati |
| Suite Python dopo migrazione e regressioni aggiunte | 119 test superati, provider mock |
| Svelte/TypeScript `npm run check` | 0 errori, 0 avvisi |
| Frontend `npm test` | 6 test superati |
| Frontend `npm run build` | Statici compilati correttamente |
| SSE su socket HTTP reale | Client disconnessi senza cancellare la task; replay e snapshot verificati |
| Quattro provider attraverso il server | Codex app-server simulato, Ollama NDJSON mock, OpenAI/OpenRouter SSE mock |
| Pausa/ripresa e shutdown | Turno terminato prima della pausa; parziali salvati all'arresto |
| Thread concorrenti e errori export | Avvio duplicato rifiutato; task e risorse rilasciate |
| Autenticazione, origini, Host, CSRF, input, rate limit | Casi di rifiuto e accesso autorizzato verificati |
| Storici precedenti e migrazione | Lettura senza riscrittura, backup prima della ripresa, copia con SHA-256 e rifiuto sovrascritture |
| Wheel e sdist | Costruiti e ispezionati; statici inclusi e file personali esclusi |
| CLI dal wheel, fuori dal checkout | Installazione isolata/import/guida verificati |
| Standalone Windows PyInstaller | Build riuscita; server+CLI HTTP+Web+demo+persistenza+shutdown verificati fuori dal repository |
| Docker multistage Linux | Immagine compilata localmente, senza pubblicazione |
| Runtime Docker | UID 10001, health/API/demo e persistenza dopo stop/start verificati |
| Codex CLI nell'immagine | `--version` e `app-server --help` verificati, senza login/inferenze |
| Anteprima browser locale | Backend e pagina rispondono 200 su localhost; controllo visivo non completato |

Non sono state consumate quote Codex/OpenAI/OpenRouter né eseguite inferenze Ollama. I test non scaricano modelli. Docker ha scaricato le immagini di base e il pacchetto ufficiale Codex CLI per costruire il runtime; non ha usato le credenziali dell'utente.

Comandi principali eseguiti:

```text
python -m unittest discover -v
npm run check
npm test
npm run build
python -m build --no-isolation
python deploy/check-package.py
python -m PyInstaller --noconfirm deploy/alterecho.spec
python deploy/check-standalone.py
docker build -t alterecho:local-test .
python deploy/docker-smoke.py
python deploy/docker-smoke.py --check-persisted
```

La verifica Docker locale usa una porta alternativa e un volume esclusivamente di test. I container di test vengono rimossi dopo le prove. Le procedure di servizi rimangono esempi da installare manualmente.

## File e struttura delle modifiche

- Core/provider: `coordinator.py`, `profile_runtime.py`, `events.py`, modifiche puntuali ai tre adapter per delta reali e protezione dell'ambiente del figlio Codex.
- Server: `server.py`, `server_settings.py`, `sessions.py`, `api_models.py`, `security.py`.
- Client: `cli.py`, `client.py`, modifiche a `ui.py` per preferenze/catalogo remoti e opzioni riservate al server.
- Persistenza/configurazione: `migration.py`, validazione endpoint Ollama in `config.py`, compatibilità profili in `integrations.py`. I moduli canonici di storico/storage/export restano conservati.
- Web: `web/src/`, configurazione Vite/TypeScript, lock npm e `alterecho/static/` compilato.
- Distribuzione: `pyproject.toml`, `MANIFEST.in`, lock server, Dockerfile/Compose, template e strumenti in `deploy/`, pipeline `.github/workflows/test.yml`.
- Regressioni: test precedenti mantenuti/adattati al client HTTP; nuovi `test_server.py`, `test_lifecycle.py`, harness HTTP e test frontend.
- Documentazione: README e ARCHITETTURA aggiornati, `deploy/README.md`, questo resoconto; documenti 0.3 conservati in `docs/legacy/`.

## Installazione e utilizzo

Da questa copia locale, dopo la build frontend: `python -m pip install ".[server]"`; alternativa `uv tool install ".[server]"`. Solo client: `pip install .`. I pacchetti preparati sono in `dist/`, insieme allo standalone Windows.

Avvia il server con `alterecho serve`; collega la CLI con `alterecho`, oppure `alterecho --server URL`. Browser locale: `http://127.0.0.1:8765`, token nella configurazione del server. `alterecho status`, `run`, `watch ID`, `pause ID`, `stop ID`, `resume ID --turns N` e `export ID` usano lo stesso backend.

LAN: binding esplicito, token obbligatorio, origini e host ammessi. Internet: reverse proxy TLS e porta applicativa privata. Configurazioni concrete nella [guida all’uso](GUIDA.md#lan-e-accesso-remoto) e in `deploy/Caddyfile`. Servizi systemd/launchd/WinSW e Docker documentati in `deploy/README.md`; nessuno è stato attivato automaticamente.

## Limiti e verifiche non eseguite

- Nessuna prova con generazioni AI reali o autenticazione reale dei provider; i mock verificano i protocolli e le regressioni, non accesso/quote/account dell'utente.
- Il controllo visivo nel browser è stato interrotto da Computer Use (URL non determinabile, poi interruzione Esc). Sono verificati build, tipi, test frontend e HTTP; non è dichiarato un collaudo manuale su smartphone/tablet.
- Non sono state eseguite installazioni native su Linux/macOS né l'installazione dei servizi systemd/launchd/WinSW. Il runtime Linux è stato eseguito tramite Docker.
- La matrice GitHub Actions è predisposta, ma non è stata eseguita in remoto: nessun push autorizzato.
- La configurazione Caddy/HTTPS è un esempio documentato, non un dominio pubblico distribuito o collaudato.
- Lo standalone è stato costruito e verificato solo su Windows. Le build Linux/macOS richiedono i rispettivi sistemi.
- Un solo processo/worker, quattro task attive come limite iniziale, un token amministrativo condiviso; nessun sistema utenti/ruoli.
- Replay SSE in memoria con buffer limitato, recupero tramite snapshot dopo riavvio. Inferenze interrotte da un crash richiedono ripresa esplicita; non vengono dichiarate completate né rilanciate silenziosamente.
- Token/chiavi API e autenticazione Codex dell'installazione reale devono essere configurati dal proprietario nel solo ambiente del server.

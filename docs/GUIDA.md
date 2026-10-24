# Guida all’uso di AlterEcho 1.0

[Torna alla presentazione](../README.md) · [Servizi e container](../deploy/README.md) · [Architettura](../ARCHITETTURA.md)

Qui trovi le istruzioni complete trasferite dal README: installazione, autenticazione, provider, rete, salvataggi e manutenzione.

## Installazione locale

Python 3.11 o successivo. Per compilare il frontend dal sorgente serve Node 22.12+; wheel e standalone includono già i file statici. Node non serve per eseguire la Web UI in produzione. Codex può richiedere il proprio runtime se installato tramite npm.

Dalla copia locale del repository:

```sh
cd web
npm ci
npm run build
cd ..
python -m pip install ".[server]"
```

Si consiglia un virtualenv. Su Windows: `python -m venv .venv`, poi usa `.\.venv\Scripts\python.exe -m pip install ".[server]"`. Su Linux/macOS: `python3 -m venv .venv`, poi `.venv/bin/python -m pip install ".[server]"`.

Con uv: `uv tool install ".[server]"`. Per un computer che deve usare solo la CLI: `pip install .` oppure `uv tool install .`; FastAPI/Uvicorn restano opzionali. Il codice del server è nello stesso pacchetto, ma `serve` richiede l'extra `server`.

L'installazione non editable da wheel o sorgente non dipende dalla posizione del repository. I launcher storici `start.*` e `install-user.*` restano disponibili per sviluppo: continuano a riferirsi al virtualenv del checkout e non sono necessari per l'installazione normale.

## Token del server

Il token di AlterEcho autorizza l’accesso al servizio. È distinto dal login ChatGPT e dalle chiavi OpenAI/OpenRouter. Il browser lo mantiene soltanto in memoria; non inserirlo negli URL o negli screenshot.

Nell’installazione locale il primo `alterecho serve` crea `server-token`. Senza percorsi personalizzati si trova in:

| Sistema | File |
| --- | --- |
| Windows | `%APPDATA%/AlterEcho/server-token` |
| Linux/macOS | `~/.config/alterecho/server-token`, oppure sotto `$XDG_CONFIG_HOME` |
| Con `ALTERECHO_HOME` | `<ALTERECHO_HOME>/config/server-token` |

Per leggerlo, usa il tuo gestore di file o `Get-Content "$env:APPDATA/AlterEcho/server-token"` in PowerShell; su Linux/macOS, `cat ~/.config/alterecho/server-token` se usi il percorso predefinito. Incolla il valore nel modulo di accesso della Web UI. La CLI locale sullo stesso account lo legge automaticamente.

Se imposti `ALTERECHO_TOKEN` o `ALTERECHO_TOKEN_FILE`, viene usato quel valore e il file automatico può non essere creato. L’API richiede un bearer token; proteggerlo con permessi/ACL è responsabilità dell’account del server.

### Preparare il token per Docker

Compose legge `secrets/service-token.txt`: crealo prima dell’avvio, dalla cartella del repository. Con Python già disponibile, questo comando funziona anche in PowerShell e rifiuta di sovrascrivere un file esistente:

```sh
python -c "from pathlib import Path; import secrets; p=Path('secrets'); p.mkdir(exist_ok=True); f=(p/'service-token.txt').open('x', encoding='utf-8'); f.write(secrets.token_urlsafe(32)); f.close()"
```

Senza Python locale puoi usare il runtime Docker per generare il valore: `docker run --rm python:3.12-slim python -c "import secrets; print(secrets.token_urlsafe(32))"`, poi salvalo nel file richiesto. Non utilizzare token di esempio. Il file deve essere leggibile dall’UID 10001 del container e riservato agli account autorizzati; consulta anche la [guida Docker](../deploy/README.md#docker-e-codex-headless).

Su Docker Engine Linux senza rimappatura degli utenti, un esempio di permessi è:

```sh
chmod 700 secrets
sudo chown 10001:10001 secrets/service-token.txt
sudo chmod 400 secrets/service-token.txt
```

Dopo questo passaggio, sul computer host puoi leggere il token con `sudo cat secrets/service-token.txt`. Con Docker rootless o rimappatura degli UID, adatta il proprietario al mapping effettivo; su Docker Desktop verifica la lettura nel container e proteggi il file con i permessi/ACL dell'host. Non usare un token di esempio o esporre la porta alla rete per aggirare problemi di autenticazione.

## Server, CLI e browser

Primo terminale, con l'ambiente dei provider configurato:

```sh
alterecho serve
```

Ascolta solo su **http://127.0.0.1:8765**. Non apre porte di rete e non avvia inferenze. Al primo avvio locale crea `server-token` nella cartella di configurazione; il valore non viene stampato nei log. La CLI sullo stesso account lo legge automaticamente. Nel browser apri l'URL e inserisci quel token. Anche su localhost le operazioni sono autenticate.

Secondo terminale:

```sh
alterecho
alterecho doctor
alterecho status
alterecho run
alterecho demo --turns 4
```

`doctor` verifica i cataloghi senza inferenze né scaricamenti. La demo viene eseguita sul server con adapter simulati. Il menu conserva nuova conversazione, archivio, ripresa, eliminazione, visualizzazione e impostazioni; tutte le operazioni applicative passano dalle API.

```sh
alterecho run --non-interactive --detach
alterecho watch ID
alterecho pause ID
alterecho stop ID
alterecho resume ID --turns 20 --detach
alterecho export ID --format html
alterecho web
alterecho help
```

Il limite conta **messaggi totali**, non coppie. La ripresa a 20 include quelli già salvati. `pause` termina il turno corrente prima di sospendere; `stop` interrompe il turno e preserva i parziali. **Ctrl+C nella CLI scollega soltanto il client**. Per fermare il dialogo usa `stop`; chiudere browser o terminale non ferma il server.

`export` scarica copie offline esplicite nella cartella corrente e rifiuta di sovrascrivere file esistenti. Non crea uno storico operativo della CLI. Sono disponibili Markdown, TXT e HTML; l'API e il browser offrono anche il JSON canonico. L'HTML rimane un documento autonomo, sicuro e utilizzabile offline, distinto dalla Web UI.

Per `resume` ed `export` sono accettati anche il nome di un JSON già indicizzato sul server o il suo ID. Un percorso locale del client non carica file nel server. `run --config FILE.toml` mantiene le opzioni del dialogo; percorsi, eseguibili e profili devono essere autorizzati/configurati sul server.

Le impostazioni condivise sono modificabili da CLI e browser. Percorsi di salvataggio, installazione Codex e directory delle credenziali si configurano direttamente sul server e non sono modificabili via API.

## Provider e profili

I profili distinguono l’interlocutore A/B dal provider effettivo. Nella versione attuale Codex CLI può occupare soltanto A ed è ammesso un solo interlocutore Ollama per conversazione. OpenAI e OpenRouter usano API a consumo; non tutti i modelli dei cataloghi sono necessariamente compatibili o accessibili con il proprio account. Claude Code non è implementato.


Nel browser o nel menu **Impostazioni → Modelli e adapter → Adapter e integrazioni** aggiungi/seleziona i profili. Usa **Verifica cataloghi** per ottenere i modelli. Per Codex scegli un livello di ragionamento supportato dal modello. Le API HTTP mantengono lo streaming nativo, usage e cronologia completa, senza eseguire strumenti.

Codex continua a usare l'app-server ufficiale, il login ChatGPT, thread persistenti e verifica della ripresa. Non viene sostituito con OpenAI API. Sul computer/account del server, prima dell'avvio:

```sh
codex login
# Su un server senza browser, se abilitato per l'account:
codex login --device-auth
codex login status
```

Il device login è un meccanismo ufficiale; disponibilità e permessi dipendono dall'account. Vedi [documentazione ufficiale OpenAI sull'autenticazione](https://learn.chatgpt.com/docs/auth). AlterEcho non legge né restituisce `auth.json` e non effettua login automaticamente. Per servizi usa `CODEX_HOME` o `codex_home` espliciti, accessibili soltanto all'account del servizio. Non condividere lo stesso thread con altre applicazioni durante una conversazione.

Ollama non viene installato e non scarica modelli automaticamente. Installa esplicitamente il modello scelto. Restano `ollama_keep_alive=-1` e lo scaricamento finale prudente: nessun modello viene scaricato se l'uso esclusivo non è verificabile.

Per Ollama in Docker/LAN, autorizza **sul server** gli hostname esatti:

```sh
export ALTERECHO_OLLAMA_HOSTS=ollama,host.docker.internal,192.168.1.20
```

Poi imposta l'URL nel profilo, ad esempio `http://ollama:11434`. Il default resta loopback HTTP. Non sono accettati credenziali negli URL, redirect, percorsi, query o host non autorizzati. Autorizza soltanto servizi fidati; usa VPN/TLS quando opportuno.

Per OpenAI/OpenRouter imposta `OPENAI_API_KEY` / `OPENROUTER_API_KEY` nell'ambiente del **server**, oppure il nome di variabile registrato nel profilo. Non inserirne il valore in CLI, moduli Web, TOML, `adapters.json` o URL.

```sh
alterecho run --non-interactive --confirm-paid
alterecho resume ID --turns 20 --confirm-paid
```

Il menu interattivo mostra i provider a consumo e chiede conferma. Il browser richiede una casella esplicita. Le API richiedono `confirm_paid: true`; ogni ripresa richiede una nuova conferma.

## CLI su un altro computer

```sh
alterecho --server https://echo.example.org connect --token-file /percorso/protetto/service-token
alterecho status
alterecho run
```

`client.json` salva solo endpoint e riferimento al file locale del token, mai chiavi dei provider. Puoi anche usare `ALTERECHO_SERVER`, `ALTERECHO_TOKEN` o `ALTERECHO_TOKEN_FILE`. `--server` è un'opzione globale e precede il comando. Se il server non risponde, la CLI indica come avviarlo/configurarlo e non avvia alcun motore locale.

## LAN e accesso remoto

Per abilitare la LAN sono obbligatori token di almeno 32 caratteri, origini esatte e host ammessi. PowerShell:

```powershell
$env:ALTERECHO_TOKEN_FILE = 'C:\ProgramData\AlterEcho\service-token'
$env:ALTERECHO_ORIGINS = 'http://192.168.1.20:8765'
$env:ALTERECHO_ALLOWED_HOSTS = '192.168.1.20,127.0.0.1,localhost'
alterecho serve --host 0.0.0.0 --port 8765
```

Crea il file del token con `python -c "import secrets; print(secrets.token_urlsafe(32))"` e proteggilo con ACL. Su Linux/macOS usa le corrispondenti variabili `export` e permessi `0600`. In LAN HTTP il token transita in chiaro: usa una LAN fidata, una VPN o preferibilmente un reverse proxy HTTPS.

Per Internet mantieni il backend su loopback e configura un reverse proxy TLS. Esempio Caddy in [deploy/Caddyfile](../deploy/Caddyfile), con dominio e DNS reali:

```sh
export ALTERECHO_TOKEN_FILE=/etc/alterecho/service-token
export ALTERECHO_ORIGINS=https://echo.example.org
export ALTERECHO_ALLOWED_HOSTS=echo.example.org,127.0.0.1,localhost
export ALTERECHO_PROXY_IPS=127.0.0.1
alterecho serve
```

Pubblica soltanto il proxy HTTPS; non fare port forwarding non protetto della porta applicativa. SSE richiede buffering disabilitato (`flush_interval -1` in Caddy; `proxy_buffering off` e timeout adeguato in Nginx). Non usare wildcard per origini o proxy fidati. Sono supportati anche VPN e tunnel privati. L'app non gestisce certificati TLS autonomamente e non richiede cloud.

### Esempio Nginx

Se preferisci Nginx a Caddy, ecco un esempio da adattare al tuo dominio e a certificati TLS già disponibili. Non è una configurazione distribuita o collaudata su un dominio reale.

```nginx
server {
    listen 443 ssl;
    server_name echo.example.org;
    ssl_certificate /etc/letsencrypt/live/echo.example.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/echo.example.org/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }
}
```

Mantieni token, origini, host ammessi e `ALTERECHO_PROXY_IPS=127.0.0.1` come nell'esempio precedente; non pubblicare la porta del backend. Il buffering disabilitato permette di inoltrare subito gli eventi SSE. Riferimento: [modulo proxy ufficiale Nginx](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).

## Percorsi, backup e migrazione

I file precedenti restano leggibili: `config.json`, `adapters.json`, JSON schema 1, export e checkpoint Codex. Gli slot storici `codex`/`ollama` vengono tradotti in **A/B nelle API**; non sono identificatori del provider. I profili salvati nelle conversazioni restano la fonte della ripresa, anche se il catalogo cambia.

| Dato | Percorso predefinito |
| --- | --- |
| Configurazione Windows | `%APPDATA%/AlterEcho` |
| Configurazione Linux/macOS | `$XDG_CONFIG_HOME/alterecho`, altrimenti `~/.config/alterecho` |
| Storici | cartella Documenti nativa, `AlterEcho/conversations` |
| Installazione con `ALTERECHO_HOME` assoluto | `config/` e `data/conversations/` sotto quella directory |

Percorsi personalizzati, directory legacy e vecchia `outputs/conversations` del checkout vengono ricercati come prima. Nessuno storico viene modificato soltanto perché letto. Uno stato `running` rimasto dopo un crash viene presentato come `interrupted`; la ripresa è esplicita. L'eliminazione esplicita di uno storico rimuove anche i suoi backup di ripresa, senza toccare quelli di altre chat. Prima della ripresa viene conservata una copia del JSON in `.backups/*.bak` e Codex verifica il thread. Parziali e turni non completati non diventano messaggi completi.

Prima di cambiare account o computer: arresta ordinatamente il server e fai un backup separato di configurazione, storici e stato Codex. Per una copia verificabile e senza sovrascritture:

```sh
alterecho migrate /vecchi/storici /nuovi/storici
alterecho migrate /vecchi/storici /nuovi/storici --apply
```

Il primo comando produce un piano SHA-256 senza scritture. `--apply` copia soltanto in una directory nuova/vuota, verifica gli hash e conserva gli originali. Rifiuta link simbolici e JSON sconosciuti. Non copia automaticamente `auth.json`/`client.json`. Non riscrive percorsi interni: verifica `output_dir`, `codex_work_dir`, `codex_home`, eseguibili e `history_directories` nel **nuovo** `config.json`, mantenendo un backup del precedente. Per trasferire sessioni Codex usa solo le procedure ufficiali, con permessi riservati. I JSON storici restano byte per byte invariati durante la copia.

Per servizi/container imposta sempre `ALTERECHO_HOME` assoluto e persistente: non dipendere da Documenti o dalla sessione desktop dell'account interattivo.

## Servizi di sistema

I template non vengono installati o attivati automaticamente. Vedi le procedure in [deploy/README.md](../deploy/README.md): systemd, launchd di sistema e servizio Windows con WinSW. Tutti avviano lo stesso `alterecho serve`. Esegui il processo con un account dedicato/non amministrativo, directory riservate e Codex autenticato sotto quell'account.

## Docker

La build multistage compila Svelte, prepara il pacchetto Python e include Codex CLI; Ollama resta esterno. Nessuna credenziale o modello nell'immagine. Runtime UID/GID 10001, `SIGTERM`, healthcheck e volumi distinti per dati/configurazione e stato Codex.

Crea `secrets/service-token.txt` con un token casuale di almeno 32 caratteri, proteggi la cartella e poi:

```sh
docker compose build
docker compose up -d
docker compose exec alterecho codex login --device-auth
docker compose logs -f alterecho
```

Compose pubblica **solo `127.0.0.1:8765`** e usa `restart: unless-stopped`. Il login è un'operazione manuale, non un test automatico. Configura il profilo Ollama tramite UI/API con `http://host.docker.internal:11434`, un container su una rete condivisa o un host LAN fidato. Nel container `localhost` identifica il container stesso. Non esporre Ollama senza protezione su una rete non fidata.

I volumi `alterecho_data` e `codex_state` persistono dopo `docker compose down`; **non usare `down -v` per aggiornare**. Lo stato Codex deve essere scrivibile dal suo account per checkpoint e refresh delle credenziali. Non montare l'intera home personale nel container. `CODEX_VERSION` permette di fissare una versione verificata invece del default `latest`.

## Build e verifica

I risultati riportati in [VERIFICA.md](VERIFICA.md) appartengono alla verifica locale del 24 ottobre 2026: non sono uno stato CI pubblico. Il redesign del README non richiede nuove inferenze o modifiche al programma.

```sh
cd web
npm ci
npm run check
npm test
npm run build
cd ..
python -m pip install ".[server]" build
python -m unittest discover -v
python -m build
python deploy/check-package.py
```

La suite standard usa provider mock e un app-server Codex simulato. Non consuma quote e non effettua inferenze Ollama. La pipeline GitHub Actions comprende Windows/Linux/macOS con Python 3.11–3.13, frontend, wheel/sdist e Docker. La sua esecuzione remota richiede che l'utente decida di pubblicare le modifiche.

Per standalone: `pip install ".[standalone]"`, poi `pyinstaller deploy/alterecho.spec`. Esegui la build sul sistema operativo di destinazione; Codex e Ollama restano dipendenze esterne. Non sono inclusi pesi, home utente o credenziali.

Per aggiornare, arresta il servizio, esegui backup, installa il nuovo wheel non editable e riavvia. Non avviare più worker Uvicorn o due server sulle stesse directory.

## Risoluzione dei problemi e limiti

- **Server non raggiungibile:** controlla `alterecho serve`, endpoint e porta; chiudere la CLI non avvia né arresta il servizio.
- **401:** token del servizio errato/assente. è distinto dalle chiavi dei provider e dal login ChatGPT.
- **403/host non valido:** verifica origini esatte, hostname ammessi, dominio/proxy e URL del browser.
- **Codex non trovato o login assente nel servizio:** configura PATH, `codex_binary`/`codex_home`, account e permessi sul server, non nel client.
- **Ripresa rifiutata:** conserva i file; verifica thread Codex, limiti, modelli e dialoghi concorrenti. Gli storici demo non vengono ripresi con provider reali.
- **Frontend 503:** compila `web/` o installa un pacchetto con risorse statiche.
- **Memoria Ollama:** nessuno scaricamento automatico di modelli di altre app; usa keep_alive a tempo se desideri scadenza.

La versione 1.0 usa un singolo processo e un token amministrativo condiviso, senza utenti/ruoli multipli. I checkpoint sono durevoli, il replay SSE è limitato e in memoria: al riavvio o a cursore scaduto i client ricevono uno snapshot canonico. Non viene riavviata automaticamente un'inferenza interrotta dal crash. Non sono previsti un database distribuito o un desktop autonomo.

I risultati effettivamente eseguiti e le verifiche ancora mancanti sono in [docs/VERIFICA.md](VERIFICA.md). Dettagli tecnici in [ARCHITETTURA.md](../ARCHITETTURA.md). I documenti precedenti sono conservati in `docs/legacy/` come riferimento della versione 0.3.

# Installazione persistente

## Installazione da GitHub Releases e GHCR

Il workflow di distribuzione è predisposto per il push di nuovi tag `vMAJOR.MINOR.PATCH`. Nessuna nuova release è stata pubblicata da questa revisione. Quando disponibile, scarica gli allegati da [GitHub Releases](https://github.com/giovannirob/AlterEcho/releases) con un account autorizzato e verifica i checksum. La release elenca soltanto gli archivi prodotti e verificati.

Per il wheel, da un ambiente Python 3.11+:

```sh
python -m pip install "alterecho-1.1.0-py3-none-any.whl[server]"
alterecho serve
```

Gli standalone vanno estratti in una cartella stabile; su Linux/macOS usa `./alterecho serve`, su Windows `./alterecho.exe serve`. Il binario comprende CLI, server e statici, mentre Codex e Ollama restano esterni. Gli archivi Linux richiedono glibc 2.35+; gli archivi macOS non sono firmati o notarizzati. Gatekeeper può richiedere una decisione esplicita dell’utente dopo la verifica della provenienza; non viene disattivato automaticamente.

Per l’immagine privata GHCR, autenticati come descritto nella [guida release](../docs/RELEASE.md#docker--ghcr), prepara il token del servizio in `secrets/service-token.txt` e usa il file Compose senza build:

```sh
export ALTERECHO_VERSION=1.1.0
docker compose -f compose.registry.yaml pull
docker compose -f compose.registry.yaml up -d --no-build
docker compose -f compose.registry.yaml logs -f
docker compose -f compose.registry.yaml stop
```

In PowerShell imposta `$env:ALTERECHO_VERSION='1.1.0'`. Usa una versione effettivamente pubblicata; `latest` è aggiornato soltanto dalle stabili. `compose.registry.yaml` mantiene localhost, volumi, secret separato e utente non privilegiato dell’immagine. Conserva lo stesso progetto Compose e fai backup dei volumi durante gli aggiornamenti; non usare `down -v` per aggiornare. Il `compose.yaml` originale rimane disponibile per compilare dal sorgente.

La [guida del manutentore](../docs/RELEASE.md) documenta tag, prerelease, permessi, ruleset, GHCR privato e recupero da una pubblicazione fallita. Nessun servizio, permesso remoto o package è stato attivato automaticamente.

Queste procedure sono esempi da revisionare sul sistema di destinazione. Non vengono eseguite dall'installazione del pacchetto. Tutte avviano `alterecho serve --foreground`, con directory assolute e un account con permessi limitati. Prima verifica in primo piano, effettua un backup e configura Codex/Ollama sotto l'account corretto.

## Linux / systemd

Dalla versione 1.1 `serve` da solo è detached: i template usano esplicitamente **`serve --foreground`** per lasciare il controllo al supervisore. Per prove locali senza installare servizi puoi usare `alterecho serve`, consultare URL/PID/log nell’output e arrestare con `alterecho down`. Questa modalità sopravvive al terminale ma non abilita l’avvio al boot. I log sono nella directory dati `logs/server.log`; sotto un supervisore restano nei percorsi/journal configurati dal supervisore stesso.

`down` non arresta istanze avviate in foreground da systemd, launchd, WinSW o Docker: usa i comandi riportati sotto. Non cancellare i file di lease mentre il server è attivo.

Esempio per una distribuzione con `useradd` e Python 3.11+, eseguito dall'amministratore dopo revisione:

```sh
sudo useradd --system --home /var/lib/alterecho --shell /usr/sbin/nologin alterecho
sudo install -d -o alterecho -g alterecho -m 0700 /var/lib/alterecho /var/lib/alterecho-codex
sudo install -d -m 0755 /opt/alterecho
sudo python3 -m venv /opt/alterecho/venv
sudo /opt/alterecho/venv/bin/pip install '/percorso/alterecho-1.1.0-py3-none-any.whl[server]'
sudo install -d -m 0750 /etc/alterecho
sudo install -m 0644 deploy/systemd/alterecho.service /etc/systemd/system/alterecho.service
```

Copia `server.env.example` in `/etc/alterecho/server.env` e modifica i valori. Se contiene segreti, usa `0600 root:root` (systemd lo legge prima di cambiare utente). Installa Codex in un percorso accessibile e configura `codex_binary` nel file `/var/lib/alterecho/config/config.json`, oppure PATH nel file dell'ambiente. Esegui il login ufficiale con `CODEX_HOME=/var/lib/alterecho-codex` come account `alterecho`; non avviare inferenze per provarlo.

Solo quando la configurazione è stata verificata:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now alterecho
sudo systemctl status alterecho
sudo journalctl -u alterecho -f
# Arresto ordinato:
sudo systemctl stop alterecho
```

`ProtectHome=true` impedisce di usare accidentalmente la home interattiva. Se gli storici sono fuori dalle directory previste, copia/migra esplicitamente i dati e aggiorna configurazione e `ReadWritePaths` dopo aver verificato permessi e backup.

## macOS / launchd di sistema

Usa un account di servizio `_alterecho` creato dall'amministratore secondo le procedure del Mac. Non usare un LaunchAgent utente se vuoi funzionamento senza login desktop.

1. Crea `/var/lib/alterecho` e `/var/lib/alterecho-codex`, proprietario `_alterecho`, permessi `0700`.
2. Installa il wheel con extra `server` nel virtualenv `/opt/alterecho/venv`.
3. Installa e autentica Codex per l'account del servizio con home esplicita. Verifica percorsi del binario e PATH (Homebrew ARM e Intel differiscono).
4. Adatta `deploy/launchd/org.alterecho.server.plist`. Per accesso di rete aggiungi token-file, origini e host in `EnvironmentVariables`; non inserire valori segreti in un plist pubblico.
5. Prepara file di log riservati all'account del servizio e installa il plist come `root:wheel`, `0644`, in `/Library/LaunchDaemons/`.

```sh
sudo plutil -lint /Library/LaunchDaemons/org.alterecho.server.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/org.alterecho.server.plist
sudo launchctl print system/org.alterecho.server
# Arresto/rimozione dal dominio launchd:
sudo launchctl bootout system /Library/LaunchDaemons/org.alterecho.server.plist
```

Il template abilita `RunAtLoad` e `KeepAlive`. La creazione dell'account e l'installazione launchd non sono state eseguite da questo lavoro.

## Windows / WinSW

Usa una release ufficiale WinSW compatibile con il formato XML del template, da [winsw/winsw](https://github.com/winsw/winsw). La configurazione dell'account segue la [documentazione ufficiale WinSW](https://github.com/winsw/winsw/blob/v3/docs/xml-config-file.md). Non viene scaricato o installato automaticamente alcun wrapper.

Esempio di preparazione (PowerShell amministrativa, percorsi da verificare):

```powershell
python -m venv C:\ProgramData\AlterEcho\venv
C:\ProgramData\AlterEcho\venv\Scripts\python.exe -m pip install 'C:\pacchetti\alterecho-1.1.0-py3-none-any.whl[server]'
```

Metti il binario WinSW come `C:\ProgramData\AlterEcho\AlterEcho.exe` e copia `windows/AlterEcho.xml` accanto con lo stesso nome base. Crea `state`, `codex` e `logs`. Il template usa **LocalService**, non LocalSystem. Configura ACL: LocalService deve poter modificare solo directory dati/Codex/log; la directory del programma va protetta da modifiche non amministrative. Per un account dedicato modifica `serviceaccount` secondo la versione WinSW utilizzata e concedi il diritto di accesso come servizio. Evita password in chiaro in file condivisi.

Codex deve essere installato in un percorso accessibile al servizio, con `codex_binary` esplicito se necessario. Il login ChatGPT dell'utente desktop non equivale al login del servizio: usa la directory Codex dedicata e la procedura ufficiale di autenticazione/trasferimento sicuro; non pubblicare mai `auth.json`. Prima verifica che il servizio abbia accesso al suo token locale, alle sessioni e ai modelli selezionati.

Comandi **manuali**, dopo revisione:

```powershell
C:\ProgramData\AlterEcho\AlterEcho.exe install
C:\ProgramData\AlterEcho\AlterEcho.exe start
C:\ProgramData\AlterEcho\AlterEcho.exe status
C:\ProgramData\AlterEcho\AlterEcho.exe stop
```

WinSW inoltra l'arresto al processo console e concede il timeout configurato; verifica il comportamento di stop con la release e l'account scelti prima di usarlo in produzione. Un servizio non richiede un desktop aperto. Non confondere il wrapper `AlterEcho.exe` in ProgramData con lo standalone del pacchetto.

## Docker e Codex headless

Da checkout, genera un token casuale in `secrets/service-token.txt`; il file è escluso dalla build. Verifica che l'UID 10001 possa leggerlo nel container. Su Linux proteggi file e directory rispetto agli altri utenti ma concedi la lettura al gruppo/UID appropriato; il backend deve poter leggere il secret. Non rendere leggibili globalmente credenziali Codex.

```sh
docker compose build
docker compose up -d
docker compose exec alterecho codex login --device-auth
docker compose ps
```

Il device login richiede abilitazione nelle impostazioni dell'account/workspace; vedi [OpenAI authentication](https://learn.chatgpt.com/docs/auth). Il volume `codex_state` conserva credenziali e sessioni e deve essere scrivibile per refresh e checkpoint. Nessun file di autenticazione è copiato nell'immagine.

Puoi usare Ollama sull'host (`host.docker.internal`), su un container separato collegato alla stessa rete (`ollama`) o in LAN. Aggiorna `ALTERECHO_OLLAMA_HOSTS` e il profilo, senza aprire automaticamente Ollama alla rete. Le chiavi OpenAI/OpenRouter si possono passare all'ambiente del container usando un file dell'ambiente protetto, escluso dal controllo versione.

Per un proxy in un container separato usa una rete Docker privata condivisa e non pubblicare la porta applicativa all'esterno. Consenti l'hostname necessario in `ALTERECHO_ALLOWED_HOSTS`, il dominio HTTPS esatto in `ALTERECHO_ORIGINS` e solo gli IP proxy realmente fidati.

## Aggiornamento e backup

Arresta ordinatamente, copia dati/configurazione e volume Codex con strumenti adatti e accesso riservato, aggiorna il pacchetto/immagine e riavvia. Non usare `compose down -v` per un aggiornamento. Mantieni un backup dei JSON e dei percorsi precedenti; la migrazione di directory è esplicita e non riscrive gli storici.

Lo standalone si costruisce con `python -m PyInstaller deploy/alterecho.spec`, dopo la build frontend. Ogni OS richiede una propria build; non include Codex, Ollama o modelli. Il pacchetto Python rimane il percorso principale di installazione.

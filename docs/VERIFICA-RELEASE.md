# Verifica del sistema di release

Data: **26 ottobre 2026**. Sistema preparato e verificato localmente. Le verifiche qui riportate precedono il commit e il tag locale della 1.1.0, autorizzati successivamente. **Nessun push, workflow remoto, GitHub Release o pubblicazione GHCR eseguito per questa versione.** Le operazioni di scrittura remota sono state provate soltanto con client fittizi nei test.

## File di questa revisione

- `.github/workflows/test.yml`: CI di soli controlli, su branch/PR e richiamabile dalla release; nessuna build di distribuzione, container o upload di artifact.
- `.github/workflows/release.yml`: nuovo workflow esclusivamente da push di nuovi tag `v…`; validazione, CI riutilizzata, frontend, Python, cinque standalone nativi, due immagini native, GHCR e Release finale.
- `deploy/release.py`: versioni/tag, commit remoto, duplicati, archivi, checksum, manifest, pubblicazione Docker e upload GitHub con draft verificato.
- `deploy/check-package.py`: controllo versionato dei contenuti e installazione pulita separata di wheel e sdist con prove HTTP/CLI/Web/demo/restart fuori dal checkout.
- `deploy/check-standalone.py`: controllo versione dinamico e verifiche dell’eseguibile fuori dal repository; nessuna versione di release codificata nello script.
- `deploy/check-image.py`, `deploy/codex-version.txt`: prova immagine, Codex fissato, persistenza/SIGTERM, trasporto dell’immagine verificata con SHA-256.
- `Dockerfile`, `compose.yaml`, `compose.registry.yaml`: OCI source/revision/version, Codex fissato e Compose separato per immagini private già pubblicate.
- `web/vite.config.ts`, `web/playwright.config.ts`, `tests/browser_server.py`: modalità test con Vite in sviluppo e backend mock, senza build frontend di produzione nella CI ordinaria. La versione visualizzata nella Web UI deriva da `web/package.json` ed è verificata insieme alle altre versioni.
- `tests/test_release.py`: controlli di accettazione offline; dipendenze di sviluppo aggiornate, manifest limitato e ignore per artifact intermedi.
- README, guida, architettura e deployment: download, GHCR privato, link aggiornati al report 1.1 esistente; [procedura del manutentore](RELEASE.md). Il motore applicativo non è stato riscritto.

## Risultati effettivi

| Prova | Risultato |
| --- | --- |
| Suite Python completa / Windows Python 3.12 | **150 test superati** |
| Nuovi test di release, inclusi nella suite | **14 test superati**, rete e pubblicazioni simulate |
| Frontend Vitest | **11 test superati** |
| Svelte/TypeScript | **0 errori, 0 warning** |
| Playwright con Vite dev e backend HTTP/SSE mock | **12 test desktop/mobile emulato superati**, senza `npm run build` |
| actionlint 1.7.12 | Entrambi i workflow validi; tool scaricato dalla release ufficiale e SHA-256 verificato |
| Wheel/sdist 1.1.0 | Costruiti localmente, contenuti controllati e installati ciascuno in un nuovo virtualenv; server, CLI, statici, demo e persistenza verificati fuori dal checkout |
| Standalone Windows x64 | Smoke test versione/foreground/detached/down/Web/demo/persistenza superato; archivio Windows locale con nome di release prodotto |
| Standalone Linux x64 | Compilato ed eseguito nel container Debian bookworm, smoke test superato. Questo collaudo usa glibc 2.36, **non** il futuro runner Ubuntu 22.04/glibc 2.35 |
| Immagine Docker AMD64 | Buildx locale, UID 10001, label OCI, foreground, Codex `0.164.0`, health/API/Web/demo, SIGTERM e persistenza dopo restart superati |
| Immagine Docker ARM64 | Realmente costruita ed eseguita **in emulazione Docker Desktop**; gli stessi controlli sono superati, incluso il binario Codex ARM64 |
| Archivi delle immagini | Salvati localmente con record di architettura/versione/revisione e SHA-256 verificabile; nessun push |
| File personali/credenziali | Controlli su nomi/percorsi vietati e contenuti richiesti degli archivi superati; nessun peso o file di autenticazione incluso |

I container e volumi temporanei del collaudo immagini sono stati rimossi dopo verifica di etichetta e identità. Immagini e archivi locali rimangono disponibili nelle directory ignorate (`dist/`, `.runtime-test/`). La revisione OCI delle immagini di prova è dichiarata `local-uncommitted`: non viene presentata come build pubblicata di un commit remoto.

L'ultimo allineamento della versione visualizzata nella Web UI è stato verificato con check TypeScript/Svelte, 11 test frontend e build; wheel e sdist sono stati ricostruiti con questi asset. Le prove operative di standalone e immagini precedono questo solo aggiornamento del testo di versione. La pipeline ricostruirà tutti i prodotti dal commit del tag.

## Criteri di accettazione

| Requisito | Evidenza e limite |
| --- | --- |
| Main/branch non producono distribuzioni | Test strutturale dei trigger e dei comandi CI; actionlint |
| PR non pubblicano | Nessun trigger PR nel workflow release; permessi CI di sola lettura; test del validatore evento |
| Tag invalidi non producono release | Prefiltro e test SemVer, zeri iniziali, input estranei e prerelease non rappresentabili rifiutati |
| Nuovo tag valido avvia il percorso | Trigger e DAG verificati staticamente; esecuzione remota ancora da autorizzare |
| Versioni incoerenti falliscono | Test progetto/runtime/npm/lock e mapping prerelease PEP 440; file non modificati |
| Test falliti impediscono pubblicazione | Verifica ricorsiva delle dipendenze di tutti i job di build e scrittura |
| Wheel/sdist installabili | Due installazioni reali pulite e prove operative senza checkout |
| Standalone avviabili fuori repo | Windows e Linux x64 verificati; macOS e Linux ARM64 standalone attendono i runner nativi |
| Asset Web inclusi | Risorse archiviate e HTTP degli asset JS/CSS verificati negli ambienti installati |
| Container foreground/headless | Inspect del command e prove reali, entrambe le architetture |
| Multiarch solo con immagini testate | Controllo di entrambi gli archivi prima delle scritture; digest e piattaforme del manifest finale verificati dal codice e da mock |
| Tag GHCR corretti | Test di stable/prerelease e manifest simulati; autenticazione/push reali non eseguiti |
| Release con file/checksum completi | Test dei sette file obbligatori, manifest, checksum, upload interrotto e ripresa di draft; API reale di upload non invocata |
| Prerelease non cambiano latest | Test sia Docker sia `make_latest=false` GitHub |
| Nessuna sovrascrittura | Rifiuto duplicati/draft estranei/versioni esistenti, tag spostati, allegati alterati, immagini GHCR già presenti; mock senza scritture reali |
| Nessun file personale nelle distribuzioni | Ispezione wheel/sdist e archivi standalone limitati a binario/guida; denylist e manifest sorgente ristretto |

## CI precedente e percorsi

È stata consultata l’[esecuzione remota precedente](https://github.com/giovannirob/AlterEcho/actions/runs/40119953017), ancora fallita al momento della lettura. Le correzioni già presenti nella working tree risolvono canonicamente le radici temporanee in `test_cli_ui.py` e `test_document_paths.py`, evitando confronti fra `RUNNER~1`/`runneradmin` o `/var`/`/private/var`. Sono conservate: nessun test è stato eliminato o disabilitato per la migrazione. I 150 test locali sono passati su Windows; **non viene dichiarata superata una nuova CI macOS**.

## Verifiche rimaste per la prima release autorizzata

- Esecuzione completa dei due workflow su GitHub e disponibilità/policy/minuti dei runner privati, soprattutto i due macOS e Linux ARM64.
- Standalone prodotti sui runner Ubuntu 22.04/glibc 2.35 e macOS 15 Intel/ARM; il solo standalone Linux locale usa un ambiente diverso. Nessuna cross-compilazione fittizia.
- Autorizzazioni reali `GITHUB_TOKEN` su GHCR, prima creazione/associazione del package, visibilità privata e pull autenticato.
- Push dei due archivi verificati, manifest remoto e alias `latest`/minore, upload reali GitHub, generazione note e transizione draft → release completa.
- Attivazione **manuale** dei ruleset per i tag e delle eventuali release immutabili. Nessuna impostazione remota modificata.
- Firma/notarizzazione e attestazioni non configurate; nessuna credenziale richiesta o simulata. Nessuna distribuzione PyPI.

La guida [RELEASE.md](RELEASE.md) descrive anche il recupero da una pubblicazione parziale senza sovrascrivere tag o versioni già pubblicati. GHCR e GitHub Releases non costituiscono una transazione atomica comune: il workflow non elimina automaticamente pubblicazioni per tentare un rollback.

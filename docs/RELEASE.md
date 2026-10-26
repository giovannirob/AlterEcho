# Build e release da tag

La distribuzione è preparata in `.github/workflows/release.yml`. La versione 1.1.0 è preparata per il tag locale `v1.1.0`, senza push, immagini remote o GitHub Releases. Il primo ciclo di pubblicazione dovrà essere verificato su GitHub dopo un push autorizzato del tag. Il repository e i package mantengono la loro visibilità privata.

## Due workflow

| Evento | `test.yml` | `release.yml` |
| --- | --- | --- |
| Push su main o altro branch, anche solo README | Test Python, frontend e browser | Non parte |
| Pull request | Gli stessi controlli, senza scritture remote | Non parte |
| Tag non relativo a versioni, es. `docs-update` o il vecchio `1.0.0` | Non parte | Non parte |
| Nuovo tag `v1.1.0` | Richiamato dalla release come workflow riutilizzabile | Valida, testa, costruisce e pubblica |
| Tag che supera il filtro ma è invalido, es. `v01.1.0` | Non richiamato | Fallisce nel primo job, senza build |
| Tag cancellato/spostato o versione già pubblicata | Non richiamato | Validazione rifiutata |

Il workflow di pubblicazione non ha `workflow_dispatch`, `pull_request`, trigger sui branch o `workflow_call`. Il filtro GitHub `v[0-9]*.[0-9]*.[0-9]*` è solo un prefiltro: `deploy/release.py` verifica rigorosamente SemVer, evento `push`, `created=true`, `forced=false`, `deleted=false`, versioni e commit effettivo del tag remoto. Sono gestiti tag lightweight e annotati.

La CI ordinaria non invoca `python -m build`, PyInstaller, build Docker, pubblicazione o upload di artifact. Installa il progetto in editable per testare il launcher; non produce distribuzioni in `dist/`. I test Python usano le risorse statiche già versionate; Playwright usa i sorgenti correnti tramite Vite in sviluppo, con API reali e provider simulati. Non dipende da una build frontend di produzione per i test browser.

## Ordine e permessi

```text
validate → tests (CI riutilizzata) → frontend → python
        → standalone (5 runner nativi) → docker-build (2 runner nativi)
        → docker-publish → publish GitHub Release
```

Ogni fase dipende dai successi precedenti. Un test/build/smoke test fallito impedisce la pubblicazione. Le due immagini vengono prima salvate in artifact intermedi con SHA-256 e un record della verifica. Il job di pubblicazione controlla **entrambi** i record prima di inviare immagini; non ricostruisce immagini non testate.

Il token predefinito ha solo `contents: read`. Soltanto `docker-publish` richiede `packages: write`; soltanto `publish` richiede `contents: write`. Si usa il `GITHUB_TOKEN` fornito da Actions: nessun PAT necessario per pubblicare dal workflow, nessuna chiave dei provider, firma o login Codex. Checkout senza credenziali persistenti; Actions ufficiali GitHub/Docker fissate a SHA di commit, da aggiornare con revisione.

Una concurrency globale serializza tutte le release, senza interrompere quella in corso: protegge anche gli alias Docker `latest` e `MAJOR.MINOR`. Non inviare raffiche di tag: GitHub può sostituire un’esecuzione ancora pending con una successiva dello stesso gruppo.

## Versioni senza modifiche automatiche

Prima di creare il tag, prepara e committa versioni coerenti:

| Componente | Stabile | Prerelease di esempio |
| --- | --- | --- |
| Tag Git | `v1.1.0` | `v1.2.0-rc.1` |
| `pyproject.toml` e `alterecho/__init__.py` | `1.1.0` | `1.2.0rc1` |
| `web/package.json` e due campi versione nel lock npm | `1.1.0` | `1.2.0-rc.1` |
| Nome pacchetto Python | `alterecho-1.1.0…` | `alterecho-1.2.0rc1…` |
| Tag Docker specifico | `1.1.0` | `1.2.0-rc.1` |

I pacchetti Python seguono PEP 440; il tag e npm seguono SemVer. Il validatore verifica questa corrispondenza esplicita, e runtime/CLI/server devono dichiarare esattamente la versione del progetto Python. Nessun job riscrive una versione dopo il checkout. Sono supportate le fasi `alpha.N`, `beta.N`, `rc.N`, `dev.N`; altri identificatori SemVer prerelease vengono rifiutati con spiegazione perché non rappresentabili direttamente nella versione Python scelta.

La build metadata SemVer `+build.4` è supportata: il nome Python usa la normalizzazione PEP 440 e il tag Docker sostituisce `+` con `_`, perché `+` non è ammesso nei tag OCI/Docker. La label OCI conserva la versione SemVer originale. Il tag specifico deve rispettare il limite Docker di 128 caratteri.

Le release stabili devono essere crescenti rispetto alle stabili già pubblicate, per non retrocedere `latest`. Sono rifiutati anche un duplicato senza prefisso `v` e qualsiasi release/draft preesistente della medesima versione. Il tag remoto viene ricontrollato prima delle pubblicazioni.

## Matrice e allegati

| Sistema | Runner nativo | Allegato atteso per `v1.1.0` |
| --- | --- | --- |
| Windows x64 | `windows-2022` | `AlterEcho-1.1.0-windows-x64.zip` |
| Linux x64 | `ubuntu-22.04` | `AlterEcho-1.1.0-linux-x64.tar.gz` |
| Linux ARM64 | `ubuntu-22.04-arm` | `AlterEcho-1.1.0-linux-arm64.tar.gz` |
| macOS Apple Silicon | `macos-15` | `AlterEcho-1.1.0-macos-arm64.tar.gz` |
| macOS Intel | `macos-15-intel` | `AlterEcho-1.1.0-macos-x64.tar.gz` |
| Python | `ubuntu-22.04` | `alterecho-1.1.0-py3-none-any.whl`, `alterecho-1.1.0.tar.gz` |

I runner ARM64 standard sono documentati anche per repository privati da [GitHub](https://docs.github.com/en/actions/reference/runners/github-hosted-runners). Disponibilità, policy e minuti del piano restano da verificare nell’account. Se un runner richiesto non è disponibile, la release si ferma: non viene saltata una piattaforma né generato un binario fittizio. Per cambiare le piattaforme supportate, modificare insieme matrice e `PLATFORMS` nel validatore, prima di un nuovo tag e dopo i relativi test.

Ogni eseguibile viene eseguito fuori dal checkout: server foreground, Web statica, CLI HTTP, demo, persistenza, shutdown e nuovo avvio detached. Su Windows viene controllata anche l’assenza di console visibile. Gli archivi contengono il binario e una guida breve; le risorse Web sono incorporate. Non contengono Codex, Ollama, pesi o credenziali.

Linux: i binari sono costruiti su Ubuntu 22.04 con glibc 2.35; richiedono una distribuzione glibc compatibile, non Alpine/musl. Versioni precedenti di glibc non sono supportate da queste build. macOS: non viene configurata firma Developer ID o notarizzazione; Gatekeeper può bloccare il download. Il runner usa macOS 15: compatibilità con versioni precedenti o altri browser/dispositivi va collaudata separatamente. Verificare provenienza e checksum, senza disabilitare globalmente Gatekeeper.

Wheel e sdist vengono installati ciascuno in un virtualenv nuovo: il test verifica server, CLI, statici, provider dichiarati, demo e persistenza senza usare il checkout come modulo. Nessuna pubblicazione PyPI. Gli artifact Actions servono solo tra job e scadono dopo tre giorni; la distribuzione finale è nella GitHub Release.

## Docker / GHCR

Repository immagine: `ghcr.io/giovannirob/alterecho`. Per una stabile vengono pubblicati `1.1.0`, `1.1` e `latest`; per `v1.2.0-rc.1` solo `1.2.0-rc.1`. Le prerelease non aggiornano né `latest` né l’alias minore.

Il Dockerfile mantiene build multistage, Node solo per frontend e runtime Codex, Python headless non root UID 10001, healthcheck, SIGTERM, volumi esterni e `serve --foreground`. Ollama rimane esterno. Codex CLI è fissato alla versione verificata in `deploy/codex-version.txt`; il workflow la passa come build argument. Aggiornare anche i default di Dockerfile/Compose quando si cambia la versione predefinita di sviluppo, e ricollaudare entrambi i target.

Le immagini AMD64/ARM64 sono costruite e avviate su runner nativi distinti. I test invocano soltanto `codex --version` e `codex app-server --help`, mai login o generazioni reali. Le prove HTTP usano la demo. Il manifest multiarch viene creato solo dopo i due successi. Il job controlla architetture, user, command, label, Web/API, healthcheck, salvataggi, restart e shutdown; trasporta e pubblica gli stessi archivi immagine già verificati.

Le label OCI includono `source`, `revision`, `version`, titolo e descrizione. `source` associa il package al repository. Il tag immagine specifico viene controllato su GHCR prima del push e non viene sovrascritto; errori di autenticazione non sono interpretati come immagine assente. I tag `build-RUN-ATTEMPT-ARCH` sono riferimenti intermedi usati per assemblare il manifest e possono rimanere nel package; non sono release raccomandate per l’uso.

Il package nasce con le impostazioni GHCR appropriate all’account/repository; **il workflow non modifica visibilità o policy**. Per pull privati serve autenticazione con un’identità autorizzata. Da Actions si può usare `GITHUB_TOKEN` con `packages: read`; da un computer locale usa il metodo previsto da GitHub, ad esempio un PAT classic con il solo `read:packages` e accesso al repository (SSO se richiesto). Non committare il token:

```sh
# GHCR_READ_TOKEN è una credenziale di lettura caricata in modo protetto.
printf '%s' "$GHCR_READ_TOKEN" | docker login ghcr.io -u IL_TUO_UTENTE --password-stdin
docker pull ghcr.io/giovannirob/alterecho:1.1.0
```

Vedi [autenticazione Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry) e [pubblicazione da Actions](https://docs.github.com/en/actions/use-cases-and-examples/publishing-packages/publishing-docker-images).

## Configurazione manuale GitHub

Prima del primo tag autorizzato:

1. Abilitare Actions e consentire le Actions ufficiali GitHub/Docker fissate nel workflow. Verificare accesso ai cinque runner e minuti disponibili; i repository privati possono consumare minuti fatturabili.
2. Consentire al `GITHUB_TOKEN` i permessi richiesti nei due soli job di pubblicazione (`contents: write`, `packages: write`), nel rispetto delle policy dell’organizzazione. Non configurare chiavi dei provider per i test.
3. Se il package GHCR esiste già ed è stato creato con altre credenziali, assegnare al repository l’accesso Actions di scrittura nelle impostazioni del package. Dopo la prima pubblicazione controllare associazione al repository, visibilità privata e permessi di lettura.
4. Creare un ruleset per i tag `v*`: limitarne la creazione ai manutentori autorizzati, bloccare aggiornamenti forzati e cancellazioni, ridurre i bypass. Proteggere anche le modifiche ai workflow con le normali revisioni del branch. Il prefiltro Actions non sostituisce queste regole.
5. Valutare l’attivazione manuale delle release immutabili. Il workflow carica tutti gli allegati in draft prima di pubblicare, compatibilmente con [le release immutabili GitHub](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).

Non sono state modificate impostazioni remote da questo lavoro. Firma del codice, notarizzazione e attestazioni OIDC sono possibili estensioni future, non simulate né richieste implicitamente.

## Procedura del manutentore

Revisionare e committare il codice completo, incluse versioni e workflow; verificare la CI del commit scelto. Il tag deve puntare a quel commit, non a modifiche presenti soltanto nella working tree.

Aggiornare anche [CHANGELOG.md](../CHANGELOG.md): raccogliere le modifiche in **Non rilasciato** durante lo sviluppo e, quando si prepara una release, assegnare loro la versione e la data prevista. Il changelog è il riepilogo editoriale; le note automatiche GitHub aggiungono i riferimenti alle modifiche del repository. La sola modifica del changelog non pubblica alcuna distribuzione.

```sh
git status
git show HEAD:pyproject.toml
git tag -a v1.1.0 -m "AlterEcho 1.1.0"
git push origin v1.1.0
```

Non occorre creare manualmente la release o caricare gli allegati. Il workflow genera le note con l’API GitHub, aggiunge data, elenco dei file effettivi, immagine/digest e istruzioni. Pubblica come prerelease quando appropriato. `SHA256SUMS.txt` copre tutti i pacchetti/archivi e `release-manifest.json`, che registra versione, commit, piattaforme e digest Docker. Ogni upload viene verificato contro digest e dimensione restituiti da GitHub prima di rimuovere lo stato draft.

## Se la release fallisce

- Prima di qualsiasi pubblicazione: correggere la causa. Per un errore transitorio usare **Re-run failed jobs**, conservando i job riusciti e i loro artifact entro il periodo di retention.
- Errore durante upload GitHub: resta un draft privato identificato da run ID e commit. Il job fallito può riprendere quel solo draft; riutilizza allegati già presenti solo se digest e dimensione coincidono. Non sovrascrive allegati diversi o draft di altre esecuzioni.
- Se GHCR è già stato pubblicato e GitHub Release fallisce: rieseguire il solo job fallito di pubblicazione della release. Non rieseguire i job Docker riusciti: il controllo sulla versione GHCR li rifiuterebbe. Le due piattaforme non offrono una transazione atomica comune; il workflow non cancella automaticamente immagini o release per tentare rollback.
- Se gli artifact sono scaduti, una build deve cambiare o un tag punta al commit errato: preparare una **nuova versione e un nuovo tag**. Non spostare o riscrivere tag già pubblicati. L’eventuale rimozione di un draft fallito o di riferimenti intermedi è un’operazione manuale da revisionare; una release pubblicata rimane intatta.

## Verifica locale senza pubblicare

```sh
python -m pip install -e '.[dev]'
python -m unittest tests.test_release -v
python -m unittest discover -q
cd web
npm run check
npm test
# impostare ALTERECHO_BROWSER_DEV=1 nell'ambiente per evitare la build Vite:
npm run test:e2e
cd ..
python -m build
python deploy/check-package.py --clean-install
python -m PyInstaller --noconfirm deploy/alterecho.spec
python deploy/check-standalone.py dist/alterecho.exe
```

Su Linux/macOS l’eseguibile è `dist/alterecho`. I comandi `publish-docker` e `publish-release` non sono test locali: scrivono su servizi remoti e non vanno invocati senza autorizzazione. I test usano client fittizi per queste operazioni. Nessun tag di prova è necessario per verificare trigger, normalizzazione versioni, DAG dei job, duplicati, checksum, upload parziali e protezioni.

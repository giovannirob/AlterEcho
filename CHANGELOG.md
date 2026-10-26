# Changelog

Le modifiche sono raccolte per versione. Un tag Git locale non indica una pubblicazione su GitHub Releases o GHCR. Questo registro parte dalla versione 1.0.0.

## 1.1.0 — 2026-10-26

Versione preparata per il tag Git locale `v1.1.0`; nessun push o caricamento su GitHub Releases/GHCR eseguito. La pubblicazione automatica richiederà un successivo push autorizzato del tag.

### Aggiunte

- Avvio del server in background con verifica HTTP autenticata, log persistenti e controllo dell'identità dell'istanza; comando `alterecho down` per l'arresto locale ordinato.
- Chat Web con messaggi distinti per interlocutore, Markdown progressivo sanitizzato, copia, ricerca, dettagli e navigazione verso l'ultimo messaggio.
- Selettori di modelli dai cataloghi dei profili, filtro e gestione dei modelli non disponibili; modali di riepilogo e conferma per avvio, ripresa ed eliminazione.
- Workflow di release attivato soltanto dal push di un nuovo tag di versione valido: validazione, test, frontend, pacchetti Python, standalone nativi, Docker, GHCR e GitHub Release automatica.
- Matrice di build predisposta per Windows x64, Linux x64/ARM64 e macOS ARM64/Intel, con verifica degli eseguibili fuori dal checkout.
- Immagini Docker AMD64/ARM64 con versione Codex fissata, label OCI e manifest multiarch subordinato al collaudo di entrambe le immagini.
- Archivi versionati, checksum SHA-256 e manifest di release; controlli contro versioni incoerenti, duplicati, tag spostati e sovrascritture.
- Configurazione `compose.registry.yaml` per immagini GHCR private già pubblicate e guida alla distribuzione da tag.

### Modifiche

- `alterecho serve` avvia il server in background per impostazione predefinita; `--detach` resta un alias e `--foreground` è l'opzione per diagnostica, container e supervisori.
- Streaming CLI con riquadro aggiornabile durante il turno e output completo per pipe/file; recupero degli eventi condiviso con il backend.
- Auto-scroll della Web UI rispettoso della posizione di lettura, con ripristino durante la navigazione e controlli compatti.
- CI ordinaria separata dalla distribuzione: test Python, frontend e browser tramite Vite in sviluppo, senza build distribuibili o pubblicazioni.
- Versioni di progetto, runtime e frontend validate rispetto al tag, incluse le prerelease; versione visualizzata nella Web UI derivata dal pacchetto npm.
- Packaging verificato tramite installazioni pulite separate di wheel e sdist, con asset Web inclusi e prove fuori dal repository.
- Documentazione aggiornata per server gestito, CLI, chat, servizi, download, GHCR e recupero delle release fallite.

### Correzioni

- Eliminata la console Python separata visibile durante l'avvio in background su Windows; la chiusura del client non arresta il server.
- Deduplicazione dei messaggi e dei frammenti durante riconnessione SSE e ripresa di `watch`, con risoluzione coerente degli ID.
- Normalizzazione delle radici temporanee nei test Windows/macOS per percorsi equivalenti, inclusi nomi brevi Windows e collegamenti `/var`/`/private/var`.

### Verifiche e limiti

La revisione locale comprende 150 test Python, 11 frontend e 12 browser superati, senza inferenze AI reali. Standalone Windows/Linux x64 e immagini Docker sono stati provati localmente; Docker ARM64 è stato eseguito in emulazione. Restano da verificare i runner nativi macOS/Linux ARM64 e la pubblicazione effettiva su GitHub/GHCR. Le build macOS non sono firmate o notarizzate.

Dettagli: [verifica applicativa 1.1](docs/VERIFICA-1.1.md), [verifica della distribuzione](docs/VERIFICA-RELEASE.md) e [guida release](docs/RELEASE.md).

## 1.0.0 — 2026-10-24

Versione registrata nel tag Git `1.0.0`. La presenza del tag non implica la disponibilità di allegati GitHub Releases o immagini GHCR.

### Aggiunte e modifiche

- Unico server headless FastAPI/Uvicorn, proprietario delle conversazioni e della persistenza; CLI Rich e Web UI Svelte/TypeScript come client delle stesse API versionate e SSE.
- Gestione centralizzata di avvio, arresto, pausa, ripresa, streaming, statistiche, cronologia ed esportazione; le generazioni continuano quando i client si scollegano.
- Supporto preservato a Codex CLI con ChatGPT, Ollama, OpenAI API e OpenRouter, con profili e conferme per le API a consumo.
- Compatibilità con JSON precedenti, checkpoint e sessioni Codex, scritture atomiche ed esportazioni Markdown, TXT e HTML offline.
- Autenticazione, binding locale predefinito, controlli delle origini e degli host, validazione degli input e limitazione delle richieste.
- Packaging Python, build standalone Windows, Docker multistage e template per servizi Windows, systemd e launchd.

Il [resoconto storico 1.0](docs/VERIFICA-1.0.md) documenta le prove e i limiti della revisione prima della creazione del tag; non attesta il superamento della CI remota.

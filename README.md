# AlterEcho

Un coordinatore Python che inoltra automaticamente i messaggi fra **Codex, con accesso ChatGPT**, e **Ollama locale**. Interfaccia terminale Rich, tre modalità, memoria del dialogo, arresto con Ctrl+C e salvataggio JSON/Markdown/TXT. Non usa l'SDK OpenAI, non chiama direttamente le API OpenAI e non richiede API key.

## Avvio sul computer attuale

L'ambiente `.venv` è già installato. Apri PowerShell nella cartella di questo progetto:

```powershell
.\.venv\Scripts\python.exe -m alterecho doctor
.\.venv\Scripts\python.exe -m alterecho run
```

Seleziona **qwen3.5:9b**, scegli un modello Codex dal catalogo, inserisci argomento e ruoli, scegli chi comincia e il numero massimo di messaggi, quindi premi Invio. Il programma alterna gli interlocutori fino al limite. `Ctrl+C` interrompe e salva lo storico. Non serve attivare il virtualenv né cambiare le policy PowerShell.

Il primo comando verifica autenticazione e connessioni senza generare messaggi. Il secondo avvia la configurazione interattiva e genera soltanto dopo l'Invio finale.

Alternative: `powershell -File .\start.ps1 run`, oppure `.\.venv\Scripts\alterecho.exe run`.

### Primo test reale

Il test di **due messaggi totali** è stato eseguito dopo l'approvazione dell'utente: apertura `gpt-6.1-sol`, risposta `qwen3.5:9b`, completamento riuscito. Codex ha impiegato circa 9 secondi, Qwen circa 62 secondi (24 token/s durante la generazione). Anche la riapertura del thread Codex e il confronto dell'ultima risposta salvata sono riusciti, senza ulteriori generazioni. Dettagli in `outputs/TEST-REALE.md`.

```powershell
.\.venv\Scripts\python.exe -m alterecho run --config smoke-test.toml
```

Per ripetere la prova, scegli Qwen 9B e un modello Codex disponibile, mantieni `2` come limite e premi Invio. Questo test verifica il primo inoltro reale; un terzo messaggio richiederebbe un turno Codex aggiuntivo per verificare anche il ritorno reale. I cicli in entrambe le direzioni sono già verificati con simulazioni.

## Installazione Windows

Prerequisiti: Python 3.11+, Ollama in esecuzione e Codex CLI recente con `app-server --strict-config`. La versione concretamente verificata è `0.162.0-alpha.17.2`; le versioni precedenti non sono tutte compatibili con i flag di sicurezza usati. Node serve solo se usi la distribuzione npm della CLI.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
codex login
ollama list
.\.venv\Scripts\python.exe -m alterecho doctor
```

`codex login` va eseguito solo se non hai già effettuato l'accesso: scegli ChatGPT, non API key. Installa Codex seguendo le [istruzioni ufficiali CLI](https://learn.chatgpt.com/docs/cli). Se Qwen non è installato, scaricalo esplicitamente con `ollama pull qwen3.5:9b` oppure `ollama pull qwen3.5:4b`. AlterEcho non avvia download da solo.

Se compare un errore sulla directory utente, puoi indicare `codex_home` nel TOML con il percorso della tua directory Codex esistente. Su Windows, se `CODEX_HOME` manca, AlterEcho passa al solo processo figlio `%USERPROFILE%/.codex`. Non legge `auth.json` e non copia credenziali. Codex deve poter scrivere i propri file di sessione in quella directory. Un terminale normale dell'utente è sufficiente; non serve avviare il programma come amministratore.

Se `codex` manca dal PATH, AlterEcho cerca automaticamente anche `codex.exe` nelle directory dell'app desktop Windows, sotto `%LOCALAPPDATA%/OpenAI/Codex/bin`. Per altre installazioni imposta `codex_binary` nel TOML con il percorso completo; usa slash `/` oppure una stringa TOML fra apici singoli per i percorsi Windows. Un override esplicito errato genera un errore, senza scegliere silenziosamente un altro binario.

## Installazione Linux

Installa Python 3.11+ con il modulo venv, Codex CLI e Ollama. Avvia il servizio locale Ollama (oppure `ollama serve` se non è già attivo), poi:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
codex login
ollama list
.venv/bin/python -m alterecho doctor
.venv/bin/python -m alterecho run
# Alternativa senza attivazione:
sh start.sh run
```

Il codice usa API Python e trasporti multipiattaforma. Linux è predisposto ma **non testato su un host Linux durante questa sessione**.

## Configurazione

`config.example.toml` documenta i parametri. Copialo come `config.toml` e personalizzalo:

```powershell
.\.venv\Scripts\python.exe -m alterecho run --config config.toml
```

Il selettore Codex usa `model/list`, con paginazione. Non contiene nomi di modelli hardcoded. La presenza nel catalogo CLI può riflettere cache e non prova l'accesso o le quote per una futura richiesta: l'inferenza reale resta la verifica finale. Anche il livello di ragionamento viene scelto fra quelli dichiarati dal modello.

Per un'esecuzione senza domande, imposta un `codex_model` dal catalogo e usa:

```powershell
.\.venv\Scripts\python.exe -m alterecho run --config config.toml --non-interactive
```

Questo comando avvia **inferenza reale immediatamente**. `--turns 6` può sovrascrivere il massimo del file. Un turno è **un messaggio prodotto**, non una coppia: 6 messaggi = 3 risposte per interlocutore.

Parametri principali:

| Parametro | Significato |
| --- | --- |
| `mode` | `free`, `debate`, `blind` |
| `first` | `codex` oppure `ollama` |
| `roles` | Personalità individuali, facoltative |
| `positions` | Posizioni iniziali distinte per il dibattito |
| `max_turns`, `delay`, `timeout` | Limite messaggi, pausa e timeout per generazione |
| `num_ctx` | Contesto configurato Ollama |
| `num_predict` | Massimo token di generazione Ollama |
| `temperature`, `ollama_options` | Sampling Ollama, ad esempio `top_p`, `seed`, `repeat_penalty` |
| `codex_effort` | Ragionamento Codex, validato rispetto al catalogo |
| `output_dir` | Directory dei salvataggi |

Codex non espone qui un controllo affidabile sulla temperature o un equivalente universale di `num_predict`: non vengono inventati. Il prompt invita a risposte brevi, ma non è un limite rigido dei token Codex.

Per GTX 1070 e 16 GB RAM i valori iniziali sono `num_ctx=4096`, `num_predict=512`, ragionamento Codex basso e `think=false` per Qwen. Nel test breve il 9B ha generato a circa 24 token/s, ma il turno completo ha richiesto circa 62 secondi; il tempo include attesa e caricamento, che non sono stati profilati separatamente. Non è stata misurata la capienza VRAM: scegli 4B se il 9B risulta lento o usa molta RAM. AlterEcho carica soltanto il modello Ollama scelto, scarica dalla memoria gli altri modelli già residenti prima del dialogo e richiede `keep_alive=0` a ogni risposta. Questo riduce l'occupazione ma comporta ricaricamenti fra i turni; altre applicazioni Ollama possono interferire e vanno chiuse se vuoi uso esclusivo.

## Memoria e ruoli

Il JSON locale è lo storico canonico. Ogni messaggio contiene interlocutore, modello, timestamp UTC ISO 8601, testo completo, durata e usage quando disponibile.

- **Codex:** un thread persistente mediante `thread/start` e `thread/resume`. Ogni `turn/start` contiene soltanto l'ultimo messaggio dell'altro interlocutore. La cronologia già presente nel thread non viene reinviata. Il primo turno riceve un breve invito ad aprire il dialogo.
- **Ollama:** `/api/chat` riceve una sola istruzione di sistema e l'intera cronologia canonica. Le risposte proprie sono `assistant`, quelle Codex sono `user`. Se Ollama comincia, viene preservato anche il suo invito iniziale. Ollama non ha bisogno di tenere il modello caricato per ricordare: la memoria viene ripristinata dalla cronologia.

L'inoltro usa il testo esatto delle risposte. Tempi, nomi dei modelli e contatori appartengono al log e all'interfaccia, non vengono aggiunti ai messaggi inoltrati. Le istruzioni di ruolo e argomento vengono configurate separatamente. La modalità cieca omette ogni dichiarazione esplicita dell'identità dell'interlocutore; evita di inserire tu stesso nomi dei modelli nell'argomento o nei ruoli. Non impedisce ai modelli di dichiarare spontaneamente la propria identità.

## Salvataggio, esportazione e ripresa

Il percorso viene mostrato all'avvio. I file si trovano normalmente in `outputs/conversations/UUID.json`, insieme a `.md` e `.txt`. JSON viene aggiornato atomicamente con flush/fsync dopo ogni risposta e prima del successivo turno. Durante lo streaming vengono salvati anche i parziali ricevuti, circa ogni mezzo secondo; Ctrl+C salva nuovamente i parziali già ricevuti. Un'interruzione brutale dell'alimentazione può perdere gli ultimi frammenti non ancora salvati, non i messaggi già confermati.

```powershell
.\.venv\Scripts\python.exe -m alterecho export outputs/conversations/UUID.json
.\.venv\Scripts\python.exe -m alterecho resume outputs/conversations/UUID.json --turns 20
# Se Ollama segnala il limite reale del contesto, puoi aumentarlo:
.\.venv\Scripts\python.exe -m alterecho resume outputs/conversations/UUID.json --turns 20 --num-ctx 8192
```

`--turns 20` è il nuovo massimo **totale**, compresi i messaggi precedenti. La ripresa richiede la stessa sessione locale Codex, lo stesso account, il modello disponibile e i file del thread ancora esistenti. Non usare il thread Codex da altre applicazioni e non avviare due coordinatori sullo stesso JSON.

`--num-ctx` modifica solo il contesto Ollama nella configurazione salvata: i messaggi e il thread Codex vengono preservati. Il nuovo valore viene validato e confrontato con il limite dichiarato dal modello. La ripresa avvia inferenza reale. Puoi usare `run --num-ctx 8192` anche per un nuovo dialogo; nel menu interattivo sono disponibili contesto e massimo token per risposta. Valori maggiori possono usare più RAM/VRAM. Il numero massimo di messaggi resta soggetto ai limiti reali dei modelli.

La ripresa verifica l'ultimo ID di turno e il testo dell'ultima risposta Codex. Se Codex ha completato un turno ma il coordinatore è stato interrotto prima di salvarne il risultato, recupera il messaggio dal thread soltanto quando input, ID e stato corrispondono. Se l'interruzione è avvenuta durante Ollama, può riprovare usando lo storico salvato; la vecchia risposta parziale resta disponibile nei file fino al completamento della nuova.

**Limite esplicito:** un turno Codex rimasto incompleto o interrotto non viene reinviato automaticamente. La sessione contiene già quell'input e reinviarlo rischierebbe duplicazioni: AlterEcho conserva i dati e rifiuta la ripresa. Avvia un nuovo dialogo. Non simula la continuità creando segretamente una nuova conversazione. Un thread completamente vuoto, prima di qualsiasi turno Codex, viene invece ricreato: la CLI verificata non persiste ancora un rollout per i thread senza turni.

## Contesto, statistiche ed errori

Lo storico non viene mai eliminato o riassunto automaticamente. È stata rimossa la guardia preventiva che usava i byte UTF-8 come stima dei token: non ci sono più arresti basati su quella stima. AlterEcho inoltra a Ollama lo storico completo e invia `truncate=false` e `shift=false` per chiedere al runtime di segnalare il limite reale invece di eliminare messaggi o spostare il contesto. Questi campi sono stati verificati nel [protocollo ufficiale Ollama 0.40.3](https://github.com/ollama/ollama/blob/v0.40.3/api/types.go), la versione installata sull'host; il loro supporto su versioni precedenti non è stato verificato. Ollama verifica anche il contesto dichiarato in `/api/show`. Codex conserva il proprio thread e vengono controllati i dati reali di usage quando esposti. Il vecchio campo `codex_context_budget` viene ancora accettato per aprire configurazioni e salvataggi precedenti, ma non applica più un limite.

Un evento di compattazione Codex o di contesto esaurito arresta il dialogo. Una risposta Ollama al limite `num_predict` viene conservata come parziale e non inoltrata. Aumenta i limiti consapevolmente; non c'è uno sliding window che scarta silenziosamente vecchi messaggi.

La UI mostra testo, modello, durata, contatore e connessioni. I token Ollama provengono da `prompt_eval_count`/`eval_count`; i token/s usano `eval_duration`, escludendo il caricamento. Codex usa `thread/tokenUsage/updated` quando ricevuto, senza attribuirgli una velocità di decoding inesistente. Le statistiche finali sommano i campioni rilevati; zero campioni significa dato non disponibile, non zero consumo. Il conteggio input ripetuto Ollama misura lavoro elaborato, non token unici del dialogo.

Timeout, errori HTTP, EOF dello stream, errori RPC, autenticazione, quote o richieste di strumenti fanno arrestare il coordinatore. Non sono previsti retry automatici del coordinatore; la CLI può fare tentativi interni limitati, sempre soggetti al timeout applicativo. Ctrl+C tenta `turn/interrupt` e chiude il processo app-server. Codici di uscita: 0 completamento, 1 errore/arresto, 130 interruzione manuale.

## Sicurezza e autenticazione

Codex app-server usa l'autenticazione ChatGPT già gestita dalla CLI. AlterEcho controlla `account/read` e rifiuta account API key e provider alternativi; rimuove dal processo figlio `OPENAI_API_KEY`, `CODEX_API_KEY` e l'override `OPENAI_BASE_URL`. Non legge token, non li esporta e non modifica il login. Il programma non compra crediti e non invoca strumenti di fatturazione o ripristino quote. L'accesso e le quote restano quelli del tuo account Codex/ChatGPT.

Il processo Codex riceve istruzioni da interlocutore, una directory di lavoro vuota, sandbox `read-only`, approvazioni `never`, strumenti shell/unified exec disabilitati, insieme a browser, computer use, plugin, app, agenti, ricerca, immagini, hook e MCP ereditati disabilitati. Le richieste RPC provenienti dal server vengono rifiutate; elementi di turno diversi da testo/ragionamento arrestano la conversazione. `--strict-config` fa fallire l'avvio se la CLI non riconosce impostazioni invece di ignorarle. Le configurazioni personali non vengono riscritte.

Questa è una restrizione del normale harness Codex, **non un contenitore OS senza accesso in lettura all'intero disco**: il processo CLI continua a gestire i propri file di autenticazione/sessione. Non si dichiara un isolamento assoluto contro bug del runtime. Le operazioni di scrittura e i comandi del dialogo vengono disabilitati senza utilizzare permessi `danger-full-access`.

Ollama accetta esclusivamente URL HTTP loopback; proxy ambientali e redirect non sono usati. AlterEcho non apre listener e non modifica `OLLAMA_HOST`. Open WebUI non è una dipendenza. Le istruzioni di sistema trattano i messaggi dell'altro interlocutore come contenuto non attendibile; il coordinatore non interpreta né esegue il testo generato. La UI neutralizza i controlli terminale per la visualizzazione; il testo salvato e inoltrato resta integrale.

## Struttura e test

```text
alterecho/
  adapters/base.py       interfaccia comune e Reply
  adapters/codex.py      app-server, JSON RPC, thread, autenticazione
  adapters/ollama.py     chat HTTP in streaming e memoria
  coordinator.py        alternanza e arresto
  history.py            messaggi, istruzioni e ruoli
  config.py             TOML e validazione
  stats.py              statistiche
  storage.py            salvataggi atomici ed esportazioni
  ui.py                 terminale Rich
  cli.py                avvio, doctor, demo, resume, export
tests/                  test unittest e server RPC simulato
```

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe -m alterecho demo --turns 4
```

Su Linux usa `.venv/bin/python` negli stessi comandi. Tutti i test automatici usano mock/fixture locali, non eseguono inferenza Codex o Ollama. `tests/fake_server.py` verifica anche il trasporto stdio strutturato senza lanciare la CLI reale.

## Decisioni tecniche e fonti

È stato scelto app-server perché permette controllo esplicito del ciclo, thread e notifiche JSON senza dipendere da Node per il coordinatore. Il [Codex SDK ufficiale](https://learn.chatgpt.com/docs/codex-sdk) è un'alternativa TypeScript; [codex exec](https://learn.chatgpt.com/docs/non-interactive-mode) offre eventi JSON e `exec resume` per continuare sessioni, ma non è l'adapter implementato. La CLI installata conferma `codex exec resume --help`; nessun comando `exec` di inferenza è stato lanciato.

Fonti consultate il 12 ottobre 2026:

- [App-server: protocollo, sessioni, modello e autenticazione](https://learn.chatgpt.com/docs/app-server).
- [Autenticazione Codex](https://learn.chatgpt.com/docs/auth).
- [Riferimento configurazione Codex](https://learn.chatgpt.com/docs/config-file/config-reference).
- [Ollama `/api/chat`](https://docs.ollama.com/api/chat).
- [Ollama: memoria, contesto e keep_alive](https://docs.ollama.com/faq).

La verifica locale degli schemi generati dalla CLI è stata usata insieme alla documentazione per evitare di inventare parametri. I risultati effettivamente eseguiti e i controlli ancora da fare sono riportati in `outputs/VERIFICA.md`.

## Nome e compatibilità

Il progetto e il pacchetto si chiamano **AlterEcho**. Il comando principale è `python -m alterecho`, oppure `alterecho` dopo l'installazione. I comandi precedenti `python -m ai_bridge` e `ai-bridge` restano disponibili come alias. I JSON salvati sono compatibili e possono essere ripresi ed esportati senza modificare il testo dei messaggi. La cartella del checkout può mantenere un nome diverso: `AlterEcho.code-workspace` mostra il nuovo nome in VS Code senza spostare il virtualenv.

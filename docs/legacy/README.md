> Documento della versione 0.3, conservato come riferimento storico. I comandi operativi attuali sono descritti nel README principale.

# AlterEcho

Fai conversare **due modelli** automaticamente, dal terminale. Scegli gli interlocutori, assegna un argomento e osserva il dialogo.

La configurazione predefinita usa Codex con accesso ChatGPT e Ollama locale, senza API key OpenAI. Puoi aggiungere profili OpenAI e OpenRouter se scegli di usare le rispettive API con una tua chiave e relativa fatturazione. Le conversazioni mantengono lo storico e vengono salvate in JSON, Markdown, TXT e HTML.

## Avvio

Se AlterEcho è già installato, apri un terminale in qualsiasi cartella:

```powershell
alterecho
```

Il menu principale è organizzato così:

| Voce | Cosa fa |
| --- | --- |
| **1. Nuova conversazione** | Scegli i due modelli, l'argomento e il massimo dei messaggi |
| **2. Archivio conversazioni** | Riprendi, elimina o visualizza in HTML una chat salvata |
| **3. Impostazioni** | Configura dialogo, adapter, parametri, limiti e salvataggi |
| **0. Esci** | Chiude il programma |

Per iniziare, scegli **1**, seleziona un modello Ollama già disponibile e un modello Codex mostrato nel catalogo, inserisci argomento e limite, poi conferma il riepilogo. Per una prova breve imposta **2 messaggi totali**.

Un messaggio è una risposta di un modello: **10 messaggi = 5 risposte ciascuno**. La generazione inizia solo dopo la conferma; `n` annulla. Le scelte confermate vengono ricordate.

Durante il dialogo, **Ctrl+C** interrompe e salva le risposte e i parziali ricevuti. Il programma torna al menu; Ctrl+C nel menu principale esce.

## Installazione

Serve **Python 3.11+**. Per gli interlocutori predefiniti servono **Codex CLI compatibile con app-server** con accesso ChatGPT e **Ollama** in esecuzione, normalmente su `http://localhost:11434`. Open WebUI è facoltativo. Con una coppia di adapter diversa servono solo i servizi selezionati.

Prima dell'uso, installa in Ollama il modello locale che vuoi utilizzare. Ad esempio:

```sh
ollama pull nome-modello
```

AlterEcho non scarica modelli da solo. Per configurare l'accesso Codex, usa `codex login` e scegli ChatGPT.

### Windows

Dalla cartella del progetto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
powershell -ExecutionPolicy Bypass -File .\install-user.ps1
```

Lo script chiede conferma e installa il comando nel **PATH utente**, senza privilegi amministrativi. Apri una nuova PowerShell; se VS Code o Windows Terminal era già aperto, riavvialo.

Senza installazione globale puoi usare `.\.venv\Scripts\alterecho.exe`.

### Linux

Dalla cartella del progetto:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
sh install-user.sh
```

Accetta l'installazione e apri un nuovo terminale. Il comando viene creato in `~/.local/bin`; i profili Bash/Zsh vengono aggiornati con il tuo consenso. Senza installazione globale usa `.venv/bin/python -m alterecho`.

Linux è predisposto, ma non è stato verificato su un host Linux.

### Verifica e aggiornamento

```sh
alterecho doctor
```

`doctor` controlla Codex/ChatGPT, Ollama e i cataloghi, senza generare risposte.

Per aggiornare su Windows, dalla cartella del progetto ripeti `.\.venv\Scripts\python.exe -m pip install -e .` e `install-user.ps1`; su Linux ripeti i comandi di installazione del pacchetto e del launcher. **Se sposti la cartella, ricrea il virtualenv e reinstalla il launcher.**

## Impostazioni e salvataggi

Le **Impostazioni** sono divise in quattro sezioni:

| Sezione | Opzioni |
| --- | --- |
| **Conversazione** | Modalità, personalità e chi inizia |
| **Modelli e adapter** | Profili e integrazioni, Codex, parametri Ollama |
| **Esecuzione e salvataggi** | Numero di messaggi, timeout, ritardo e cartella delle chat |
| **Diagnostica e manutenzione** | Verifica connessioni e ripristino delle impostazioni |

Dopo una modifica resti nella stessa sezione. Usa **0** per tornare al livello precedente.

| File | Windows | Linux, percorsi predefiniti |
| --- | --- | --- |
| Impostazioni | `%APPDATA%\AlterEcho\config.json` | `~/.config/alterecho/config.json` |
| Conversazioni | `Documenti\AlterEcho\conversations` (cartella Documenti di Windows, anche reindirizzata) | `$XDG_DOCUMENTS_DIR/AlterEcho/conversations`, oppure `~/Documents/AlterEcho/conversations` |

La cartella dei salvataggi è modificabile dal menu. Per ogni nuova chat viene creata una sottocartella con il suo ID, che contiene JSON ed esportazioni `.md`, `.txt` e `.html`. Tutti i file vengono aggiornati dopo ogni risposta e alla chiusura della chat. Riprendere una conversazione aggiorna gli stessi file con i nuovi messaggi. Il percorso viene mostrato nel terminale. Gli storici precedenti salvati direttamente nella cartella vengono ancora rilevati.

Su macOS il percorso predefinito è `~/Documents/AlterEcho/conversations`. I vecchi salvataggi in AppData o nella directory dati Linux restano individuabili; il precedente percorso predefinito nelle preferenze passa a Documenti. Le cartelle personalizzate restano valide. `ALTERECHO_HOME` conserva il comportamento portatile con salvataggi in `data/conversations`.

L'HTML è un singolo file autonomo: CSS, JavaScript e messaggi sono incorporati, quindi puoi copiarlo e aprirlo offline in un browser. Offre tema scuro/chiaro, ricerca nei messaggi, copia di messaggi e codice, navigazione e statistiche. Non carica risorse dalla rete; i link esterni si aprono solo se cliccati.

Per leggerlo scegli **Archivio conversazioni → Visualizza in HTML** e seleziona la chat: il programma rigenera il file e lo apre nel browser. Digita nella barra di ricerca per evidenziare e filtrare i messaggi, oppure usa **Tema chiaro / Tema scuro** per cambiare aspetto. Se avevi già aperto il file durante una continuazione, ricarica la pagina per vedere gli aggiornamenti.

## Adapter e provider API

Apri **Impostazioni → Modelli e adapter → Adapter e integrazioni → Aggiungi adapter**. Puoi creare profili Codex CLI, Ollama locale, OpenAI API e OpenRouter API. Per ogni profilo scegli un nome, il modello preferito facoltativo e l'eseguibile o l'endpoint locale, quando pertinente. Puoi poi modificarlo, rimuoverlo e selezionarlo in **Scegli interlocutori A e B**. Codex CLI occupa la posizione A; è consentito un solo adapter Ollama per conversazione.

I profili sono in `adapters.json`, accanto alle impostazioni. Le chiavi API non vanno inserite nel menu: indica soltanto il nome della variabile d'ambiente, normalmente `OPENAI_API_KEY` o `OPENROUTER_API_KEY`, e impostala nel terminale prima di avviare AlterEcho. Gli endpoint API sono quelli ufficiali. Nessun adapter viene installato o autenticato automaticamente; non si acquistano crediti. Il riepilogo segnala l'uso di provider API prima dell'avvio; **Limite token delle risposte API** regola il massimo richiesto senza cambiare il ragionamento dei modelli.

Le chat salvano una copia della configurazione dei due interlocutori, senza il valore delle chiavi: cambiare un profilo non cambia gli storici. Le API ricevono a ogni turno la cronologia completa con i ruoli corretti; Codex conserva il proprio thread. **Torna a Codex e Ollama predefiniti** ripristina la coppia iniziale. La diagnostica consulta i cataloghi della coppia selezionata senza generare risposte.

OpenAI e OpenRouter sono provider di modelli, non server MCP. MCP serve a collegare strumenti e risorse: questa versione non collega server MCP e non esegue strumenti nei dialoghi. Claude Code non è ancora un adapter implementato. Riferimenti: [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create), [OpenRouter](https://openrouter.ai/docs/quickstart).

**Riprendi conversazione** elenca anche gli storici nella precedente `outputs/conversations` del progetto. Verifica la sessione Codex prima di chiedere conferma: un thread mancante o incompleto può impedire la ripresa. Gli storici demo non si riprendono con modelli reali.

## Memoria Ollama

Il modello locale rimane caricato tra i turni con `ollama_keep_alive = -1` per impostazione predefinita. In **Impostazioni → Modelli e adapter → Parametri Ollama** puoi scegliere `-1` (senza scadenza), `"10m"`, `"5m"` o `0` (scarica dopo ogni risposta). Le configurazioni precedenti ricevono i nuovi valori predefiniti senza riscrivere gli storici. Ollama può comunque liberare memoria o ricaricare un modello per esigenze del runtime.

**Scarica il modello alla fine della conversazione** (`ollama_unload_on_exit`, predefinito `true`) è una richiesta prudente. L'API condivisa non permette di verificare se un'altra applicazione usa lo stesso modello: in questo caso AlterEcho omette lo scaricamento e lo segnala. Protegge anche i modelli già residenti e non scarica altri modelli all'avvio. Con `-1` il modello può quindi restare caricato anche dopo la chat; scegli una durata temporizzata se vuoi una scadenza, oppure esegui `ollama stop NOME_MODELLO` quando nessun'altra applicazione lo usa.

Per controllare durante un dialogo usa `ollama ps` da un secondo terminale: il modello deve rimanere nell'elenco durante i turni Codex. Puoi anche interrogare `http://localhost:11434/api/ps` (PowerShell: `Invoke-RestMethod http://localhost:11434/api/ps`). I nuovi messaggi mostrano separatamente caricamento e generazione quando Ollama fornisce le durate; un piccolo tempo di caricamento non è, da solo, prova di un ricaricamento completo. Riferimento: [gestione ufficiale keep_alive](https://docs.ollama.com/faq).

## Guida e comandi

```sh
alterecho help
alterecho help run
```

Puoi usare anche `--help`, per esempio `alterecho resume --help`.

| Comando | Uso |
| --- | --- |
| `alterecho run` | Nuovo dialogo con selezione e conferma |
| `alterecho doctor` | Diagnostica senza generazione |
| `alterecho demo --turns 4` | Simulazione locale, senza modelli o quote |
| `alterecho run --config config.toml` | Usa una configurazione TOML personalizzata |
| `alterecho resume chat.json --turns 20` | Ripresa avanzata fino a **20 messaggi totali**, inclusi quelli salvati |
| `alterecho export chat.json` | Rigenera Markdown, TXT e HTML accanto al JSON |
| `alterecho export chat.json --format html` | Genera soltanto l'HTML |

Per preparare un TOML parti da [config.example.toml](../../config.example.toml). `run --non-interactive` avvia subito la generazione con la configurazione scelta; anche il comando avanzato `resume` genera dopo le verifiche, senza la conferma del menu. L'esportazione di chat esistenti non contatta i modelli e non modifica il JSON canonico.

## Se qualcosa non funziona

- **Comando non trovato:** apri un nuovo terminale o ripeti l'installazione del launcher.
- **Errore di connessione o accesso:** esegui `alterecho doctor`; verifica Ollama e il login ChatGPT in Codex.
- **Limite di contesto o risposta:** lo storico resta salvato. Regola i parametri appropriati o avvia un nuovo dialogo; la memoria non viene tagliata automaticamente.
- **Ripresa rifiutata:** leggi il motivo mostrato. Non usare contemporaneamente la stessa chat o il suo thread Codex da altre applicazioni.

Per struttura del progetto, funzionamento degli adapter, sicurezza, configurazione avanzata e test, leggi [ARCHITETTURA.md](ARCHITETTURA.md).

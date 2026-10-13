# AlterEcho

Fai conversare **Codex e un modello Ollama** automaticamente, dal terminale. Scegli i modelli, assegna un argomento e osserva il dialogo.

Codex usa il tuo accesso ChatGPT e le relative quote; Ollama gira sul computer. Non serve una API key OpenAI. Le conversazioni mantengono lo storico e vengono salvate in JSON, Markdown, TXT e HTML.

## Avvio

Se AlterEcho è già installato, apri un terminale in qualsiasi cartella:

```powershell
alterecho
```

Il menu offre sei scelte:

| Voce | Cosa fa |
| --- | --- |
| **1. Nuova conversazione** | Scegli i due modelli, l'argomento e il massimo dei messaggi |
| **2. Riprendi conversazione** | Seleziona una chat salvata e quanti messaggi aggiungere |
| **3. Elimina conversazione** | Sceglie una chat salvata e, dopo conferma, elimina i file JSON, Markdown, TXT e HTML associati |
| **4. Visualizza in HTML** | Seleziona una chat: l'HTML viene aggiornato e aperto nel browser |
| **5. Impostazioni** | Configura modalità, personalità, parametri, limiti e salvataggi |
| **6. Esci** | Chiude il programma |

Per iniziare, scegli **1**, seleziona un modello Ollama già disponibile e un modello Codex mostrato nel catalogo, inserisci argomento e limite, poi conferma il riepilogo. Per una prova breve imposta **2 messaggi totali**.

Un messaggio è una risposta di un modello: **10 messaggi = 5 risposte ciascuno**. La generazione inizia solo dopo la conferma; `n` annulla. Le scelte confermate vengono ricordate.

Durante il dialogo, **Ctrl+C** interrompe e salva le risposte e i parziali ricevuti. Il programma torna al menu; Ctrl+C nel menu principale esce.

## Installazione

Servono **Python 3.11+**, **Codex CLI compatibile con app-server** con accesso ChatGPT e **Ollama** in esecuzione, normalmente su `http://localhost:11434`. Open WebUI è facoltativo.

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

In **Impostazioni** puoi scegliere conversazione libera, dibattito o esperimento cieco, assegnare personalità, cambiare chi inizia e regolare ritardo, timeout, ragionamento Codex e parametri Ollama.

| File | Windows | Linux, percorsi predefiniti |
| --- | --- | --- |
| Impostazioni | `%APPDATA%\AlterEcho\config.json` | `~/.config/alterecho/config.json` |
| Conversazioni | `%LOCALAPPDATA%\AlterEcho\conversations` | `~/.local/share/alterecho/conversations` |

La cartella dei salvataggi è modificabile dal menu. Per ogni nuova chat viene creata una sottocartella con il suo ID, che contiene JSON ed esportazioni `.md`, `.txt` e `.html`. Tutti i file vengono aggiornati dopo ogni risposta e alla chiusura della chat. Riprendere una conversazione aggiorna gli stessi file con i nuovi messaggi. Il percorso viene mostrato nel terminale. Gli storici precedenti salvati direttamente nella cartella vengono ancora rilevati.

L'HTML è un singolo file autonomo: CSS, JavaScript e messaggi sono incorporati, quindi puoi copiarlo e aprirlo offline in un browser. Offre tema scuro/chiaro, ricerca nei messaggi, copia di messaggi e codice, navigazione e statistiche. Non carica risorse dalla rete; i link esterni si aprono solo se cliccati.

Per leggerlo scegli **Visualizza in HTML** e seleziona la chat: il programma rigenera il file e lo apre nel browser. Digita nella barra di ricerca per evidenziare e filtrare i messaggi, oppure usa **Tema chiaro / Tema scuro** per cambiare aspetto. Se avevi già aperto il file durante una continuazione, ricarica la pagina per vedere gli aggiornamenti.

**Riprendi conversazione** elenca anche gli storici nella precedente `outputs/conversations` del progetto. Verifica la sessione Codex prima di chiedere conferma: un thread mancante o incompleto può impedire la ripresa. Gli storici demo non si riprendono con modelli reali.

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

Per preparare un TOML parti da [config.example.toml](config.example.toml). `run --non-interactive` avvia subito la generazione con la configurazione scelta; anche il comando avanzato `resume` genera dopo le verifiche, senza la conferma del menu. L'esportazione di chat esistenti non contatta i modelli e non modifica il JSON canonico.

## Se qualcosa non funziona

- **Comando non trovato:** apri un nuovo terminale o ripeti l'installazione del launcher.
- **Errore di connessione o accesso:** esegui `alterecho doctor`; verifica Ollama e il login ChatGPT in Codex.
- **Limite di contesto o risposta:** lo storico resta salvato. Regola i parametri appropriati o avvia un nuovo dialogo; la memoria non viene tagliata automaticamente.
- **Ripresa rifiutata:** leggi il motivo mostrato. Non usare contemporaneamente la stessa chat o il suo thread Codex da altre applicazioni.

Per struttura del progetto, funzionamento degli adapter, sicurezza, configurazione avanzata e test, leggi [ARCHITETTURA.md](ARCHITETTURA.md).

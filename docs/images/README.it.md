# Immagini del progetto

[English](README.md) | **Italiano**

Questa cartella raccoglie le risorse visive della documentazione. Tutti i percorsi usati nel README sono locali al repository.

| File | Contenuto | Provenienza |
| --- | --- | --- |
| `dashboard.png` | Panoramica, provider, statistiche e cronologia | Screenshot autentico fornito dall'autore |
| `nuova-conversazione.png` | Scelta dei due interlocutori e impostazione del dialogo | Screenshot autentico fornito dall'autore |
| `profili.png` | Profili Codex e Ollama | Screenshot autentico fornito dall'autore |
| `alterecho-hero.svg` | Copertina alternativa: due prospettive che si rispondono | Illustrazione vettoriale originale, non una schermata dell’app |
| `architettura.svg` | Terminale e browser → un solo server → quattro provider | Diagramma del funzionamento implementato |

I colori riprendono `web/src/style.css`: sfondo `#101319`, pannelli `#181d25`, accento A `#80ddcf`, accento B `#aaa0ef`. Gli SVG non contengono script, font remoti, immagini incorporate o dati personali.

## Screenshot autentici

Per questa revisione Computer Use ha impedito la cattura automatica perché non riusciva a verificare con certezza l’URL corrente di Chrome su Windows. L'autore ha quindi fornito tre file PNG, ispezionati e rinominati senza modificare i pixel. Non sono state create schermate fittizie o dichiarate acquisizioni mai avvenute.

La dashboard mostra titoli di conversazioni e contatori della sua istanza: non viene dichiarata una cattura con provider mock, né presentata come misura delle prestazioni. Le altre due schermate mostrano moduli di configurazione. Non sono visibili token, chiavi API o dati identificativi personali. Non sono state effettuate inferenze per produrre questi asset durante il lavoro di documentazione.

## Catture 1.1 del 26 ottobre 2026

La cartella `1.1/` contiene screenshot reali acquisiti da Playwright/Chromium su Windows con il backend isolato `tests/browser_server.py`. I provider sono simulati e i testi sono fixture scritte per le prove: non sono risposte di Codex, Ollama o API reali, né benchmark. Non sono state ritoccate le catture o inserite interfacce fittizie.

| File | Vista |
| --- | --- |
| `1.1/chat-desktop.png` | Chat desktop scura, tre messaggi simulati |
| `1.1/chat-mobile-light.png` | Chat chiara nel viewport smartphone emulato |
| `1.1/conferma.png` | Modale di avvio e consenso esplicito ai costi |
| `1.1/nuova-conversazione.png` | Modelli selezionabili da cataloghi di test |

I PNG originali forniti dall’autore restano conservati. Le schermate della 1.1 sono state ispezionate dopo la cattura. L’emulazione mobile non equivale a un test su dispositivo fisico.

Usare soltanto provider mock o la demo integrata. Evitare login, token, chiavi, conversazioni private, notifiche e indirizzi personali nella cornice del browser. Annotare la provenienza delle immagini e mantenere visibile la natura dimostrativa dei contenuti. Nessuna inferenza reale è necessaria.

Per aggiungere o sostituire gli asset, mantenere percorsi relativi e testo alternativo, preferire WebP/PNG ottimizzati per le catture e controllare la leggibilità anche a larghezza ridotta.

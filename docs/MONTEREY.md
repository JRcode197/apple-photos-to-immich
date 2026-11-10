# Guida italiana: migrazione da Apple Foto a Immich su macOS Monterey

> **Stato: anteprima da collaudare.** La GUI e i test automatici non certificano la riuscita di un import da 600 GB. Mantieni il backup originale. Il fork è basato su [shaisegal/apple-photos-to-immich](https://github.com/shaisegal/apple-photos-to-immich) (licenza MIT).

## Requisiti

- Mac Intel con macOS Monterey 12 e libreria Foto leggibile localmente.
- Python **3.11 o 3.12** di python.org, con Tkinter funzionante. Verifica: `python3.11 -m tkinter`.
- [OSXPhotos](https://github.com/RhetTbull/osxphotos), installato nell'ambiente Python (vedi sotto).
- [immich-go](https://github.com/simulot/immich-go/releases): scegli il rilascio per **darwin_amd64**; controlla provenienza, firma/checksum e compatibilità con il tuo server Immich.
- Immich accessibile da Mac con una chiave API personale abilitata all'importazione e alla gestione degli album.
- Spazio libero sul disco di esportazione: per 600 GB consigliati **almeno 750 GB–1 TB**, oltre allo spazio sul server Immich. Meglio SSD esterno.

## Installazione senza Homebrew

Apri Terminale:

```bash
git clone https://github.com/JRcode197/apple-photos-to-immich.git
cd apple-photos-to-immich
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install osxphotos
python -m unittest discover -s tests -v
python -m apple_photos_to_immich.gui
```

Se `immich-go` non è nel PATH, usa il suo percorso assoluto nella scheda **Avanzate**. Per OSXPhotos, normalmente basta `osxphotos` installato nel venv.

**Permessi:** in *Impostazioni di Sistema → Privacy e sicurezza → Accesso completo al disco*, abilita Terminale o l'app che esegue Python, se OSXPhotos non può leggere la libreria. Chiudi Apple Foto durante l'esportazione. Per librerie iCloud, seleziona **Scarica originali su questo Mac**, attendendo il download completo.

## Interfaccia grafica

La GUI comprende quattro schede:

1. **Connessione e percorsi**: libreria `.photoslibrary`, directory di esportazione, report, URL Immich e chiave API. La configurazione viene salvata per impostazione predefinita in `~/.config/apple-photos-to-immich/config.toml` con permessi 0600. Non condividerla.
2. **Migrazione**: 22 azioni fra requisiti, export, import, album, verifica e operazioni complete. Le azioni con scrittura richiedono conferma.
3. **Avanzate**: binari, prefissi album, tag, batch API, campione, impostazioni HEIC/JPEG e RAW/JPEG.
4. **Report e log**: messaggi dal processo, riepilogo dei JSON e apertura della cartella report. I log possono contenere percorsi personali.

Le azioni sono eseguite in sottoprocesso; **Interrompi** termina il processo attivo. Una barra indeterminata indica l'attività, non la percentuale dei 600 GB.

## Sequenza consigliata

1. Esegui **backup completo indipendente** della libreria; non lavorare mai sull'unica copia.
2. Salva la configurazione della GUI e verifica URL, chiave API e percorsi.
3. Avvia **Requisiti**, poi **Export campione** (30 foto per impostazione predefinita). Questo comando non importa nulla su Immich.
4. Esamina i file campione (HEIC, MOV, Live Photos, data e GPS). Per testare anche l'importazione, usa preferibilmente un'**istanza Immich di prova** e una directory di esportazione separata: il comando Import carica tutti i file presenti nella directory scelta.
5. Esegui **Export completo / incrementale** sulla libreria principale, poi **Audit export**. L'opzione SHA256 legge l'intero archivio e impiega molto più tempo.
6. Esegui **Import su Immich**, attendi i lavori del server, quindi **Genera mappa album**, **Anteprima album**, **Ricostruisci album**.
7. Esegui **Verifica foto e album**, poi **Verifica GPS/date** su campione e, se necessario, su tutta la libreria. Esamina i report JSON.
8. Conferma manualmente timeline, mappa, album multipli e Live Photos nel browser Immich. Conserva la libreria Apple originale e il backup.

## CLI per utenti avanzati

```bash
apple-photos-to-immich --config ~/.config/apple-photos-to-immich/config.toml check
apple-photos-to-immich --config ~/.config/apple-photos-to-immich/config.toml all --test
apple-photos-to-immich --config ~/.config/apple-photos-to-immich/config.toml audit-export
apple-photos-to-immich --config ~/.config/apple-photos-to-immich/config.toml verify-metadata --limit 300
apple-photos-to-immich --config ~/.config/apple-photos-to-immich/config.toml verify-metadata --all
```

Il comando `all` comprende export incrementale, upload, attesa, mappa, ricostruzione album e verifica; per passaggi individuali usa la GUI. `all --test` NON scrive su Immich. `all --no-resume` riesegue la sequenza; `all --reset-state` cancella il solo stato delle fasi, **non** le foto.

## Protezioni e limiti noti

- I file in Apple Foto vengono **letti**, mai eliminati o modificati dal codice di migrazione.
- Il matching album è rigoroso per UUID; foto con nomi alterati possono risultare mancanti invece di essere abbinate erroneamente.
- Le copie di vecchi album non vengono eliminate automaticamente: potrebbero richiedere pulizia manuale.
- Lo stato di ripresa è legato alla configurazione e contiene hash della chiave API, non la chiave in chiaro. Non è una verifica per-file; dopo cambiamenti nell'archivio riesegui e verifica.
- L'API key è passata a immich-go tramite variabile d'ambiente. Un amministratore locale può comunque ispezionare l'ambiente dei processi. Non condividere i log.
- L'audit segnala più file con UUID identico anche quando sono un Live Photo o originali/modifiche: non indica necessariamente duplicati.
- Le differenze di giorno fra data Apple e Immich possono essere causate dal fuso orario.
- Gli album intelligenti non diventano regole Immich; riconoscimento dei volti e modifiche non distruttive richiedono controlli separati.
- La GUI non è un file `.app` firmato o notarizzato; richiede Python/Tkinter.
- Le workflow CI su macOS moderno **non** provano la compatibilità con macOS Monterey: occorre un test reale sul Mac Intel.

## Diagnostica

`python -m unittest discover -s tests -v` esegue la suite. I report `audit-export.json`, `match-report.json`, `verify-report.json`, `metadata-verification.json` si trovano nella directory metadati. Non cancellare la libreria di origine se qualche asset risulta mancante o se ci sono errori.

## Licenza

MIT, basata sul codice di **shaisegal** (Copyright 2026). Licenza originale conservata in LICENSE.

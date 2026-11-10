"""Tkinter GUI for Monterey and newer. Operations use the project's CLI."""
from __future__ import annotations
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import tkinter as tk
import tomllib
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, scrolledtext
from urllib import request
import ssl

ACTIONS=[
 ("Requisiti","check","check",False),
 ("Anteprima export","export","export --dry-run",False),
 ("Export campione","export","export --test",False),
 ("Export completo","export","export",True),
 ("Export incrementale","export","export --update",True),
 ("Audit export","export","audit-export",False),
 ("Audit con SHA256","export","audit-export --sha256",True),
 ("Anteprima import","import","import-assets --dry-run",False),
 ("Import su Immich","import","import-assets",True),
 ("Import senza attesa","import","import-assets --no-wait",True),
 ("Attendi lavori Immich","import","wait-for-immich --timeout 7200",False),
 ("Genera mappa album","album","make-map",False),
 ("Anteprima album","album","apply-albums --dry-run",False),
 ("Ricostruisci album","album","apply-albums",True),
 ("Verifica foto e album","verifica","verify",False),
 ("Verifica GPS/date (300)","verifica","verify-metadata --limit 300",False),
 ("Verifica tutti i metadati","verifica","verify-metadata --all",True),
 ("Piano completo, anteprima","automazione","all --dry-run",False),
 ("Solo campione, sicuro","automazione","all --test",False),
 ("Migrazione completa, riprendi","automazione","all",True),
 ("Migrazione completa, riesegui","automazione","all --no-resume",True),
 ("Azzera stato e riesegui","automazione","all --reset-state",True),
]
DEFAULTS={
 "server":"http://localhost:2283","api_key":"","verify_ssl":"true",
 "library":str(Path.home()/"Pictures"/"Photos Library.photoslibrary"),
 "export_dir":str(Path.home()/"Pictures"/"Immich-Export"),
 "meta_dir":str(Path.home()/"Pictures"/"Immich-Metadata"),
 "album_prefix":"","system_album_prefix":"Apple Foto",
 "osxphotos_binary":"osxphotos","osxphotos_python":"","immich_go_binary":"immich-go",
 "test_export_limit":"30","page_size":"250","album_chunk_size":"500",
 "retry_attempts":"5","retry_backoff_seconds":"1",
 "import_session_tag":"apple-photos-to-immich",
 "import_manage_heic_jpeg":"StackCoverHeic","import_manage_raw_jpeg":"StackCoverRaw"
}
GROUPS={
 "immich":["server","api_key"],
 "photos":["library","album_prefix","system_album_prefix"],
 "paths":["export_dir","meta_dir"],
 "runtime":["osxphotos_binary","osxphotos_python","immich_go_binary",
   "test_export_limit","page_size","album_chunk_size","retry_attempts",
   "retry_backoff_seconds","import_session_tag","import_manage_heic_jpeg",
   "import_manage_raw_jpeg"]
}
NUMERIC={"test_export_limit":(1,100000),"page_size":(1,10000),
 "album_chunk_size":(1,10000),"retry_attempts":(1,20),
 "retry_backoff_seconds":(0,120)}
LABELS={
 "server":"URL Immich","api_key":"Chiave API personale",
 "library":"Libreria Apple Foto (.photoslibrary)",
 "export_dir":"Cartella export (almeno 750 GB liberi)",
 "meta_dir":"Cartella report e stato","album_prefix":"Prefisso album legacy",
 "system_album_prefix":"Prefisso album di sistema",
 "osxphotos_binary":"Eseguibile osxphotos","osxphotos_python":"Python osxphotos (facoltativo)",
 "immich_go_binary":"Eseguibile immich-go",
 "test_export_limit":"Foto nel campione","page_size":"Pagina API",
 "album_chunk_size":"Dimensione lotto album","retry_attempts":"Tentativi API",
 "retry_backoff_seconds":"Intervallo retry (secondi)",
 "import_session_tag":"Tag importazione","import_manage_heic_jpeg":"Accoppiamento HEIC/JPEG",
 "import_manage_raw_jpeg":"Accoppiamento RAW/JPEG"
}

def make_config(values:dict[str,str])->str:
    def val(k:str)->str:
        if k in NUMERIC:
            lo,hi=NUMERIC[k]
            n=int(values.get(k,DEFAULTS[k]))
            if not lo<=n<=hi:raise ValueError(f"{k}: expected {lo}–{hi}")
            return str(n)
        return json.dumps(values.get(k,DEFAULTS.get(k,"")),ensure_ascii=False)
    lines=["# Contains an Immich secret. Never commit this file."]
    for section,keys in GROUPS.items():
        lines.extend(["",f"[{section}]"])
        for key in keys:lines.append(f"{key} = {val(key)}")
        if section=="immich":
            lines.append(f"skip_verify_ssl = {str(values.get('verify_ssl','true')!='true').lower()}")
    return "\n".join(lines)+"\n"

def save_private_config(path:Path,content:str)->None:
    path=path.expanduser()
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+".tmp")
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            f.write(content);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o600);os.replace(tmp,path)
        os.chmod(path,0o600)
    finally:
        tmp.unlink(missing_ok=True)

def read_config(path:Path)->dict[str,str]:
    data=tomllib.loads(path.read_text(encoding="utf-8"))
    out={}
    for section in GROUPS:
        for key,value in data.get(section,{}).items():
            out[key]=str(value)
    out["verify_ssl"]="false" if data.get("immich",{}).get("skip_verify_ssl",False) else "true"
    return out

class Studio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Apple Foto → Immich · Migration Studio")
        self.geometry("1060x760")
        self.minsize(820,600)
        self.config_path=tk.StringVar(value=str(Path.home()/".config/apple-photos-to-immich/config.toml"))
        self.vars={k:tk.StringVar(value=v) for k,v in DEFAULTS.items()}
        self.action=tk.StringVar(value=ACTIONS[0][0])
        self.verbose=tk.BooleanVar(value=False)
        self.status=tk.StringVar(value="Pronto. Configura la libreria e Immich.")
        self.summary=tk.StringVar(value="Report non ancora generati")
        self.events=queue.Queue()
        self.process=None
        self.busy=False
        self._layout()
        if Path(self.config_path.get()).exists():self.load_config(silent=True)
        self.after(120,self.poll)

    def _layout(self):
        top=ttk.Frame(self,padding=12);top.pack(fill="both",expand=True)
        ttk.Label(top,text="Apple Foto → Immich",font=("Helvetica",19,"bold")).pack(anchor="w")
        ttk.Label(top,text="Originali • Album • Date • GPS • Verifiche").pack(anchor="w",pady=(0,12))
        bar=ttk.Frame(top);bar.pack(fill="x",pady=4)
        ttk.Label(bar,text="Config:").pack(side="left")
        ttk.Entry(bar,textvariable=self.config_path).pack(side="left",expand=True,fill="x",padx=6)
        ttk.Button(bar,text="Scegli…",command=self.choose_config).pack(side="left")
        ttk.Button(bar,text="Carica",command=self.load_config).pack(side="left",padx=4)
        ttk.Button(bar,text="Salva",command=self.save_config).pack(side="left")
        self.tabs=ttk.Notebook(top);self.tabs.pack(fill="both",expand=True,pady=10)
        pages=[ttk.Frame(self.tabs,padding=12) for _ in range(4)]
        for page,title in zip(pages,["Connessione e percorsi","Migrazione","Avanzate","Report e log"]):
            self.tabs.add(page,text=title)
        self.config_tab,self.migrate_tab,self.advanced_tab,self.report_tab=pages
        self._section(self.config_tab,"Server Immich",["server","api_key"],0)
        ttk.Checkbutton(self.config_tab,text="Verifica TLS (consigliato)",variable=self.vars["verify_ssl"],onvalue="true",offvalue="false").grid(row=1,column=0,sticky="w",pady=4)
        ttk.Button(self.config_tab,text="Test connessione API",command=self.test_connection).grid(row=2,column=0,sticky="w",pady=4)
        self._section(self.config_tab,"Libreria e directory",["library","export_dir","meta_dir"],3)
        ttk.Label(self.config_tab,text="Le credenziali restano sul Mac in config.toml (permessi 0600). Non pubblicare la configurazione su GitHub.").grid(row=4,column=0,sticky="w",pady=12)
        self.config_tab.columnconfigure(0,weight=1)
        self._section(self.advanced_tab,"Strumenti, album e opzioni",list(GROUPS["photos"][1:])+GROUPS["runtime"],0)
        self.advanced_tab.columnconfigure(0,weight=1)
        canvas=tk.Canvas(self.migrate_tab,highlightthickness=0)
        canvas.pack(fill="both",expand=True,side="left")
        scroll=ttk.Scrollbar(self.migrate_tab,orient="vertical",command=canvas.yview);scroll.pack(side="right",fill="y")
        canvas.configure(yscrollcommand=scroll.set)
        body=ttk.Frame(canvas)
        window=canvas.create_window((0,0),window=body,anchor="nw")
        body.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",lambda e:canvas.itemconfigure(window,width=e.width))
        for group in dict.fromkeys(a[1] for a in ACTIONS):
            frame=ttk.LabelFrame(body,text=group.capitalize(),padding=8);frame.pack(fill="x",pady=5)
            for i,a in enumerate(x for x in ACTIONS if x[1]==group):
                ttk.Radiobutton(frame,text=a[0],variable=self.action,value=a[0]).grid(row=i//2,column=i%2,sticky="w",padx=8,pady=4)
            frame.columnconfigure(0,weight=1);frame.columnconfigure(1,weight=1)
        actions=ttk.Frame(body);actions.pack(fill="x",pady=10)
        self.run_button=ttk.Button(actions,text="Esegui operazione",command=self.run_action)
        self.run_button.pack(side="left")
        self.stop_button=ttk.Button(actions,text="Interrompi",command=self.stop,state="disabled")
        self.stop_button.pack(side="left",padx=8)
        ttk.Checkbutton(body,text="Log dettagliati",variable=self.verbose).pack(anchor="w")
        rb=ttk.Frame(self.report_tab);rb.pack(fill="x")
        ttk.Button(rb,text="Aggiorna report",command=self.refresh_summary).pack(side="left")
        ttk.Button(rb,text="Apri cartella report",command=self.open_report_folder).pack(side="left",padx=6)
        ttk.Button(rb,text="Copia log",command=self.copy_log).pack(side="left")
        ttk.Label(self.report_tab,textvariable=self.summary,wraplength=900,justify="left").pack(anchor="w",pady=12)
        self.log=scrolledtext.ScrolledText(self.report_tab,state="disabled",font=("Menlo",10),wrap="word")
        self.log.pack(fill="both",expand=True)
        bottom=ttk.Frame(top);bottom.pack(fill="x")
        ttk.Label(bottom,textvariable=self.status).pack(side="left")
        self.spinner=ttk.Progressbar(bottom,mode="indeterminate",length=150)
        self.spinner.pack(side="right")
        self.protocol("WM_DELETE_WINDOW",self.close)

    def _section(self,page,title,keys,row):
        frame=ttk.LabelFrame(page,text=title,padding=10)
        frame.grid(row=row,column=0,sticky="ew",pady=8)
        frame.columnconfigure(1,weight=1)
        for n,key in enumerate(keys):
            ttk.Label(frame,text=LABELS.get(key,key)).grid(row=n,column=0,sticky="w",padx=5,pady=6)
            ttk.Entry(frame,textvariable=self.vars[key],show="●" if key=="api_key" else "").grid(row=n,column=1,sticky="ew",padx=5,pady=6)
            if key in ("library","export_dir","meta_dir"):
                ttk.Button(frame,text="Sfoglia…",command=lambda k=key:self.browse(k)).grid(row=n,column=2,padx=5)

    def browse(self,key):
        path=filedialog.askdirectory(title=LABELS[key])
        if path:self.vars[key].set(path)

    def choose_config(self):
        path=filedialog.askopenfilename(filetypes=[("TOML","*.toml")])
        if path:self.config_path.set(path);self.load_config()

    def save_config(self,silent=False):
        try:
            values={k:v.get() for k,v in self.vars.items()}
            if not values["server"].startswith(("http://","https://")):raise ValueError("URL server must begin with http:// or https://")
            if not values["api_key"]:raise ValueError("Inserisci la chiave API Immich")
            if not values["library"]:raise ValueError("Seleziona la libreria Apple Foto")
            save_private_config(Path(self.config_path.get()),make_config(values))
            self.status.set("Configurazione salvata")
            if not silent:messagebox.showinfo("Salvato","Configurazione salvata in modo riservato sul Mac.")
            return True
        except (OSError,ValueError) as exc:
            messagebox.showerror("Configurazione",str(exc));return False

    def load_config(self,silent=False):
        try:
            for k,v in read_config(Path(self.config_path.get())).items():
                if k in self.vars:self.vars[k].set(v)
            self.status.set("Configurazione caricata")
            self.refresh_summary()
        except (OSError,ValueError) as exc:
            if not silent:messagebox.showerror("Caricamento",str(exc))

    def run_action(self):
        if self.busy or not self.save_config(silent=True):return
        selected=next(a for a in ACTIONS if a[0]==self.action.get())
        title,_,cmd,confirm=selected
        if confirm and not messagebox.askyesno("Conferma",f"{title}\n\nProcedere? Apple Foto non sarà modificato."):return
        command=[sys.executable,"-m","apple_photos_to_immich","--config",self.config_path.get()]
        if self.verbose.get():command.append("--verbose")
        command.extend(cmd.split())
        self.busy=True;self.run_button.config(state="disabled");self.stop_button.config(state="normal")
        self.spinner.start(10);self.status.set(f"In corso: {title}")
        self.tabs.select(self.report_tab)
        self.append(f"\n=== {title} ===\n")
        threading.Thread(target=self.worker,args=(command,),daemon=True).start()

    def worker(self,argv):
        try:
            self.process=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                          text=True,encoding="utf-8",errors="replace",bufsize=1,start_new_session=True)
            for line in self.process.stdout:self.events.put(("line",line))
            rc=self.process.wait()
            self.events.put(("done",str(rc)))
        except OSError as exc:
            self.events.put(("line",str(exc)+"\n"));self.events.put(("done","1"))
        finally:self.process=None

    def stop(self):
        p=self.process
        if p is None or p.poll() is not None:return
        if messagebox.askyesno("Interrompere","Interrompere il lavoro in corso?"):
            os.killpg(p.pid,signal.SIGTERM)

    def poll(self):
        try:
            for _ in range(250):
                kind,msg=self.events.get_nowait()
                if kind=="line":self.append(msg)
                elif kind=="done":
                    self.busy=False;self.run_button.config(state="normal");self.stop_button.config(state="disabled")
                    self.spinner.stop()
                    self.status.set("Completato" if msg=="0" else f"Errore o anomalie: codice {msg}")
                    self.append(f"\n=== Codice uscita: {msg} ===\n")
                    self.refresh_summary()
        except queue.Empty:pass
        self.after(120,self.poll)

    def append(self,text):
        # Best-effort suppression of sensitive API keys in visible logs.
        secret=self.vars["api_key"].get()
        if secret:text=text.replace(secret,"[REDACTED]")
        self.log.config(state="normal")
        self.log.insert("end",re.sub(r"\x1b\[[0-9;]*[A-Za-z]","",text))
        self.log.see("end");self.log.config(state="disabled")

    def refresh_summary(self):
        root=Path(self.vars["meta_dir"].get()).expanduser()
        result=[]
        for filename in ("audit-export.json","match-report.json","verify-report.json","metadata-verification.json"):
            file=root/filename
            if not file.exists():continue
            try:
                data=json.loads(file.read_text(encoding="utf-8"))
                fields=["mediaFiles","matchedCount","missingCount","albumsMissingInImmich","checked",
                        "gpsMissing","gpsMismatch","dateMissing","dateMismatch"]
                result.append(filename+": "+", ".join(f"{k}={data[k]}" for k in fields if k in data))
            except (OSError,ValueError) as exc:result.append(filename+": "+str(exc))
        self.summary.set("\n".join(result) if result else "Nessun report disponibile")

    def test_connection(self):
        def run():
            try:
                url=self.vars["server"].get().rstrip("/")+"/api/server/ping"
                req=request.Request(url,headers={"x-api-key":self.vars["api_key"].get()})
                context=ssl.create_default_context() if self.vars["verify_ssl"].get()=="true" else ssl._create_unverified_context()
                with request.urlopen(req,context=context,timeout=12) as response:
                    self.events.put(("line",f"Connessione server: HTTP {response.status}\n"))
            except Exception as exc:self.events.put(("line","Connessione non riuscita: "+str(exc)+"\n"))
        threading.Thread(target=run,daemon=True).start()
        self.tabs.select(self.report_tab)

    def open_report_folder(self):
        p=Path(self.vars["meta_dir"].get()).expanduser()
        if not p.is_dir():messagebox.showinfo("Report","Cartella non ancora creata");return
        subprocess.Popen(["open",str(p)] if sys.platform=="darwin" else ["xdg-open",str(p)])

    def copy_log(self):
        self.clipboard_clear();self.clipboard_append(self.log.get("1.0","end-1c"))

    def close(self):
        if self.busy:
            if not messagebox.askyesno("Uscita","Il lavoro è in corso. Interrompere?"):return
            if self.process is not None:
                try:os.killpg(self.process.pid,signal.SIGTERM)
                except OSError:pass
        self.destroy()

def main()->int:
    try:
        Studio().mainloop()
        return 0
    except tk.TclError as exc:
        print("Unable to start GUI:",exc,file=sys.stderr)
        return 1

if __name__=="__main__":raise SystemExit(main())

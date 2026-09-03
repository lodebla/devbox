# Guida passo passo — OMP Devbox su ZimaOS

Questa guida porta da zero a un ambiente persistente sul server con OMP, tmux, orca-cli e Chromium condiviso. Dopo l'installazione iniziale, la gestione normale avviene entrando in SSH nel container: non serve usare `docker compose` dal terminale root di ZimaOS.

## 1. Cosa viene creato

Un solo container `omp-devbox` contiene:

- OpenSSH server;
- `tmux`;
- OMP;
- `orca-cli/orca`;
- `rg`, Git, `gh`, Git LFS;
- Bun, Node/npm, Python, Go e build tools;
- Vim completo + Neovim stable con configurazione Kickstart.nvim persistente;
- Chromium;
- Chrome DevTools MCP per dare a OMP accesso allo stesso Chromium;
- Xvfb + Openbox per il display virtuale;
- x11vnc + noVNC, ma **spenti normalmente**;
- helper `browser-service`, `browser-gui`, `omp-session`, `omp-sync-import`, `devbox-health`.

Persistono fuori dal container:

```text
/DATA/AppData/omp-devbox/persist   -> /persist
/DATA/AppData/omp-devbox/workspace -> /workspace
```

Quindi ricreare il container non elimina configurazione OMP, browser profile, chiavi SSH, stato Orca e repository.

---

## 2. Pubblica una volta l'immagine Docker

ZimaOS può importare il Compose dalla UI, ma deve poter **scaricare** l'immagine da un registry. Il metodo più comodo è GHCR.

### Metodo consigliato: GitHub Actions + GHCR

1. Crea un repository GitHub chiamato, per esempio, `omp-devbox` (il sorgente del kit non contiene segreti).
2. Estrai questo kit e, dalla sua cartella, inizializza/pusha il repository:

```bash
git init
git add .
git commit -m "feat: add persistent OMP devbox"
git branch -M main
git remote add origin git@github.com:TUO_UTENTE/omp-devbox.git
git push -u origin main
```

Se preferisci HTTPS, usa il normale URL HTTPS del repository al posto del remote SSH.

3. Il workflow `.github/workflows/build-image.yml` partirà sul push di `main`. Prima costruisce e **avvia realmente** la variante AMD64 come smoke test (`devbox-health`, Chromium/CDP, GUI spenta di default e un vero login SSH con chiave pubblica); solo dopo il test costruisce AMD64 + ARM64 e pubblica:

```text
ghcr.io/TUO_UTENTE/omp-devbox:latest
```

4. Se il package GHCR è privato, rendilo pubblico dalle impostazioni del package **oppure** configura in ZimaOS le credenziali del registry. L'immagine non contiene API key, chiavi SSH o password VNC: quelle vengono passate solo a runtime.

### Alternativa: build dal tuo PC

Se hai Docker sul PC:

```bash
docker build -t TUO_REGISTRY/omp-devbox:latest .
docker push TUO_REGISTRY/omp-devbox:latest
```

Poi usa quell'indirizzo nel Compose ZimaOS.

---

## 3. Prepara una chiave SSH

Sul PC dal quale vuoi collegarti:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/omp_devbox -C "omp-devbox"
```

Visualizza la pubblica:

```bash
cat ~/.ssh/omp_devbox.pub
```

Su PowerShell:

```powershell
Get-Content $HOME\.ssh\omp_devbox.pub
```

Copia **l'intera riga** `ssh-ed25519 ...`.

---

## 4. Modifica `zimaos-compose.yml`

Cambia questi due valori:

```yaml
image: ghcr.io/REPLACE_WITH_YOUR_GITHUB_USER/omp-devbox:latest

DEVBOX_AUTHORIZED_KEYS: "ssh-ed25519 AAAA..."
```

Puoi lasciare:

```yaml
DEVBOX_VNC_PASSWORD: ""
```

e impostare la password VNC in seguito dall'interno del container con `browser-gui password`. È il metodo che consiglio, perché la password non resta nel Compose. Se preferisci automatizzarla al boot, puoi invece valorizzare `DEVBOX_VNC_PASSWORD`.

Le porte sono:

```text
2222 -> SSH del devbox
6080 -> noVNC, ma c'è un listener solo quando esegui browser-gui start
```

**La porta CDP 9222 non va aggiunta.** Rimane raggiungibile solamente come `127.0.0.1:9222` dentro devbox.

Se vuoi usare una cartella già esistente con i repository, modifica solo il lato host:

```yaml
- /DATA/LaTuaCartellaProgetti:/workspace
```

Per una prima installazione consiglio invece la cartella nuova già indicata nel file.

---

## 5. Importa il Compose dalla UI di ZimaOS

Dalla dashboard ZimaOS:

1. premi `+`;
2. scegli **Install a customized app**;
3. premi **Import**;
4. apri la scheda **Docker Compose**;
5. incolla il contenuto di `zimaos-compose.yml`;
6. premi **Submit** e poi installa.

È il flusso previsto dalla documentazione ZimaOS per le Custom App.

A questo punto non devi più entrare nel terminale root dell'host per la gestione normale.

---

## 6. Configura l'alias SSH sul PC

Nel file `~/.ssh/config`:

```sshconfig
Host devbox
    HostName IP_DEL_TUO_SERVER
    Port 2222
    User dev
    IdentityFile ~/.ssh/omp_devbox
    ServerAliveInterval 30
```

Da quel momento:

```bash
ssh devbox
```

Al primo collegamento accetta la host key.

Le host key SSH sono salvate in `/persist`, quindi non cambiano quando ricrei il container.

---

## 7. Verifica l'ambiente

Dopo l'accesso SSH:

```bash
devbox-health
```

Dovresti vedere disponibili almeno:

```text
omp
orca
rg
git
gh
tmux
bun
node
npm
python3
go
chromium
chrome-devtools-mcp
browser CDP
```

Controlla anche:

```bash
omp --version
orca version
rg --version
browser-service status
```

---


## 7.5 Vim e Neovim con Kickstart.nvim

L'immagine include `vim` completo e installa Neovim dalla release **stable ufficiale** al momento del build, invece di usare la versione spesso arretrata dei repository Debian. Include anche le dipendenze richieste dal Kickstart corrente: `git`, `make`, compilatore C/C++, `ripgrep`, `fd`, `tree-sitter` CLI, `unzip`, Node/npm e `xclip`.

Il repo `nvim-lua/kickstart.nvim` viene clonato nell'immagine come seed. Al primo avvio del container viene copiato in:

```text
/persist/nvim
```

e collegato a:

```text
/persist/config/nvim -> /persist/nvim
```

Poiché `XDG_CONFIG_HOME=/persist/config`, `nvim` usa automaticamente quella configurazione. Le modifiche che fai a `init.lua` restano quindi sul volume `/persist` anche quando aggiorni o ricrei il container. Se esiste già una configurazione Neovim in `/persist/config/nvim`, l'entrypoint la lascia intatta.

Verifica:

```bash
vim --version | head -n 1
nvim --version | head -n 1
fd --version
tree-sitter --version
readlink /persist/config/nvim
```

Al primo avvio di:

```bash
nvim
```

Kickstart usa il package manager integrato `vim.pack` del Neovim corrente per scaricare/configurare i plugin. I successivi rebuild dell'immagine non sovrascrivono la tua configurazione persistente.

## 8. Primo login OMP sul server

La sincronizzazione descritta dopo **non copia** `agent.db`, `.env` o altri token dal PC. È intenzionale: così non trasferiamo alla cieca credenziali e DB SQLite mentre OMP è in esecuzione.

La prima volta avvia:

```bash
omp
```

ed effettua `/login` per i provider che usi.

Se il login OAuth necessita di interazione con il browser, puoi prima fare:

```bash
browser-gui start
```

per vedere il Chromium del server.

OMP salva le proprie credenziali server-side in `/persist/omp`, quindi sopravvivono alla ricreazione del container.

---

## 9. Sincronizza la tua configurazione OMP locale

Questa è la parte pensata per mantenere il server allineato quando aggiungi skill, command, hook, tool, extension o plugin.

### Linux / macOS / WSL

Dalla cartella di questo kit sul PC:

```bash
./sync/sync-omp.sh devbox
```

### Windows PowerShell

```powershell
.\sync\sync-omp.ps1 -Remote devbox
```

Gli script usano `tar + scp + ssh`; non serve Docker.

### Cosa viene sincronizzato

Viene sincronizzato l’intero albero `~/.omp` (inclusi eventuali profili nominati), con poche esclusioni di sicurezza/runtime. Per esempio:

```text
~/.omp/agent/config.yml
~/.omp/agent/models.yml
~/.omp/agent/mcp.json
~/.omp/agent/skills/
~/.omp/agent/commands/
~/.omp/agent/rules/
~/.omp/agent/prompts/
~/.omp/agent/instructions/
~/.omp/agent/hooks/
~/.omp/agent/tools/
~/.omp/agent/extensions/
~/.omp/marketplaces.json
~/.omp/plugins/
```

A qualsiasi profondità sono esclusi di proposito:

```text
agent.db e relativi file SQLite
.env
sessioni / blob / log runtime
auth-broker.token / auth-gateway.token
node_modules
```

`node_modules` viene escluso perché copiare moduli installati su Windows/macOS dentro Linux può rompere plugin con dipendenze native. Se `~/.omp/plugins/package.json` esiste, il server esegue `bun install` per ricreare le dipendenze Linux.

I plugin creati con `omp plugin link` verso una directory **esterna** a `~/.omp` non possono essere replicati automaticamente: in quel caso metti il sorgente anche sul server oppure installa il plugin da Git/marketplace.

### Perché il browser server non rovina la tua config

La configurazione browser specifica del server resta **fuori da `~/.omp`**. Ci sono due piccoli file inclusi nell'immagine:

```text
/etc/devbox/omp-server.yml
/etc/devbox/omp-devbox-mcp.json
```

Il primo applica, tramite `PI_CONFIG_FILES`, solo questa differenza server-side:

```yaml
browser:
  enabled: false
```

Questo è intenzionale: nella release OMP corrente l'impostazione per collegare il browser built-in a un CDP esterno non è ancora parte della configurazione documentata. Se lasciassimo il browser built-in attivo, OMP potrebbe creare un secondo browser non corrispondente a quello che vedi via noVNC.

Il secondo file definisce invece un MCP `devbox-chromium` che esegue `chrome-devtools-mcp` verso:

```text
http://127.0.0.1:9222
```

All'avvio del container viene esposto a OMP tramite una sorgente MCP esterna (`~/.cursor/mcp.json` è un symlink al file dell'immagine). OMP scopre le configurazioni MCP di tool esterni oltre a `~/.omp/agent/mcp.json`; in questo modo l'integrazione browser è indipendente anche dai profili OMP.

Quindi la sincronizzazione può continuare a sostituire la tua `~/.omp` con quella locale senza perdere la configurazione browser del server. Se in futuro OMP rilascerà ufficialmente `browser.cdpUrl`, potremo semplificare questa parte eliminando il piccolo shim MCP.

---

## 10. Usa OMP con tmux

Puoi usare tmux normalmente:

```bash
tmux new -s progetto
cd /workspace/progetto
omp
```

poi staccarti con:

```text
Ctrl+B, poi D
```

OMP continua a girare sul server.

Ho incluso anche un helper più comodo:

```bash
omp-session start progetto /workspace/progetto
omp-session attach progetto
```

Elenco sessioni:

```bash
omp-session list
```

Leggi le ultime 200 righe senza attaccarti:

```bash
omp-session capture progetto 200
```

Invia un prompt a OMP dall'esterno della TUI:

```bash
omp-session send progetto "esegui i test e correggi gli errori"
```

Ferma la sessione:

```bash
omp-session stop progetto
```

Questi comandi sono anche molto facili da invocare da Hermes via SSH.

---

## 11. Come funziona il browser condiviso

All'avvio del container partono:

```text
Xvfb :99
Openbox
Chromium
```

Chromium usa il profilo persistente:

```text
/persist/chromium
```

e il suo CDP è:

```text
http://127.0.0.1:9222
```

OMP usa **quella** istanza tramite il server MCP `devbox-chromium`. Il browser built-in di OMP viene disabilitato nel solo ambiente server per evitare che venga creata una seconda istanza invisibile.

Dentro OMP puoi verificare la discovery con:

```text
/mcp list
/mcp test devbox-chromium
```

Controlla anche il processo browser:

```bash
browser-service status
```

Log:

```bash
browser-service logs
```

Riavvio del solo browser:

```bash
browser-service restart
```

Il browser rimane disponibile anche quando la GUI noVNC è spenta.

---

## 12. Attiva la GUI solo quando vuoi guardarla

Stato normale:

```bash
browser-gui status
```

mostrerà noVNC e x11vnc spenti.

La prima volta imposta una password VNC direttamente via SSH:

```bash
browser-gui password
```

La password viene salvata in `/persist/vnc/passwd` e sopravvive agli aggiornamenti del container.

Quando vuoi vedere lo stesso Chromium usato da OMP:

```bash
browser-gui start
```

Poi dal PC o telefono apri:

```text
http://IP_DEL_SERVER:6080/vnc.html?autoconnect=1&resize=scale
```

Inserisci la password VNC configurata in `DEVBOX_VNC_PASSWORD`.

Quando hai finito:

```bash
browser-gui stop
```

Questo spegne solamente:

```text
x11vnc
noVNC/websockify
```

**Chromium, Xvfb, le tab, i cookie e OMP continuano a funzionare.**

Puoi anche cambiare password dall'interno:

```bash
browser-gui password
```

### Cloudflare

Se vuoi raggiungerlo da Internet, punta un hostname del tuo Cloudflare Tunnel alla porta `6080` dell'host e proteggilo con **Cloudflare Access**. Non considero la sola password VNC una protezione sufficiente per pubblicare la GUI liberamente su Internet.

---

## 13. Collega Hermes allo stesso Chromium

Il CDP non viene esposto da Docker. Hermes può raggiungerlo tramite il server SSH di devbox.

Dentro il container Hermes serve una chiave SSH autorizzata in devbox. Poi crea un local-forward, per esempio:

```bash
ssh -N \
  -L 127.0.0.1:19223:127.0.0.1:9222 \
  -p 2222 dev@IP_DEL_SERVER
```

Dal punto di vista di Hermes, Chromium diventa quindi:

```text
http://127.0.0.1:19223
```

Imposta Hermes con:

```yaml
browser:
  cdp_url: http://127.0.0.1:19223
```

oppure usa:

```bash
BROWSER_CDP_URL=http://127.0.0.1:19223
```

A quel punto:

```text
OMP -- Chrome DevTools MCP --┐
                   v
               Chromium
                   ^
Hermes -- SSH/CDP -┘
                   |
                  Xvfb
                   |
             x11vnc/noVNC (solo quando attivo)
                   |
               tu dal browser
```

Il tunnel SSH di Hermes è il prossimo pezzo che conviene automatizzare una volta verificato manualmente che Hermes controlli correttamente la stessa sessione.

---

## 14. Git e GitHub CLI

Dentro devbox configura Git una volta:

```bash
git config --global user.name "Il tuo nome"
git config --global user.email "tu@example.com"
```

La config globale viene salvata in `/persist/gitconfig`.

Login GitHub CLI:

```bash
gh auth login
```

La config di `gh` usa `/persist/config`, quindi rimane persistente.

---

## 15. Orca CLI

Verifica:

```bash
orca version
```

Lo stato di Orca in `~/.orca` finisce in `/persist/orca`.

La versione inclusa è `github.com/orca-cli/orca`, cioè l'orchestratore standalone in Go, **non** la CLI dell'app Orca di stablyai.

---

## 16. Aggiornamenti senza toccare ZimaOS

Aggiorna OMP dentro il container:

```bash
omp-update
```

oppure una versione precisa:

```bash
omp-update 17.1.8
```

Aggiorna orca-cli:

```bash
orca-update
```

Questi aggiornamenti modificano il writable layer del container corrente. Se ZimaOS ricrea il container dall'immagine, torneranno le versioni contenute nell'immagine. Per rendere permanente un aggiornamento, fai rebuild/push dell'immagine.

La configurazione e i dati in `/persist` non vengono persi.

---

## 17. Backup

Le directory più importanti sono:

```text
/DATA/AppData/omp-devbox/persist
/DATA/AppData/omp-devbox/workspace
```

Il primo contiene configurazione OMP, credenziali OMP server-side, browser profile, chiavi SSH, stato Orca e config Git/gh.

Il secondo contiene repository e worktree.

---

## 18. Sicurezza da non cambiare

Non aggiungere mai al Compose:

```yaml
- "9222:9222"
```

CDP permette di controllare completamente Chromium, incluse tab e sessioni autenticate.

SSH è configurato con:

```text
root login: no
password login: no
public key: yes
TCP forwarding: yes (necessario per Hermes)
```

Il dev user ha `sudo` senza password **dentro il container** per poter installare strumenti di sviluppo. Ricorda però che `/persist` e `/workspace` sono mount reali: un coding agent con permessi ampi può modificare quei dati.

---

## 19. Troubleshooting rapido

### SSH non entra

Le build correnti sbloccano esplicitamente l'account `dev` per l'autenticazione a chiave mantenendo `PasswordAuthentication no`, e correggono `/persist` a permessi `755` per essere compatibili con `sshd StrictModes`. Il workflow GitHub prova anche un vero login SSH prima di pubblicare l'immagine, quindi una regressione di questo tipo blocca la release.

Se stai ancora eseguendo un'immagine precedente e nei log compare `User dev not allowed because account is locked`, la correzione temporanea è:

```bash
usermod -p '*' dev
```

Dopo aver aggiornato all'immagine corrente non è più necessario eseguire questo comando manualmente.

Verifica che `DEVBOX_AUTHORIZED_KEYS` contenga la riga `.pub` e che stai usando:

```bash
ssh -p 2222 dev@IP_SERVER
```

### OMP non vede il browser

```bash
browser-service status
browser-service logs
curl http://127.0.0.1:9222/json/version
```

Poi, dentro OMP:

```text
/mcp list
/mcp test devbox-chromium
```

`devbox-chromium` deve risultare disponibile. Se il CDP risponde con `curl` ma il test MCP fallisce, controlla anche:

```bash
node --version
chrome-devtools-mcp --help
```

### La pagina noVNC non risponde

È normale finché non fai:

```bash
browser-gui start
```

Controlla:

```bash
browser-gui status
browser-gui logs
```

### Plugin sincronizzato ma extension non caricata

Questo può succedere soprattutto al primo passaggio cross-platform, perché `node_modules` non viene copiato.

Per un marketplace plugin:

```bash
omp plugin install --force nome@marketplace
```

Questo ricrea link/dipendenze usando Linux senza dover copiare i binari dal PC.

### Directory `/workspace` non scrivibile

Se stai montando una cartella preesistente, imposta `PUID` e `PGID` nel Compose uguali all'owner dei file oppure usa inizialmente la directory dedicata `/DATA/AppData/omp-devbox/workspace`.

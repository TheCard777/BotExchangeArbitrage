# Bot d'arbitrage crypto

Compare les prix entre plusieurs exchanges crypto et peut trader
automatiquement les écarts de prix rentables.

> 📖 **Débutant ?** Lis d'abord **[GUIDE.md](GUIDE.md)** : il explique tout
> pas à pas (installation, mode démo, passage au trading réel, et les points
> de sécurité à connaître). Pour créer tes clés API exchange par exchange,
> vois **[GUIDE_API.md](GUIDE_API.md)**.

## Démarrage rapide (débutants)

1. **Installer** (crée l'environnement et installe tout automatiquement) :

   ```bash
   ./install.sh
   ```

   Un assistant va te poser quelques questions simples (exchanges, paires à
   surveiller, etc.). Si tu n'as pas encore de clés API, choisis le **mode
   démonstration** : le bot fonctionnera sans rien risquer, juste pour te
   montrer les opportunités qu'il détecte.

2. **Lancer** le bot :

   ```bash
   ./start.sh
   ```

3. Pour changer la configuration plus tard (ajouter des clés API, passer en
   mode réel, changer les paires...), relance simplement `./install.sh`.

Sur Windows, utilise Git Bash ou WSL pour exécuter ces commandes `.sh`.

## ⚠️ À lire avant de passer en argent réel

- En mode réel (`dry_run: false`), le bot place de **vrais ordres avec de
  l'argent réel**. Un ordre peut s'exécuter à un prix différent de celui
  prévu, l'API d'un exchange peut échouer en cours de route, et la jambe
  d'achat peut être exécutée alors que la jambe de vente échoue, te
  laissant avec une position ouverte non couverte.
- L'arbitrage inter-exchange suppose que tu as **déjà des fonds sur chaque
  exchange** (la monnaie de cotation côté achat, la monnaie de base côté
  vente) — il n'y a pas le temps de transférer des cryptos entre exchanges
  avant que l'écart de prix ne disparaisse.
- Commence toujours par le mode démonstration et observe les logs plusieurs
  jours avant d'envisager le mode réel.
- Utilise des clés API avec uniquement les droits de **trading**, jamais de
  droit de retrait.
- Tu es seul responsable des fonds que tu engages avec ce bot.

## Configuration manuelle (avancé)

Si tu préfères éditer les fichiers toi-même plutôt que d'utiliser
`./install.sh` :

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # puis renseigne tes vraies cles API
```

Dans `config.yaml` :

- `exchanges` : identifiants ccxt des exchanges à comparer (doivent
  correspondre aux préfixes des clés dans `.env`)
- `pairs` : paires à surveiller, format ccxt (ex. `BTC/USDT`)
- `min_profit_threshold` : profit net minimum (après frais des deux
  exchanges) pour agir, en fraction (`0.005` = 0.5 %)
- `max_trade_size_quote` : plafond de taille de trade en monnaie de
  cotation
- `request_timeout_seconds` : temps d'attente max (en secondes) avant
  d'abandonner une requête à un exchange. Augmente-le si ta connexion est
  lente ou instable (par défaut 30)
- `dry_run` : garder `true` tant que tu n'as pas validé le comportement
  dans les logs

## Problèmes de connexion

**Diagnostic en un clic** : lance `./diagnose.sh` (Windows : via Git Bash).
L'outil teste ta connexion internet puis chaque exchange un par un, et
t'explique en clair pourquoi chacun est joignable ou non (blocage
géographique, connexion trop lente, pare-feu, clés API...).

Le bot se débrouille déjà tout seul dans la plupart des cas : il réessaie,
utilise le proxy système s'il y en a un, résout les noms via le DNS du
système (comme `curl` et le navigateur, et non via un résolveur tiers qui
échoue sur certains réseaux), et si le **DNS** de la machine est lui-même
cassé, il bascule automatiquement sur un DNS public (1.1.1.1 / 8.8.8.8) —
le tout sans aucune manipulation.

Si le bot affiche « impossible de se connecter aux exchanges » :

- Certains exchanges (dont Binance) **bloquent l'accès depuis certains
  pays**. Si `diagnose.sh` indique un blocage géographique, ce n'est pas un
  bug : remplace l'exchange concerné par un autre (Kraken, KuCoin, OKX
  fonctionnent souvent là où Binance est bloqué) en relançant
  `./install.sh`, ou utilise un VPN vers un pays autorisé.
- Il réessaie automatiquement chaque exchange plusieurs fois, et ignore
  ceux qui restent injoignables au lieu de tout bloquer (il lui faut au
  moins 2 exchanges joignables pour comparer les prix).
- Au démarrage, il teste lui-même ta connexion internet et te dit s'il
  s'agit d'une absence totale de connexion, ou d'un réseau qui fonctionne
  mais bloque l'accès aux sites crypto (opérateur/pare-feu).
- Sur une connexion lente, augmente `request_timeout_seconds` dans
  `config.yaml` (par exemple `60`).
- Si ton opérateur ou ton réseau bloque les exchanges crypto, essaie un
  autre réseau (Wi-Fi au lieu de 4G, ou inversement) ou un VPN.

## Lancer le bot manuellement

```bash
.venv/bin/python main.py
```

Les logs s'affichent dans le terminal et sont écrits dans le fichier
configuré sous `logging.file` (par défaut `logs/arbitrage.log`).

## Tests

```bash
.venv/bin/python -m pytest
```

Les tests couvrent les calculs de profit/frais, le filtrage des
opportunités, le chargement et la validation de la configuration, la
récupération des prix, les garde-fous de l'exécuteur (soldes, dérapage,
échec d'une jambe), la résilience de connexion (réessais et abandon d'un
exchange injoignable) et le diagnostic réseau — le tout sans aucun appel
réel aux exchanges.

## Fonctionnement

1. `bot/scanner.py` interroge le dernier prix de chaque paire configurée
   sur chaque exchange et calcule le profit net (après frais taker) entre
   un achat sur l'un et une vente sur l'autre.
2. Les opportunités au-dessus de `min_profit_threshold` sont transmises à
   `bot/executor.py`.
3. En mode `dry_run`, l'exécuteur se contente de logger ce qu'il *ferait*.
   En mode réel : il vérifie les soldes disponibles, recontrôle les prix
   pour détecter un dérapage (`max_slippage`), puis place un ordre d'achat
   au marché sur l'exchange le moins cher et un ordre de vente au marché
   sur l'exchange le plus cher.

## Limites connues

- Pas d'analyse de la profondeur du carnet d'ordres — utilise le dernier
  prix échangé, donc l'exécution réelle peut différer du prix scanné
  (atténué par le contrôle de dérapage, pas éliminé).
- Pas de rééquilibrage automatique des fonds entre exchanges.
- Pas de persistance entre redémarrages (pas de suivi de position au-delà
  de ce que chaque exchange rapporte).

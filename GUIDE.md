# Guide d'utilisation — Bot d'arbitrage crypto

Ce guide explique, étape par étape et en langage simple, comment utiliser le
bot : de l'installation jusqu'au trading réel. Prends ton temps, lis tout une
fois avant de commencer.

---

## 1. C'est quoi ce bot, en une phrase

Il compare en continu le prix d'une même crypto (ex. Bitcoin) entre plusieurs
exchanges (Binance, Kraken...) et, quand l'écart de prix est assez grand pour
être rentable **après les frais**, il peut **acheter là où c'est moins cher et
vendre là où c'est plus cher** — automatiquement.

Le bot **trade tout seul**. Tu ne cliques pas « acheter » à la main : tu le
surveilles, et lui exécute quand c'est rentable.

---

## 2. Installer et lancer (mode démonstration, sans risque)

1. Décompresse le dossier du bot dans un endroit simple (ex. le Bureau).
   > Astuce : ne garde qu'**une seule** copie du dossier, pour ne pas lancer
   > par erreur une vieille version.
2. Lance **`install.sh`** (sur Windows : clic droit → *Git Bash Here*, puis
   tape `./install.sh`).
   Un assistant te pose quelques questions simples (exchanges, paires...).
3. Si l'assistant demande le mode : choisis **démonstration** (aucun risque).
4. Lance **`start.sh`**.

En mode démonstration, le bot **n'achète jamais rien**. Il affiche seulement
ce qu'il observe et ce qu'il *ferait*.

### Conseil pour une connexion lente
Choisis **seulement 2 exchanges** (ex. Binance + Kraken) : c'est plus rapide à
démarrer et 2 suffisent pour comparer les prix.

---

## 3. Comprendre ce qui s'affiche

Au démarrage tu verras, par exemple :

```
Bot d'arbitrage version 1.5.3
Diagnostic DNS : resolveur=ThreadedResolver, test api.binance.com=OK
Connexion aux exchanges en cours (binance, kraken)...
Connecte a binance
Connecte a kraken
Tous les exchanges sont connectes : binance, kraken
```

Puis, toutes les 10 secondes, une ligne de « battement de cœur » :

```
Scan OK (2 exchanges) — meilleur ecart net : -0.230% sur ETH/USDT (binance->kraken) | seuil 0.500% | 0 opportunite(s) exploitable(s)
```

Ça veut dire : **le bot travaille bien.** Ici le meilleur écart du moment est
-0,23 %, c'est en dessous du seuil de 0,5 %, donc le bot n'agit pas.

> **C'est normal de ne « rien voir » pendant longtemps.** Les vraies
> opportunités rentables sont rares (voir section 6). Tant que la ligne
> « Scan OK » défile, tout va bien.

Quand une opportunité dépasse le seuil, en démonstration tu verras :

```
[DRY RUN] BTC/USDT: buy on binance @ 109820, sell on kraken @ 110500, net profit 0.62%
```

`[DRY RUN]` = simulation. Le bot montre ce qu'il *ferait*, sans rien acheter.

---

## 4. Passer au trading RÉEL (argent réel)

⚠️ **À ne faire que quand tu as observé la démo et que tu comprends le
comportement du bot.** À partir d'ici, le bot utilise ton vrai argent.

### Ce qu'il te faut avant

1. **Des clés API** sur chaque exchange utilisé, avec le droit de
   **TRADING UNIQUEMENT** — jamais le droit de **retrait/withdrawal**
   (sécurité : même si les clés fuient, personne ne peut sortir tes fonds).
   > 📖 Marche à suivre détaillée, exchange par exchange :
   > **[GUIDE_API.md](GUIDE_API.md)**.
2. **Des fonds déjà présents des DEUX côtés.** Le bot **ne transfère pas** de
   crypto entre exchanges (trop lent). Il faut donc, par exemple :
   - sur l'exchange où il **achète** : de l'**USDT** ;
   - sur l'exchange où il **vend** : déjà de la **crypto** (BTC, ETH...).

### Les étapes

1. Relance **`install.sh`**.
2. Entre tes **clés API** quand c'est demandé.
3. Indique ton **montant maximum par trade** (commence petit, ex. 20 à 50 USDT).
4. À la dernière question, tape **`ACTIVER`** pour activer le trading réel.
   (Si tu appuies juste sur Entrée, tu restes en démonstration.)
5. Lance **`start.sh`**. Le bot surveille et exécute automatiquement dès qu'une
   opportunité rentable apparaît. Surveille les logs.

Pour **revenir en démonstration** à tout moment : relance `install.sh` et
n'écris pas `ACTIVER` à la dernière question.

---

## 5. Comment un trade réel se passe

Quand le bot trouve un écart > seuil, il fait, **en même temps** :

1. un **achat au marché** sur l'exchange le moins cher ;
2. une **vente au marché** sur l'exchange le plus cher.

Avant d'agir, il vérifie :
- que tu as **assez de solde** des deux côtés ;
- que l'écart est **toujours là** (contrôle de « slippage ») — sinon il annule.

Le profit = différence de prix − frais des deux exchanges.

---

## 6. À lire absolument (la réalité, sans enrobage)

- **Les vraies opportunités > 0,5 % sont RARES** entre gros exchanges. Des
  robots professionnels les raflent en millisecondes. Il peut se passer des
  heures ou des jours sans aucun trade. **Ce n'est pas une machine à cash
  automatique.**
- **C'est de l'argent réel et il y a des risques :**
  - un ordre peut s'exécuter à un prix un peu différent (slippage) ;
  - l'API d'un exchange peut échouer en cours de route : l'achat passe mais
    pas la vente → tu te retrouves avec une position non couverte ;
  - les frais réduisent le profit (déjà pris en compte dans le calcul).
- **Commence petit** : un petit `max_trade_size_quote` (20-50 USDT) le temps de
  prendre confiance.
- **Tu es seul responsable** des fonds que tu engages avec ce bot.

---

## 7. Réglages utiles (fichier `config.yaml`)

Tu peux ouvrir `config.yaml` avec un éditeur de texte pour ajuster :

- `min_profit_threshold` : profit minimum pour agir. `0.005` = 0,5 %.
  - Baisse-le à `0.001` (0,1 %) **en démonstration** si tu veux voir le bot
    réagir plus souvent (juste pour comprendre le mécanisme).
- `max_trade_size_quote` : montant maximum par trade (en USDT).
- `scan_interval_seconds` : fréquence des scans (par défaut 10 secondes).
- `request_timeout_seconds` : temps d'attente max par exchange. Augmente-le
  (ex. `90`) si ta connexion est très lente.

Après modification, relance `start.sh`.

---

## 8. Si ça ne se connecte pas

Lance **`diagnose.sh`** : l'outil teste ta connexion internet puis chaque
exchange un par un, et t'explique en clair où est le problème (connexion
lente, blocage, DNS...). Le bot gère déjà tout seul la plupart des cas
(réessais, DNS, proxy système).

---

## Rappel de sécurité

- Clés API : **trading seulement, jamais de retrait**.
- Ne partage **jamais** ton fichier `.env` (il contient tes clés).
- Commence **toujours** en démonstration, puis en réel avec de petits montants.

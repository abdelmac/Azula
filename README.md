# Azula

Première tranche d’un ERP web : clients, catalogue sans stock, factures, règlements manuels et comptabilité de démonstration. Vue 3/TypeScript et Django REST Framework, avec **PostgreSQL uniquement**.

L’interface est disponible en français, anglais, arabe, allemand et turc. La langue de l’utilisateur, celle du document, la devise et les conventions régionales sont distinctes. Les traductions initiales nécessitent une relecture humaine.

Ce prototype n’est ni un ERP complet, ni un logiciel audité ou fiscalement certifié. Aucun pays fiscal n’est configuré. Les documents imprimés portent une mention de démonstration. La taxe de 20 % du scénario est une donnée d’essai.

## Démarrage avec Docker Compose

Sur le **serveur de développement**, installer Docker avec Compose et Python 3 pour générer la configuration. Docker n’est pas nécessaire sur les postes utilisateurs : un navigateur et l’accès au serveur suffisent.

Sous Windows, utiliser [Docker Desktop avec WSL 2](https://docs.docker.com/desktop/setup/install/windows-install/). À la première installation de [WSL](https://learn.microsoft.com/en-us/windows/wsl/install), redémarrer Windows lorsque demandé pour terminer l’activation de la plateforme de virtualisation, puis démarrer Docker Desktop avant les commandes ci-dessous.

Depuis la racine, dans PowerShell ou un terminal macOS :

```text
python scripts/setup_env.py
docker compose up -d --build
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py bootstrap_admin --username administrateur --company-name "Ma société" --currency EUR
```

La commande demande deux fois un mot de passe d’au moins 12 caractères, sans mot de passe partagé. `EUR` est un exemple explicite à remplacer par votre choix ; la langue ne choisit jamais la devise. Le premier administrateur crée la société et son plan de comptes de démonstration. Une deuxième initialisation est refusée.

Ouvrir **http://localhost:8080**. Dans les paramètres, vérifier les coordonnées, la devise, la précision et créer une période ouverte couvrant les dates de facture et de règlement. Les migrations sont une étape explicite ; le démarrage du serveur ne modifie pas automatiquement le schéma.

Sous macOS, employer `python3` à la place de `python` si nécessaire. Pour un environnement sans Docker, suivre [le guide Windows/macOS](docs/development.md).

## Déploiement Internet à 0 €

L’instance **[azula.onrender.com](https://azula.onrender.com)** est déployée sur **Render Free**, avec une base **Neon Free** séparée, à Francfort. La connexion HTTPS et le thème bleu ont été vérifiés le 7 septembre 2026. Les accès Internet sont conservés sur le poste de déploiement dans `.local/azula-cloud-access.json`, hors Git ; ils sont distincts des accès locaux.

Le profil [render.yaml](render.yaml) et [le guide de déploiement](docs/deployment.md) documentent l’installation et son évolution vers des offres payantes sans réécrire l’application. Render Free met l’application en veille après 15 minutes sans activité ; le premier accès peut être plus lent. Les données restent dans Neon, dans les quotas gratuits. Aucun abonnement payant n’a été souscrit ; les déploiements automatiques sont désactivés.

## Parcours de démonstration manuel

1. Se connecter avec l’administrateur créé. Ajouter une période ouverte dans les paramètres.
2. Créer un client, puis une facture avec une ligne : quantité `1`, prix hors taxe `100.00`, taxe de test `20`.
3. Enregistrer le brouillon : les montants calculés par le serveur sont `100.00`, `20.00`, `120.00`.
4. Valider : numéro unique et copie figée du document. Le journal contient client au débit `120.00`, revenu au crédit `100.00`, taxe au crédit `20.00`.
5. Enregistrer un règlement manuel de `50.00`, à une date incluse dans une période ouverte : banque au débit `50.00`, client au crédit `50.00`, solde `70.00`.
6. Enregistrer `70.00` : solde nul. Une répétition avec la même clé d’idempotence ne crée aucun règlement supplémentaire.
7. Consulter le journal et la balance de la période. Changer les langues de l’interface. Pour une facture arabe, choisir cette langue **avant** validation puis ouvrir la version imprimable.

L’impression utilise le navigateur, y compris sa fonction « Enregistrer au format PDF ». Il n’existe pas d’export PDF serveur. Les factures validées ne sont plus modifiables ou annulables ; les avoirs et remboursements sont hors de cette tranche.

## Données synthétiques facultatives

L’application normale ne crée aucun faux client, facture ou chiffre d’activité. Les commandes suivantes sont réservées à une installation jetable. Activer explicitement `ALLOW_DEMO_DATA=1` dans `.env`, conserver `ENVIRONMENT=development`, puis recréer le conteneur backend si nécessaire :

```text
docker compose up -d backend
docker compose exec backend python manage.py seed_demo --company 1 --confirm-synthetic
```

Le scénario crée une facture de `120.00` et un premier règlement de `50.00`. Pour préparer un volume de mesure, employer **une installation avec une base jetable dédiée**, puis :

```text
docker compose exec backend python manage.py seed_performance --company 1 --confirm-synthetic --invoices 100000 --customers 10000 --batch-size 1000
```

Le générateur volumétrique crée des **brouillons avec lignes**, sans fabriquer de journal comptable validé. Ces deux commandes refusent l’environnement `production` et n’effacent aucune donnée. Désactiver `ALLOW_DEMO_DATA` après usage.

## Vérifications et documentation

Les résultats réellement obtenus et leurs limites sont consignés dans [le rapport de vérification](docs/verification.md). La CI lance les migrations depuis une base vide, les tests PostgreSQL, les contrôles frontend et Playwright ; elle a réussi pour le [commit déployé `d9adab9`](https://github.com/abdelmac/Azula/actions/runs/34163887967).

- [Installation et développement Windows/macOS](docs/development.md)
- [Architecture, permissions et règles comptables](docs/architecture.md)
- [Exploitation, HTTPS, sauvegarde et restauration](docs/operations.md)
- [Protocole et mesures de performance](docs/performance.md)
- [Suivi et feuille de route](docs/status.md)

Une installation sur un serveur du réseau local peut fonctionner sans Internet après installation des dépendances. Il faut rester connecté à ce serveur : aucune synchronisation ni utilisation autonome hors ligne n’est proposée.

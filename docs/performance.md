# Performance : protocole et mesures

Les budgets ci-dessous sont des objectifs, pas des garanties : JavaScript initial de production ≤250 Ko gzip ; liste simple p95<500 ms avec 10 requêtes concurrentes sur un serveur décrit ; utilisation sur un véritable ordinateur double cœur avec 4 Go de RAM.

## JavaScript

Depuis `frontend/`, `npm run build` puis `npm run size`. Le script compte l’entrée Vite, ses imports statiques transitifs, le catalogue français et la route de connexion nécessaires au premier écran, puis les comprime en gzip ; il indique leurs noms exacts. Les autres routes et langues restent chargées à la demande et ne sont pas comprises dans ce total. La taille initiale ne mesure ni le chargement réseau complet, ni le rendu navigateur. Le rapport de vérification conserve les valeurs réellement produites.

Le hook `postbuild` écrit également les variantes `.gz` des ressources dans `dist/assets/`. WhiteNoise les sert quand le navigateur annonce `Accept-Encoding: gzip`. Le fichier HTML d’entrée conserve une politique de revalidation, afin d’éviter un ancien écran après mise à jour.

## API et volumes

Sur une base synthétique dédiée, activer les données d’essai comme décrit au README, puis :

```text
python manage.py seed_performance --company 1 --confirm-synthetic --customers 10000 --invoices 100000 --batch-size 1000
```

Les factures volumétriques sont des brouillons avec lignes et totaux exacts. Le volume de règlements et d’écritures validées doit être indiqué séparément ; ce jeu ne suffit pas à évaluer un journal massif. Ne pas générer ces volumes dans une installation normale.

Après démarrage du build de production avec Waitress, depuis la racine :

```text
python scripts/benchmark_api.py --username mesure --url http://127.0.0.1:8080 --path invoices --requests 500 --concurrency 10
python scripts/benchmark_api.py --username mesure --url http://127.0.0.1:8080 --path customers --requests 500 --concurrency 10
```

Le mot de passe est demandé interactivement. Utiliser un compte de lecture dédié, sans divulguer ses cookies. Le script ne modifie pas les données métier ; il ouvre une session, effectue 10 requêtes de préchauffage, puis des requêtes paginées à 50 lignes et ferme la session. Il refuse HTTP distant. Le protocole représente 10 requêtes simultanées partageant un compte de lecture ; ce n’est pas un test complet de 10 utilisateurs aux comportements distincts.

Les résultats sont des temps **HTTP observés côté client**, incluant temps serveur, transport et lecture de la réponse, sans rendu navigateur. Le p95 est calculé au rang `ceil(0.95 × n)`. Décrire CPU, RAM, stockage, OS, versions Python/PostgreSQL, nombre de threads serveur, origine réseau, volumes réels et état chaud/froid du cache. Ne pas appeler cette valeur « temps serveur pur ».

## Plans SQL

Pour les requêtes observées lentes, ouvrir une session `python manage.py shell` sur la base synthétique. Exemples de plans sans modification des données :

```python
from erp.models import Customer, Invoice
print(Customer.objects.filter(company_id=1, archived=False).order_by('name', 'id')[:50].explain(analyze=True, buffers=True))
print(Invoice.objects.filter(company_id=1, status='draft').order_by('-issue_date', '-id')[:50].explain(analyze=True, buffers=True))
```

Pour un plan représentatif de l’API, inclure également les jointures/agrégats réellement employés par `InvoiceViewSet.get_queryset`. Mesurer séparément la requête de décompte et les recherches insensibles à la casse. Les index B-tree ne garantissent pas l’accélération de toutes les recherches `icontains` ; ajouter un index trigramme uniquement après mesure justifiée. La pagination par numéro de page utilise un offset et peut ralentir aux pages très profondes ; une pagination par curseur pourra être envisagée si le besoin est mesuré.

## Navigateur et machine modeste

Mesurer sur une machine double cœur/4 Go réelle : ouverture de liste, recherche temporisée, formulaire, changement de langue, mémoire de l’onglet et impression arabe. Garder les outils développeur fermés pour une mesure représentative, puis les utiliser séparément pour comprendre les délais. La latence réseau et le rendu navigateur ne doivent pas être confondus avec le temps SQL.

Un ralentissement CPU Playwright/DevTools constitue un essai complémentaire, jamais une validation matérielle. Les chiffres non mesurés restent signalés comme tels dans `verification.md`.

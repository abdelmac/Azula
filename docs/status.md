# État de la première tranche

## Abonnements — 11 septembre 2026

Le module [Abonnements](abonnements.md) est **publié sur [azula.onrender.com](https://azula.onrender.com)**. Le [commit `6233d061cf43b4ad5b3e5255931e1428150919df`](https://github.com/abdelmac/Azula/commit/6233d061cf43b4ad5b3e5255931e1428150919df) est confirmé `live` sur le service Render Free existant, avec la même base Neon Free séparée.

Le module propose les abonnements mensuels ou annuels par société, Stripe Checkout, un portail de gestion, les notifications signées et le contrôle d’accès serveur aux modules ERP. La page reste accessible lorsque l’abonnement expire ; seuls les administrateurs peuvent souscrire ou gérer l’abonnement. Le retour depuis la page de paiement ne suffit pas à ouvrir l’accès : le serveur attend la confirmation du prestataire.

Sur l’instance publique, **`BILLING_ENABLED=0`** et aucun tarif ni compte Stripe n’est configuré. Les sociétés existantes conservent leur accès. L’activation commerciale, les tarifs et la configuration Stripe restent à décider par l’exploitant ; aucun paiement réel n’a été créé par cette publication.

La [CI du commit déployé](https://github.com/abdelmac/Azula/actions/runs/34611793412) a réussi. Les **539 tests backend, 18 tests Vitest et 33 scénarios Playwright** ont réussi en local, sur des données de test séparées et avec paiements simulés pour l’abonnement. Les contrôles publics HTTPS, cookies, CSRF, API, exports CSV et neuf modules ont réussi sans écriture métier. La page Abonnements confirme la facturation désactivée, l’absence de tarifs et de configuration Stripe, et l’accès conservé. L’affichage arabe à 390 pixels ne déborde pas ; la langue initiale a été restaurée et les identifiants sont inchangés. Les résultats sont consignés dans [verification.md](verification.md).

## Évolution ERP — historique du 10 septembre 2026

Les fiches clients et articles détaillées, tarifs clients, relevés, remises par ligne, duplication de brouillons, atelier d’impression, API externes à clés révocables, import et rapprochement bancaire, tableau de bord et exports CSV ont été publiés le 10 septembre sur [azula.onrender.com](https://azula.onrender.com). Le commit `bef3209cc84203f1cfe236fbe5d321fe5db76e71` avait été confirmé `live` sur le service Render Free existant, avec la base Neon Free séparée. Ces fonctions restent intégrées à la version du 11 septembre décrite ci-dessus.

La [CI du commit déployé](https://github.com/abdelmac/Azula/actions/runs/34512026795) a réussi, avec 310 cas backend ; les 18 tests Vitest et les 24 scénarios Chrome ont réussi en local. Une sauvegarde vérifiée a précédé les migrations ERP `0005` à `0007` et connections `0001`/`0002`. Les anciennes données, droits et protections PostgreSQL ont été conservés ; aucun secret ni mot de passe n’a changé. Les contrôles publics HTTPS, API, exports, huit modules et navigation mobile arabe ont réussi, sans création ni modification d’objet métier.

Le [guide de cette évolution](evolution-erp.md) décrit les écrans et leurs limites. Les résultats effectifs de publication sont suivis dans [verification.md](verification.md). Les sections historiques ci-dessous conservent les résultats des versions précédentes.

## Évolution du catalogue — 8 septembre 2026

État historique du 8 septembre : la [liste des prix](catalogue.md) et ses paramètres étaient implémentés, avec classes, entrepôts, unités, prix d’achat, caractéristiques, photos HTTPS, filtres et impression. **212 tests backend, 18 tests Vitest et 9 tests Chrome avaient réussi**, avec migration vérifiée sur PostgreSQL de test. Le catalogue restait alors à publier ; il est maintenant intégré au déploiement ERP du 10 septembre décrit ci-dessus.

## Socle initial — historique du 7 septembre 2026

- Socle Vue 3/TypeScript/Vite/Router/I18n et Django REST Framework, PostgreSQL exclusif.
- Sessions, protection CSRF, limitation des connexions persistante, premier administrateur par commande, quatre rôles.
- Configuration de la société, utilisateurs, langues, devise/précision et périodes.
- Clients et catalogue : création, lecture, modification, archivage, recherche/tri/pagination serveur.
- Factures brouillon, calcul Decimal serveur, validation atomique, numérotation, snapshot figé.
- Règlements manuels partiels/complets, solde exact, idempotence et protection contre dépassement.
- Comptes/journaux de démonstration, écritures automatiques, balance par période et historique d’audit.
- Contraintes et triggers PostgreSQL pour les invariants, restrictions API et admin sur les objets validés.
- Cinq catalogues traduits, RTL, impression HTML depuis le snapshot, ressources locales.
- Tests Python unitaires, tests PostgreSQL financiers/API/concurrence, Vitest et scénarios Playwright.
- Dépendances verrouillées, Docker Compose, CI PostgreSQL, installation Windows/macOS et documentation d’exploitation.
- Générateurs synthétiques protégés, protocole de mesure HTTP et calcul de taille JavaScript.

« Implémenté » décrit la présence du code. Cela ne signifie pas que tous les parcours ont été exécutés ; les résultats exacts sont dans [verification.md](verification.md).

Contrôles réellement réussis après adaptation du thème bleu et préparation de l’hébergement : **161 tests Python**, dont les 63 tests PostgreSQL API/comptabilité/concurrence et le contrôle de santé PostgreSQL, **18 tests Vitest**, **6 tests Chrome sans aucun ignoré**, build/types/lints. Le parcours réel client → facture 120 → règlements 50/70 → journal → impression arabe a réussi sur la base séparée `azula_e2e`. La mesure antérieure du JavaScript du premier écran sur Windows est de 65 317 octets gzip ; elle n’a pas été remesurée dans Docker.

Le déploiement initial du 7 septembre utilisait le commit `d9adab9` sur **Render Free + Neon Free**, à Francfort. Le rôle PostgreSQL restreint et TLS `verify-full` avaient été contrôlés, ainsi que la sonde PostgreSQL, la connexion administrateur, les cookies sécurisés, le refus des accès anonymes et des actions sans CSRF, le thème bleu et l’affichage arabe mobile. Aucun client ni facture d’essai n’avait été créé en ligne. Ces vérifications historiques ne remplacent pas celles de la version courante. Les accès Internet sont dans `.local/azula-cloud-access.json` sur le poste de déploiement ; voir [deployment.md](deployment.md).

## Démarrage local vérifié — historique du 7 septembre 2026

- Docker Desktop 4.90.0, WSL 2.7.13, moteur Docker 29.7.2 et Compose 5.5.1 installés et disponibles après redémarrage Windows.
- `docker compose up -d --build` réussi ; PostgreSQL 17.11 sain et Azula actif uniquement sur `http://localhost:8080`.
- Migrations appliquées depuis une base vide, contrôles Django, tests d’intégration/concurrence et parcours réel de bout en bout réussis.
- Premier administrateur local créé ; mot de passe aléatoire dans `.local/azula-access.json`, hors Git, droits Windows restreints. Société de développement en EUR, sans pays fiscal. Connexion réelle vérifiée dans Chrome ; aucun client ni facture de test dans cette instance.
- L’ancien refus de `initdb.exe` natif par Windows ne bloque plus le lancement via Docker. Aucune politique de sécurité n’a été désactivée.

## À vérifier sur une machine équipée

Restent les générateurs volumétriques, plans SQL, p95 API et restauration d’une sauvegarde. La [CI GitHub du commit courant `6233d061`](https://github.com/abdelmac/Azula/actions/runs/34611793412) et ses contrôles publics ont réussi. Sur chaque instance, créer une période comptable ouverte dans les paramètres avant de valider la première facture. Les quotas gratuits et la mise en veille doivent être pris en compte ; aucun abonnement payant ni déploiement automatique n’a été activé.

Restent également la relecture humaine des cinq langues, l’impression arabe sur les polices/imprimantes cibles, Safari/macOS, les autres moteurs de navigateur et l’essai sur un vrai ordinateur double cœur/4 Go. Les essais avec fixtures visuelles ne remplacent pas la démonstration de données réellement comptabilisées.

## Feuille de route hors tranche

- Choix du pays et analyse des obligations fiscales ; aucun régime fiscal déduit de la langue.
- Avoirs/remboursements puis corrections comptables contrôlées. En attendant, annulation/modification des documents validés refusée.
- Achats, fournisseurs, stock, paie, fabrication.
- Connexions bancaires directes et paiements réels ; l’import CSV et le rapprochement manuel sont disponibles dans l’évolution du 10 septembre.
- Devises multiples/conversion et facturation électronique réglementaire.
- Synchronisation hors ligne, applications natives et éventuelle offre SaaS.
- Après mesures : pagination par curseur si nécessaire, index de recherche spécialisés et verrouillage plus fin des écritures.

Aucun faux écran ni bouton inactif n’annonce ces modules comme disponibles.

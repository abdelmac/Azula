# État de la première tranche

## Implémenté

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

Contrôles réellement réussis : 72 tests Python sans base, 18 tests Vitest, 5 essais Chrome d’interface avec fixtures, build/types/lints. JavaScript du premier écran : 65 317 octets gzip. Le parcours navigateur PostgreSQL reste ignoré et 63 tests PostgreSQL restent à exécuter.

## Bloqué dans cet environnement

- Démarrage PostgreSQL : programme officiel `initdb` refusé par le contrôle d’applications Windows (`0xc0e90002`). Ni Docker ni WSL disponibles.
- Application des migrations depuis une base vide, tests d’intégration/concurrence et parcours complet réel de bout en bout.
- Exécution des générateurs volumétriques, plans SQL, p95 API et restauration d’une sauvegarde.

## À vérifier sur une machine équipée

Prochaine tâche précise : sur une machine avec Docker, exécuter le démarrage README, appliquer les migrations puis lancer `docker compose exec backend python -m pytest`. Préparer ensuite la base `azula_e2e` et exécuter le projet Playwright `workflow-chromium`, ou exécuter la CI fournie sur une branche autorisée. Corriger tout échec PostgreSQL avant de considérer le parcours comptable validé.

Restent également la relecture humaine des cinq langues, l’impression arabe sur les polices/imprimantes cibles, Safari/macOS, les autres moteurs de navigateur et l’essai sur un vrai ordinateur double cœur/4 Go. Les essais avec fixtures visuelles ne remplacent pas la démonstration de données réellement comptabilisées.

## Feuille de route hors tranche

- Choix du pays et analyse des obligations fiscales ; aucun régime fiscal déduit de la langue.
- Avoirs/remboursements puis corrections comptables contrôlées. En attendant, annulation/modification des documents validés refusée.
- Achats, fournisseurs, stock, paie, fabrication.
- Rapprochement bancaire, connexions bancaires et paiements réels.
- Devises multiples/conversion et facturation électronique réglementaire.
- Synchronisation hors ligne, applications natives et éventuelle offre SaaS.
- Après mesures : pagination par curseur si nécessaire, index de recherche spécialisés et verrouillage plus fin des écritures.

Aucun faux écran ni bouton inactif n’annonce ces modules comme disponibles.

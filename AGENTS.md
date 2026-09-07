# Azula — conventions

- Répondre et documenter en français ; identifiants de code en anglais.
- Monolithe : `backend/` Django REST Framework + PostgreSQL, `frontend/` Vue 3 TypeScript, `docs/`.
- Aucun float faisant foi pour les montants. API : chaînes décimales, arrondi HALF_UP par ligne, précision figée à la validation.
- Toutes les données métier et recherches sont limitées à la société du compte connecté.
- Validations et règlements passent par des services atomiques, verrouillés et idempotents. Aucune suppression/modification d'écriture ou facture validée.
- Sessions HttpOnly et CSRF ; permissions vérifiées au serveur. Aucun secret dans Git. Pas de déploiement public.
- PostgreSQL également pour les tests. Ne pas utiliser SQLite. Aucune opération sur une base réelle.
- Frontend : textes dans les catalogues fr/en/ar/de/tr, CSS logiques, routes/langues chargées à la demande.
- Vérifications : `python -m pytest` et `ruff check .` dans backend ; `npm run check`, `npm run test`, `npm run build`, `npm run test:e2e` dans frontend.
- Documenter les contrôles réellement exécutés et leurs limites dans `docs/verification.md`.

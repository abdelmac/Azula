# Catalogue et liste des prix

L’écran **Catalogue** reprend les options de la liste des prix montrée en référence : code et nom d’article, classe, entrepôt, devise, type de prix, unité, statut, caractéristiques et photo. L’interface garde les couleurs Azula et les cinq langues. Les autres menus visibles dans la capture (restaurant, fabrication, banques, etc.) ne font pas partie de cet ajout.

## Configurer les références

Dans **Paramètres → Catalogue**, un administrateur peut créer, modifier, archiver et restaurer les **classes d’articles**, **entrepôts** et **unités**. Chaque référence possède un code unique dans la société, de 40 caractères maximum, et un nom de 150 caractères maximum. Les listes sont recherchables et paginées.

L’archivage préserve les affectations existantes. Une référence archivée n’est plus proposée pour une nouvelle affectation ; elle reste utilisable dans les filtres pour retrouver les articles historiques. Les API appliquent les permissions et la société du compte connecté à toutes les lectures et écritures. Les rôles administrateur, comptable et commercial peuvent gérer ces références par l’API, comme les articles ; l’onglet de configuration reste dans les paramètres administrateur.

## Renseigner un article

**Catalogue → Nouvel article** propose les champs suivants :

| Champ | Comportement |
| --- | --- |
| Code et nom | Obligatoires ; code unique par société. |
| Classe | Une classe facultative pour le classement et la recherche. |
| Unité | Unité par défaut facultative, par exemple pièce ou boîte. |
| Entrepôts | Plusieurs affectations possibles ; recherche et pagination dans le sélecteur. |
| Prix d’achat | Facultatif. Vide signifie « non renseigné », sans être remplacé par zéro. |
| Prix de vente et taxe | Champs existants utilisés par la facturation. |
| Caractéristiques | Texte libre de 4 000 caractères maximum. |
| URL de la photo | Adresse HTTPS de 1 000 caractères maximum, sans identifiants dans l’URL. |

Les montants restent des chaînes décimales dans l’API, avec jusqu’à six décimales pour les prix. La photo est chargée par le navigateur sans en-tête de provenance ; le serveur ne télécharge pas l’URL. Une image manquante ou inaccessible affiche un pictogramme de remplacement. Il n’y a pas de téléversement de fichier dans cette version.

## Consulter et imprimer les prix

Le sélecteur **Type de tarification** affiche le prix d’achat ou le prix de vente. Il détermine également le prix utilisé par le tri croissant ou décroissant. La devise affichée est celle de la société ; aucune conversion n’est effectuée. Changer ce sélecteur ne modifie aucun tarif enregistré.

La recherche rapide par nom ou code est accessible avec **F3**. Elle recherche également dans la classe et les caractéristiques. Les filtres classe, entrepôt, unité, statut et caractéristiques se combinent côté serveur ; le filtre de caractéristiques accepte 128 caractères maximum. Le bouton de réinitialisation efface les filtres et revient aux articles actifs.

**Imprimer les prix** ouvre l’impression du navigateur pour la **page courante**, après son chargement. Le document indique la société, la devise, le type de prix, les filtres, le numéro de page et le nombre d’articles affichés par rapport au total. Pour enregistrer un PDF, utiliser la destination PDF du navigateur. L’impression de toutes les pages en une seule opération n’est pas proposée.

Les entrepôts sont des affectations de catalogue : il n’y a pas de calcul de stock, de mouvements ou d’achat fournisseur. L’unité sert à décrire le tarif ; les conversions d’unités et les tarifs par conditionnement ne sont pas implémentés. La sélection d’un article dans une facture continue d’utiliser son **prix de vente**. Une facture validée garde son snapshot, même si l’article ou ses références changent ensuite.

## Mise à jour d’une installation

La migration additive `0005_catalog_parameters` crée les trois référentiels, la table de liaison des entrepôts et les nouveaux champs de produit. Elle conserve les prix de vente et les factures existants ; les anciens produits commencent avec un prix d’achat inconnu et des références vides.

Après migration, un rôle PostgreSQL restreint a besoin des droits `SELECT, INSERT, UPDATE, DELETE` sur `erp_productcategory`, `erp_warehouse`, `erp_unit`, `erp_product_warehouses`, ainsi que `USAGE, SELECT` sur leurs séquences. Aucun droit supplémentaire n’est nécessaire sur les factures ou écritures. Suivre [le guide de déploiement](deployment.md) pour préparer une sauvegarde et appliquer la migration dans le cadre autorisé. Les résultats réellement exécutés sont dans [verification.md](verification.md).

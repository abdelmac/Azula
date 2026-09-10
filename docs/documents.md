# Édition et impression des factures

Les brouillons acceptent une référence client/commande, un objet, des notes, des conditions de paiement et une adresse de livraison. L’éditeur permet de copier et réordonner les lignes. Les lignes enregistrées conservent leur ordre.

Chaque ligne accepte une remise décimale de 0 à 100 %, sur quatre décimales au maximum. Le calcul canonique est `arrondi_HALF_UP(quantité × prix_unitaire × (1 − remise / 100), précision_société)`. La taxe est calculée sur ce net arrondi, puis arrondie par ligne. Les totaux restent des chaînes décimales produites par le serveur. Une facture entièrement gratuite peut rester en brouillon ; sa validation est refusée faute de montant positif à comptabiliser.

La sélection d’un client préremplit l’échéance selon son délai de paiement, son adresse de livraison si elle est vide et la remise de la première ligne vide. L’ajout d’un article appelle son tarif client ; le changement de client ne réécrit pas les prix déjà saisis. Les prix spécifiques restent éditables avant enregistrement et validation.

Le studio d’impression propose les mises en page standard et compacte, une couleur, un logo HTTPS, les codes articles, la colonne des taux de taxe, les instructions de paiement et le pied de page. Les montants de taxe et le total restent visibles même lorsque la colonne des taux est masquée. L’aperçu du studio est explicitement fictif, en EUR, et n’enregistre aucune facture. Les textes sont échappés, sans HTML ni CSS arbitraires.

La validation fige ces options avec les données de facture. Les anciens instantanés restent lisibles grâce aux valeurs de présentation par défaut ; ils ne sont ni réécrits ni complétés en base. La langue d’impression peut être changée à l’écran sans modifier les faits enregistrés. L’impression/PDF utilise la boîte de dialogue du navigateur.

`GET /api/invoices/{id}/preview/` renvoie un instantané transitoire pour un brouillon, recalculé à la précision actuelle sous verrou société sans écriture de la facture. L’impression affiche obligatoirement « Brouillon ». Pour une facture validée, ce point d’entrée retourne l’instantané conservé. Il applique les mêmes droits de lecture et le même périmètre société que les factures.

`POST /api/invoices/{id}/duplicate/`, avec `Idempotency-Key` et les dates `issue_date`/`due_date`, crée un nouveau brouillon. Il copie les lignes, remises et champs documentaires, sans numéro définitif, règlement ou écriture comptable. Une répétition avec la même clé et le même contenu retrouve le même brouillon. Les références archivées, les références d’une autre société et les rôles sans préparation sont refusés.

La liste accepte `date_from`/`date_to` inclusifs sur la date d’émission, `customer`, `payment_status=unpaid|overdue|settled` et la recherche par référence client/objet. Les états de paiement ne concernent que les factures validées ; « en retard » exige un solde positif et une échéance strictement antérieure à la date du serveur.

Cette évolution concerne les factures de vente existantes. Les devis, commandes, avoirs, achats, expéditions, caisses et obligations nationales de facturation électronique nécessitent des workflows dédiés ; ils ne sont pas simulés par un titre libre de document.

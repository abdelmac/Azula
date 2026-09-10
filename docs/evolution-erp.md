# Évolution fonctionnelle d’Azula

Cette évolution reprend les usages visibles dans les écrans du logiciel de référence : fiches structurées, informations commerciales, prix clients, édition des documents, suivi des échéances et liens avec des applications externes. Le périmètre décrit le code ajouté ; la publication et les vérifications réellement effectuées sont consignées séparément dans [verification.md](verification.md).

## Clients et articles

La fiche client rassemble l’identité et les noms commerciaux, les interlocuteurs, les téléphones, le site Web, les coordonnées de facturation et de livraison, le groupe et la région, les renseignements bancaires, les conditions de règlement, le plafond de crédit, la remise habituelle, les notes et les champs complémentaires. La consultation des factures et du relevé permet de retrouver les montants facturés, réglés et restant dus du client. Les plafonds et renseignements descriptifs n’autorisent aucun prélèvement bancaire automatique.

Les tarifs client associent un prix de vente spécifique à un article. L’éditeur de facture utilise ce prix lorsque l’article est ajouté après sélection du client. Un changement de client ne remplace pas silencieusement les prix et remises des lignes déjà saisies.

Les articles conservent les classes, entrepôts, unités, prix d’achat/vente et photos introduits dans le [catalogue](catalogue.md). Les fiches ajoutent des renseignements tels que code-barres, nom alternatif, fabricant, fournisseur, origine, couleur, dimensions, poids et notes. Ces renseignements ne constituent pas une gestion de mouvements de stock, de lots, de fabrication ou d’approvisionnement.

## Factures et impression

Les brouillons proposent une référence client/commande, un objet, une livraison, des conditions et des notes imprimables. Les lignes peuvent être copiées et réordonnées. Une remise de 0 à 100 % est appliquée avant l’arrondi du net par ligne ; la taxe est ensuite calculée sur ce net arrondi. Les montants restent des chaînes décimales calculées au serveur. Le [guide des documents](documents.md) précise les règles et les points d’entrée.

Une facture peut être dupliquée en nouveau brouillon avec des dates choisies. Cette opération ne copie aucun règlement, numéro définitif ou écriture comptable. Les reprises réseau utilisent une clé d’idempotence. Les clients et articles archivés doivent être remplacés avant de créer une nouvelle facture qui les référence.

Le studio d’impression configure la présentation standard ou compacte, la couleur, le logo HTTPS, les codes articles, les taux par ligne, les instructions de paiement et le pied de page. Son exemple est identifié comme fictif. Les brouillons peuvent être prévisualisés et imprimés avec une mention explicite ; les factures validées utilisent leur instantané figé. La boîte de dialogue du navigateur propose l’impression et l’enregistrement PDF.

Les factures validées et les écritures restent immuables. Un objet libre de facture n’ajoute pas un workflow de devis, commande, avoir, retour, achat ou transfert de stock.

## API et applications externes

L’espace Connexions permet de déclarer une application et de créer des clés d’API ayant une échéance et des droits explicites. Le secret n’est présenté qu’à sa création, puis seul son condensat est conservé. Une clé peut être révoquée et une connexion désactivée. L’administration des clés reste réservée à l’administrateur de la société.

L’API versionnée `/api/external/v1/` fournit, selon les droits de la clé, la lecture du catalogue et des clients, la création de clients et de brouillons de facture, la lecture des factures et des transactions bancaires, ainsi que la réception de transactions provenant d’une application externe. Les exemples de requête dans l’interface utilisent un emplacement de clé à remplacer côté serveur.

Les créations externes exigent une clé d’idempotence. Les factures créées restent des brouillons ; les transactions externes reçues restent des informations à examiner. Leur réception ne valide aucune facture et ne comptabilise aucun règlement automatiquement. Les clés d’API ne remplacent pas les sessions HttpOnly et CSRF de l’interface utilisateur. Elles doivent être conservées côté serveur du site ou de l’application appelante, hors du JavaScript public.

Déclarer le nom d’une banque ou d’un prestataire ne le connecte pas. Cette évolution n’active aucun compte tiers, contrat bancaire, Open Banking, webhook de prestataire, virement sortant, prélèvement ou transfert d’argent. Les adaptateurs d’un fournisseur précis demandent son protocole, des identifiants dédiés et des essais en environnement de test.

## Banque et rapprochement

Les administrateurs et comptables disposent de fiches de comptes bancaires, d’un import CSV avec aperçu, d’une confirmation d’import et de listes filtrées. Le format comprend un identifiant externe stable, une date, un montant décimal signé, une description et une référence facultative. Un fichier est limité à 500 lignes et 250 000 octets. Les répétitions identiques sont reconnues ; un même identifiant portant un contenu différent est refusé.

Le rapprochement d’une entrée positive demande de choisir explicitement une facture validée. La confirmation crée un règlement via le service comptable existant, avec contrôle de la société, de la devise, du solde, de la précision et de la période ouverte. Une répétition ne crée pas de deuxième règlement. Les frais, sorties bancaires, remboursements et ventilations d’une ligne sur plusieurs factures n’ont pas de workflow comptable automatique dans cette version.

La devise et la précision de la société se figent lorsqu’un compte bancaire ou une transaction externe existe, ainsi qu’après la première facture validée. Cette règle évite de réétiqueter des montants historiques avec une nouvelle unité monétaire. Il n’y a pas de conversion entre devises.

## Tableau de bord et exports

Le tableau de bord montre les factures validées et encaissements sur les dates sélectionnées, les soldes ouverts et retards toutes dates confondues, les compteurs de clients/articles et des liens vers les documents concernés. Les chiffres proviennent des données de la société ; aucun chiffre d’activité de démonstration n’est injecté.

Les exports CSV couvrent les clients, articles, factures et, pour les rôles financiers, les règlements. Ils proposent la recherche et les filtres applicables à chaque objet. Un export est limité à 5 000 lignes et refuse un dépassement au lieu de livrer silencieusement un fichier tronqué. Les chaînes monétaires sont conservées et les cellules pouvant être interprétées comme formules par un tableur sont neutralisées.

## Exploitation et étapes suivantes

Les écrans suivent les cinq langues existantes, le sens arabe de droite à gauche et les permissions serveur. Toutes les recherches et mutations métier restent dans la société du compte. Les nouvelles migrations doivent être appliquées explicitement lors d’un déploiement, après sauvegarde ; le démarrage de l’application ne migre pas automatiquement une base existante.

Le code ne prétend pas reproduire tous les menus du logiciel de référence. Restent à concevoir les achats et fournisseurs opérationnels, stocks et inventaires, commandes et livraisons, devis/avoirs, points de vente et caisses, fabrication, paie, fidélité, pièces jointes gérées, automatisations de relance, synchronisation hors ligne et connecteurs de prestataires réels. Le pays fiscal, la facturation électronique réglementaire et les exigences locales nécessitent un cadrage distinct. Les résultats de tests et l’état exact du site Internet doivent être lus dans le rapport de vérification, sans déduire une publication de la seule présence d’un écran dans le dépôt.

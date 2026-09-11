# Contrat de travail API v1

Toutes les routes sous `/api/`, slash final. Sessions Django + CSRF pour l’interface ; les routes externes `/api/external/v1/` utilisent exclusivement une clé Bearer limitée par droits, société et échéance. Listes `{count,next,previous,results}` ; pagination `page`, `page_size` (50, max 100), `search`, `ordering`. Dates ISO. Montants chaînes décimales. Erreurs `{code, detail}` ; UI traduit `code`, ne montre jamais de message anglais interne.

Les extensions du 10 septembre sont documentées dans [clients et tarifs](clients-et-tarifs.md), [documents et impression](documents.md) et [connexions API et banque](connexions.md). Ces guides complètent les champs des contrats historiques ci-dessous.

- GET `dashboard/?start=YYYY-MM-DD&end=YYYY-MM-DD` → `{currency,precision,metrics:{invoiced,received,outstanding,overdue},counts:{drafts,validated,customers,products},overdue_invoices,period}`. Facturation et règlements filtrés par date ; encours et retards toutes dates confondues. Lecture authentifiée, calculs cohérents sous verrou de société.
- GET `export/?resource=customers|products|invoices|payments` → CSV UTF-8 avec BOM et séparateur `;`. Recherche `search`, dates `start/end` pour factures/règlements, `archived=true|false` pour clients/articles, `status=draft|validated` pour factures. Au plus 5 000 lignes ; erreur 400 `export_limit` au-delà. Les règlements sont réservés aux rôles admin/comptable. Les erreurs restent des réponses JSON, même avec `Accept: text/csv`. Les noms clients validés proviennent du snapshot ; la devise effective des brouillons est celle de la société. Cellules de texte pouvant déclencher une formule de tableur neutralisées.

Rôles `admin`, `accountant`, `sales`, `viewer`. Langues `fr`, `en`, `ar`, `de`, `tr`.

- GET `auth/csrf/` → `{csrfToken}` ; POST `auth/login/` `{username,password}` → user ; POST `auth/logout/` ; GET/PATCH `auth/me/` → `{id,username,role,language,company}` (PATCH language uniquement).
- GET/PATCH `company/` → `{id,name,address,email,currency,precision,document_language,locale}`. PATCH admin.
- GET/POST `customers/`, GET/PATCH `customers/:id/` → `{id,name,email,address,tax_id,archived}`. Filtre archived=true/false. Pas de DELETE.
- GET/POST `products/`, GET/PATCH `products/:id/` → `{id,reference,name,unit_price,purchase_price,tax_rate,archived,category,category_name,unit,unit_name,warehouses,specifications,image_url}`. Aucun stock. `purchase_price` est une chaîne décimale positive ou nulle, ou `null` si inconnu ; `unit_price` reste le prix de vente. `category` et `unit` sont des IDs facultatifs (`null`), leurs noms sont en lecture seule, `warehouses` est une liste d’IDs. Caractéristiques : texte de 4 000 caractères maximum. Photo : URL HTTPS de 1 000 caractères maximum, sans identifiants, ou chaîne vide ; aucun téléchargement serveur.
- Filtres `products/` : `product`, `category`, `warehouse`, `unit` (ID appartenant à la société, sinon 404), `archived=true|false`, `specifications` (sous-chaîne, 128 caractères maximum). `search` porte sur le nom, le code, les caractéristiques et la classe. Tris autorisés : `id`, `name`, `reference`, `unit_price`, `purchase_price`, `archived`, préfixe `-` pour décroissant ; ID ajouté pour stabiliser la pagination.
- GET/POST `product-categories/`, `warehouses/`, `units/` et GET/PATCH `:id/` → `{id,code,name,archived}`. Code unique par société (40 caractères maximum), nom (150 maximum), recherche sur code/nom, filtre archived et tri name/code/id/archived. Aucune suppression. Lecture authentifiée, écriture admin/comptable/commercial ; audit et mutation atomiques. Les références archivées déjà affectées restent conservables, mais une nouvelle affectation est refusée.
- GET/POST `invoices/`, GET/PATCH `invoices/:id/` → `{id,customer,customer_name,issue_date,due_date,document_language,status,number,lines,net,tax,total,paid,balance,snapshot,payments}`. `status=draft|validated`. POST/PATCH `{customer,issue_date,due_date,document_language,lines:[{product:null|id,description,quantity,unit_price,tax_rate}]}`. Lignes de sortie ajoutent `{id,net,tax,total}`. Listes peuvent omettre lines/snapshot/payments. Filtre status et customer. Calcul brouillon par POST/PATCH.
- POST `invoices/:id/validate/` `{}` + header `Idempotency-Key` → facture complète.
- POST `invoices/:id/payments/` `{amount,date,reference}` + header `Idempotency-Key` → facture complète. Règlements `{id,amount,date,reference}`.
- Impression HTML via route frontend `/invoices/:id/print` et données GET sécurisées, snapshot validé figé. Navigateur imprime.
- GET `accounts/` → liste `{id,code,name,kind}` ; GET `journals/` → liste `{id,code,name}`.
- GET/POST `periods/`, PATCH `periods/:id/` → `{id,name,start,end,closed}` ; admin seul écrit.
- GET `entries/` et `entries/:id/` → `{id,date,reference,journal,journal_code,invoice,lines:[{account,account_code,debit,credit}],total_debit,total_credit}` ; filtre `period`, `journal`, ordering date/id.
- GET `trial-balance/?period=:id` → `{accounts:[{code,name,debit,credit,balance}],total_debit,total_credit}`.
- GET `audit/` → liste `{id,created_at,actor_name,action,object_type,object_id,metadata}` ; admin/comptable.
- GET/POST `users/`, PATCH `users/:id/` → `{id,username,role,language,is_active}` ; admin, POST ajoute `password`.

Codes attendus : `invalid_input`, `invalid_credentials`, `rate_limited`, `permission_denied`, `not_authenticated`, `not_found`, `csrf_failed`, `immutable`, `period_closed`, `period_missing`, `invalid_amount`, `overpayment`, `idempotency_required`, `idempotency_conflict`, `already_validated`, `archived_reference`, `configuration_locked`, `network_error`, `server_error`. UI ajoute secours générique traduit.

Modèles convenus : Company, User (AbstractUser : company FK, role, language), Customer, Product, ProductCategory, Warehouse, Unit, Invoice, InvoiceLine, Payment, Account, Journal, Period, Entry, EntryLine, AuditEvent, IdempotencyRecord, NumberSequence, LoginAttempt. Services `save_draft(company, actor, data, invoice_id=None)`, `validate_invoice(company, actor, invoice_id, key, payload=None)`, `record_payment(company, actor, invoice_id, key, data)`, `configure_company(company, actor, data)`, `set_period(company, actor, data, period_id=None)`, `bootstrap_company(company)` ; erreurs métier `DomainError(code)`.

## Abonnement d’accès à Azula

`auth/me/` et la réponse de connexion ajoutent `billing: {enabled,has_access,exempt,status}`. Lorsque le contrôle est activé, les accès métier sans abonnement ou exemption reçoivent HTTP **402**, `{code:"subscription_required",detail:"subscription_required"}`. Le profil et les routes de facturation de l’abonnement restent disponibles, indépendamment de l’accès métier. Les API externes et l’administration vérifient aussi cette condition.

- GET `billing/` : `{enabled,configured,can_manage,exempt,has_access,status,subscription,plans,checkout_pending}`. Les montants des offres sont des chaînes décimales, avec devise, précision, intervalle `month|year` et essai applicable à cette société. Aucun identifiant ni secret Stripe n’est exposé.
- POST `billing/checkout/` : administrateur, session et CSRF, `{plan_code}` et `Idempotency-Key`. Réponse `{url}` vers Stripe Checkout. Prix, quantité, client Stripe et URL de retour sont déterminés au serveur ; les champs supplémentaires sont refusés. Le retour du navigateur n’accorde pas l’accès.
- POST `billing/portal/` : administrateur, session et CSRF, corps `{}` ; retourne `{url}` vers le portail du client Stripe de la société connectée.
- POST `billing/webhook/` : exception aux sessions/CSRF, exclusivement authentifiée par `Stripe-Signature` sur les octets bruts. Version et mode contrôlés, corps limité à 1 Mio. Les événements sont dédupliqués ; le serveur relit l’abonnement canonique sous verrou avant d’actualiser l’accès. Réponse `{received:true}` sans données privées.

Codes supplémentaires : `billing_unavailable` (503), `billing_invalid_event`, `billing_invalid_plan`, `billing_idempotency_required`, `billing_use_portal`, `billing_checkout_pending`, `billing_checkout_finished`, `billing_subscription_conflict`, `billing_mode_conflict`, `billing_no_subscription`. Les instructions et limites sont dans [abonnements.md](abonnements.md).

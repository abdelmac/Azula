# Contrat de travail API v1

Toutes les routes sous `/api/`, slash final. Sessions Django + CSRF. Listes `{count,next,previous,results}` ; pagination `page`, `page_size` (50, max 100), `search`, `ordering`. Dates ISO. Montants chaînes décimales. Erreurs `{code, detail}` ; UI traduit `code`, ne montre jamais de message anglais interne.

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

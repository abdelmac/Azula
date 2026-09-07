from django.db import migrations


SQL = r"""
CREATE FUNCTION azula_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'immutable' USING ERRCODE = '23514';
END $$;

CREATE TRIGGER entry_immutable BEFORE UPDATE OR DELETE ON erp_entry
FOR EACH ROW EXECUTE FUNCTION azula_immutable();
CREATE TRIGGER entryline_immutable BEFORE UPDATE OR DELETE ON erp_entryline
FOR EACH ROW EXECUTE FUNCTION azula_immutable();
CREATE TRIGGER payment_immutable BEFORE UPDATE OR DELETE ON erp_payment
FOR EACH ROW EXECUTE FUNCTION azula_immutable();
CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE ON erp_auditevent
FOR EACH ROW EXECUTE FUNCTION azula_immutable();
CREATE TRIGGER idempotency_immutable BEFORE UPDATE OR DELETE ON erp_idempotencyrecord
FOR EACH ROW EXECUTE FUNCTION azula_immutable();

CREATE FUNCTION azula_invoice_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' AND OLD.status = 'validated' THEN
        RAISE EXCEPTION 'immutable' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    PERFORM 1 FROM erp_company WHERE id = NEW.company_id FOR UPDATE;
    IF NOT EXISTS (SELECT 1 FROM erp_customer WHERE id = NEW.customer_id AND company_id = NEW.company_id) THEN
        RAISE EXCEPTION 'company_mismatch' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER invoice_guard BEFORE INSERT OR UPDATE OR DELETE ON erp_invoice
FOR EACH ROW EXECUTE FUNCTION azula_invoice_guard();

CREATE FUNCTION azula_invoiceline_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner bigint;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        PERFORM 1 FROM erp_company WHERE id = OLD.company_id FOR UPDATE;
        IF EXISTS (SELECT 1 FROM erp_invoice WHERE id = OLD.invoice_id AND status = 'validated') THEN
            RAISE EXCEPTION 'immutable' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    PERFORM 1 FROM erp_company WHERE id = NEW.company_id FOR UPDATE;
    SELECT company_id INTO owner FROM erp_invoice WHERE id = NEW.invoice_id AND status = 'draft';
    IF owner IS NULL OR owner <> NEW.company_id THEN
        RAISE EXCEPTION 'immutable_or_company_mismatch' USING ERRCODE = '23514';
    END IF;
    IF NEW.product_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM erp_product WHERE id = NEW.product_id AND company_id = NEW.company_id) THEN
        RAISE EXCEPTION 'company_mismatch' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER invoiceline_guard BEFORE INSERT OR UPDATE OR DELETE ON erp_invoiceline
FOR EACH ROW EXECUTE FUNCTION azula_invoiceline_guard();

CREATE FUNCTION azula_period_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM erp_company WHERE id = NEW.company_id FOR UPDATE;
    IF TG_OP = 'UPDATE' AND (OLD.company_id <> NEW.company_id OR OLD.start <> NEW.start OR OLD."end" <> NEW."end")
       AND EXISTS (SELECT 1 FROM erp_entry WHERE period_id = OLD.id) THEN
        RAISE EXCEPTION 'immutable' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (SELECT 1 FROM erp_period WHERE company_id = NEW.company_id AND id <> NEW.id AND start <= NEW."end" AND "end" >= NEW.start) THEN
        RAISE EXCEPTION 'overlapping_periods' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER period_guard BEFORE INSERT OR UPDATE ON erp_period
FOR EACH ROW EXECUTE FUNCTION azula_period_guard();

CREATE FUNCTION azula_company_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (OLD.currency <> NEW.currency OR OLD.precision <> NEW.precision)
       AND EXISTS (SELECT 1 FROM erp_invoice WHERE company_id = OLD.id AND status = 'validated') THEN
        RAISE EXCEPTION 'configuration_locked' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER company_guard BEFORE UPDATE ON erp_company
FOR EACH ROW EXECUTE FUNCTION azula_company_guard();

CREATE FUNCTION azula_payment_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE document erp_invoice%ROWTYPE;
DECLARE already_paid numeric;
BEGIN
    PERFORM 1 FROM erp_company WHERE id = NEW.company_id FOR UPDATE;
    SELECT * INTO document FROM erp_invoice WHERE id = NEW.invoice_id FOR UPDATE;
    IF document.id IS NULL OR document.company_id <> NEW.company_id OR document.status <> 'validated' THEN
        RAISE EXCEPTION 'invalid_payment_invoice' USING ERRCODE = '23514';
    END IF;
    IF NEW.amount <> round(NEW.amount, document.precision) OR NEW.date < document.issue_date THEN
        RAISE EXCEPTION 'invalid_amount_or_date' USING ERRCODE = '23514';
    END IF;
    SELECT coalesce(sum(amount), 0) INTO already_paid FROM erp_payment WHERE invoice_id = NEW.invoice_id;
    IF NEW.amount + already_paid > document.total THEN
        RAISE EXCEPTION 'overpayment' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER payment_guard BEFORE INSERT ON erp_payment
FOR EACH ROW EXECUTE FUNCTION azula_payment_guard();

CREATE FUNCTION azula_entry_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE accounting_period erp_period%ROWTYPE;
BEGIN
    PERFORM 1 FROM erp_company WHERE id = NEW.company_id FOR UPDATE;
    NEW.transaction_id := pg_current_xact_id()::text::bigint;
    SELECT * INTO accounting_period FROM erp_period WHERE id = NEW.period_id FOR UPDATE;
    IF accounting_period.id IS NULL OR accounting_period.company_id <> NEW.company_id OR accounting_period.closed
       OR NEW.date < accounting_period.start OR NEW.date > accounting_period."end" THEN
        RAISE EXCEPTION 'period_closed_or_invalid' USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM erp_invoice WHERE id = NEW.invoice_id AND company_id = NEW.company_id AND status = 'validated')
       OR NOT EXISTS (SELECT 1 FROM erp_journal WHERE id = NEW.journal_id AND company_id = NEW.company_id) THEN
        RAISE EXCEPTION 'company_mismatch' USING ERRCODE = '23514';
    END IF;
    IF (NEW.kind = 'invoice' AND NEW.payment_id IS NOT NULL)
       OR (NEW.kind = 'payment' AND (NEW.payment_id IS NULL OR NOT EXISTS (
           SELECT 1 FROM erp_payment WHERE id = NEW.payment_id AND invoice_id = NEW.invoice_id AND company_id = NEW.company_id AND date = NEW.date)))
       OR NEW.kind NOT IN ('invoice', 'payment') THEN
        RAISE EXCEPTION 'invalid_entry_kind' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER entry_guard BEFORE INSERT ON erp_entry
FOR EACH ROW EXECUTE FUNCTION azula_entry_guard();

CREATE FUNCTION azula_entryline_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner bigint;
DECLARE created_transaction bigint;
BEGIN
    SELECT company_id, transaction_id INTO owner, created_transaction FROM erp_entry WHERE id = NEW.entry_id;
    IF owner IS NULL OR owner <> NEW.company_id OR NOT EXISTS (SELECT 1 FROM erp_account WHERE id = NEW.account_id AND company_id = NEW.company_id) THEN
        RAISE EXCEPTION 'company_mismatch' USING ERRCODE = '23514';
    END IF;
    -- Une ligne ne peut être ajoutée qu'à une écriture créée dans la même
    -- transaction. Les écritures commises restent définitivement fermées.
    IF created_transaction <> pg_current_xact_id()::text::bigint THEN
        RAISE EXCEPTION 'immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER entryline_guard BEFORE INSERT ON erp_entryline
FOR EACH ROW EXECUTE FUNCTION azula_entryline_guard();

CREATE FUNCTION azula_check_entry() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_id bigint;
DECLARE debit_sum numeric;
DECLARE credit_sum numeric;
DECLARE line_count bigint;
DECLARE expected numeric;
BEGIN
    IF TG_TABLE_NAME = 'erp_entry' THEN target_id := NEW.id; ELSE target_id := NEW.entry_id; END IF;
    SELECT coalesce(sum(debit), 0), coalesce(sum(credit), 0), count(*) INTO debit_sum, credit_sum, line_count
      FROM erp_entryline WHERE entry_id = target_id;
    SELECT CASE WHEN e.kind = 'invoice' THEN i.total ELSE p.amount END INTO expected
      FROM erp_entry e JOIN erp_invoice i ON i.id = e.invoice_id LEFT JOIN erp_payment p ON p.id = e.payment_id WHERE e.id = target_id;
    IF line_count < 2 OR debit_sum <= 0 OR debit_sum <> credit_sum OR debit_sum <> expected THEN
        RAISE EXCEPTION 'unbalanced_entry' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER entry_balanced AFTER INSERT ON erp_entry
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION azula_check_entry();
CREATE CONSTRAINT TRIGGER entryline_balanced AFTER INSERT ON erp_entryline
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION azula_check_entry();

CREATE FUNCTION azula_check_document() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE document erp_invoice%ROWTYPE;
DECLARE net_sum numeric;
DECLARE tax_sum numeric;
DECLARE line_count bigint;
BEGIN
    SELECT * INTO document FROM erp_invoice WHERE id = NEW.id;
    IF document.id IS NULL OR document.status <> 'validated' THEN RETURN NULL; END IF;
    SELECT coalesce(sum(net), 0), coalesce(sum(tax), 0), count(*) INTO net_sum, tax_sum, line_count FROM erp_invoiceline WHERE invoice_id = document.id;
    IF line_count = 0 OR net_sum <> document.net OR tax_sum <> document.tax OR document.snapshot = '{}'::jsonb
       OR NOT EXISTS (SELECT 1 FROM erp_entry WHERE invoice_id = document.id AND kind = 'invoice') THEN
        RAISE EXCEPTION 'invalid_validated_invoice' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER invoice_complete AFTER INSERT OR UPDATE ON erp_invoice
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION azula_check_document();

CREATE FUNCTION azula_check_payment() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM erp_entry WHERE payment_id = NEW.id AND kind = 'payment') THEN
        RAISE EXCEPTION 'payment_entry_missing' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER payment_complete AFTER INSERT ON erp_payment
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION azula_check_payment();
"""

REVERSE = """
DROP FUNCTION azula_immutable() CASCADE;
DROP FUNCTION azula_invoice_guard() CASCADE;
DROP FUNCTION azula_invoiceline_guard() CASCADE;
DROP FUNCTION azula_period_guard() CASCADE;
DROP FUNCTION azula_company_guard() CASCADE;
DROP FUNCTION azula_payment_guard() CASCADE;
DROP FUNCTION azula_entry_guard() CASCADE;
DROP FUNCTION azula_entryline_guard() CASCADE;
DROP FUNCTION azula_check_entry() CASCADE;
DROP FUNCTION azula_check_document() CASCADE;
DROP FUNCTION azula_check_payment() CASCADE;
"""


class Migration(migrations.Migration):
    dependencies = [("erp", "0001_initial")]
    operations = [migrations.RunSQL(SQL, reverse_sql=REVERSE)]

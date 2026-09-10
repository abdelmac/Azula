from django.db import migrations

FORWARD = r"""
CREATE FUNCTION azula_connection_company_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.company_id <> NEW.company_id THEN
        RAISE EXCEPTION 'company_mismatch' USING ERRCODE = '23514';
    END IF;
    PERFORM 1 FROM erp_company WHERE id = NEW.company_id FOR UPDATE;
    IF TG_TABLE_NAME = 'connections_integrationkey' THEN
        IF NOT EXISTS (SELECT 1 FROM erp_user WHERE id=NEW.creator_id AND company_id=NEW.company_id)
           OR NOT EXISTS (SELECT 1 FROM connections_integration WHERE id=NEW.integration_id AND company_id=NEW.company_id) THEN
            RAISE EXCEPTION 'company_mismatch' USING ERRCODE = '23514';
        END IF;
        IF TG_OP = 'UPDATE' AND (OLD.revoked_at IS NOT NULL OR
            (to_jsonb(NEW) - 'revoked_at') IS DISTINCT FROM (to_jsonb(OLD) - 'revoked_at') OR NEW.revoked_at IS NULL) THEN
            RAISE EXCEPTION 'immutable' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_TABLE_NAME IN ('connections_externalrequest', 'connections_externaltransaction') THEN
        IF NOT EXISTS (SELECT 1 FROM connections_integration WHERE id=NEW.integration_id AND company_id=NEW.company_id) THEN
            RAISE EXCEPTION 'company_mismatch' USING ERRCODE = '23514';
        END IF;
        IF TG_TABLE_NAME = 'connections_externaltransaction' THEN
            IF NOT EXISTS (SELECT 1 FROM erp_company WHERE id=NEW.company_id AND currency=NEW.currency) THEN
                RAISE EXCEPTION 'currency_mismatch' USING ERRCODE = '23514';
            END IF;
        END IF;
    ELSIF TG_TABLE_NAME = 'connections_bankaccount' THEN
        IF NOT EXISTS (SELECT 1 FROM erp_company WHERE id=NEW.company_id AND currency=NEW.currency) THEN
            RAISE EXCEPTION 'currency_mismatch' USING ERRCODE = '23514';
        END IF;
        IF TG_OP = 'UPDATE' AND (OLD.currency <> NEW.currency OR OLD.iban <> NEW.iban)
           AND EXISTS (SELECT 1 FROM connections_banktransaction WHERE account_id=OLD.id) THEN
            RAISE EXCEPTION 'immutable' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END; $$;
CREATE TRIGGER connection_integration_owner BEFORE INSERT OR UPDATE ON connections_integration FOR EACH ROW EXECUTE FUNCTION azula_connection_company_guard();
CREATE TRIGGER connection_key_owner BEFORE INSERT OR UPDATE ON connections_integrationkey FOR EACH ROW EXECUTE FUNCTION azula_connection_company_guard();
CREATE TRIGGER connection_bankaccount_owner BEFORE INSERT OR UPDATE ON connections_bankaccount FOR EACH ROW EXECUTE FUNCTION azula_connection_company_guard();
CREATE TRIGGER connection_externalrequest_owner BEFORE INSERT ON connections_externalrequest FOR EACH ROW EXECUTE FUNCTION azula_connection_company_guard();
CREATE TRIGGER connection_externaltransaction_owner BEFORE INSERT ON connections_externaltransaction FOR EACH ROW EXECUTE FUNCTION azula_connection_company_guard();
CREATE TRIGGER connection_externalrequest_immutable BEFORE UPDATE OR DELETE ON connections_externalrequest FOR EACH ROW EXECUTE FUNCTION azula_immutable();
CREATE TRIGGER connection_externaltransaction_immutable BEFORE UPDATE OR DELETE ON connections_externaltransaction FOR EACH ROW EXECUTE FUNCTION azula_immutable();
CREATE TRIGGER connection_key_no_delete BEFORE DELETE ON connections_integrationkey FOR EACH ROW EXECUTE FUNCTION azula_immutable();

CREATE FUNCTION azula_banktransaction_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'immutable' USING ERRCODE = '23514';
    END IF;
    PERFORM 1 FROM erp_company WHERE id=NEW.company_id FOR UPDATE;
    IF NOT EXISTS (SELECT 1 FROM connections_bankaccount WHERE id=NEW.account_id AND company_id=NEW.company_id) THEN
        RAISE EXCEPTION 'company_mismatch' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'INSERT' AND (NEW.invoice_id IS NOT NULL OR NEW.payment_id IS NOT NULL OR NEW.reconciled_at IS NOT NULL) THEN
        RAISE EXCEPTION 'reconciliation_required' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF OLD.reconciled_at IS NOT NULL OR NEW.reconciled_at IS NULL OR NEW.invoice_id IS NULL OR NEW.payment_id IS NULL
           OR (to_jsonb(NEW) - ARRAY['invoice_id','payment_id','reconciled_at']) IS DISTINCT FROM
              (to_jsonb(OLD) - ARRAY['invoice_id','payment_id','reconciled_at']) THEN
            RAISE EXCEPTION 'immutable' USING ERRCODE = '23514';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM erp_payment p JOIN erp_invoice i ON i.id=p.invoice_id
                       JOIN connections_bankaccount a ON a.id=NEW.account_id
                       WHERE p.id=NEW.payment_id AND p.invoice_id=NEW.invoice_id AND p.company_id=NEW.company_id
                         AND p.amount=NEW.amount AND p.date=NEW.date AND i.company_id=NEW.company_id
                         AND i.status='validated' AND i.currency=a.currency AND NOT a.archived) THEN
            RAISE EXCEPTION 'payment_mismatch' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END; $$;
CREATE TRIGGER banktransaction_guard BEFORE INSERT OR UPDATE OR DELETE ON connections_banktransaction FOR EACH ROW EXECUTE FUNCTION azula_banktransaction_guard();

CREATE FUNCTION azula_bank_company_configuration_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (OLD.currency <> NEW.currency OR OLD.precision <> NEW.precision) AND
       (EXISTS (SELECT 1 FROM connections_bankaccount WHERE company_id=OLD.id)
        OR EXISTS (SELECT 1 FROM connections_externaltransaction WHERE company_id=OLD.id)) THEN
        RAISE EXCEPTION 'configuration_locked' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END; $$;
CREATE TRIGGER bank_company_configuration_guard BEFORE UPDATE ON erp_company FOR EACH ROW EXECUTE FUNCTION azula_bank_company_configuration_guard();
"""

REVERSE = """
DROP TRIGGER bank_company_configuration_guard ON erp_company;
DROP FUNCTION azula_bank_company_configuration_guard();
DROP TRIGGER banktransaction_guard ON connections_banktransaction;
DROP FUNCTION azula_banktransaction_guard();
DROP TRIGGER connection_integration_owner ON connections_integration;
DROP TRIGGER connection_key_owner ON connections_integrationkey;
DROP TRIGGER connection_bankaccount_owner ON connections_bankaccount;
DROP TRIGGER connection_externalrequest_owner ON connections_externalrequest;
DROP TRIGGER connection_externaltransaction_owner ON connections_externaltransaction;
DROP TRIGGER connection_externalrequest_immutable ON connections_externalrequest;
DROP TRIGGER connection_externaltransaction_immutable ON connections_externaltransaction;
DROP TRIGGER connection_key_no_delete ON connections_integrationkey;
DROP FUNCTION azula_connection_company_guard();
"""


class Migration(migrations.Migration):
    dependencies = [("connections", "0001_initial")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]

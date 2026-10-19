-- Voir les transferts de lot en attente de validation
SELECT * FROM lots WHERE status = 'in_transfer';
#!/bin/bash
# ============================================
# Script de migration vers multi-tenant
# ============================================

set -e

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Migration BrainNotFound vers Multi-Tenant ===${NC}"
echo ""

# Charger les variables d'environnement (seulement celles nécessaires)
if [ -f .env ]; then
    export MYSQL_USER=$(grep '^MYSQL_USER=' .env | cut -d'=' -f2)
    export MYSQL_PASSWORD=$(grep '^MYSQL_PASSWORD=' .env | cut -d'=' -f2)
    export MYSQL_DATABASE=$(grep '^MYSQL_DATABASE=' .env | cut -d'=' -f2)
else
    echo -e "${RED}Erreur: fichier .env non trouvé${NC}"
    exit 1
fi

# Vérifier que les containers tournent
if ! docker compose ps | grep -q "quiz_db.*Up"; then
    echo -e "${RED}Erreur: Le container de base de données n'est pas démarré${NC}"
    echo "Lancez d'abord: docker compose up -d"
    exit 1
fi

echo -e "${GREEN}✓${NC} Variables .env chargées"
echo -e "${GREEN}✓${NC} Container DB actif"
echo ""

# 1. Backup
echo -e "${YELLOW}[1/4] Création du backup...${NC}"
BACKUP_FILE="backup_avant_migration_$(date +%Y%m%d_%H%M%S).sql"
docker compose exec -T db mysqldump -u${MYSQL_USER} -p${MYSQL_PASSWORD} ${MYSQL_DATABASE} > ${BACKUP_FILE}
echo -e "${GREEN}✓${NC} Backup créé: ${BACKUP_FILE}"
echo ""

# 2. Exécuter la migration
echo -e "${YELLOW}[2/4] Exécution de la migration...${NC}"

docker compose exec -T db mysql -u${MYSQL_USER} -p${MYSQL_PASSWORD} ${MYSQL_DATABASE} << 'EOSQL'

-- Désactiver les checks FK temporairement
SET FOREIGN_KEY_CHECKS = 0;

-- 1. Créer la table tenants
CREATE TABLE IF NOT EXISTS `tenants` (
  `id` int NOT NULL AUTO_INCREMENT,
  `slug` varchar(50) NOT NULL,
  `name` varchar(200) NOT NULL,
  `description` text,
  `is_active` tinyint(1) DEFAULT '1',
  `max_users` int DEFAULT '0',
  `max_quizzes` int DEFAULT '0',
  `max_groups` int DEFAULT '0',
  `max_storage_mb` int DEFAULT '0',
  `contact_email` varchar(200) DEFAULT NULL,
  `contact_name` varchar(200) DEFAULT NULL,
  `internal_notes` text,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `monthly_ai_corrections` int DEFAULT '0',
  `monthly_quiz_generations` int DEFAULT '0',
  `monthly_class_analyses` int DEFAULT '0',
  `used_ai_corrections` int DEFAULT '0',
  `used_quiz_generations` int DEFAULT '0',
  `used_class_analyses` int DEFAULT '0',
  `usage_reset_date` date DEFAULT NULL,
  `subscription_expires_at` date DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_tenants_slug` (`slug`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 2. Créer la table tenant_admins
CREATE TABLE IF NOT EXISTS `tenant_admins` (
  `tenant_id` int NOT NULL,
  `user_id` int NOT NULL,
  `created_at` datetime DEFAULT NULL,
  PRIMARY KEY (`tenant_id`, `user_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `tenant_admins_ibfk_1` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`),
  CONSTRAINT `tenant_admins_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 3. Ajouter tenant_id à groups si pas déjà présent
SET @col_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'groups' AND COLUMN_NAME = 'tenant_id');
SET @sql = IF(@col_exists = 0, 'ALTER TABLE `groups` ADD COLUMN `tenant_id` int DEFAULT NULL', 'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Ajouter l'index et FK si pas déjà présent
SET @idx_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'groups' AND INDEX_NAME = 'ix_groups_tenant_id');
SET @sql = IF(@idx_exists = 0, 'ALTER TABLE `groups` ADD INDEX `ix_groups_tenant_id` (`tenant_id`)', 'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @fk_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'groups' AND CONSTRAINT_NAME = 'fk_groups_tenant_id');
SET @sql = IF(@fk_exists = 0, 'ALTER TABLE `groups` ADD CONSTRAINT `fk_groups_tenant_id` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`)', 'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 4. Ajouter tenant_id à quizzes si pas déjà présent
SET @col_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'quizzes' AND COLUMN_NAME = 'tenant_id');
SET @sql = IF(@col_exists = 0, 'ALTER TABLE `quizzes` ADD COLUMN `tenant_id` int DEFAULT NULL', 'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @idx_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'quizzes' AND INDEX_NAME = 'ix_quizzes_tenant_id');
SET @sql = IF(@idx_exists = 0, 'ALTER TABLE `quizzes` ADD INDEX `ix_quizzes_tenant_id` (`tenant_id`)', 'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @fk_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'quizzes' AND CONSTRAINT_NAME = 'fk_quizzes_tenant_id');
SET @sql = IF(@fk_exists = 0, 'ALTER TABLE `quizzes` ADD CONSTRAINT `fk_quizzes_tenant_id` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`)', 'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 5. Créer le tenant par défaut
INSERT INTO `tenants` (`slug`, `name`, `description`, `is_active`, `created_at`, `updated_at`)
SELECT 'default', 'UTT', 'Organisation créée lors de la migration', 1, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM `tenants` WHERE `slug` = 'default');

-- 6. Migrer les données existantes
SET @tenant_id = (SELECT `id` FROM `tenants` WHERE `slug` = 'default');
UPDATE `groups` SET `tenant_id` = @tenant_id WHERE `tenant_id` IS NULL;
UPDATE `quizzes` SET `tenant_id` = @tenant_id WHERE `tenant_id` IS NULL;

-- 7. Ajouter l'admin comme admin du tenant
INSERT IGNORE INTO `tenant_admins` (`tenant_id`, `user_id`, `created_at`)
SELECT @tenant_id, `id`, NOW() FROM `users` WHERE `is_admin` = 1 LIMIT 1;

-- 8. Ajouter la colonne is_superadmin si elle n'existe pas
SET @col_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'is_superadmin');
SET @sql = IF(@col_exists = 0, 'ALTER TABLE `users` ADD COLUMN `is_superadmin` tinyint(1) DEFAULT 0', 'SELECT 1');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 9. Promouvoir le premier admin en superadmin
UPDATE `users` SET `is_superadmin` = 1 WHERE `is_admin` = 1 LIMIT 1;

-- 8. Mettre à jour alembic_version
DELETE FROM `alembic_version`;
INSERT INTO `alembic_version` (`version_num`) VALUES ('008_tenant_limits');

SET FOREIGN_KEY_CHECKS = 1;

EOSQL

echo -e "${GREEN}✓${NC} Migration SQL exécutée"
echo ""

# 3. Vérification
echo -e "${YELLOW}[3/4] Vérification...${NC}"

docker compose exec -T db mysql -u${MYSQL_USER} -p${MYSQL_PASSWORD} ${MYSQL_DATABASE} -e "
SELECT 'Tables créées:' AS info;
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN ('tenants', 'tenant_admins');

SELECT '' AS '';
SELECT 'Tenant par défaut:' AS info;
SELECT id, slug, name FROM tenants WHERE slug = 'default';

SELECT '' AS '';
SELECT 'Données migrées:' AS info;
SELECT
  (SELECT COUNT(*) FROM \`groups\` WHERE tenant_id IS NOT NULL) AS groups_migres,
  (SELECT COUNT(*) FROM quizzes WHERE tenant_id IS NOT NULL) AS quizzes_migres;

SELECT '' AS '';
SELECT 'Version Alembic:' AS info;
SELECT version_num FROM alembic_version;
"

echo ""
echo -e "${GREEN}✓${NC} Vérification terminée"
echo ""

# 4. Rebuild de l'app
echo -e "${YELLOW}[4/4] Rebuild et redémarrage de l'application...${NC}"
docker compose build web
docker compose up -d web
echo -e "${GREEN}✓${NC} Application redémarrée"
echo ""

echo -e "${GREEN}=== Migration terminée avec succès ! ===${NC}"
echo ""
echo "Backup sauvegardé dans: ${BACKUP_FILE}"
echo "En cas de problème, restaurez avec:"
echo "  docker compose exec -T db mysql -u${MYSQL_USER} -p${MYSQL_PASSWORD} ${MYSQL_DATABASE} < ${BACKUP_FILE}"
